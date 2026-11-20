"""Endpoints del dashboard (API §22.1): ``/dashboard/summary``, ``/dashboard/funnel``,
``/dashboard/workload`` y ``/dashboard/bank-results``.

Todos exigen ``dashboard.read``. El broker solo recibe conteos: el resumen sin
``amounts`` y el embudo; la carga por asesor y los resultados por banco son solo para el
administrador y el asesor (``403 PERMISSION_DENIED``).
"""

from typing import cast

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import BasePagination
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.services import get_application_scope
from apps.crm.services import CrmScope
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from apps.identity.throttling import GENERAL_THROTTLES
from apps.reporting import services
from apps.reporting.filters import DashboardFilterSerializer, ReportFilters, parse_filters
from apps.reporting.serializers import (
    DashboardBankResultsSerializer,
    DashboardFunnelSerializer,
    DashboardSummarySerializer,
    DashboardWorkloadSerializer,
)
from apps.reporting.throttling import ReportsRateThrottle
from config.serializers import ErrorSerializer

DASHBOARD_TAG = "Dashboard"


def _error(description: str, examples: list[OpenApiExample] | None = None) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description, examples=examples)


VALIDATION_EXAMPLE = OpenApiExample(
    "Rango demasiado largo",
    value={
        "code": "VALIDATION_ERROR",
        "message": "Los datos enviados no son válidos.",
        "details": [
            {
                "field": "date_to",
                "code": "INVALID",
                "message": "El rango no puede superar 366 días.",
            }
        ],
        "request_id": "req_01J9Z6S4T6R7",
    },
    response_only=True,
    status_codes=["400"],
)
OUT_OF_SCOPE_EXAMPLE = OpenApiExample(
    "Filtro fuera del alcance",
    value={
        "code": "FILTER_OUT_OF_SCOPE",
        "message": "Uno de los filtros está fuera de tu alcance.",
        "details": [
            {
                "field": "advisor_id",
                "code": "FILTER_OUT_OF_SCOPE",
                "message": "Este filtro está fuera de tu alcance.",
            }
        ],
        "request_id": "req_01J9Z6S4T6R7",
    },
    response_only=True,
    status_codes=["403"],
)
DASHBOARD_ERRORS = {
    400: _error(
        "VALIDATION_ERROR: fecha mal escrita, `date_from > date_to`, rango de más de 366 "
        "días, un id que no existe o un `purpose_code` desconocido.",
        [VALIDATION_EXAMPLE],
    ),
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error(
        "PERMISSION_DENIED o FILTER_OUT_OF_SCOPE (un filtro fuera del alcance del usuario).",
        [OUT_OF_SCOPE_EXAMPLE],
    ),
    429: _error(
        "RATE_LIMITED: más de 20 consultas por minuto al dashboard y los reportes "
        "(cupo compartido, por usuario). `Retry-After` dice cuántos segundos esperar."
    ),
}

FILTER_PARAMETERS = [
    OpenApiParameter(
        "date_from",
        OpenApiTypes.DATE,
        description=(
            "Primer día (`YYYY-MM-DD`, incluido, hora de Bogotá). Sin `date_from` ni "
            "`date_to` el rango es el mes en curso (día 1 a hoy); con solo `date_to`, el "
            "día 1 de su mes."
        ),
    ),
    OpenApiParameter(
        "date_to",
        OpenApiTypes.DATE,
        description=(
            "Último día (`YYYY-MM-DD`, incluido). Por omisión, hoy; una fecha futura se "
            "recorta a hoy. El rango no puede superar 366 días."
        ),
    ),
    OpenApiParameter(
        "advisor_id",
        OpenApiTypes.UUID,
        description=(
            "Asesor asignado. El asesor solo puede mandar el suyo y el broker ninguno: "
            "otro valor responde `403 FILTER_OUT_OF_SCOPE`."
        ),
    ),
    OpenApiParameter(
        "partner_id",
        OpenApiTypes.UUID,
        description=(
            "Constructora del proyecto de la solicitud (el del inmueble o, si no tiene, el "
            "de la oportunidad). El broker no puede usarlo (`403 FILTER_OUT_OF_SCOPE`)."
        ),
    ),
    OpenApiParameter(
        "project_id",
        OpenApiTypes.UUID,
        description=(
            "Proyecto de la solicitud (el del inmueble o, si no tiene, el de la "
            "oportunidad). El broker no puede usarlo (`403 FILTER_OUT_OF_SCOPE`)."
        ),
    ),
    OpenApiParameter("bank_id", OpenApiTypes.UUID, description="Banco del producto."),
    OpenApiParameter(
        "purpose_code",
        OpenApiTypes.STR,
        description="Código `loan_purpose`. Uno que no existe responde `400`.",
    ),
]

