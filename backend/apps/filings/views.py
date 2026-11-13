"""Radicaciones y respuestas del banco (API §20). Las reglas viven en
``apps.filings.services``, ``responses`` y ``evidence``."""

from typing import Any, BinaryIO, cast

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.concurrency import with_etag
from apps.applications.models import CreditApplication
from apps.applications.services import applications_visible_to
from apps.documents.dossier_serializers import DocumentDownloadSerializer
from apps.documents.dossier_views import no_store
from apps.documents.exceptions import PayloadTooLarge
from apps.filings import evidence, responses, services
from apps.filings.models import Filing, FilingResponse
from apps.filings.serializers import (
    EvidenceUploadSerializer,
    FilingCreateSerializer,
    FilingDocumentSnapshotSerializer,
    FilingResponseCreateSerializer,
    FilingResponseSerializer,
    FilingSerializer,
    FilingUpdateSerializer,
)
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from apps.identity.throttling import DocumentDownloadRateThrottle
from config.serializers import ErrorSerializer

FILINGS_TAG = "Filings"
RESPONSES_TAG = "Filing responses"

READ = "filings.read"
CREATE = "filings.create"
UPDATE = "filings.update"
RECORD_RESPONSE = "filings.record_response"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND (inexistente o fuera del alcance)")}
MANAGE_NOTE = "Solo el administrador o el asesor asignado a la solicitud (`403`)."


class FilingView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {}

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)

    def get_application(self, application_id: Any) -> CreditApplication:
        return get_object_or_404(applications_visible_to(self.actor), pk=application_id)

    def get_filing(self, filing_id: Any) -> Filing:
        return get_object_or_404(services.filings_visible_to(self.actor), pk=filing_id)

    def filing_data(self, filing: Filing) -> dict[str, Any]:
        restricted = services.is_restricted(self.actor)
        return cast(
            dict[str, Any], FilingSerializer(filing, context={"restricted": restricted}).data
        )


