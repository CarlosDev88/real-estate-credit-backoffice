"""Respuestas del dashboard. Son de solo lectura y leen los diccionarios de
``services``; las etiquetas salen de las ``TextChoices`` (``ChoiceLabelField``)."""

from rest_framework import serializers

from apps.catalogs.workflow import ApplicationStatus
from apps.reporting.services import FunnelStage
from config.serializers import ChoiceLabelField


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
