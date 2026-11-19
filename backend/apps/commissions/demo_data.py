"""Comisiones de demo (``seed_demo_data``).

- Un plan vigente por cada producto bancario: 1 %, asesor 70 / broker 30, desde el 1 de
  enero de 2026. Se crean antes de los casos, así que un desembolso de la demo se liquida
  solo por la señal.
- Al final, liquida las solicitudes de demo en `DISBURSED` que aún no tengan liquidación.

Pasa por los servicios. La idempotencia es la del comando (si ya hay demo, no corre) y,
además, aquí no se repite un plan ni una liquidación.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.applications.models import CreditApplication
from apps.banking.models import BankProduct
from apps.catalogs.workflow import ApplicationStatus
from apps.commissions import plans
from apps.commissions.models import (
    BeneficiaryRole,
    CommissionPlan,
    CommissionSettlement,
    CommissionShare,
)
from apps.commissions.payments import pay_share
from apps.commissions.settlement import active_settlement, settle_application, void_settlement
from apps.identity.models import User

DEMO_RATE = Decimal("1.0000")
DEMO_ADVISOR_SHARE = Decimal("70.0000")
DEMO_BROKER_SHARE = Decimal("30.0000")
DEMO_VALID_FROM = date(2026, 1, 1)


def seed_plans(admin: User) -> list[CommissionPlan]:
    created = []
    for product in BankProduct.objects.order_by("bank__name", "name"):
        if CommissionPlan.objects.filter(bank_product=product).exists():
            continue
        created.append(
            plans.create_plan(
                admin,
                {
                    "bank_product": product,
                    "rate_pct": DEMO_RATE,
                    "advisor_share_pct": DEMO_ADVISOR_SHARE,
                    "broker_share_pct": DEMO_BROKER_SHARE,
                    "valid_from": DEMO_VALID_FROM,
                    "notes": "Plan de demo",
                },
            )
        )
    return created


def settle_disbursed(
    admin: User, applications: list[CreditApplication]
) -> list[CommissionSettlement]:
    settled = []
    for application in applications:
        application.refresh_from_db(fields=["status"])
        if application.status != ApplicationStatus.DISBURSED:
            continue
        settled.append(settle_application(application.pk, actor=admin).settlement)
    return settled


# Estados de liquidación de la historia (TAREA-brechas-3-demo): pagada, con una parte
# pagada y revisión pendiente, anulada (y liquidada otra vez) y pendientes. Marca: la
# referencia de pago.
PAYMENT_REFERENCE_PREFIX = "DEMO-PAGO-"
VOID_REASON = "Se liquidó con el plan equivocado."


def commission_states_exist() -> bool:
    return CommissionShare.objects.filter(
        payment_reference__startswith=PAYMENT_REFERENCE_PREFIX
    ).exists()


def _paid_on(settlement: CommissionSettlement, days: int) -> date:
    disbursed = timezone.localtime(settlement.filing_response.received_at).date()
    return min(disbursed + timedelta(days=days), timezone.localdate())


def _pay(admin: User, share: CommissionShare, settlement: CommissionSettlement, days: int) -> None:
    pay_share(
        share,
        actor=admin,
        paid_at=_paid_on(settlement, days),
        reference=f"{PAYMENT_REFERENCE_PREFIX}{settlement.application.code}-{share.beneficiary_role}",
    )


def _correct_disbursement(admin: User, settlement: CommissionSettlement) -> None:
    """El administrador corrige el monto desembolsado: con una parte ya pagada, la
    liquidación queda con revisión pendiente (``needs_review``)."""
    # Import local: `filings` importa `applications`, que importa este módulo al sembrar.
    from apps.catalogs.models import CatalogItem
    from apps.filings import responses

    response = settlement.filing_response
    application = CreditApplication.objects.get(pk=settlement.application_id)
    responses.record_response(
        admin,
        response.filing,
        responses.ResponseInput(
            response_type=CatalogItem.objects.get(
                catalog__code=responses.RESPONSE_TYPE_CATALOG, code=responses.DISBURSED
            ),
            received_at=response.received_at + timedelta(days=2),
            disbursed_amount_cop=(response.disbursed_amount_cop or 0) + 1_500_000,
            internal_comment="El banco corrigió el monto desembolsado.",
            corrects_response_id=response.pk,
        ),
        expected_version=application.version,
    )


def seed_commission_states(admin: User, applications: list[CreditApplication]) -> int:
    """Lleva las liquidaciones de las desembolsadas (de la más antigua a la más reciente)
    a estados distintos. Devuelve cuántas tocó."""
    settlements: list[CommissionSettlement] = []
    for application in sorted(applications, key=lambda a: a.created_at):
        if application.status != ApplicationStatus.DISBURSED:
            continue
        settlement = (
            active_settlement(application.pk)
            .select_related("filing_response__filing", "application")
            .first()
        )
        if settlement is not None:
            settlements.append(settlement)
    brokered = [s for s in settlements if s.lead_origin_code == "BROKER"]
    direct = [s for s in settlements if s.lead_origin_code != "BROKER"]
    touched = 0
    if brokered:
        # Pagada: las dos partes.
        paid = brokered[0]
        for share in paid.shares.order_by("beneficiary_role"):
            _pay(admin, share, paid, days=20)
        touched += 1
    if len(brokered) > 1:
        # Una parte pagada y después una corrección del desembolso: revisión pendiente.
        review = brokered[1]
        _pay(
            admin,
            review.shares.get(beneficiary_role=BeneficiaryRole.INDEPENDENT_BROKER),
            review,
            10,
        )
        _correct_disbursement(admin, review)
        touched += 1
    if direct:
        # Directa (100 % del asesor) pagada.
        direct_paid = direct[0]
        _pay(admin, direct_paid.shares.get(), direct_paid, days=25)
        touched += 1
    if len(direct) > 1:
        # Anulada y liquidada otra vez (queda pendiente).
        voided = direct[1]
        void_settlement(voided, actor=admin, reason=VOID_REASON)
        again = settle_application(voided.application_id, actor=admin).settlement
        CommissionSettlement.objects.filter(pk=voided.pk).update(
            voided_at=voided.created_at + timedelta(days=3)
        )
        CommissionSettlement.objects.filter(pk=again.pk).update(
            created_at=voided.created_at + timedelta(days=3, hours=1)
        )
        again.shares.update(created_at=voided.created_at + timedelta(days=3, hours=1))
        touched += 1
    return touched
