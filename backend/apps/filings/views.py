"""Radicaciones (API §20.1). Las reglas viven en ``apps.filings.services``."""

from typing import Any, cast

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.concurrency import with_etag
from apps.applications.models import CreditApplication
from apps.applications.services import applications_visible_to
from apps.filings import services
from apps.filings.models import Filing
from apps.filings.serializers import (
    FilingCreateSerializer,
    FilingDocumentSnapshotSerializer,
    FilingSerializer,
    FilingUpdateSerializer,
)
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from config.serializers import ErrorSerializer

FILINGS_TAG = "Filings"

READ = "filings.read"
CREATE = "filings.create"
UPDATE = "filings.update"


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
