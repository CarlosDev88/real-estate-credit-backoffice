"""Exportación asíncrona del reporte de solicitudes (API §22.2):
``/reports/applications/export-jobs``, ``/report-export-jobs/{job_id}`` y su descarga.

Pedir y listar exige ``reports.export``. Cada usuario ve sus exportaciones; con
``reports.manage`` (administrador) ve cualquiera, y en la lista con ``?all=true``. Una
exportación ajena sin ``reports.manage`` responde ``404`` (no confirma que existe).
"""

from typing import Any, cast

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.services import get_application_scope
from apps.audit.actions import AuditAction
from apps.documents.dossier_serializers import DocumentDownloadSerializer
from apps.documents.dossier_views import no_store
from apps.idempotency.decorators import IDEMPOTENCY_PARAMETER, idempotency_responses, idempotent
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode, get_request_permission_codes
from apps.identity.throttling import DocumentDownloadRateThrottle
from apps.reporting import export_jobs
from apps.reporting.filters import out_of_scope, parse_filters
from apps.reporting.models import ReportExportJob
from apps.reporting.report_views import REPORTS_TAG
from apps.reporting.serializers import ExportJobRequestSerializer, ReportExportJobSerializer
from apps.reporting.throttling import ReportsRateThrottle
from apps.reporting.views import DASHBOARD_ERRORS, _error
from config.api import StandardResultsSetPagination
from config.filters import parse_bool_param

COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND (inexistente o de otro usuario)")}

JOB_EXAMPLE = OpenApiExample(
    "Pendiente",
    value={
        "id": "3f0f2a8e-4b3c-4f7e-9d61-2a1b5c6d7e80",
        "report_type": "applications",
        "report_type_label": "Solicitudes",
        "format": "csv",
        "status": "PENDING",
        "status_label": "Pendiente",
        "filters": {
            "date_from": "2026-11-01",
            "date_to": "2026-11-17",
            "advisor_id": None,
            "partner_id": None,
            "project_id": None,
            "bank_id": None,
            "purpose_code": None,
            "status": ["FILED", "APPROVED"],
        },
        "row_count": None,
        "error_code": None,
        "requested_by": {"id": "6f1c2c1e-3f0e-4a59-9c39-0b6b5c3a8d11", "name": "Andrea García"},
        "created_at": "2026-11-17T15:04:05-05:00",
        "started_at": None,
        "completed_at": None,
        "expires_at": None,
    },
    response_only=True,
    status_codes=["202", "200"],
)


class ExportJobView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {"GET": export_jobs.EXPORT_PERMISSION}

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)

    @property
    def is_manager(self) -> bool:
        return export_jobs.MANAGE_PERMISSION in get_request_permission_codes(self.request)

    def get_job(self, job_id: Any) -> ReportExportJob:
        jobs = export_jobs.jobs_visible_to(self.actor, manager=self.is_manager)
        return get_object_or_404(jobs, pk=job_id)


