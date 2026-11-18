"""Respuestas del dashboard. Son de solo lectura y leen los diccionarios de
``services``; las etiquetas salen de las ``TextChoices`` (``ChoiceLabelField``)."""

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalogs.workflow import ApplicationStatus
from apps.reporting.filters import ReportFilterSerializer
from apps.reporting.models import ExportJobStatus, ReportExportJob, ReportType
from apps.reporting.services import FunnelGroupBy, FunnelStage
from config.serializers import ChoiceLabelField, StrictSerializer


def _money_field(help_text: str) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=20, decimal_places=2, help_text=help_text)


def _ratio_field(help_text: str) -> serializers.DecimalField:
    return serializers.DecimalField(
        max_digits=5, decimal_places=4, allow_null=True, help_text=help_text
    )


class PeriodSerializer(serializers.Serializer):
    date_from = serializers.DateField(help_text="Primer día del rango efectivo (incluido).")
    date_to = serializers.DateField(help_text="Último día del rango efectivo (incluido).")


class StatusCountSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ApplicationStatus.choices)
    status_label = ChoiceLabelField(ApplicationStatus, source="status")
    count = serializers.IntegerField()


class TaskCountsSerializer(serializers.Serializer):
    overdue = serializers.IntegerField(help_text="Tareas `PENDING` con fecha anterior a hoy.")
    due_today = serializers.IntegerField(help_text="Tareas `PENDING` con fecha de hoy.")


class AmountsSerializer(serializers.Serializer):
    requested_total = _money_field("Suma del monto solicitado en la financiación, en COP.")
    approved_total = _money_field(
        "Suma del monto de la última aprobación del banco de cada solicitud, en COP."
    )
    disbursed_total = _money_field(
        "Suma del monto del último desembolso registrado de cada solicitud, en COP."
    )


class DashboardSummarySerializer(serializers.Serializer):
    period = PeriodSerializer()
    clients_created = serializers.IntegerField(
        help_text="Clientes creados en el periodo dentro del alcance de CRM del usuario."
    )
    applications_created = serializers.IntegerField(
        help_text="Solicitudes creadas en el periodo, con el alcance y los filtros."
    )
    snapshot = StatusCountSerializer(
        many=True,
        help_text="Solicitudes que hoy están en cada estado (sin el filtro de fechas). "
        "Trae todos los estados, incluso en 0.",
    )
    tasks = TaskCountsSerializer()
    amounts = AmountsSerializer(
        required=False,
        help_text="Solo administrador y asesor, sobre las solicitudes creadas en el "
        "periodo. El broker no recibe este campo.",
    )


class FunnelStageSerializer(serializers.Serializer):
    code = serializers.ChoiceField(choices=FunnelStage.choices)
    # `label` choca con el atributo `Field.label` de los stubs de DRF.
    label = ChoiceLabelField(FunnelStage, source="code")  # type: ignore[assignment]
    count = serializers.IntegerField()
    conversion = _ratio_field("`count / CREATED` con 4 decimales; `null` si `CREATED` es 0.")
    step_conversion = _ratio_field(
        "`count` contra la etapa anterior; `null` en `CREATED` o si la anterior es 0."
    )


class DashboardFunnelSerializer(serializers.Serializer):
    period = PeriodSerializer()
    stages = FunnelStageSerializer(many=True)


class AdvisorWorkloadSerializer(serializers.Serializer):
    advisor_id = serializers.UUIDField()
    advisor_name = serializers.CharField()
    open_applications = serializers.IntegerField(help_text="Solicitudes no terminales.")
    overdue_tasks = serializers.IntegerField()
    due_today_tasks = serializers.IntegerField()
    waiting_buyer = serializers.IntegerField(
        help_text="Solicitudes esperando datos o documentos del comprador."
    )
    ready_to_file = serializers.IntegerField(help_text="Solicitudes listas para radicar.")


class DashboardWorkloadSerializer(serializers.Serializer):
    advisors = AdvisorWorkloadSerializer(many=True)


class BankResultSerializer(serializers.Serializer):
    bank_id = serializers.UUIDField()
    bank_name = serializers.CharField()
    filings = serializers.IntegerField(help_text="Radicaciones con `filed_at` en el periodo.")
    returned = serializers.IntegerField(help_text="Radicaciones que el banco devolvió.")
    approved = serializers.IntegerField()
    rejected = serializers.IntegerField()
    disbursed = serializers.IntegerField()
    avg_days_to_response = serializers.DecimalField(
        max_digits=7,
        decimal_places=1,
        allow_null=True,
        help_text="Promedio de días entre `filed_at` y la primera respuesta, con 1 decimal; "
        "`null` si ninguna radicación tiene respuesta.",
    )


