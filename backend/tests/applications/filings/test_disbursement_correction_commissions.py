"""Corrección del desembolso de punta a punta con comisiones (TAREA-brechas-2, parte 2,
punto 10): desembolso → liquidación → corrección → anulación y nueva liquidación; con una
parte pagada, solo `needs_review`.

Comisiones vive en otra rama hasta la fusión: sin la app instalada, estas pruebas se
saltan. Los modelos se importan al usarlos (``models()``), para que mypy no los busque.
"""

import importlib
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.apps import apps as django_apps
from rest_framework.test import APIClient

from apps.filings.models import Filing, FilingResponse
from apps.identity.models import User
from tests.applications.filings.test_filings_api import package, ready
from tests.applications.filings.test_responses_api import (
    APPROVED_BODY,
    DISBURSED_BODY,
    filed,
    recorded,
    respond,
)
from tests.applications.test_status_api import transition

__all__ = ["filed", "package", "ready"]

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        not django_apps.is_installed("apps.commissions"),
        reason="apps.commissions llega al fusionar con master.",
    ),
]


def models() -> Any:
    return importlib.import_module("apps.commissions.models")


@pytest.fixture
def plan(filed: Filing, admin_user: User) -> Any:
    return models().CommissionPlan.objects.create(
        bank_product=filed.bank_product,
        rate_pct=Decimal("1.0000"),
        advisor_share_pct=Decimal("70.0000"),
        broker_share_pct=Decimal("30.0000"),
        valid_from=date(2026, 1, 1),
        created_by=admin_user,
    )


@pytest.fixture
def disbursed(advisor_client: APIClient, filed: Filing, plan: Any) -> FilingResponse:
    application = filed.application
    recorded(advisor_client, filed, "APPROVED", **APPROVED_BODY)
    application.refresh_from_db()
    assert (
        transition(
            advisor_client, application, "LEGALIZATION", version=application.version
        ).status_code
        == 200
    )
    return recorded(advisor_client, filed, "DISBURSED", **DISBURSED_BODY)


def correct(admin_client: APIClient, filed: Filing, corrected: FilingResponse) -> FilingResponse:
    response = respond(
        admin_client,
        filed,
        "DISBURSED",
        disbursed_amount_cop=300_000_000,
        corrects_response_id=str(corrected.pk),
    )
    assert response.status_code == 201, response.content
    return FilingResponse.objects.get(pk=response.json()["id"])


def test_a_correction_voids_and_settles_again(
    admin_client: APIClient, filed: Filing, disbursed: FilingResponse
) -> None:
    m = models()
    CommissionSettlement, SettlementStatus = m.CommissionSettlement, m.SettlementStatus  # noqa: N806

    [original] = CommissionSettlement.objects.filter(application=filed.application)
    assert (original.status, original.filing_response_id) == (
        SettlementStatus.ACTIVE,
        disbursed.pk,
    )
    assert original.base_amount_cop == DISBURSED_BODY["disbursed_amount_cop"]

    fixed = correct(admin_client, filed, disbursed)

    original.refresh_from_db()
    assert original.status == SettlementStatus.VOIDED
    active = CommissionSettlement.objects.get(
        application=filed.application, status=SettlementStatus.ACTIVE
    )
    assert (active.filing_response_id, active.base_amount_cop) == (fixed.pk, 300_000_000)


def test_with_a_paid_share_the_correction_only_flags_review(
    admin_client: APIClient, admin_user: User, filed: Filing, disbursed: FilingResponse
) -> None:
    m = models()
    CommissionSettlement, SettlementStatus = m.CommissionSettlement, m.SettlementStatus  # noqa: N806
    ShareStatus = m.ShareStatus  # noqa: N806

    settlement = CommissionSettlement.objects.get(application=filed.application)
    settlement.shares.filter(pk=settlement.shares.first().pk).update(
        status=ShareStatus.PAID, paid_at=date(2026, 11, 1), paid_by=admin_user
    )

    correct(admin_client, filed, disbursed)

    settlement.refresh_from_db()
    assert (settlement.status, settlement.needs_review) == (SettlementStatus.ACTIVE, True)
    assert CommissionSettlement.objects.filter(application=filed.application).count() == 1
