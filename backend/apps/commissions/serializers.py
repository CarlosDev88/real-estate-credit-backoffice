from typing import Any

from django.db.models import QuerySet
from rest_framework import serializers

from apps.banking.models import BankProduct
from apps.banking.serializers import RuleProductRefSerializer
from apps.commissions.models import (
    BeneficiaryRole,
    CommissionPlan,
    CommissionSettlement,
    CommissionShare,
    SettlementStatus,
    ShareStatus,
)
from apps.crm.serializers import UserRefSerializer
from config.serializers import ChoiceLabelField, StrictSerializer


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


# --- Liquidaciones (vista del administrador) --------------------------------------------


class CommissionApplicationRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()


class CommissionShareSerializer(serializers.ModelSerializer):
    beneficiary = UserRefSerializer(source="beneficiary_user")
    beneficiary_role_label = ChoiceLabelField(BeneficiaryRole, source="beneficiary_role")
    status_label = ChoiceLabelField(ShareStatus, source="status")
    paid_by = UserRefSerializer(allow_null=True)

    class Meta:
        model = CommissionShare
        fields = [
            "id",
            "beneficiary",
            "beneficiary_role",
            "beneficiary_role_label",
            "share_pct",
            "amount_cop",
            "status",
            "status_label",
            "paid_at",
            "paid_by",
            "payment_reference",
        ]
        read_only_fields = fields


class CommissionSettlementSerializer(serializers.ModelSerializer):
    application = CommissionApplicationRefSerializer()
    lead_origin_label = serializers.CharField(
        help_text="Etiqueta del origen (catálogo `lead_origin`)."
    )
    status_label = ChoiceLabelField(SettlementStatus, source="status")
    voided_by = UserRefSerializer(allow_null=True)
    shares = CommissionShareSerializer(many=True)

    class Meta:
        model = CommissionSettlement
        fields = [
            "id",
            "application",
            "filing_response_id",
            "plan_id",
            "lead_origin_code",
            "lead_origin_label",
            "base_amount_cop",
            "rate_pct",
            "total_amount_cop",
            "status",
            "status_label",
            "needs_review",
            "voided_at",
            "voided_by",
            "void_reason",
            "shares",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SettlementVoidSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=255)
