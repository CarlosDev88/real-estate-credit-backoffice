"""Endpoints internos del expediente documental (API §19): lista, detalle y versiones
de los slots, y recálculo manual. Las rutas del comprador van bajo ``/buyer/...``
(Parte 4)."""

from typing import Any, cast

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.models import CreditApplication
from apps.applications.services import applications_visible_to
from apps.documents import dossier
from apps.documents.dossier_serializers import (
    DocumentFileSerializer,
    DocumentSlotSerializer,
    SlotRefreshSerializer,
)
from apps.documents.models import ApplicationDocumentSlot, SlotStatus
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from config.filters import parse_bool_param, parse_uuid_param
from config.serializers import ErrorSerializer

DOSSIER_TAG = "Document dossier"

READ = "documents.read"
MANAGE_REQUIREMENTS = "documents.manage_requirements"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND (inexistente o fuera del alcance)")}


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
            409: _error("APPLICATION_NOT_EDITABLE"),
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
        description="Incluye los slots retirados.",
        responses={200: DocumentSlotSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, slot_id: Any) -> Response:
        return Response(DocumentSlotSerializer(self.get_slot(slot_id)).data)


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
