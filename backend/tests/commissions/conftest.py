"""Fixtures de comisiones (paso 16).

Reexporta los de ``tests/applications`` (usuarios, clientes y solicitudes), que pytest no
hereda fuera de esa carpeta, y agrega la fábrica de planes.
"""

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.applications.models import CreditApplication
from apps.banking.models import BankProduct
from apps.commissions.models import CommissionPlan, CommissionSettlement
from apps.filings.models import Filing, FilingResponse
from apps.identity.models import User
from tests.applications.conftest import (
    admin_client,
    admin_user,
    advisor_client,
    advisor_user,
    application,
    broker_client,
    broker_user,
    buyer,
    catalog_item,
    make_application,
    make_client,
    make_opportunity,
    opportunity,
    other_advisor,
    other_advisor_client,
    partner,
    partner_client,
    primary,
    seeded_product,
)
from tests.applications.filings.conftest import make_filing

__all__ = [
    "admin_client",
    "admin_user",
    "advisor_client",
    "advisor_user",
    "application",
    "broker_client",
    "broker_user",
    "buyer",
    "make_application",
    "make_client",
    "make_filing",
    "make_opportunity",
    "opportunity",
    "other_advisor",
    "other_advisor_client",
    "partner",
    "partner_client",
    "primary",
]

PLANS_URL = "/api/v1/commission-plans"

PlanFactory = Callable[..., CommissionPlan]
DisbursementFactory = Callable[..., FilingResponse]
SettlementFactory = Callable[..., CommissionSettlement]


def plan_url(plan: CommissionPlan | str, suffix: str = "") -> str:
    plan_id = plan.pk if isinstance(plan, CommissionPlan) else plan
    return f"{PLANS_URL}/{plan_id}{suffix}"


@pytest.fixture
def product(db: Any) -> BankProduct:
    return seeded_product()


@pytest.fixture
def make_plan(admin_user: User, product: BankProduct) -> PlanFactory:
    """Plan creado directamente en la base: 1 %, asesor 70 / broker 30, desde 2026-01-01."""

    def _make_plan(**extra: Any) -> CommissionPlan:
        extra.setdefault("bank_product", product)
        extra.setdefault("rate_pct", Decimal("1.0000"))
        extra.setdefault("advisor_share_pct", Decimal("70.0000"))
        extra.setdefault("broker_share_pct", Decimal("30.0000"))
        extra.setdefault("valid_from", date(2026, 1, 1))
        extra.setdefault("created_by", admin_user)
        return CommissionPlan.objects.create(**extra)

    return _make_plan


@pytest.fixture
def make_disbursement(
    advisor_user: User, make_filing: Callable[..., Filing]
) -> DisbursementFactory:
    """Respuesta ``DISBURSED`` creada directamente en la base (sin la señal)."""

    def _make(
        application: CreditApplication,
        amount: int = 294_000_000,
        received_at: datetime | None = None,
        **extra: Any,
    ) -> FilingResponse:
        filing = extra.pop("filing", None) or make_filing(application)
        return FilingResponse.objects.create(
            filing=filing,
            response_type_item=catalog_item("filing_response_type", "DISBURSED"),
            received_at=received_at or timezone.now(),
            disbursed_amount_cop=amount,
            recorded_by=advisor_user,
            **extra,
        )

    return _make


@pytest.fixture
def make_settlement(make_disbursement: DisbursementFactory) -> SettlementFactory:
    """Liquidación vigente creada directamente en la base, sin partes."""

    def _make(
        plan: CommissionPlan, application: CreditApplication, **extra: Any
    ) -> CommissionSettlement:
        response = extra.pop("filing_response", None) or make_disbursement(application)
        extra.setdefault("lead_origin_code", "DIRECT")
        extra.setdefault("base_amount_cop", response.disbursed_amount_cop)
        extra.setdefault("rate_pct", plan.rate_pct)
        extra.setdefault("total_amount_cop", 2_940_000)
        return CommissionSettlement.objects.create(
            application=application, filing_response=response, plan=plan, **extra
        )

    return _make