class ApplicationFilingListView(FilingView):
    required_permissions = {"GET": READ, "POST": CREATE}

    @extend_schema(
        tags=[FILINGS_TAG],
        operation_id="applications_filings_list",
        summary="Radicaciones de la solicitud",
        description=(
            "Historial de radicaciones y re-radicaciones, la más reciente primero. El broker "
            "ve las de las solicitudes que originó, sin `comment`."
        ),
        responses={200: FilingSerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        filings = services.filings_queryset().filter(application=application)
        page = self.paginate_queryset(filings)
        restricted = services.is_restricted(self.actor)
        data = FilingSerializer(page, many=True, context={"restricted": restricted}).data
        return self.get_paginated_response(data)

    @extend_schema(
        tags=[FILINGS_TAG],
        operation_id="applications_filings_create",
        summary="Registrar la radicación manual",
        description=(
            "Registra la entrega del paquete al banco; la API no se comunica con el banco. "
            "Exige la solicitud en `READY_TO_FILE`, el producto de la financiación, los "
            "documentos obligatorios aprobados o exonerados, las reglas del banco sin "
            "bloqueos y un paquete de la solicitud terminado, vigente, sin radicar y con la "
            "huella documental actual. `expected_version` va en el cuerpo (no `If-Match`).\n\n"
            "Crea la radicación con el consecutivo siguiente, guarda las versiones exactas "
            "del paquete (`/document-snapshots`), bloquea esos documentos y pasa la "
            "solicitud a `FILED`. `target_response_at` es `filed_at` más los días de "
            f"respuesta del banco, o nulo. Responde `ETag` con la versión de la solicitud. "
            f"{MANAGE_NOTE}"
        ),
        request=FilingCreateSerializer,
        responses={
            201: FilingSerializer,
            409: _error(
                "STALE_VERSION, APPLICATION_CLOSED, INVALID_STATE_TRANSITION (no está en "
                "READY_TO_FILE), PACKAGE_NOT_READY, PACKAGE_EXPIRED, PACKAGE_OUTDATED, "
                "PACKAGE_ALREADY_FILED o FILING_REFERENCE_EXISTS"
            ),
            422: _error(
                "BANK_PRODUCT_MISMATCH o APPLICATION_NOT_READY (documentos o reglas del "
                "banco, en `details`)"
            ),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        services.ensure_can_manage(self.actor, application)
        serializer = FilingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        filing = services.create_filing(
            self.actor,
            application,
            bank_product_id=data["bank_product_id"],
            package_job_id=data["package_job_id"],
            channel=data["channel_code"],
            filed_at=data["filed_at"],
            expected_version=data["expected_version"],
            external_reference=data["external_reference"],
            comment=data["comment"],
        )
        created = services.filings_queryset().get(pk=filing.pk)
        response = Response(self.filing_data(created), status=status.HTTP_201_CREATED)
        return with_etag(response, created.application.version)


class FilingDetailView(FilingView):
    required_permissions = {"GET": READ, "PATCH": UPDATE}

    @extend_schema(
        tags=[FILINGS_TAG],
        operation_id="filings_retrieve",
        summary="Detalle de una radicación",
        description="El broker no recibe `comment`.",
        responses={200: FilingSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, filing_id: Any) -> Response:
        return Response(self.filing_data(self.get_filing(filing_id)))

    @extend_schema(
        tags=[FILINGS_TAG],
        operation_id="filings_partial_update",
        summary="Corregir la referencia o el comentario",
        description=(
            "Solo `external_reference` y `comment`; `null` o vacío los borra. No cambia el "
            "estado, los snapshots ni las respuestas, ni la versión de la solicitud, así que "
            f"no exige `If-Match`. {MANAGE_NOTE}"
        ),
        request=FilingUpdateSerializer,
        responses={
            200: FilingSerializer,
            409: _error("FILING_REFERENCE_EXISTS"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, filing_id: Any) -> Response:
        filing = self.get_filing(filing_id)
        services.ensure_can_manage(self.actor, filing.application)
        serializer = FilingUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_filing(self.actor, filing, dict(serializer.validated_data))
        return Response(self.filing_data(self.get_filing(filing_id)))


class FilingDocumentSnapshotListView(FilingView):
    required_permissions = {"GET": READ}

    @extend_schema(
        tags=[FILINGS_TAG],
        operation_id="filings_document_snapshots_list",
        summary="Documentos que se entregaron en la radicación",
        description=(
            "Las versiones exactas del paquete radicado (los exonerados no tienen archivo). "
            f"{MANAGE_NOTE}"
        ),
        responses={
            200: FilingDocumentSnapshotSerializer(many=True),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def get(self, request: Request, filing_id: Any) -> Response:
        filing = self.get_filing(filing_id)
        services.ensure_can_manage(self.actor, filing.application)
        page = self.paginate_queryset(services.snapshots_queryset(filing))
        return self.get_paginated_response(FilingDocumentSnapshotSerializer(page, many=True).data)


# --------------------------------------------------------------------------------------
# Respuestas del banco (API §20.2)
# --------------------------------------------------------------------------------------

RESPONSE_RULES_DESCRIPTION = """
| `response_type` | Estados admitidos | Obligatorio | Efecto en la solicitud |
| --- | --- | --- | --- |
| `RECEIVED` | `FILED`, `FILING_VALIDATION` | — | → `FILING_VALIDATION` (si ya está, no cambia) |
| `IN_ANALYSIS` | `FILED`, `FILING_VALIDATION` | — | → `CREDIT_ANALYSIS` |
| `RETURNED` | `FILED`, `FILING_VALIDATION`, `CREDIT_ANALYSIS` | `reason_code`, \
`public_message`, `observations` | → `BANK_OBSERVATION` |
| `APPROVED` | `FILED`, `FILING_VALIDATION`, `CREDIT_ANALYSIS` | `approved_amount_cop`, \
`approved_term_months`, `public_message` | → `APPROVED` |
| `REJECTED` | `FILED`, `FILING_VALIDATION`, `CREDIT_ANALYSIS`, `BANK_OBSERVATION` | \
`reason_code`, `public_message` | → `REJECTED` |
| `DISBURSED` | `LEGALIZATION` | `disbursed_amount_cop` | → `DISBURSED` |
| `OTHER` | cualquiera no terminal | `internal_comment` | no cambia |

Los campos de un tipo (`reason_code`, `observations`, montos, plazo y vigencia) no se \
admiten en otro (`400`). Cada observación de un `RETURNED` rechaza la versión vigente \
del documento con su motivo y mensaje: el comprador la ve como "Corrígelo" y, después de \
radicar, solo reemplaza esos documentos. Aprobar la versión nueva resuelve la \
observación.
"""


def _response_errors(conflicts: str) -> dict[int, OpenApiResponse]:
    return {409: _error(conflicts), **NOT_FOUND, **COMMON_ERRORS}


class ResponseView(FilingView):
    def get_response(self, response_id: Any) -> FilingResponse:
        return get_object_or_404(responses.responses_visible_to(self.actor), pk=response_id)

    def response_data(self, response: FilingResponse) -> dict[str, Any]:
        restricted = services.is_restricted(self.actor)
        return cast(
            dict[str, Any],
            FilingResponseSerializer(response, context={"restricted": restricted}).data,
        )


class FilingResponseListView(ResponseView):
    required_permissions = {"GET": READ, "POST": RECORD_RESPONSE}

    @extend_schema(
        tags=[RESPONSES_TAG],
        operation_id="filings_responses_list",
        summary="Respuestas del banco a una radicación",
        description=(
            "Historial cronológico, incluidas las correcciones. El broker solo recibe "
            "`response_type`, su etiqueta, `received_at` y `public_message`: nunca "
            "`internal_comment`, evidencia ni montos."
        ),
        responses={200: FilingResponseSerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, filing_id: Any) -> Response:
        filing = self.get_filing(filing_id)
        page = self.paginate_queryset(responses.responses_queryset().filter(filing=filing))
        restricted = services.is_restricted(self.actor)
        data = FilingResponseSerializer(page, many=True, context={"restricted": restricted}).data
        return self.get_paginated_response(data)

    @extend_schema(
        tags=[RESPONSES_TAG],
        operation_id="filings_responses_create",
        summary="Registrar una respuesta del banco",
        description=(
            "Se registra a mano y solo contra la última radicación de la solicitud. Es "
            "inmutable: una corrección es otra respuesta con `corrects_response_id`. "
            "`expected_version` va en el cuerpo. Responde `ETag` con la versión de la "
            f"solicitud. {MANAGE_NOTE}\n" + RESPONSE_RULES_DESCRIPTION
        ),
        request=FilingResponseCreateSerializer,
        responses={
            201: FilingResponseSerializer,
            **_response_errors(
                "STALE_VERSION, APPLICATION_CLOSED, INVALID_STATE_TRANSITION (el tipo no se "
                "admite en el estado actual), FILING_NOT_LATEST o "
                "RESPONSE_CORRECTION_NOT_ALLOWED"
            ),
        },
    )
    def post(self, request: Request, filing_id: Any) -> Response:
        filing = self.get_filing(filing_id)
        services.ensure_can_manage(self.actor, filing.application)
        serializer = FilingResponseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recorded = responses.record_response(
            self.actor,
            filing,
            serializer.to_input(),
            expected_version=serializer.validated_data["expected_version"],
        )
        created = responses.responses_queryset().get(pk=recorded.pk)
        response = Response(self.response_data(created), status=status.HTTP_201_CREATED)
        return with_etag(response, created.filing.application.version)


class FilingResponseDetailView(ResponseView):
    required_permissions = {"GET": READ}

    @extend_schema(
        tags=[RESPONSES_TAG],
        operation_id="filing_responses_retrieve",
        summary="Detalle de una respuesta del banco",
        description="Con sus observaciones. El broker recibe solo los datos públicos.",
        responses={200: FilingResponseSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, response_id: Any) -> Response:
        return Response(self.response_data(self.get_response(response_id)))


def _ensure_request_size(request: Request) -> None:
    """Corta un cuerpo demasiado grande antes de leerlo (``413``)."""
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    limit = settings.DOCUMENT_UPLOAD_MAX_REQUEST_BYTES
    if length > limit:
        raise PayloadTooLarge(f"La carga supera el máximo de {limit} bytes.")


class FilingResponseEvidenceView(ResponseView):
    required_permissions = {"POST": RECORD_RESPONSE}
    parser_classes = [MultiPartParser]

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        _ensure_request_size(request)
        super().initial(request, *args, **kwargs)

    @extend_schema(
        tags=[RESPONSES_TAG],
        operation_id="filing_responses_evidence_create",
        summary="Adjuntar la evidencia de una respuesta",
        description=(
            "Un PDF, JPG o PNG de hasta 10 MB (tipo real por su contenido, extensión y "
            "tamaño, como los documentos), una sola vez por respuesta. Pasa por el mismo "
            "análisis antivirus que los documentos: queda `PENDING` hasta que termina. Solo "
            "quien registró la respuesta o un administrador (`403`)."
        ),
        request={"multipart/form-data": EvidenceUploadSerializer},
        responses={
            201: FilingResponseSerializer,
            400: _error("VALIDATION_ERROR (sin archivo o vacío)"),
            409: _error("EVIDENCE_ALREADY_ATTACHED"),
            413: _error("PAYLOAD_TOO_LARGE"),
            422: _error("UNSUPPORTED_FILE_TYPE o FILE_TOO_LARGE"),
            503: _error("SERVICE_UNAVAILABLE (almacenamiento no disponible)"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, response_id: Any) -> Response:
        response = self.get_response(response_id)
        serializer = EvidenceUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data["file"]
        evidence.attach_evidence(
            self.actor,
            response,
            stream=cast(BinaryIO, uploaded),
            filename=uploaded.name or "",
            declared_mime_type=uploaded.content_type,
        )
        updated = self.get_response(response_id)
        return Response(self.response_data(updated), status=status.HTTP_201_CREATED)


class FilingResponseEvidenceDownloadView(ResponseView):
    required_permissions = {"GET": READ}
    throttle_classes = [DocumentDownloadRateThrottle]

    @extend_schema(
        tags=[RESPONSES_TAG],
        operation_id="filing_responses_evidence_download",
        summary="Descargar la evidencia de una respuesta",
        description=(
            "URL prefirmada de corta duración, como las versiones de los documentos, solo "
            "si el análisis dejó el archivo limpio. `404` si la respuesta no tiene "
            f"evidencia. {MANAGE_NOTE}"
        ),
        responses={
            200: DocumentDownloadSerializer,
            409: _error("FILE_NOT_CLEAN"),
            429: _error("RATE_LIMITED"),
            503: _error("SERVICE_UNAVAILABLE (almacenamiento no disponible)"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def get(self, request: Request, response_id: Any) -> Response:
        response = self.get_response(response_id)
        services.ensure_can_manage(self.actor, response.filing.application)
        if response.evidence_file_object_id is None:
            raise Http404
        link = evidence.evidence_download(response, requested_by=f"user:{self.actor.pk}")
        return no_store(Response(DocumentDownloadSerializer(link).data))
