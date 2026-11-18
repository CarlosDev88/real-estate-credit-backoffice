"""Parte 1 de comisiones: planes por producto (API §23.6)."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.banking.models import BankProduct
from apps.commissions.models import CommissionPlan, CommissionShare
from apps.identity.models import User
from tests.applications.conftest import seeded_product
from tests.commissions.conftest import PLANS_URL, PlanFactory, SettlementFactory, plan_url
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

BODY = {
    "rate_pct": "1.2500",
    "advisor_share_pct": "70",
    "broker_share_pct": "30",
    "valid_from": "2026-01-01",
}


def create(client: APIClient, product: BankProduct, **body: Any) -> Any:
    return client.post(
        PLANS_URL, {**BODY, "bank_product_id": str(product.pk), **body}, format="json"
    )


def patch(client: APIClient, plan: CommissionPlan, body: dict[str, Any], version: int = 1) -> Any:
    return client.patch(plan_url(plan), body, format="json", headers={"If-Match": f'"{version}"'})


def field_of(response: Any) -> str:
    return str(assert_error(response, 400, "VALIDATION_ERROR")["details"][0]["field"])


# --- Crear ------------------------------------------------------------------------------


def test_admin_creates_a_plan(
    admin_client: APIClient, admin_user: User, product: BankProduct
) -> None:
    response = create(admin_client, product, notes="Convenio 2026")

    assert response.status_code == 201, response.content
    assert response["ETag"] == '"1"'
    body = response.json()
    assert body == {
        "id": body["id"],
        "bank_product": {
            "id": str(product.pk),
            "code": product.code,
            "name": product.name,
            "bank": body["bank_product"]["bank"],
        },
        "rate_pct": "1.2500",
        "advisor_share_pct": "70.0000",
        "broker_share_pct": "30.0000",
        "valid_from": "2026-01-01",
        "valid_until": None,
        "notes": "Convenio 2026",
        "in_use": False,
        "version": 1,
        "created_by": {"id": str(admin_user.pk), "name": admin_user.get_full_name()},
        "created_at": body["created_at"],
        "updated_at": body["updated_at"],
    }
    assert body["bank_product"]["bank"]["code"] == "BANCOLOMBIA"
    event = AuditEvent.objects.get(action=AuditAction.COMMISSION_PLAN_CHANGED)
    assert (event.resource_type, str(event.resource_id)) == ("commission_plans", body["id"])


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"rate_pct": "0"}, "rate_pct"),
        ({"rate_pct": "100.0001"}, "rate_pct"),
        ({"advisor_share_pct": "60", "broker_share_pct": "30"}, "advisor_share_pct"),
        ({"advisor_share_pct": "50", "broker_share_pct": "50"}, "advisor_share_pct"),
        ({"advisor_share_pct": "30", "broker_share_pct": "70"}, "advisor_share_pct"),
        ({"advisor_share_pct": "101", "broker_share_pct": "-1"}, "broker_share_pct"),
        ({"valid_until": "2026-01-01"}, "valid_until"),
        ({"rate_pct": "1.23456"}, "rate_pct"),
        ({"bank_product_id": "8f9b8f5e-0000-4000-8000-000000000000"}, "bank_product_id"),
        ({"status": "ACTIVE"}, "status"),
    ],
)
def test_create_validates_the_terms(
    admin_client: APIClient, product: BankProduct, body: dict[str, Any], field: str
) -> None:
    assert field_of(create(admin_client, product, **body)) == field
    assert not CommissionPlan.objects.exists()


def test_a_plan_without_broker_share_is_valid(
    admin_client: APIClient, product: BankProduct
) -> None:
    response = create(admin_client, product, advisor_share_pct="100", broker_share_pct="0")

    assert response.status_code == 201, response.content


@pytest.mark.parametrize(
    ("existing", "new", "overlaps"),
    [
        # Abierto desde enero: cualquier fecha posterior se solapa.
        ((date(2026, 1, 1), None), ("2026-06-01", None), True),
        ((date(2026, 1, 1), None), ("2025-01-01", "2026-01-02"), True),
        # Fin exclusivo: empezar justo el día en que termina el otro no se solapa.
        ((date(2026, 1, 1), date(2026, 7, 1)), ("2026-07-01", None), False),
        ((date(2026, 1, 1), date(2026, 7, 1)), ("2026-06-30", None), True),
        ((date(2026, 7, 1), None), ("2026-01-01", "2026-07-01"), False),
        ((date(2026, 7, 1), None), ("2026-01-01", "2026-07-02"), True),
    ],
)
def test_overlapping_validity_is_rejected(
    admin_client: APIClient,
    product: BankProduct,
    make_plan: PlanFactory,
    existing: tuple[date, date | None],
    new: tuple[str, str | None],
    overlaps: bool,
) -> None:
    make_plan(valid_from=existing[0], valid_until=existing[1])

    response = create(admin_client, product, valid_from=new[0], valid_until=new[1])

    if overlaps:
        assert_error(response, 409, "COMMISSION_PLAN_OVERLAP")
    else:
        assert response.status_code == 201, response.content


def test_other_products_do_not_overlap(admin_client: APIClient, make_plan: PlanFactory) -> None:
    make_plan()

    response = create(admin_client, seeded_product("FNA"))

    assert response.status_code == 201, response.content


def test_the_database_rejects_inconsistent_shares(
    make_plan: PlanFactory,
) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        make_plan(advisor_share_pct=Decimal("70"), broker_share_pct=Decimal("40"))


# --- Leer -------------------------------------------------------------------------------


def test_list_filters_by_product_and_validity(
    admin_client: APIClient, make_plan: PlanFactory
) -> None:
    old = make_plan(valid_from=date(2025, 1, 1), valid_until=date(2026, 1, 1))
    current = make_plan(valid_from=date(2026, 1, 1))
    other = make_plan(bank_product=seeded_product("FNA"))

    def ids(**params: Any) -> list[str]:
        response = admin_client.get(PLANS_URL, params)
        assert response.status_code == 200, response.content
        return [item["id"] for item in response.json()["items"]]

    assert set(ids()) == {str(old.pk), str(current.pk), str(other.pk)}
    product_id = str(current.bank_product_id)
    assert ids(bank_product_id=product_id) == [str(current.pk), str(old.pk)]
    assert ids(bank_product_id=product_id, vigente_en="2025-12-31") == [str(old.pk)]
    assert ids(bank_product_id=product_id, vigente_en="2026-01-01") == [str(current.pk)]
    assert field_of(admin_client.get(PLANS_URL, {"vigente_en": "mañana"})) == "vigente_en"
    assert field_of(admin_client.get(PLANS_URL, {"vigente_en": "2026-02-30"})) == "vigente_en"
    assert field_of(admin_client.get(PLANS_URL, {"bank_product_id": "x"})) == "bank_product_id"


def test_detail_has_the_etag_and_in_use(
    admin_client: APIClient,
    make_plan: PlanFactory,
    make_settlement: SettlementFactory,
    application: CreditApplication,
) -> None:
    plan = make_plan()
    make_settlement(plan, application)

    response = admin_client.get(plan_url(plan))

    assert response.status_code == 200
    assert response["ETag"] == '"1"'
    assert response.json()["in_use"] is True


def test_list_queries_do_not_grow(admin_client: APIClient, make_plan: PlanFactory) -> None:
    def measure() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert admin_client.get(PLANS_URL).status_code == 200
        return len(queries)

    make_plan(valid_from=date(2020, 1, 1), valid_until=date(2020, 2, 1))
    one = measure()
    for month in range(2, 12):
        make_plan(valid_from=date(2020, month, 1), valid_until=date(2020, month + 1, 1))

    assert measure() == one


# --- Editar -----------------------------------------------------------------------------


def test_patch_needs_if_match_and_bumps_the_version(
    admin_client: APIClient, make_plan: PlanFactory
) -> None:
    plan = make_plan()

    assert_error(
        admin_client.patch(plan_url(plan), {"notes": "x"}, format="json"),
        428,
        "PRECONDITION_REQUIRED",
    )
    response = patch(admin_client, plan, {"rate_pct": "1.5", "notes": "Ajuste"})
    assert response.status_code == 200, response.content
    assert response["ETag"] == '"2"'
    assert (response.json()["rate_pct"], response.json()["notes"]) == ("1.5000", "Ajuste")
    stale = patch(admin_client, plan, {"notes": "otra"}, version=1)
    assert assert_error(stale, 409, "STALE_VERSION")["details"][0]["current_version"] == 2


def test_patch_revalidates_the_whole_plan(admin_client: APIClient, make_plan: PlanFactory) -> None:
    plan = make_plan()
    make_plan(valid_from=date(2025, 1, 1), valid_until=date(2025, 6, 1))

    assert field_of(patch(admin_client, plan, {"broker_share_pct": "40"})) == "advisor_share_pct"
    overlap = patch(admin_client, plan, {"valid_from": "2025-05-01"})
    assert_error(overlap, 409, "COMMISSION_PLAN_OVERLAP")
    assert field_of(patch(admin_client, plan, {"bank_product_id": "x"})) == "bank_product_id"
    plan.refresh_from_db()
    assert (plan.version, plan.broker_share_pct) == (1, Decimal("30.0000"))


def test_an_empty_patch_keeps_the_version(admin_client: APIClient, make_plan: PlanFactory) -> None:
    plan = make_plan()

    response = patch(admin_client, plan, {})

    assert (response.status_code, response["ETag"]) == (200, '"1"')


def test_a_plan_in_use_is_not_edited_but_can_be_closed(
    admin_client: APIClient,
    make_plan: PlanFactory,
    make_settlement: SettlementFactory,
    application: CreditApplication,
) -> None:
    plan = make_plan()
    make_settlement(plan, application)

    assert_error(patch(admin_client, plan, {"notes": "x"}), 409, "COMMISSION_PLAN_IN_USE")
    closed = admin_client.post(
        plan_url(plan, "/close"), {"valid_until": "2026-12-01"}, format="json"
    )
    assert closed.status_code == 200, closed.content
    assert (closed.json()["valid_until"], closed["ETag"]) == ("2026-12-01", '"2"')


def test_close_only_moves_the_end_earlier(admin_client: APIClient, make_plan: PlanFactory) -> None:
    plan = make_plan(valid_until=date(2026, 6, 1))

    def close(day: str) -> Any:
        return admin_client.post(plan_url(plan, "/close"), {"valid_until": day}, format="json")

    assert field_of(close("2026-07-01")) == "valid_until"
    assert field_of(close("2026-01-01")) == "valid_until"
    assert field_of(admin_client.post(plan_url(plan, "/close"), {}, format="json")) == "valid_until"
    assert close("2026-03-01").json()["valid_until"] == "2026-03-01"
    assert AuditEvent.objects.filter(action=AuditAction.COMMISSION_PLAN_CHANGED).count() == 1


# --- Permisos ---------------------------------------------------------------------------


@pytest.mark.parametrize("client_name", ["advisor_client", "broker_client", "partner_client"])
def test_only_the_admin_reads_and_manages_plans(
    request: pytest.FixtureRequest,
    client_name: str,
    make_plan: PlanFactory,
    product: BankProduct,
) -> None:
    client: APIClient = request.getfixturevalue(client_name)
    plan = make_plan()

    assert_error(client.get(PLANS_URL), 403, "PERMISSION_DENIED")
    assert_error(client.get(plan_url(plan)), 403, "PERMISSION_DENIED")
    assert_error(create(client, product), 403, "PERMISSION_DENIED")
    assert_error(patch(client, plan, {"notes": "x"}), 403, "PERMISSION_DENIED")
    closed = client.post(plan_url(plan, "/close"), {"valid_until": "2026-06-01"}, format="json")
    assert_error(closed, 403, "PERMISSION_DENIED")


def test_unknown_plan_is_not_found(admin_client: APIClient) -> None:
    missing = "8f9b8f5e-0000-4000-8000-000000000000"

    assert_error(admin_client.get(plan_url(missing)), 404, "RESOURCE_NOT_FOUND")
    assert_error(patch(admin_client, CommissionPlan(pk=missing), {}), 404, "RESOURCE_NOT_FOUND")


def test_str_of_the_models(
    make_plan: PlanFactory,
    make_settlement: SettlementFactory,
    application: CreditApplication,
    advisor_user: User,
) -> None:
    plan = make_plan()
    settlement = make_settlement(plan, application)
    share = CommissionShare.objects.create(
        settlement=settlement,
        beneficiary_user=advisor_user,
        beneficiary_role="ADVISOR",
        share_pct=Decimal("100"),
        amount_cop=2_940_000,
    )

    assert "desde 2026-01-01" in str(plan)
    assert str(settlement).endswith("ACTIVE")
    assert str(share) == "ADVISOR 2940000"
