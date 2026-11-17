"""Actividad y notas del expediente (API §21.1) y la actividad del comprador."""

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.activity import services
from apps.activity.models import ActivityEventType, ActivityVisibility
from apps.activity.serializers import ActivitySerializer, NoteCreateSerializer, NoteSerializer
from apps.applications.views import ApplicationView
from apps.identity.buyer_portal_views import BUYER_PORTAL_TAG, SESSION_ERRORS, BuyerPortalView
from config.serializers import ErrorSerializer

ACTIVITY_TAG = "Activity"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND (inexistente o fuera del alcance)")}

EVENT_TYPE_PARAM = OpenApiParameter(
    "event_type",
    OpenApiTypes.STR,
    enum=ActivityEventType.values,
    many=True,
    explode=True,
    description=(
        "Uno o varios tipos (`?event_type=A&event_type=B`). Un código desconocido responde `400`."
    ),
)


def event_types_param(request: Request) -> list[str]:
    values = request.query_params.getlist("event_type")
    unknown = sorted(set(values) - set(ActivityEventType.values))
    if unknown:
        options = ", ".join(ActivityEventType.values)
        raise ValidationError({"event_type": [f"Valor no permitido. Opciones: {options}."]})
    return values


class ApplicationActivityView(ApplicationView):
    required_permissions = {"GET": "applications.read"}

    @extend_schema(
        tags=[ACTIVITY_TAG],
        operation_id="applications_activity_list",
        summary="Actividad de la solicitud",
        description=(
            "Línea de tiempo del expediente, de la más reciente a la más antigua. El "
            "administrador y el asesor ven las filas internas; el broker, solo las del "
            "comprador (las mismas de `/buyer/applications/{id}/activity`). `actor` es "
            '`{name}` ("Portal del comprador" si lo hizo el comprador) o nulo.'
        ),
        parameters=[EVENT_TYPE_PARAM],
        responses={200: ActivitySerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        visibility = (
            ActivityVisibility.BUYER if self.scope.is_restricted else ActivityVisibility.INTERNAL
        )
        rows = services.application_activity(
            application, visibility=visibility, event_types=event_types_param(request)
        )
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(ActivitySerializer(page, many=True).data)


class ApplicationNotesView(ApplicationView):
    required_permissions = {"GET": "applications.add_note", "POST": "applications.add_note"}

    @extend_schema(
        tags=[ACTIVITY_TAG],
        operation_id="applications_notes_list",
        summary="Notas internas de la solicitud",
        description="La más reciente primero. Solo el administrador y el asesor asignado.",
        responses={200: NoteSerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        page = self.paginate_queryset(services.application_notes(application))
        return self.get_paginated_response(NoteSerializer(page, many=True).data)

    @extend_schema(
        tags=[ACTIVITY_TAG],
        operation_id="applications_notes_create",
        summary="Agregar una nota interna",
        description=(
            "`body` obligatorio, hasta 2000 caracteres. Queda en la actividad como "
            "`NOTE_ADDED`, interna: el comprador y el broker nunca la ven. Se admite "
            "también en una solicitud terminada."
        ),
        request=NoteCreateSerializer,
        responses={
            201: NoteSerializer,
            400: _error("VALIDATION_ERROR"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        serializer = NoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = services.add_note(self.actor, application, serializer.validated_data["body"])
        return Response(NoteSerializer(note).data, status=status.HTTP_201_CREATED)


class BuyerActivityView(BuyerPortalView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_applications_activity_list",
        summary="Actividad de la solicitud para el comprador",
        description=(
            "Solo las filas para el comprador, de la más reciente a la más antigua. "
            '`actor` es "Tú", "Tu asesor" o nulo.'
        ),
        parameters=[EVENT_TYPE_PARAM],
        responses={
            200: ActivitySerializer(many=True),
            404: _error("RESOURCE_NOT_FOUND (no es la solicitud de la sesión)"),
            **SESSION_ERRORS,
        },
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.ensure_session_application(application_id)
        rows = services.application_activity(
            application, visibility=ActivityVisibility.BUYER, event_types=event_types_param(request)
        )
        page = self.paginate_queryset(rows)
        data = ActivitySerializer(page, many=True, context={"buyer": True}).data
        return self.get_paginated_response(data)
