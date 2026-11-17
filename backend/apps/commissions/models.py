"""Comisiones (paso 16): planes por producto, liquidación por solicitud y partes por
beneficiario (``specs/TAREA-comisiones.md``).

Dinero COP en ``BIGINT`` y porcentajes en ``NUMERIC(8,4)``. Desvíos del SQL:
``commission_plans.version``, para el ``If-Match`` de ``PATCH /commission-plans/{id}``
(API §6), y los textos opcionales son texto vacío en lugar de nulos.
"""

import uuid
from decimal import Decimal

from django.db import models
from django.db.models import F, Q

ZERO = Decimal("0")
HUNDRED = Decimal("100")


class SettlementStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Vigente"
    VOIDED = "VOIDED", "Anulada"


class ShareStatus(models.TextChoices):
    PENDING = "PENDING", "Pendiente de pago"
    PAID = "PAID", "Pagada"
    VOIDED = "VOIDED", "Anulada"


class BeneficiaryRole(models.TextChoices):
    ADVISOR = "ADVISOR", "Asesor"
    INDEPENDENT_BROKER = "INDEPENDENT_BROKER", "Broker independiente"


def _pct_field() -> models.DecimalField:
    return models.DecimalField(max_digits=8, decimal_places=4)


class CommissionPlan(models.Model):
    """Tasa y reparto de un producto bancario, con vigencia ``[valid_from, valid_until)``."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    bank_product = models.ForeignKey(
        "banking.BankProduct", on_delete=models.RESTRICT, related_name="commission_plans"
    )
    rate_pct = _pct_field()
    advisor_share_pct = _pct_field()
    broker_share_pct = _pct_field()
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        "identity.User", on_delete=models.RESTRICT, related_name="commission_plans_created"
    )
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "commission_plans"
        ordering = ["bank_product", "-valid_from"]
        constraints = [
            models.CheckConstraint(
                condition=Q(rate_pct__gt=ZERO) & Q(rate_pct__lte=HUNDRED),
                name="ck_commission_plans_rate",
            ),
            models.CheckConstraint(
                condition=Q(advisor_share_pct=HUNDRED - F("broker_share_pct")),
                name="ck_commission_plans_shares_sum",
            ),
            models.CheckConstraint(
                condition=Q(advisor_share_pct__gt=F("broker_share_pct"))
                & Q(broker_share_pct__gte=ZERO),
                name="ck_commission_plans_advisor_major",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gt=F("valid_from")),
                name="ck_commission_plans_validity",
            ),
        ]
        indexes = [
            models.Index(
                fields=["bank_product", "-valid_from"], name="ix_commission_plans_product"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.bank_product_id} {self.rate_pct}% desde {self.valid_from}"


class CommissionSettlement(models.Model):
    """Liquidación de una solicitud desembolsada. Base, tasa y origen son instantáneas."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    application = models.ForeignKey(
        "applications.CreditApplication",
        on_delete=models.RESTRICT,
        related_name="commission_settlements",
    )
    filing_response = models.OneToOneField(
        "filings.FilingResponse", on_delete=models.RESTRICT, related_name="commission_settlement"
    )
    plan = models.ForeignKey(CommissionPlan, on_delete=models.RESTRICT, related_name="settlements")
    lead_origin_code = models.CharField(max_length=50)
    base_amount_cop = models.BigIntegerField()
    rate_pct = _pct_field()
    total_amount_cop = models.BigIntegerField()
    status = models.CharField(
        max_length=20, choices=SettlementStatus.choices, default=SettlementStatus.ACTIVE
    )
    needs_review = models.BooleanField(default=False)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        "identity.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "commission_settlements"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(base_amount_cop__gt=0), name="ck_commission_settlements_base"
            ),
            models.CheckConstraint(
                condition=Q(rate_pct__gt=ZERO) & Q(rate_pct__lte=HUNDRED),
                name="ck_commission_settlements_rate",
            ),
            models.CheckConstraint(
                condition=Q(total_amount_cop__gte=0), name="ck_commission_settlements_total"
            ),
            models.CheckConstraint(
                condition=Q(status__in=SettlementStatus.values),
                name="ck_commission_settlements_status",
            ),
            models.CheckConstraint(
                condition=~Q(status=SettlementStatus.VOIDED)
                | (Q(voided_at__isnull=False) & ~Q(void_reason="")),
                name="ck_commission_settlements_void",
            ),
            models.UniqueConstraint(
                fields=["application"],
                condition=Q(status=SettlementStatus.ACTIVE),
                name="uq_commission_settlements_active",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="ix_commission_settl_status"),
        ]

    def __str__(self) -> str:
        return f"{self.application_id} {self.status}"


class CommissionShare(models.Model):
    """Parte de un beneficiario (asesor o broker) y su pago."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    settlement = models.ForeignKey(
        CommissionSettlement, on_delete=models.CASCADE, related_name="shares"
    )
    beneficiary_user = models.ForeignKey(
        "identity.User", on_delete=models.RESTRICT, related_name="commission_shares"
    )
    beneficiary_role = models.CharField(max_length=40, choices=BeneficiaryRole.choices)
    share_pct = _pct_field()
    amount_cop = models.BigIntegerField()
    status = models.CharField(
        max_length=20, choices=ShareStatus.choices, default=ShareStatus.PENDING
    )
    paid_at = models.DateField(null=True, blank=True)
    paid_by = models.ForeignKey(
        "identity.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    payment_reference = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "commission_shares"
        ordering = ["settlement", "beneficiary_role"]
        constraints = [
            models.CheckConstraint(
                condition=Q(beneficiary_role__in=BeneficiaryRole.values),
                name="ck_commission_shares_role",
            ),
            models.CheckConstraint(
                condition=Q(share_pct__gt=ZERO) & Q(share_pct__lte=HUNDRED),
                name="ck_commission_shares_pct",
            ),
            models.CheckConstraint(
                condition=Q(amount_cop__gte=0), name="ck_commission_shares_amount"
            ),
            models.CheckConstraint(
                condition=Q(status__in=ShareStatus.values), name="ck_commission_shares_status"
            ),
            models.CheckConstraint(
                condition=~Q(status=ShareStatus.PAID) | Q(paid_at__isnull=False),
                name="ck_commission_shares_paid",
            ),
            models.UniqueConstraint(
                fields=["settlement", "beneficiary_role"], name="uq_commission_shares_role"
            ),
        ]
        indexes = [
            models.Index(
                fields=["beneficiary_user", "status", "-created_at"],
                name="ix_commission_shares_benef",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.beneficiary_role} {self.amount_cop}"
