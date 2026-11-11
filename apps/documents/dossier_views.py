"""Endpoints internos del expediente documental (API §19): lista, detalle y versiones
de los slots, recálculo manual, revisión y metadatos, análisis y descarga de las
versiones. Las rutas del comprador van bajo ``/buyer/...``."""

from typing import Any, cast

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.models import CreditApplication
from apps.applications.services import applications_visible_to
from apps.documents import dossier, downloads, reviews
from apps.documents.dossier_serializers import (
    DocumentDownloadSerializer,
    DocumentFileScanStatusSerializer,
    DocumentFileSerializer,
    DocumentSlotDetailSerializer,
    DocumentSlotReviewResultSerializer,
    DocumentSlotReviewSerializer,
    DocumentSlotSerializer,
    SlotRefreshSerializer,
)
from apps.documents.models import ApplicationDocumentSlot, DocumentFile, SlotStatus
from apps.documents.models.review import SLOT_DECISIONS
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode, get_request_permission_codes
from apps.identity.throttling import DocumentDownloadRateThrottle
from config.filters import parse_bool_param, parse_uuid_param
from config.serializers import ErrorSerializer

DOSSIER_TAG = "Document dossier"

READ = "documents.read"
MANAGE_REQUIREMENTS = "documents.manage_requirements"
REVIEW = "documents.review"
WAIVE = "documents.waive"
DOWNLOAD = "documents.download"


def error_response(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: error_response("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: error_response("PERMISSION_DENIED o CSRF_FAILED"),
}
NOT_FOUND = {404: error_response("RESOURCE_NOT_FOUND (inexistente o fuera del alcance)")}


class DossierView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {}

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)

    def get_application(self, application_id: Any) -> CreditApplication:
        return get_object_or_404(applications_visible_to(self.actor), pk=application_id)

    def get_slot(self, slot_id: Any) -> ApplicationDocumentSlot:
        return get_object_or_404(dossier.slots_visible_to(self.actor), pk=slot_id)

    def get_file(self, file_id: Any) -> DocumentFile:
        return get_object_or_404(dossier.files_visible_to(self.actor), pk=file_id)


def _status_param(request: Request) -> str | None:
    value = request.query_params.get("status")
    if not value:
        return None
    if value not in SlotStatus.values:
        raise ValidationError(
            {"status": [f"Valor no permitido. Opciones: {', '.join(SlotStatus.values)}."]}
        )
    return value


