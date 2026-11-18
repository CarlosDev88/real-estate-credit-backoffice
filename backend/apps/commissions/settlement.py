"""Liquidación de comisiones (Parte 2): ``settle_application`` y la anulación.

- **Solo con la solicitud en `DISBURSED`** (``409 APPLICATION_NOT_DISBURSED``).
- **Base:** ``disbursed_amount_cop`` de la respuesta de desembolso. **Fecha:** su
  ``received_at``, como fecha de Bogotá. **Plan:** el vigente ese día para el producto de
  la radicación (``422 COMMISSION_PLAN_NOT_FOUND``).
- **Cálculo** con ``Decimal`` y ``ROUND_HALF_UP`` al peso: ``total = base × tasa / 100``.
  Con broker, ``broker = total × porción / 100`` y ``asesor = total − broker``: la suma
  siempre cuadra.
- **Reparto:** con origen `BROKER`, asesor y broker (``opportunity.origin_user``) según
  el plan; con otro origen, el 100 % es del asesor asignado. `BROKER` sin usuario de
  origen: 100 % al asesor y ``needs_review``. Un plan con porción de broker 0 tampoco
  crea la parte del broker.
- **Idempotente:** con una liquidación `ACTIVE`, la devuelve sin crear otra. La fila de
  la solicitud se bloquea, y el índice único parcial es la última barrera.
- **Corrección del desembolso** (respuesta con ``corrects_response``): si la corregida
  tenía una liquidación `ACTIVE` sin pagos, se anula y se crea otra con el monto nuevo,
  en la misma transacción; con alguna parte pagada, solo se marca ``needs_review``.
"""

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import F, OuterRef, Prefetch, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.applications.models import CreditApplication
from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import ApplicationStatus
from apps.commissions.exceptions import (
    ApplicationNotDisbursed,
    CommissionPlanNotFound,
    SettlementHasPayments,
)
from apps.commissions.models import (
    HUNDRED,
    ZERO,
    BeneficiaryRole,
    CommissionPlan,
    CommissionSettlement,
    CommissionShare,
    SettlementStatus,
    ShareStatus,
)
from apps.commissions.plans import valid_on
from apps.commissions.signals import commission_settled, commission_settlement_voided
from apps.filings.models import FilingResponse
from apps.identity.models import User

DISBURSED_RESPONSE = "DISBURSED"
BROKER_ORIGIN = "BROKER"
CORRECTION_REASON = "Corrección del desembolso"
LEAD_ORIGIN_CATALOG = "lead_origin"


@dataclass(frozen=True)
class SettlementResult:
    settlement: CommissionSettlement
    created: bool


def round_cop(value: Decimal) -> int:
    """Al peso, con ``ROUND_HALF_UP`` (0,5 sube)."""
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def split(total: int, broker_share_pct: Decimal) -> tuple[int, int]:
    """``(asesor, broker)``: el broker se redondea y el asesor se lleva el resto."""
    broker = round_cop(Decimal(total) * broker_share_pct / HUNDRED)
    return total - broker, broker


def disbursement_response(application: CreditApplication) -> FilingResponse | None:
    """La última respuesta `DISBURSED` de la solicitud que nadie corrigió."""
    return (
        FilingResponse.objects.filter(
            filing__application=application,
            response_type_item__code=DISBURSED_RESPONSE,
            correction__isnull=True,
        )
        .select_related("filing")
        .order_by("-received_at", "-created_at")
        .first()
    )


def plan_for(response: FilingResponse) -> CommissionPlan:
    plan = (
        CommissionPlan.objects.filter(bank_product_id=response.filing.bank_product_id)
        .filter(valid_on(timezone.localtime(response.received_at).date()))
        .first()
    )
    if plan is None:
        raise CommissionPlanNotFound()
    return plan


def active_settlement(application_id: uuid.UUID) -> QuerySet[CommissionSettlement]:
    return CommissionSettlement.objects.filter(
        application_id=application_id, status=SettlementStatus.ACTIVE
    )