class DashboardBankResultsSerializer(serializers.Serializer):
    period = PeriodSerializer()
    banks = BankResultSerializer(many=True)


# --- Reportes -------------------------------------------------------------------------


class ReportFunnelGroupSerializer(serializers.Serializer):
    key = serializers.CharField(
        allow_null=True,
        help_text="Id del asesor o del banco, o código de la finalidad. `null`: sin banco.",
    )
    label = serializers.CharField()  # type: ignore[assignment]
    stages = FunnelStageSerializer(many=True)


class ReportFunnelSerializer(serializers.Serializer):
    period = PeriodSerializer()
    group_by = serializers.ChoiceField(choices=FunnelGroupBy.choices, allow_null=True)
    stages = FunnelStageSerializer(many=True, help_text="Embudo de todo el resultado.")
    groups = ReportFunnelGroupSerializer(
        many=True, help_text="Un embudo por grupo, ordenados por etiqueta. Vacío sin `group_by`."
    )


class ReportApplicationSerializer(serializers.Serializer):
    """Fila del reporte de solicitudes. Lee ``exports.application_row``; el CSV tiene las
    mismas columnas (``exports.COLUMNS``)."""

    code = serializers.CharField()
    created_at = serializers.DateTimeField()
    status = serializers.ChoiceField(choices=ApplicationStatus.choices)
    status_label = ChoiceLabelField(ApplicationStatus, source="status")
    purpose = serializers.CharField(help_text="Etiqueta de la finalidad (`loan_purpose`).")
    advisor_name = serializers.CharField()
    client_name = serializers.CharField(help_text="Titular de la oportunidad.")
    client_document_masked = serializers.CharField(
        help_text="Documento del titular con solo los últimos 4 caracteres: `******5908`."
    )
    bank_name = serializers.CharField(allow_null=True)
    project_name = serializers.CharField(
        allow_null=True, help_text="Proyecto del inmueble o, si no tiene, el de la oportunidad."
    )
    requested_amount = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        allow_null=True,
        help_text="Monto solicitado en COP; `null` sin financiación registrada.",
    )
    last_status_change_at = serializers.DateTimeField()
    filings_count = serializers.IntegerField()


# --- Exportación asíncrona --------------------------------------------------------------


class ExportJobRequestSerializer(StrictSerializer, ReportFilterSerializer):
    """Cuerpo de ``POST /reports/applications/export-jobs``: los filtros del reporte, todos
    opcionales. Un campo desconocido responde ``400``."""


class ExportFiltersSerializer(serializers.Serializer):
    """Filtros validados que guarda la exportación, con el rango efectivo."""

    date_from = serializers.DateField()
    date_to = serializers.DateField()
    advisor_id = serializers.UUIDField(allow_null=True)
    partner_id = serializers.UUIDField(allow_null=True)
    project_id = serializers.UUIDField(allow_null=True)
    bank_id = serializers.UUIDField(allow_null=True)
    purpose_code = serializers.CharField(allow_null=True)
    status = serializers.ListField(child=serializers.ChoiceField(choices=ApplicationStatus.choices))


class RequestedByRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class ReportExportJobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    report_type = serializers.ChoiceField(choices=ReportType.choices)
    report_type_label = ChoiceLabelField(ReportType, source="report_type")
    format = serializers.SerializerMethodField(help_text="Siempre `csv` en el MVP.")
    status = serializers.ChoiceField(
        choices=ExportJobStatus.choices,
        source="effective_status",
        help_text="`PENDING` → `RUNNING` → `COMPLETED` o `FAILED`; un `COMPLETED` pasa a "
        "`EXPIRED` a las 24 horas.",
    )
    status_label = ChoiceLabelField(ExportJobStatus, source="effective_status")
    filters = ExportFiltersSerializer()
    row_count = serializers.IntegerField(allow_null=True)
    error_code = serializers.CharField(
        allow_null=True,
        help_text="Solo en `FAILED`: `PERMISSION_REVOKED`, `EXPORT_TOO_LARGE`, "
        "`STORAGE_UNAVAILABLE` o `INVALID_FILTERS`.",
    )
    requested_by = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)

    def get_format(self, obj: ReportExportJob) -> str:
        return "csv"

    @extend_schema_field(RequestedByRefSerializer)
    def get_requested_by(self, obj: ReportExportJob) -> dict[str, Any]:
        user = obj.requested_by
        return {"id": user.pk, "name": user.get_full_name()}
