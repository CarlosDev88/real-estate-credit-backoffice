"""Pagos y consultas de comisiones (Parte 3).

- **Pagar una parte:** solo una `PENDING` (``409 COMMISSION_SHARE_NOT_PAYABLE``); las de
  una liquidación anulada ya están `VOIDED`. ``paid_at`` no puede ser futura (fecha de
  Bogotá). Emite ``commission_share_paid`` al confirmar.
- **Liquidaciones** (administrador): filtros por estado, banco, asesor, broker, fecha de
  desembolso y ``needs_review``.
- **Mis comisiones:** solo las partes propias del usuario, sin datos de la liquidación
  completa (ni base, ni tasa, ni total, ni la otra parte).
"""

import uuid
from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.commissions.exceptions import ShareNotPayable
from apps.commissions.models import (
    BeneficiaryRole,
    CommissionSettlement,
    CommissionShare,
    ShareStatus,
)
from apps.commissions.signals import commission_share_paid
from apps.identity.models import User


def pay_share(
    share: CommissionShare, *, actor: User, paid_at: date, reference: str
) -> CommissionShare:
    if paid_at > timezone.localdate():
        raise ValidationError({"paid_at": ["No puede ser una fecha futura."]})
    with transaction.atomic():
        locked = CommissionShare.objects.select_for_update().get(pk=share.pk)
        if locked.status != ShareStatus.PENDING:
            raise ShareNotPayable()
        locked.status = ShareStatus.PAID
        locked.paid_at = paid_at
        locked.paid_by = actor
        locked.payment_reference = reference
        locked.save(
            update_fields=["status", "paid_at", "paid_by", "payment_reference", "updated_at"]
        )
        transaction.on_commit(
            lambda: commission_share_paid.send(sender=CommissionShare, share=locked, actor=actor)
        )
    return locked


def disbursed_between(prefix: str, date_from: date | None, date_to: date | None) -> Q:
    """Condición sobre la fecha de desembolso (``received_at``), con días de Bogotá
    completos: ``date_to`` incluido."""
    condition = Q()
    if date_from is not None:
        start = timezone.make_aware(datetime.combine(date_from, time.min))
        condition &= Q(**{f"{prefix}received_at__gte": start})
    if date_to is not None:
        end = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), time.min))
        condition &= Q(**{f"{prefix}received_at__lt": end})
    return condition


def filter_settlements(
    settlements: QuerySet[CommissionSettlement],
    *,
    status: str | None = None,
    application_id: uuid.UUID | None = None,
    bank_id: uuid.UUID | None = None,
    advisor_id: uuid.UUID | None = None,
    broker_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    needs_review: bool | None = None,
) -> QuerySet[CommissionSettlement]:
    if status:
        settlements = settlements.filter(status=status)
    if application_id:
        settlements = settlements.filter(application_id=application_id)
    if bank_id:
        settlements = settlements.filter(plan__bank_product__bank_id=bank_id)
    for user_id, role in (
        (advisor_id, BeneficiaryRole.ADVISOR),
        (broker_id, BeneficiaryRole.INDEPENDENT_BROKER),
    ):
        if user_id:
            matching = CommissionShare.objects.filter(
                beneficiary_role=role, beneficiary_user_id=user_id
            )
            settlements = settlements.filter(pk__in=matching.values("settlement_id"))
    if needs_review is not None:
        settlements = settlements.filter(needs_review=needs_review)
    return settlements.filter(disbursed_between("filing_response__", date_from, date_to))


def my_shares(user: User) -> QuerySet[CommissionShare]:
    """Las partes propias, con lo que muestra la fila: sin consultas por fila."""
    return (
        CommissionShare.objects.filter(beneficiary_user=user)
        .select_related(
            "settlement__application__opportunity__client", "settlement__filing_response"
        )
        .order_by("-settlement__filing_response__received_at", "-created_at")
    )


def filter_my_shares(
    shares: QuerySet[CommissionShare],
    *,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> QuerySet[CommissionShare]:
    if status:
        shares = shares.filter(status=status)
    return shares.filter(disbursed_between("settlement__filing_response__", date_from, date_to))