def _create(application: CreditApplication, response: FilingResponse) -> CommissionSettlement:
    plan = plan_for(response)
    base = response.disbursed_amount_cop
    if not base:
        raise ApplicationNotDisbursed(detail="La respuesta de desembolso no tiene monto.")
    opportunity = application.opportunity
    origin = opportunity.origin_item.code
    total = round_cop(Decimal(base) * plan.rate_pct / HUNDRED)
    broker = opportunity.origin_user if origin == BROKER_ORIGIN else None
    settlement = CommissionSettlement.objects.create(
        application=application,
        filing_response=response,
        plan=plan,
        lead_origin_code=origin,
        base_amount_cop=base,
        rate_pct=plan.rate_pct,
        total_amount_cop=total,
        needs_review=origin == BROKER_ORIGIN and broker is None,
    )
    shares = []
    if broker is not None and plan.broker_share_pct > ZERO:
        advisor_amount, broker_amount = split(total, plan.broker_share_pct)
        shares.append(
            CommissionShare(
                settlement=settlement,
                beneficiary_user=broker,
                beneficiary_role=BeneficiaryRole.INDEPENDENT_BROKER,
                share_pct=plan.broker_share_pct,
                amount_cop=broker_amount,
            )
        )
        advisor_pct = plan.advisor_share_pct
    else:
        advisor_amount, advisor_pct = total, HUNDRED
    shares.append(
        CommissionShare(
            settlement=settlement,
            beneficiary_user=application.assigned_advisor,
            beneficiary_role=BeneficiaryRole.ADVISOR,
            share_pct=advisor_pct,
            amount_cop=advisor_amount,
        )
    )
    CommissionShare.objects.bulk_create(shares)
    return settlement


def _void(settlement: CommissionSettlement, *, actor: User | None, reason: str) -> None:
    settlement.status = SettlementStatus.VOIDED
    settlement.voided_at = timezone.now()
    settlement.voided_by = actor
    settlement.void_reason = reason
    settlement.save(update_fields=["status", "voided_at", "voided_by", "void_reason", "updated_at"])
    settlement.shares.update(status=ShareStatus.VOIDED, updated_at=timezone.now())
    transaction.on_commit(
        lambda: commission_settlement_voided.send(
            sender=CommissionSettlement, settlement=settlement, reason=reason, actor=actor
        )
    )


def _has_payments(settlement: CommissionSettlement) -> bool:
    return settlement.shares.filter(status=ShareStatus.PAID).exists()


def settle_application(
    application_id: uuid.UUID,
    *,
    actor: User | None = None,
    response: FilingResponse | None = None,
) -> SettlementResult:
    """Liquida la solicitud con ``response`` (o con su último desembolso vigente)."""
    with transaction.atomic():
        # Bloquea la solicitud: dos liquidaciones simultáneas se serializan aquí.
        application = CreditApplication.objects.select_for_update().get(pk=application_id)
        corrected = response.corrects_response if response is not None else None
        if corrected is not None:
            previous = (
                active_settlement(application.pk)
                .select_for_update()
                .filter(filing_response=corrected)
                .first()
            )
            if previous is not None:
                if _has_payments(previous):
                    previous.needs_review = True
                    previous.save(update_fields=["needs_review", "updated_at"])
                    return SettlementResult(previous, created=False)
                _void(previous, actor=actor, reason=CORRECTION_REASON)
        existing = active_settlement(application.pk).first()
        if existing is not None:
            return SettlementResult(existing, created=False)
        if application.status != ApplicationStatus.DISBURSED:
            raise ApplicationNotDisbursed()
        response = response or disbursement_response(application)
        if response is None:
            raise ApplicationNotDisbursed(
                detail="La solicitud no tiene una respuesta de desembolso."
            )
        settlement = _create(application, response)
        transaction.on_commit(
            lambda: commission_settled.send(
                sender=CommissionSettlement, settlement=settlement, actor=actor
            )
        )
    return SettlementResult(settlement, created=True)


def void_settlement(
    settlement: CommissionSettlement, *, actor: User, reason: str
) -> CommissionSettlement:
    """Anula una liquidación sin pagos (``409 COMMISSION_SETTLEMENT_HAS_PAYMENTS``). Anular
    una ya anulada la devuelve igual."""
    with transaction.atomic():
        locked = CommissionSettlement.objects.select_for_update().get(pk=settlement.pk)
        if locked.status == SettlementStatus.VOIDED:
            return locked
        if _has_payments(locked):
            raise SettlementHasPayments()
        _void(locked, actor=actor, reason=reason)
    return locked


def settlements_queryset() -> QuerySet[CommissionSettlement]:
    """Liquidaciones con la etiqueta del origen y sus partes: sin consultas por fila."""
    label = CatalogItem.objects.filter(
        catalog__code=LEAD_ORIGIN_CATALOG, code=OuterRef("lead_origin_code")
    ).values("label")[:1]
    shares = CommissionShare.objects.select_related("beneficiary_user", "paid_by")
    return (
        CommissionSettlement.objects.select_related("application", "voided_by", "filing_response")
        .prefetch_related(Prefetch("shares", queryset=shares))
        .annotate(lead_origin_label=Coalesce(Subquery(label), F("lead_origin_code")))
    )