class ApplicationExportJobsView(ExportJobView):
    required_permissions = {
        "GET": export_jobs.EXPORT_PERMISSION,
        "POST": export_jobs.EXPORT_PERMISSION,
    }
    throttle_classes = [ReportsRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        tags=[REPORTS_TAG],
        operation_id="reports_applications_export_jobs_list",
        summary="Exportaciones pedidas",
        description=(
            "Las exportaciones propias, de la más nueva a la más vieja. Con "
            "`reports.manage` (administrador), `all=true` lista las de todos; sin ese "
            "permiso, `all=true` responde `403 FILTER_OUT_OF_SCOPE`."
        ),
        parameters=[
            OpenApiParameter(
                "all",
                OpenApiTypes.BOOL,
                description="Solo con `reports.manage`: las exportaciones de todos.",
            )
        ],
        responses={
            200: ReportExportJobSerializer(many=True),
            401: COMMON_ERRORS[401],
            403: _error("PERMISSION_DENIED o FILTER_OUT_OF_SCOPE (`all` sin `reports.manage`)"),
            429: DASHBOARD_ERRORS[429],
        },
    )
    def get(self, request: Request) -> Response:
        show_all = parse_bool_param(request, "all") or False
        if show_all and not self.is_manager:
            raise out_of_scope("all")
        jobs = export_jobs.jobs_visible_to(self.actor, manager=show_all)
        page = self.paginate_queryset(jobs.order_by("-created_at", "-id"))
        assert page is not None
        return self.get_paginated_response(ReportExportJobSerializer(page, many=True).data)

    @extend_schema(
        tags=[REPORTS_TAG],
        operation_id="reports_applications_export_jobs_create",
        summary="Pedir la exportación asíncrona del reporte de solicitudes",
        description=(
            "Exporta en segundo plano, solo en CSV, el reporte de `/reports/applications` "
            "con los filtros del cuerpo (los mismos de la consulta, todos opcionales; un "
            "campo desconocido responde `400`). Guarda los filtros ya validados, con el "
            "rango efectivo. El trabajo se recalcula con el alcance del solicitante al "
            "momento de ejecutarse y no tiene el límite de 5000 filas (sí un tope de "
            "100000). Cada usuario tiene como máximo 3 exportaciones pendientes o en "
            "proceso: una más responde `429 TOO_MANY_EXPORTS`. Se consulta en "
            "`GET /report-export-jobs/{job_id}`."
        ),
        request=ExportJobRequestSerializer,
        parameters=[IDEMPOTENCY_PARAMETER],
        responses=idempotency_responses(
            {
                202: ReportExportJobSerializer,
                400: DASHBOARD_ERRORS[400],
                401: COMMON_ERRORS[401],
                403: DASHBOARD_ERRORS[403],
                429: _error(
                    "TOO_MANY_EXPORTS (3 exportaciones en curso) o RATE_LIMITED (más de 20 "
                    "consultas por minuto al dashboard y los reportes)"
                ),
            }
        ),
        examples=[JOB_EXAMPLE],
    )
    @idempotent()
    def post(self, request: Request) -> Response:
        filters = parse_filters(
            request.data,
            self.actor,
            get_application_scope(self.actor),
            serializer_class=ExportJobRequestSerializer,
        )
        job = export_jobs.request_export(self.actor, filters)
        return Response(ReportExportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class ReportExportJobDetailView(ExportJobView):
    @extend_schema(
        tags=[REPORTS_TAG],
        operation_id="report_export_jobs_retrieve",
        summary="Estado de una exportación",
        description=(
            "Del propietario, o de cualquiera con `reports.manage`. `FAILED` trae "
            "`error_code`; un `FAILED` no se reintenta: se pide otra."
        ),
        responses={200: ReportExportJobSerializer, **NOT_FOUND, **COMMON_ERRORS},
        examples=[JOB_EXAMPLE],
    )
    def get(self, request: Request, job_id: Any) -> Response:
        return Response(ReportExportJobSerializer(self.get_job(job_id)).data)


class ReportExportJobDownloadView(ExportJobView):
    throttle_classes = [DocumentDownloadRateThrottle]
    # Auditoría (módulo 14, apps/audit/hooks.py): como la descarga de paquetes.
    audit_actions = {"GET": AuditAction.REPORT_EXPORT_DOWNLOADED}
    audit_resource_type = "report_export_jobs"

    @extend_schema(
        tags=[REPORTS_TAG],
        operation_id="report_export_jobs_download",
        summary="Descargar una exportación",
        description=(
            "URL prefirmada de corta duración (`DOCUMENT_DOWNLOAD_URL_SECONDS`, 5 minutos "
            "por omisión) del CSV, con `Content-Disposition: attachment`, como la descarga "
            "de documentos (comparte su límite de 60 descargas por hora). La URL no se "
            "guarda ni va a los logs."
        ),
        responses={
            200: DocumentDownloadSerializer,
            409: _error("EXPORT_NOT_READY (pendiente, en proceso o fallida)"),
            410: _error("EXPORT_EXPIRED"),
            429: _error("RATE_LIMITED"),
            503: _error("SERVICE_UNAVAILABLE (almacenamiento no disponible)"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def get(self, request: Request, job_id: Any) -> Response:
        job = self.get_job(job_id)
        link = export_jobs.export_download(job, requested_by=f"user:{self.actor.pk}")
        return no_store(Response(DocumentDownloadSerializer(link).data))
