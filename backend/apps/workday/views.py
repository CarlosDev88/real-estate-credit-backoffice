"""Endpoints de "Mi día" (API §15.1): ``/workday/applications`` y ``/workday/summary``."""

from typing import Any, cast

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.filters import SearchFilter
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.services import get_application_scope
from apps.applications.views import (
    APPLICATION_SEARCH_FIELDS,
    COMMON_ERRORS,
    _catalog_param,
    _choice_param,
)
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from apps.workday import services
from apps.workday.rules import WORKDAY_STATUSES, AttentionSegment
from apps.workday.serializers import WorkdayApplicationSerializer, WorkdaySummarySerializer
from config.filters import StrictOrderingFilter, parse_uuid_param

WORKDAY_TAG = "Workday"

FILTER_PARAMETERS = [
    OpenApiParameter(
        "stage",
        OpenApiTypes.STR,
        enum=list(WORKDAY_STATUSES),
        description="Estado no terminal de la solicitud. Otro valor responde `400`.",
    ),
    OpenApiParameter("bank_id", OpenApiTypes.UUID),
    OpenApiParameter(
        "purpose",
        OpenApiTypes.STR,
        description="Código `loan_purpose`. Uno que no existe responde `400`.",
    ),
    OpenApiParameter(
        "advisor_id",
        OpenApiTypes.UUID,
        description="Solo el administrador. Para el asesor se ignora: siempre ve las suyas.",
    ),
]
ATTENTION_PARAM = OpenApiParameter(
    "attention",
    OpenApiTypes.STR,
    enum=AttentionSegment.values,
    description="Segmento de atención. Un código desconocido responde `400`.",
)


class WorkdayView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions = {"GET": "workday.read"}
    filter_backends = [SearchFilter]
    search_fields = APPLICATION_SEARCH_FIELDS

    def workday_queryset(self) -> Any:
        """Solicitudes del alcance con los filtros comunes a la lista y al resumen (todos,
        salvo ``attention``). La búsqueda la agrega ``SearchFilter``."""
        actor = cast(User, self.request.user)
        advisor_id = None
        if get_application_scope(actor).sees_everything:
            advisor_id = parse_uuid_param(self.request, "advisor_id")
        applications = services.workday_applications(actor, advisor_id=advisor_id)
        stage = _choice_param(self.request, "stage", list(WORKDAY_STATUSES))
        if stage:
            applications = applications.filter(status=stage)
        bank_id = parse_uuid_param(self.request, "bank_id")
        if bank_id:
            applications = applications.filter(bank_product__bank_id=bank_id)
        purpose = _catalog_param(self.request, "purpose", "loan_purpose")
        if purpose:
            applications = applications.filter(purpose_item__code=purpose)
        return applications


class WorkdayApplicationListView(WorkdayView):
    filter_backends = [SearchFilter, StrictOrderingFilter]
    ordering_fields = ["days_in_stage", "updated_at", "code"]
    # Primero las que tienen tareas vencidas o de hoy; después, las de más días en la etapa.
    ordering = ["-attention_tasks_due", "-days_in_stage", "code"]

    def get_queryset(self) -> Any:
        applications = self.workday_queryset()
        attention = _choice_param(self.request, "attention", AttentionSegment.values)
        if attention:
            applications = services.filter_by_attention(applications, attention)
        return applications

    @extend_schema(
        tags=[WORKDAY_TAG],
        operation_id="workday_applications_list",
        summary="Solicitudes en curso del asesor, con su siguiente acción",
        description=(
            "El asesor ve sus solicitudes asignadas; el administrador, todas (o las de "
            "`advisor_id`). Solo las no terminales. Por omisión van primero las que tienen "
            "tareas vencidas o de hoy y después las de más días en la etapa. `search` busca "
            "por código, nombre o documento del titular, como el listado."
        ),
        parameters=[*FILTER_PARAMETERS, ATTENTION_PARAM],
        responses={200: WorkdayApplicationSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(WorkdayApplicationSerializer(page, many=True).data)


class WorkdaySummaryView(WorkdayView):
    pagination_class = None

    @extend_schema(
        tags=[WORKDAY_TAG],
        operation_id="workday_summary",
        summary="Conteos de Mi día por segmento de atención",
        description=(
            "`total` y un conteo por segmento, en el orden fijo de los segmentos. Aplica "
            "los mismos filtros que `/workday/applications`, salvo `attention`. Los "
            "segmentos no son excluyentes."
        ),
        parameters=FILTER_PARAMETERS,
        responses={200: WorkdaySummarySerializer, **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        applications = self.filter_queryset(self.workday_queryset())
        return Response(WorkdaySummarySerializer(services.summary(applications)).data)
