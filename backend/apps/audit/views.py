"""Consulta de la auditoría (API §24.1): solo el administrador (``audit.read``)."""

from datetime import datetime, time, timedelta
from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.audit.actions import AuditAction, AuditResult
from apps.audit.models import AuditEvent
from apps.audit.serializers import AuditEventSerializer
from apps.identity.permissions import HasPermissionCode
from config.filters import parse_uuid_param
from config.serializers import ErrorSerializer

AUDIT_TAG = "Audit"
DATE_LENGTH = len("2026-11-17")


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED (solo el administrador; el intento queda auditado)"),
}

LIST_PARAMETERS = [
    OpenApiParameter("actor_user_id", OpenApiTypes.UUID),
    OpenApiParameter("actor_buyer_session_id", OpenApiTypes.UUID),
    OpenApiParameter(
        "action",
        OpenApiTypes.STR,
        enum=AuditAction.values,
        many=True,
        explode=True,
        description="Una o varias (`?action=A&action=B`). Un código desconocido responde `400`.",
    ),
    OpenApiParameter("resource_type", OpenApiTypes.STR, description="Tabla del recurso."),
    OpenApiParameter("resource_id", OpenApiTypes.UUID),
    OpenApiParameter("result", OpenApiTypes.STR, enum=AuditResult.values),
    OpenApiParameter("request_id", OpenApiTypes.STR),
    OpenApiParameter(
        "created_from",
        OpenApiTypes.STR,
        description="Fecha (`AAAA-MM-DD`, desde el inicio del día en Bogotá) o fecha y hora ISO.",
    ),
    OpenApiParameter(
        "created_to",
        OpenApiTypes.STR,
        description="Fecha (hasta el fin del día en Bogotá, incluido) o fecha y hora ISO.",
    ),
]


def _moment(request: Request, name: str, *, end_of_day: bool) -> datetime | None:
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        # Primero la fecha: `parse_datetime` también acepta "AAAA-MM-DD" (medianoche).
        day = parse_date(value) if len(value) == DATE_LENGTH else None
        moment = None if day is not None else parse_datetime(value)
    except ValueError:
        day = moment = None
    if day is not None:
        start = timezone.make_aware(datetime.combine(day, time.min))
        return start + timedelta(days=1) if end_of_day else start
    if moment is None:
        raise ValidationError({name: ["Debe ser una fecha (AAAA-MM-DD) o una fecha y hora ISO."]})
    return moment if timezone.is_aware(moment) else timezone.make_aware(moment)


def _choices(request: Request, name: str, choices: list[str]) -> list[str]:
    values = request.query_params.getlist(name)
    if set(values) - set(choices):
        raise ValidationError({name: [f"Valor no permitido. Opciones: {', '.join(choices)}."]})
    return values


def filtered_events(request: Request) -> QuerySet[AuditEvent]:
    events = AuditEvent.objects.select_related("actor_user")
    for name, field in (
        ("actor_user_id", "actor_user_id"),
        ("actor_buyer_session_id", "actor_buyer_session_id"),
        ("resource_id", "resource_id"),
    ):
        value = parse_uuid_param(request, name)
        if value:
            events = events.filter(**{field: value})
    actions = _choices(request, "action", AuditAction.values)
    if actions:
        events = events.filter(action__in=actions)
    results = _choices(request, "result", AuditResult.values)
    if results:
        events = events.filter(result__in=results)
    for name in ("resource_type", "request_id"):
        text = request.query_params.get(name)
        if text:
            events = events.filter(**{name: text})
    created_from = _moment(request, "created_from", end_of_day=False)
    if created_from:
        events = events.filter(created_at__gte=created_from)
    created_to = _moment(request, "created_to", end_of_day=True)
    if created_to:
        # Una fecha da el inicio del día siguiente (excluido); una fecha y hora, incluida.
        if len(request.query_params["created_to"]) == DATE_LENGTH:
            events = events.filter(created_at__lt=created_to)
        else:
            events = events.filter(created_at__lte=created_to)
    return events.order_by("-created_at", "-id")


class AuditEventListView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions = {"GET": "audit.read"}

    @extend_schema(
        tags=[AUDIT_TAG],
        operation_id="audit_events_list",
        summary="Eventos de auditoría",
        description=(
            "Bitácora técnica inmutable, del más nuevo al más viejo. Solo el "
            "administrador. Nunca guarda contraseñas, tokens, cookies, la cabecera "
            "`Authorization`, URLs firmadas ni números de documento completos."
        ),
        parameters=LIST_PARAMETERS,
        responses={
            200: AuditEventSerializer(many=True),
            400: _error("VALIDATION_ERROR"),
            **COMMON_ERRORS,
        },
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(filtered_events(request))
        return self.get_paginated_response(AuditEventSerializer(page, many=True).data)


class AuditEventDetailView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions = {"GET": "audit.read"}

    @extend_schema(
        tags=[AUDIT_TAG],
        operation_id="audit_events_retrieve",
        summary="Detalle de un evento de auditoría",
        responses={
            200: AuditEventSerializer,
            404: _error("RESOURCE_NOT_FOUND"),
            **COMMON_ERRORS,
        },
    )
    def get(self, request: Request, event_id: Any) -> Response:
        event = get_object_or_404(AuditEvent.objects.select_related("actor_user"), pk=event_id)
        return Response(AuditEventSerializer(event).data)