PERIOD_EXAMPLE = {"date_from": "2026-11-01", "date_to": "2026-11-17"}


class DashboardView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions = {"GET": "dashboard.read"}
    throttle_classes = [*GENERAL_THROTTLES, ReportsRateThrottle]
    pagination_class: type[BasePagination] | None = None
    filter_serializer_class: type[DashboardFilterSerializer] = DashboardFilterSerializer
    # Solo el administrador y el asesor; el broker recibe 403.
    internal_only = False

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)

    @property
    def scope(self) -> CrmScope:
        if not hasattr(self, "_scope"):
            self._scope = get_application_scope(self.actor)
        return self._scope

    def get_filters(self) -> ReportFilters:
        if self.internal_only and not (self.scope.sees_everything or self.scope.is_advisor):
            raise PermissionDenied()
        return parse_filters(
            self.request.query_params,
            self.actor,
            self.scope,
            serializer_class=self.filter_serializer_class,
        )


class DashboardSummaryView(DashboardView):
    @extend_schema(
        tags=[DASHBOARD_TAG],
        operation_id="dashboard_summary",
        summary="Indicadores principales del periodo",
        description=(
            "Clientes y solicitudes creados en el periodo, la foto de hoy por estado (sin "
            "el filtro de fechas), las tareas vencidas y de hoy y, solo para el "
            "administrador y el asesor, los montos en COP. El broker recibe solo conteos "
            "de las solicitudes de las oportunidades que originó: sin `amounts` y con "
            "`tasks` en 0."
        ),
        parameters=FILTER_PARAMETERS,
        responses={200: DashboardSummarySerializer, **DASHBOARD_ERRORS},
        examples=[
            OpenApiExample(
                "Asesor",
                value={
                    "period": PERIOD_EXAMPLE,
                    "clients_created": 12,
                    "applications_created": 9,
                    "snapshot": [
                        {"status": "DRAFT", "status_label": "Borrador", "count": 2},
                        {"status": "FILED", "status_label": "Radicada", "count": 3},
                    ],
                    "tasks": {"overdue": 1, "due_today": 4},
                    "amounts": {
                        "requested_total": "1850000000.00",
                        "approved_total": "420000000.00",
                        "disbursed_total": "0.00",
                    },
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def get(self, request: Request) -> Response:
        filters = self.get_filters()
        data = services.summary(self.actor, filters, self.scope)
        return Response(DashboardSummarySerializer(data).data)


class DashboardFunnelView(DashboardView):
    @extend_schema(
        tags=[DASHBOARD_TAG],
        operation_id="dashboard_funnel",
        summary="Embudo de conversión del periodo",
        description=(
            "Cohorte de las solicitudes creadas en el periodo: cuántas llegaron alguna vez "
            "a cada etapa, en orden (`CREATED`, `DOCUMENTS_COMPLETE`, `READY_TO_FILE`, "
            "`FILED`, `APPROVED`, `DISBURSED`). Una solicitud que llegó a una etapa "
            "posterior cuenta en las anteriores. `DOCUMENTS_COMPLETE` es haber llegado a "
            "`DOCUMENTS_REVIEW`. `conversion` es contra `CREATED` y `step_conversion` "
            "contra la etapa anterior, como decimal en texto con 4 decimales."
        ),
        parameters=FILTER_PARAMETERS,
        responses={200: DashboardFunnelSerializer, **DASHBOARD_ERRORS},
        examples=[
            OpenApiExample(
                "Embudo",
                value={
                    "period": PERIOD_EXAMPLE,
                    "stages": [
                        {
                            "code": "CREATED",
                            "label": "Creadas",
                            "count": 20,
                            "conversion": "1.0000",
                            "step_conversion": None,
                        },
                        {
                            "code": "DOCUMENTS_COMPLETE",
                            "label": "Documentos completos",
                            "count": 9,
                            "conversion": "0.4500",
                            "step_conversion": "0.4500",
                        },
                    ],
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def get(self, request: Request) -> Response:
        data = services.funnel(self.actor, self.get_filters(), self.scope)
        return Response(DashboardFunnelSerializer(data).data)


class DashboardWorkloadView(DashboardView):
    internal_only = True

    @extend_schema(
        tags=[DASHBOARD_TAG],
        operation_id="dashboard_workload",
        summary="Carga de hoy por asesor",
        description=(
            "Solo administrador y asesor (el broker recibe `403 PERMISSION_DENIED`). El "
            "asesor ve solo su fila; el administrador, la de cada asesor activo y la de "
            "quien tenga solicitudes abiertas asignadas (o solo la de `advisor_id`). Es "
            "una foto de hoy: el rango de fechas no aplica. Las tareas son las `PENDING` "
            "asignadas al asesor."
        ),
        parameters=FILTER_PARAMETERS,
        responses={200: DashboardWorkloadSerializer, **DASHBOARD_ERRORS},
        examples=[
            OpenApiExample(
                "Carga",
                value={
                    "advisors": [
                        {
                            "advisor_id": "6f1c2c1e-3f0e-4a59-9c39-0b6b5c3a8d11",
                            "advisor_name": "Andrea García",
                            "open_applications": 14,
                            "overdue_tasks": 2,
                            "due_today_tasks": 3,
                            "waiting_buyer": 5,
                            "ready_to_file": 1,
                        }
                    ]
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def get(self, request: Request) -> Response:
        data = services.workload(self.actor, self.get_filters(), self.scope)
        return Response(DashboardWorkloadSerializer(data).data)


class DashboardBankResultsView(DashboardView):
    internal_only = True

    @extend_schema(
        tags=[DASHBOARD_TAG],
        operation_id="dashboard_bank_results",
        summary="Resultados de las radicaciones por banco",
        description=(
            "Solo administrador y asesor (el broker recibe `403 PERMISSION_DENIED`). "
            "Radicaciones con `filed_at` en el periodo, agrupadas por el banco del "
            "producto radicado (`bank_id` filtra por ese banco). Una radicación cuenta en "
            "`returned`, `approved`, `rejected` o `disbursed` si alguna vez recibió esa "
            "respuesta. Solo salen los bancos con radicaciones."
        ),
        parameters=FILTER_PARAMETERS,
        responses={200: DashboardBankResultsSerializer, **DASHBOARD_ERRORS},
        examples=[
            OpenApiExample(
                "Bancos",
                value={
                    "period": PERIOD_EXAMPLE,
                    "banks": [
                        {
                            "bank_id": "0c5b8d6e-2b8f-4a0e-8f43-6a2d9f1e7b20",
                            "bank_name": "Bancolombia",
                            "filings": 8,
                            "returned": 2,
                            "approved": 4,
                            "rejected": 1,
                            "disbursed": 1,
                            "avg_days_to_response": "3.5",
                        }
                    ],
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def get(self, request: Request) -> Response:
        data = services.bank_results(self.actor, self.get_filters(), self.scope)
        return Response(DashboardBankResultsSerializer(data).data)
