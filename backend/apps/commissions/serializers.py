from typing import Any

from django.db.models import QuerySet
from rest_framework import serializers

from apps.banking.models import BankProduct
from apps.banking.serializers import RuleProductRefSerializer
from apps.commissions.models import CommissionPlan
from apps.crm.serializers import UserRefSerializer
from config.serializers import StrictSerializer


def pct_field(**kwargs: Any) -> serializers.DecimalField:
    """Porcentaje ``NUMERIC(8,4)``: hasta 4 decimales."""
    return serializers.DecimalField(max_digits=8, decimal_places=4, **kwargs)


class CommissionPlanSerializer(serializers.ModelSerializer):
    bank_product = RuleProductRefSerializer()
    created_by = UserRefSerializer()
    in_use = serializers.BooleanField(
        help_text="Alguna liquidación lo usó: ya no se edita, solo se cierra."
    )

    class Meta:
        model = CommissionPlan
        fields = [
            "id",
            "bank_product",
            "rate_pct",
            "advisor_share_pct",
            "broker_share_pct",
            "valid_from",
            "valid_until",
            "notes",
            "in_use",
            "version",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


def _products() -> QuerySet[BankProduct]:
    return BankProduct.objects.all()


class CommissionPlanCreateSerializer(StrictSerializer):
    bank_product_id = serializers.PrimaryKeyRelatedField(
        queryset=_products(), source="bank_product"
    )
    rate_pct = pct_field(help_text="Porcentaje sobre el monto desembolsado.")
    advisor_share_pct = pct_field()
    broker_share_pct = pct_field()
    valid_from = serializers.DateField()
    valid_until = serializers.DateField(
        required=False, allow_null=True, default=None, help_text="Exclusivo. Nulo: sin fin."
    )
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class CommissionPlanUpdateSerializer(StrictSerializer):
    rate_pct = pct_field(required=False)
    advisor_share_pct = pct_field(required=False)
    broker_share_pct = pct_field(required=False)
    valid_from = serializers.DateField(required=False)
    valid_until = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)


class CommissionPlanCloseSerializer(StrictSerializer):
    valid_until = serializers.DateField(help_text="Fin de vigencia (exclusivo).")