class ApplicationDocumentSlotListView(DossierView):
    required_permissions = {"GET": READ}

    @extend_schema(
        tags=[DOSSIER_TAG],
        operation_id="applications_document_slots_list",
        summary="Expediente documental de la solicitud",
        description=(
            "Un slot por archivo esperado: los documentos de la solicitud primero y después "
            "los de cada participante. Solo los vigentes, salvo `include_retired=true`. "
            '`label` es la etiqueta para mostrar ("Desprendible de nómina 2 de 3").'
        ),
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, enum=SlotStatus.values),
            OpenApiParameter(
                "participant_id",
                OpenApiTypes.UUID,
                description="Slots de un participante. Los de la solicitud no tienen.",
            ),
            OpenApiParameter("document_type_code", OpenApiTypes.STR),
            OpenApiParameter("required", OpenApiTypes.BOOL),
            OpenApiParameter(
                "include_retired",
                OpenApiTypes.BOOL,
                description="Incluye los slots que dejaron de aplicar, con su historial.",
            ),
        ],
        responses={200: DocumentSlotSerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        slots = dossier.application_slots(
            application, include_retired=bool(parse_bool_param(request, "include_retired"))
        )
        slot_status = _status_param(request)
        if slot_status:
            slots = slots.filter(status=slot_status)
        participant_id = parse_uuid_param(request, "participant_id")
        if participant_id:
            slots = slots.filter(participant_id=participant_id)
        type_code = request.query_params.get("document_type_code")
        if type_code:
            slots = slots.filter(document_type__code=type_code)
        required = parse_bool_param(request, "required")
        if required is not None:
            slots = slots.filter(is_required=required)
        page = self.paginate_queryset(slots)
        return self.get_paginated_response(DocumentSlotSerializer(page, many=True).data)


class ApplicationDocumentSlotRefreshView(DossierView):
    required_permissions = {"POST": MANAGE_REQUIREMENTS}

    @extend_schema(
        tags=[DOSSIER_TAG],
        operation_id="applications_document_slots_refresh",
        summary="Recalcular el expediente documental",
        description=(
            "Aplica los requisitos publicados hoy: crea los slots que faltan, retira los "
            "que dejaron de aplicar (conservan su historial), revive los que vuelven a "
            "aplicar y actualiza los que no tienen historial. Se hace solo en cada cambio "
            "de producto, finalidad, inmueble, participantes o perfil laboral; este "
            "endpoint sirve para tomar una configuración publicada después. Solo antes de "
            "`FILED`. No exige `If-Match` ni cambia la versión de la solicitud. Responde "
            "la lista vigente completa, sin paginar."
        ),
        request=None,
        responses={
            200: SlotRefreshSerializer,
            409: error_response("APPLICATION_NOT_EDITABLE"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        result = dossier.refresh_slots(self.actor, application)
        data = {
            "created": result.created,
            "retired": result.retired,
            "revived": result.revived,
            "updated": result.updated,
            "slots": dossier.application_slots(application),
        }
        return Response(SlotRefreshSerializer(data).data)


class DocumentSlotDetailView(DossierView):
    required_permissions = {"GET": READ}

    @extend_schema(
        tags=[DOSSIER_TAG],
        operation_id="document_slots_retrieve",
        summary="Detalle de un slot",
        description=(
            "Incluye los slots retirados. `waiver_history` trae las exoneraciones y "
            "reaperturas, de la más reciente a la primera, con quién las hizo; las "
            "aprobaciones y los rechazos van en cada versión."
        ),
        responses={200: DocumentSlotDetailSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, slot_id: Any) -> Response:
        slot = get_object_or_404(dossier.slot_detail_queryset(self.actor), pk=slot_id)
        return Response(DocumentSlotDetailSerializer(slot).data)


class DocumentSlotVersionListView(DossierView):
    required_permissions = {"GET": READ}

    @extend_schema(
        tags=[DOSSIER_TAG],
        operation_id="document_slots_versions_list",
        summary="Versiones cargadas en un slot",
        description=(
            "De la más reciente a la primera, con el análisis del archivo y las revisiones "
            "(incluido el comentario interno). `is_current` marca la versión vigente."
        ),
        responses={200: DocumentFileSerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, slot_id: Any) -> Response:
        slot = self.get_slot(slot_id)
        page = self.paginate_queryset(dossier.slot_versions(slot))
        context = {"current_file_id": slot.current_file_id}
        return self.get_paginated_response(
            DocumentFileSerializer(page, many=True, context=context).data
        )


class DocumentSlotReviewView(DossierView):
    required_permissions = {"PATCH": REVIEW}

    @extend_schema(
        tags=[DOSSIER_TAG],
        operation_id="document_slots_review",
        summary="Revisar, exonerar o reabrir un documento",
        description=(
            "Cada decisión deja una fila nueva en el historial por slot afectado; corregir "
            "es decidir otra vez, nunca se edita la anterior. No exige `If-Match` ni "
            "cambia la versión de la solicitud. Solo antes de `FILED`.\n\n"
            "- `APPROVED`: sobre `document_file_id`, la versión vigente, con análisis "
            "`CLEAN`. Si el documento tiene vigencia exige `document_date` (la del "
            "comprador o la que se envía aquí, que la corrige) y no se aprueba vencido.\n"
            "- `REJECTED`: sobre la versión vigente, con `reason_code` de "
            "`document_rejection_reason` y `buyer_comment`, que ve el comprador.\n"
            "- `WAIVED` (`documents.waive`): `reason_code` de `document_waiver_reason`. En "
            "un grupo alternativo exonera también los demás slots del grupo del mismo "
            "titular, salvo los aprobados, que conservan su aprobación; si alguno de los "
            "que se exonerarían no es exonerable, no se exonera ninguno.\n"
            "- `REOPENED` (`documents.waive`): deshace la última exoneración del slot y "
            "de los que se exoneraron con ella; cada uno vuelve al estado de su versión "
            "vigente (`PENDING` si no tiene). Exige `internal_comment`.\n\n"
            "`internal_comment` nunca llega al comprador. Responde los slots que "
            "cambiaron."
        ),
        request=DocumentSlotReviewSerializer,
        responses={
            200: DocumentSlotReviewResultSerializer,
            400: error_response(
                "VALIDATION_ERROR: campos de la decisión, `document_date` faltante o "
                "futura, `NOT_A_VERSION`, `NOT_WAIVABLE`, `NOTHING_TO_WAIVE` o "
                "`NOT_WAIVED` en `details[].code`, con el slot en `resource_id`"
            ),
            401: COMMON_ERRORS[401],
            403: error_response("PERMISSION_DENIED (también sin `documents.waive`) o CSRF_FAILED"),
            409: error_response(
                "DOCUMENT_NOT_CURRENT, FILE_NOT_CLEAN, DOCUMENT_LOCKED, "
                "APPLICATION_NOT_EDITABLE o APPLICATION_CLOSED"
            ),
            422: error_response("DOCUMENT_EXPIRED"),
            **NOT_FOUND,
        },
    )
    def patch(self, request: Request, slot_id: Any) -> Response:
        slot = self.get_slot(slot_id)
        serializer = DocumentSlotReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["decision"] in SLOT_DECISIONS and WAIVE not in get_request_permission_codes(
            request
        ):
            raise PermissionDenied("No tienes permiso para exonerar documentos.")
        changed = reviews.review_slot(self.actor, slot, reviews.Review(**data))
        slots = dossier.slots_queryset().filter(pk__in=changed)
        return Response(DocumentSlotReviewResultSerializer({"slots": slots}).data)


class DocumentFileDetailView(DossierView):
    required_permissions = {"GET": READ}

    @extend_schema(
        tags=[DOSSIER_TAG],
        operation_id="document_files_retrieve",
        summary="Metadatos de una versión",
        description=(
            "Archivo, análisis y aprobaciones o rechazos de la versión, incluido el "
            "comentario interno. Nunca la clave del almacenamiento."
        ),
        responses={200: DocumentFileSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, file_id: Any) -> Response:
        version = self.get_file(file_id)
        context = {"current_file_id": version.slot.current_file_id}
        return Response(DocumentFileSerializer(version, context=context).data)


class DocumentFileScanStatusView(DossierView):
    required_permissions = {"GET": READ}

    @extend_schema(
        tags=[DOSSIER_TAG],
        operation_id="document_files_scan_status",
        summary="Análisis de seguridad de una versión",
        description=(
            "`PENDING` mientras corre el análisis; `CLEAN`, `INFECTED` (antivirus) o "
            "`INVALID` (el objeto guardado no coincide con su huella) al terminar."
        ),
        responses={200: DocumentFileScanStatusSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, file_id: Any) -> Response:
        return Response(DocumentFileScanStatusSerializer(self.get_file(file_id)).data)


DOWNLOAD_DESCRIPTION = (
    "URL prefirmada de corta duración (`DOCUMENT_DOWNLOAD_URL_SECONDS`, 5 minutos por "
    "omisión) con `Content-Disposition: attachment` y el tipo detectado. Solo archivos "
    "con análisis `CLEAN`. Límite: 60 descargas por hora. La URL no se guarda ni va a "
    "los logs."
)


def no_store(response: Response) -> Response:
    # La URL es una credencial temporal: ninguna caché intermedia la guarda.
    response["Cache-Control"] = "no-store"
    return response


class DocumentFileDownloadView(DossierView):
    required_permissions = {"GET": DOWNLOAD}
    throttle_classes = [DocumentDownloadRateThrottle]

    @extend_schema(
        tags=[DOSSIER_TAG],
        operation_id="document_files_download",
        summary="Descargar una versión",
        description=DOWNLOAD_DESCRIPTION,
        responses={
            200: DocumentDownloadSerializer,
            409: error_response("FILE_NOT_CLEAN"),
            429: error_response("RATE_LIMITED"),
            503: error_response("SERVICE_UNAVAILABLE (almacenamiento no disponible)"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def get(self, request: Request, file_id: Any) -> Response:
        version = self.get_file(file_id)
        link = downloads.download_link(version, requested_by=f"user:{self.actor.pk}")
        return no_store(Response(DocumentDownloadSerializer(link).data))
