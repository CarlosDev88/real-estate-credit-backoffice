"""Reportes operativos (API §22.2): ``/reports/funnel``, ``/reports/applications`` y
``/reports/applications.csv``.

Solo administrador y asesor (``reports.read`` y ``reports.export``); el broker y la
constructora reciben ``403 PERMISSION_DENIED``. Comparten los filtros del dashboard más
``status`` (multivalor) y el mismo cupo de consumo.
"""

from typing import Any

from django.conf import settings
from django.http import StreamingHttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.views import _choice_param
from apps.catalogs.workflow import ApplicationStatus
from apps.reporting import exports, services
from apps.reporting.exceptions import ExportTooLarge
from apps.reporting.filters import ReportFilterSerializer
from apps.reporting.serializers import ReportApplicationSerializer, ReportFunnelSerializer
from apps.reporting.services import FunnelGroupBy
from apps.reporting.signals import report_exported
from apps.reporting.views import (
    DASHBOARD_ERRORS,
    FILTER_PARAMETERS,
    PERIOD_EXAMPLE,
    DashboardView,
    _error,
)
from config.api import StandardResultsSetPagination

REPORTS_TAG = "Reports"

STATUS_PARAMETER = OpenApiParameter(
    "status",
    OpenApiTypes.STR,
    enum=ApplicationStatus.values,
    many=True,
    explode=True,
    description="Estado actual de la solicitud; se repite para varios "
    "(`status=FILED&status=APPROVED`). Un estado desconocido responde `400`.",
)
GROUP_BY_PARAMETER = OpenApiParameter(
    "group_by",
    OpenApiTypes.STR,
    enum=FunnelGroupBy.values,
    description="Desglose opcional: un embudo por asesor, banco o finalidad. Otro valor "
    "responde `400`.",
)
REPORT_PARAMETERS = [*FILTER_PARAMETERS, STATUS_PARAMETER]


class ReportView(DashboardView):
    required_permissions = {"GET": "reports.read"}
    filter_serializer_class = ReportFilterSerializer


class ReportFunnelView(ReportView):
    @extend_schema(
        tags=[REPORTS_TAG],
        operation_id="reports_funnel",
        summary="Embudo reportable con desglose opcional",
        description=(
            "El mismo embudo de `/dashboard/funnel` (cohorte de las solicitudes creadas en "
            "el periodo) con el filtro `status` y, con `group_by`, un embudo por asesor, "
            "banco o finalidad. El asesor solo ve sus solicitudes, así que su desglose por "
            "asesor tiene un grupo."
        ),
        parameters=[*REPORT_PARAMETERS, GROUP_BY_PARAMETER],
        responses={200: ReportFunnelSerializer, **DASHBOARD_ERRORS},
        examples=[
            OpenApiExample(
                "Por banco",
                value={
                    "period": PERIOD_EXAMPLE,
                    "group_by": "bank",
                    "stages": [
                        {
                            "code": "CREATED",
                            "label": "Creadas",
                            "count": 3,
                            "conversion": "1.0000",
                            "step_conversion": None,
                        }
                    ],
                    "groups": [
                        {
                            "key": "0c5b8d6e-2b8f-4a0e-8f43-6a2d9f1e7b20",
                            "label": "Bancolombia",
                            "stages": [
                                {
                                    "code": "CREATED",
                                    "label": "Creadas",
                                    "count": 2,
                                    "conversion": "1.0000",
                                    "step_conversion": None,
                                }
                            ],
                        },
                        {
                            "key": None,
                            "label": "Sin banco",
                            "stages": [
                                {
                                    "code": "CREATED",
                                    "label": "Creadas",
                                    "count": 1,
                                    "conversion": "1.0000",
                                    "step_conversion": None,
                                }
                            ],
                        },
                    ],
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def get(self, request: Request) -> Response:
        filters = self.get_filters()
        group_by = _choice_param(request, "group_by", list(FunnelGroupBy.values))
        data = services.report_funnel(self.actor, filters, self.scope, group_by)
        return Response(ReportFunnelSerializer(data).data)


class ReportApplicationsView(ReportView):
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        tags=[REPORTS_TAG],
        operation_id="reports_applications_list",
        summary="Reporte paginado de solicitudes",
        description=(
            "Solicitudes creadas en el periodo (por fecha de creación), dentro del alcance "
            "y con los filtros, de la más nueva a la más vieja. Solo datos operativos: el "
            "documento del titular sale enmascarado y nunca salen correo, teléfono, "
            "dirección, datos financieros del comprador ni archivos."
        ),
        parameters=REPORT_PARAMETERS,
        responses={200: ReportApplicationSerializer(many=True), **DASHBOARD_ERRORS},
    )
    def get(self, request: Request) -> Response:
        filters = self.get_filters()
        applications = exports.report_applications(self.actor, filters, self.scope)
        page = self.paginate_queryset(applications)
        assert page is not None
        rows = [exports.application_row(application) for application in page]
        return self.get_paginated_response(ReportApplicationSerializer(rows, many=True).data)


class ReportApplicationsCsvView(ReportView):
    required_permissions = {"GET": "reports.export"}

    def perform_content_negotiation(self, request: Request, force: bool = False) -> Any:
        # La respuesta correcta es el CSV que arma la vista; los errores salen en JSON
        # aunque el cliente pida `text/csv`.
        return super().perform_content_negotiation(request, force=True)

    @extend_schema(
        tags=[REPORTS_TAG],
        operation_id="reports_applications_csv",
        summary="Descarga directa del reporte de solicitudes en CSV",
        description=(
            "Las mismas columnas y filtros de `/reports/applications`, en CSV UTF-8 con BOM, "
            "separado por comas y con encabezados en español. Las celdas que empiezan con "
            "`=`, `+`, `-`, `@`, tabulador o retorno de carro se prefijan con `'`. Si el "
            "resultado supera `REPORTS_CSV_MAX_ROWS` (5000) filas responde `422 "
            "EXPORT_TOO_LARGE`: hay que usar la exportación asíncrona."
        ),
        parameters=REPORT_PARAMETERS,
        responses={
            (200, "text/csv"): OpenApiResponse(
                response=OpenApiTypes.STR,
                description="Archivo `solicitudes_<date_from>_<date_to>.csv` "
                "(`Content-Disposition: attachment`).",
            ),
            **DASHBOARD_ERRORS,
            422: _error("EXPORT_TOO_LARGE: más filas que el límite de la descarga directa."),
        },
    )
    def get(self, request: Request) -> StreamingHttpResponse:
        filters = self.get_filters()
        applications = exports.report_applications(self.actor, filters, self.scope)
        row_count = applications.count()
        if row_count > settings.REPORTS_CSV_MAX_ROWS:
            raise ExportTooLarge()
        report_exported.send(
            sender=self.__class__,
            user=self.actor,
            report_type=exports.REPORT_TYPE_APPLICATIONS,
            filters=filters.as_dict(),
            row_count=row_count,
            format=exports.FORMAT_CSV,
        )
        response = StreamingHttpResponse(
            exports.csv_lines(applications.iterator(chunk_size=exports.ITERATOR_CHUNK_SIZE)),
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = f'attachment; filename="{exports.csv_filename(filters)}"'
        return response
