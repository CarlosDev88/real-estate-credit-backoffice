"""Parte 3 de comisiones: pagos, consultas, "mis comisiones", matriz de permisos y demo."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.activity.models import ActivityEventType, ActivityLog
from apps.applications.models import CreditApplication
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.banking.models import BankProduct
from apps.catalogs.workflow import ApplicationStatus
from apps.commissions.demo_data import seed_plans, settle_disbursed
from apps.commissions.models import (
    CommissionPlan,
    CommissionSettlement,
    CommissionShare,
    ShareStatus,
)
from apps.commissions.settlement import settle_application
from apps.identity.models import User
from tests.commissions.conftest import DisbursementFactory, PlanFactory
from tests.commissions.test_settlement import AppFactory, make_disbursed, settled
from tests.helpers import assert_error

__all__ = ["make_disbursed", "settled"]

pytestmark = pytest.mark.django_db

Capture = Callable[..., Any]

SETTLEMENTS_URL = "/api/v1/commission-settlements"
ME_URL = "/api/v1/me/commissions"


def pay_url(share: CommissionShare | str) -> str:
    share_id = share.pk if isinstance(share, CommissionShare) else share
    return f"/api/v1/commission-shares/{share_id}/pay"


def share_of(target: CommissionSettlement, role: str) -> CommissionShare:
    return target.shares.get(beneficiary_role=role)


def pay(client: APIClient, share: CommissionShare, **body: Any) -> Any:
    body.setdefault("paid_at", "2026-11-10")
    body.setdefault("payment_reference", "TRF-0001")
    return client.post(pay_url(share), body, format="json")


def items(response: Any) -> list[dict[str, Any]]:
    assert response.status_code == 200, response.content
    return list(response.json()["items"])


# --- Pagar una parte --------------------------------------------------------------------


def test_admin_pays_a_share(
    admin_client: APIClient,
    admin_user: User,
    settled: CommissionSettlement,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    broker_share = share_of(settled, "INDEPENDENT_BROKER")

    with django_capture_on_commit_callbacks(execute=True):
        response = pay(admin_client, broker_share)

    assert response.status_code == 200, response.content
    shares = {share["beneficiary_role"]: share for share in response.json()["shares"]}
    paid = shares["INDEPENDENT_BROKER"]
    assert (paid["status"], paid["status_label"], paid["paid_at"]) == (
        "PAID",
        "Pagada",
        "2026-11-10",
    )
    assert (paid["payment_reference"], paid["paid_by"]["id"]) == ("TRF-0001", str(admin_user.pk))
    assert shares["ADVISOR"]["status"] == "PENDING"
    event = AuditEvent.objects.get(action=AuditAction.COMMISSION_SHARE_PAID)
    assert event.metadata["beneficiary_role"] == "INDEPENDENT_BROKER"
    assert str(broker_share.amount_cop) not in str(event.metadata)
    activity = ActivityLog.objects.get(event_type=ActivityEventType.COMMISSION_SHARE_PAID)
    assert activity.title == "Pago de comisión registrado: parte del broker independiente"


def test_a_share_is_paid_only_once(admin_client: APIClient, settled: CommissionSettlement) -> None:
    share = share_of(settled, "ADVISOR")
    assert pay(admin_client, share).status_code == 200

    assert_error(pay(admin_client, share), 409, "COMMISSION_SHARE_NOT_PAYABLE")


def test_the_same_idempotency_key_returns_the_original_payment(
    admin_client: APIClient, settled: CommissionSettlement
) -> None:
    share = share_of(settled, "ADVISOR")
    headers = {"Idempotency-Key": "pago-1"}
    body = {"paid_at": "2026-11-10", "payment_reference": "TRF-1"}

    first = admin_client.post(pay_url(share), body, format="json", headers=headers)
    again = admin_client.post(pay_url(share), body, format="json", headers=headers)

    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json() == first.json()


def test_shares_of_a_voided_settlement_are_not_payable(
    admin_client: APIClient, settled: CommissionSettlement
) -> None:
    assert (
        admin_client.post(
            f"{SETTLEMENTS_URL}/{settled.pk}/void", {"reason": "Error"}, format="json"
        ).status_code
        == 200
    )

    assert_error(
        pay(admin_client, share_of(settled, "ADVISOR")), 409, "COMMISSION_SHARE_NOT_PAYABLE"
    )


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"paid_at": (timezone.localdate() + timedelta(days=1)).isoformat()}, "paid_at"),
        ({"paid_at": "ayer"}, "paid_at"),
        ({"payment_reference": ""}, "payment_reference"),
        ({"payment_reference": "x" * 101}, "payment_reference"),
        ({"amount_cop": 1}, "amount_cop"),
    ],
)
def test_pay_validates_the_body(
    admin_client: APIClient, settled: CommissionSettlement, body: dict[str, Any], field: str
) -> None:
    response = pay(admin_client, share_of(settled, "ADVISOR"), **body)

    assert assert_error(response, 400, "VALIDATION_ERROR")["details"][0]["field"] == field


def test_unknown_share_is_not_found(admin_client: APIClient) -> None:
    missing = "8f9b8f5e-0000-4000-8000-000000000000"

    assert_error(
        admin_client.post(
            pay_url(missing), {"paid_at": "2026-11-10", "payment_reference": "x"}, format="json"
        ),
        404,
        "RESOURCE_NOT_FOUND",
    )


# --- Liquidaciones (administrador) ------------------------------------------------------


@pytest.fixture
def two_settlements(
    make_plan: PlanFactory,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    broker_user: User,
    other_advisor: User,
) -> tuple[CommissionSettlement, CommissionSettlement]:
    make_plan()
    with_broker = make_disbursed("BROKER", origin_user=broker_user)
    # 23:30 del 10 de noviembre en Bogotá (04:30 UTC del 11).
    make_disbursement(with_broker, received_at=datetime(2026, 11, 11, 4, 30, tzinfo=UTC))
    direct = make_disbursed("BROKER", assigned_advisor=other_advisor)  # Sin broker: revisión.
    make_disbursement(direct, received_at=datetime(2026, 11, 12, 15, tzinfo=UTC))
    return (
        settle_application(with_broker.pk).settlement,
        settle_application(direct.pk).settlement,
    )


def test_settlement_list_and_filters(
    admin_client: APIClient,
    two_settlements: tuple[CommissionSettlement, CommissionSettlement],
    broker_user: User,
    other_advisor: User,
) -> None:
    with_broker, needs_review = two_settlements
    product = with_broker.plan.bank_product

    def ids(**params: Any) -> list[str]:
        return [row["id"] for row in items(admin_client.get(SETTLEMENTS_URL, params))]

    assert ids() == [str(needs_review.pk), str(with_broker.pk)]
    assert ids(broker_id=str(broker_user.pk)) == [str(with_broker.pk)]
    assert ids(advisor_id=str(other_advisor.pk)) == [str(needs_review.pk)]
    assert ids(needs_review="true") == [str(needs_review.pk)]
    assert ids(needs_review="false") == [str(with_broker.pk)]
    assert ids(bank_id=str(product.bank_id)) == [str(needs_review.pk), str(with_broker.pk)]
    assert ids(status="VOIDED") == []
    assert ids(application_id=str(with_broker.application_id)) == [str(with_broker.pk)]
    assert ids(application_id=str(needs_review.application_id)) == [str(needs_review.pk)]
    # Fechas de Bogotá: el desembolso de las 23:30 del 10 cuenta en el 10.
    assert ids(date_from="2026-11-10", date_to="2026-11-10") == [str(with_broker.pk)]
    assert ids(date_from="2026-11-11") == [str(needs_review.pk)]
    row = items(admin_client.get(SETTLEMENTS_URL, {"broker_id": str(broker_user.pk)}))[0]
    assert row["disbursed_on"] == "2026-11-10"


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"status": "PAID"}, "status"),
        ({"application_id": "x"}, "application_id"),
        ({"bank_id": "x"}, "bank_id"),
        ({"advisor_id": "x"}, "advisor_id"),
        ({"broker_id": "x"}, "broker_id"),
        ({"needs_review": "quizás"}, "needs_review"),
        ({"date_from": "2026-02-30"}, "date_from"),
        ({"date_to": "mañana"}, "date_to"),
    ],
)
def test_settlement_list_rejects_bad_filters(
    admin_client: APIClient, params: dict[str, str], field: str
) -> None:
    response = admin_client.get(SETTLEMENTS_URL, params)

    assert assert_error(response, 400, "VALIDATION_ERROR")["details"][0]["field"] == field


def test_settlement_detail(admin_client: APIClient, settled: CommissionSettlement) -> None:
    body = admin_client.get(f"{SETTLEMENTS_URL}/{settled.pk}").json()

    assert body["id"] == str(settled.pk)
    assert {share["beneficiary_role"] for share in body["shares"]} == {
        "ADVISOR",
        "INDEPENDENT_BROKER",
    }
    missing = admin_client.get(f"{SETTLEMENTS_URL}/8f9b8f5e-0000-4000-8000-000000000000")
    assert_error(missing, 404, "RESOURCE_NOT_FOUND")


def test_settlement_list_queries_do_not_grow(
    admin_client: APIClient,
    make_plan: PlanFactory,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    broker_user: User,
) -> None:
    make_plan()

    def add() -> None:
        application = make_disbursed("BROKER", origin_user=broker_user)
        make_disbursement(application)
        settle_application(application.pk)

    def measure() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert admin_client.get(SETTLEMENTS_URL).status_code == 200
        return len(queries)

    add()
    one = measure()
    for _ in range(5):
        add()

    assert measure() == one


# --- Mis comisiones ---------------------------------------------------------------------

MY_FIELDS = {
    "id",
    "application_code",
    "client_display_name",
    "disbursed_on",
    "share_pct",
    "amount_cop",
    "status",
    "status_label",
    "paid_at",
}


def test_each_beneficiary_sees_only_their_own_part(
    advisor_client: APIClient, broker_client: APIClient, settled: CommissionSettlement
) -> None:
    (mine,) = items(advisor_client.get(ME_URL))
    (theirs,) = items(broker_client.get(ME_URL))

    assert set(mine) == set(theirs) == MY_FIELDS
    advisor_share = share_of(settled, "ADVISOR")
    broker_share = share_of(settled, "INDEPENDENT_BROKER")
    assert (mine["id"], mine["share_pct"], mine["amount_cop"]) == (
        str(advisor_share.pk),
        "70.0000",
        advisor_share.amount_cop,
    )
    assert (theirs["id"], theirs["share_pct"], theirs["amount_cop"]) == (
        str(broker_share.pk),
        "30.0000",
        broker_share.amount_cop,
    )
    assert theirs["application_code"] == settled.application.code
    assert theirs["client_display_name"] == settled.application.opportunity.client.full_name
    # Nada de la liquidación completa ni de la otra parte.
    text = str(theirs)
    for hidden in (settled.base_amount_cop, settled.total_amount_cop, advisor_share.amount_cop):
        assert str(hidden) not in text
    assert "rate" not in text


def test_my_commissions_filters(
    advisor_client: APIClient, admin_client: APIClient, settled: CommissionSettlement
) -> None:
    assert pay(admin_client, share_of(settled, "ADVISOR")).status_code == 200
    today = timezone.localdate().isoformat()

    assert [row["status"] for row in items(advisor_client.get(ME_URL, {"status": "PAID"}))] == [
        "PAID"
    ]
    assert items(advisor_client.get(ME_URL, {"status": "PENDING"})) == []
    assert len(items(advisor_client.get(ME_URL, {"date_from": today, "date_to": today}))) == 1
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    assert items(advisor_client.get(ME_URL, {"date_from": tomorrow})) == []
    error = assert_error(advisor_client.get(ME_URL, {"status": "LOST"}), 400, "VALIDATION_ERROR")
    assert error["details"][0]["field"] == "status"


def test_other_advisors_see_nothing(
    other_advisor_client: APIClient, settled: CommissionSettlement
) -> None:
    assert items(other_advisor_client.get(ME_URL)) == []


# --- Matriz de permisos -----------------------------------------------------------------

ALLOWED_FOR_ADMIN_ONLY = [
    ("get", lambda ctx: "/api/v1/commission-plans"),
    ("post", lambda ctx: "/api/v1/commission-plans"),
    ("get", lambda ctx: f"/api/v1/commission-plans/{ctx['plan'].pk}"),
    ("patch", lambda ctx: f"/api/v1/commission-plans/{ctx['plan'].pk}"),
    ("post", lambda ctx: f"/api/v1/commission-plans/{ctx['plan'].pk}/close"),
    ("get", lambda ctx: SETTLEMENTS_URL),
    ("get", lambda ctx: f"{SETTLEMENTS_URL}/{ctx['settlement'].pk}"),
    (
        "post",
        lambda ctx: (
            f"/api/v1/applications/{ctx['settlement'].application_id}/commission-settlement"
        ),
    ),
    ("post", lambda ctx: f"{SETTLEMENTS_URL}/{ctx['settlement'].pk}/void"),
    ("post", lambda ctx: pay_url(ctx["share"])),
]


@pytest.fixture
def ctx(settled: CommissionSettlement) -> dict[str, Any]:
    return {
        "plan": settled.plan,
        "settlement": settled,
        "share": share_of(settled, "ADVISOR"),
    }


@pytest.mark.parametrize("client_name", ["advisor_client", "broker_client", "partner_client"])
@pytest.mark.parametrize(("method", "url"), ALLOWED_FOR_ADMIN_ONLY)
def test_admin_only_endpoints_deny_the_other_roles(
    request: pytest.FixtureRequest,
    ctx: dict[str, Any],
    client_name: str,
    method: str,
    url: Callable[[dict[str, Any]], str],
) -> None:
    client: APIClient = request.getfixturevalue(client_name)

    response = getattr(client, method)(url(ctx), {}, format="json")

    assert_error(response, 403, "PERMISSION_DENIED")


@pytest.mark.parametrize(("method", "url"), ALLOWED_FOR_ADMIN_ONLY)
def test_admin_only_endpoints_need_a_session(
    api_client: APIClient, ctx: dict[str, Any], method: str, url: Callable[[dict[str, Any]], str]
) -> None:
    response = getattr(api_client, method)(url(ctx), {}, format="json")

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("client_name", "status"),
    [
        ("advisor_client", 200),
        ("broker_client", 200),
        ("admin_client", 403),
        ("partner_client", 403),
        ("api_client", 401),
    ],
)
def test_my_commissions_matrix(
    request: pytest.FixtureRequest, client_name: str, status: int
) -> None:
    client: APIClient = request.getfixturevalue(client_name)

    assert client.get(ME_URL).status_code == status


# --- Demo -------------------------------------------------------------------------------


def test_demo_plans_and_settlements(
    admin_user: User,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
) -> None:
    created = seed_plans(admin_user)

    assert len(created) == BankProduct.objects.count()
    assert {
        (plan.rate_pct, plan.advisor_share_pct, plan.broker_share_pct, plan.valid_from)
        for plan in created
    } == {(Decimal("1.0000"), Decimal("70.0000"), Decimal("30.0000"), date(2026, 1, 1))}
    assert seed_plans(admin_user) == []  # Idempotente.
    disbursed = make_disbursed()
    make_disbursement(disbursed)
    legalization = make_disbursed(status=ApplicationStatus.LEGALIZATION)

    settled_now = settle_disbursed(admin_user, [disbursed, legalization])

    assert [row.application_id for row in settled_now] == [disbursed.pk]
    again = settle_disbursed(admin_user, [disbursed])
    assert again[0].pk == settled_now[0].pk
    assert CommissionPlan.objects.count() == len(created)
    assert CommissionSettlement.objects.count() == 1
    assert ShareStatus.PENDING in set(CommissionShare.objects.values_list("status", flat=True))
    assert isinstance(disbursed, CreditApplication)
