from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.applications.models import CreditApplication
from apps.applications.serializers import NamedRefSerializer
from apps.catalogs.workflow import ApplicationStatus
from apps.workday.rules import NEXT_ACTIONS, AttentionSegment, NextAction, attention_field


class WorkdayBankSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    short_name = serializers.CharField()


class AttentionRefSerializer(serializers.Serializer):
    code = serializers.ChoiceField(choices=AttentionSegment.choices)
    # `label` choca con el atributo `Field.label` de los stubs de DRF.
    label = serializers.CharField()  # type: ignore[assignment]


class WorkdayApplicationSerializer(serializers.ModelSerializer):
    """Fila de "Mi día". Lee las anotaciones de ``services.workday_applications``."""

    client_display_name = serializers.CharField(source="opportunity.client.full_name")
    bank = WorkdayBankSerializer(source="bank_product.bank", allow_null=True, default=None)
    bank_product = NamedRefSerializer(allow_null=True)
    status = serializers.ChoiceField(choices=ApplicationStatus.choices)
    status_label = serializers.CharField(source="get_status_display")
    next_action = serializers.SerializerMethodField()
    next_action_label = serializers.SerializerMethodField()
    days_in_stage = serializers.IntegerField(
        help_text="Días enteros desde el inicio de la etapa, según la fecha de Bogotá."
    )
    attention = serializers.SerializerMethodField(
        help_text="Segmentos de atención que cumple la solicitud (no son excluyentes)."
    )
    pending_tasks_count = serializers.IntegerField()

    class Meta:
        model = CreditApplication
        fields = [
            "id",
            "code",
            "client_display_name",
            "bank",
            "bank_product",
            "status",
            "status_label",
            "next_action",
            "next_action_label",
            "days_in_stage",
            "attention",
            "pending_tasks_count",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ChoiceField(choices=NextAction.choices))
    def get_next_action(self, obj: CreditApplication) -> str:
        return str(NEXT_ACTIONS[obj.status])

    def get_next_action_label(self, obj: CreditApplication) -> str:
        return str(NEXT_ACTIONS[obj.status].label)

    @extend_schema_field(AttentionRefSerializer(many=True))
    def get_attention(self, obj: CreditApplication) -> list[dict[str, Any]]:
        return [
            {"code": segment.value, "label": segment.label}
            for segment in AttentionSegment
            if getattr(obj, attention_field(segment.value))
        ]


class WorkdaySegmentSerializer(serializers.Serializer):
    code = serializers.ChoiceField(choices=AttentionSegment.choices)
    label = serializers.CharField()  # type: ignore[assignment]
    count = serializers.IntegerField()


class WorkdaySummarySerializer(serializers.Serializer):
    total = serializers.IntegerField(help_text="Solicitudes con los filtros, sin `attention`.")
    segments = WorkdaySegmentSerializer(many=True)
