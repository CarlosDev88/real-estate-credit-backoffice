"""Comisiones de demo (``seed_demo_data``).

- Un plan vigente por cada producto bancario: 1 %, asesor 70 / broker 30, desde el 1 de
  enero de 2026. Se crean antes de los casos, así que un desembolso de la demo se liquida
  solo por la señal.
- Al final, liquida las solicitudes de demo en `DISBURSED` que aún no tengan liquidación.

Pasa por los servicios. La idempotencia es la del comando (si ya hay demo, no corre) y,
además, aquí no se repite un plan ni una liquidación.
"""

from datetime import date
from decimal import Decimal

from apps.applications.models import CreditApplication
from apps.banking.models import BankProduct
from apps.catalogs.workflow import ApplicationStatus
from apps.commissions import plans
from apps.commissions.models import CommissionPlan, CommissionSettlement
from apps.commissions.settlement import settle_application
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
