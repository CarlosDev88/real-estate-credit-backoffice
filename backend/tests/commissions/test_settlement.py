"""Parte 2 de comisiones: cálculo, reparto, disparo, idempotencia, corrección y anulación."""

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import count
from typing import Any

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.activity.models import ActivityEventType, ActivityLog
from apps.applications.models import CreditApplication
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.catalogs.workflow import ApplicationStatus
from apps.commissions import receivers, settlement
from apps.commissions.exceptions import (
    ApplicationNotDisbursed,
    CommissionPlanNotFound,
    SettlementHasPayments,
)
from apps.commissions.models import (
    CommissionSettlement,
    CommissionShare,
    SettlementStatus,
    ShareStatus,
)
from apps.commissions.settlement import round_cop, settle_application, split, void_settlement
from apps.crm.models import Client, Opportunity
from apps.filings.models import Filing, FilingResponse
from apps.filings.signals import filing_response_recorded
from apps.identity.models import User
from tests.applications.conftest import catalog_item
from tests.applications.filings.test_filings_api import file, package, ready
from tests.applications.filings.test_responses_api import (
    APPROVED_BODY,
    DISBURSED_BODY,
    filed,
    recorded,
)
from tests.applications.test_status_api import transition
from tests.commissions.conftest import DisbursementFactory, PlanFactory
from tests.helpers import assert_error

__all__ = ["file", "filed", "package", "ready"]

pytestmark = pytest.mark.django_db

Capture = Callable[..., Any]
AppFactory = Callable[..., CreditApplication]

_numbers = count(1)


@pytest.fixture
def make_disbursed(
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    make_application: Callable[..., CreditApplication],
) -> AppFactory:
    """Solicitud `DISBURSED` con su propio cliente y el origen indicado."""

    def _make(
        origin: str = "DIRECT", origin_user: User | None = None, **extra: Any
    ) -> CreditApplication:
        client = make_client(document_number=f"6600{next(_numbers):06d}")
        opportunity = make_opportunity(
            client, origin_item=catalog_item("lead_origin", origin), origin_user=origin_user
        )
        extra.setdefault("status", ApplicationStatus.DISBURSED)
        return make_application(opportunity, **extra)

    return _make


def shares_of(result: CommissionSettlement) -> dict[str, tuple[Decimal, int, str]]:
    return {
        share.beneficiary_role: (share.share_pct, share.amount_cop, share.beneficiary_user.email)
        for share in result.shares.select_related("beneficiary_user")
    }


# --- Cálculo y redondeo -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(Decimal("1.5"), 2), (Decimal("2.5"), 3), (Decimal("2.4999"), 2), (Decimal("0.5"), 1)],
)
def test_round_half_up(value: Decimal, expected: int) -> None:
    assert round_cop(value) == expected


@pytest.mark.parametrize("total", [0, 1, 2, 5, 15, 101, 2_940_000, 1_234_567])
@pytest.mark.parametrize("broker_pct", ["30", "0.5", "49.9999", "33.3333"])
def test_the_split_always_adds_up(total: int, broker_pct: str) -> None:
    advisor, broker = split(total, Decimal(broker_pct))

    assert advisor + broker == total
    assert advisor >= broker


def test_split_rounds_the_broker_half_up() -> None:
    # 5 × 30 % = 1,5 → 2 para el broker; el asesor se lleva el resto.
    assert split(5, Decimal("30")) == (3, 2)


# --- Reparto ----------------------------------------------------------------------------


def test_direct_origin_gives_everything_to_the_advisor(
    make_plan: PlanFactory, make_disbursed: AppFactory, make_disbursement: DisbursementFactory
) -> None:
    plan = make_plan()
    application = make_disbursed()
    response = make_disbursement(application, amount=294_000_000)

    result = settle_application(application.pk)

    assert result.created is True
    created = result.settlement
    assert (created.filing_response, created.plan, created.lead_origin_code) == (
        response,
        plan,
        "DIRECT",
    )
    assert (created.base_amount_cop, created.rate_pct, created.total_amount_cop) == (
        294_000_000,
        Decimal("1.0000"),
        2_940_000,
    )
    assert shares_of(created) == {"ADVISOR": (Decimal("100.0000"), 2_940_000, "asesor@example.com")}
    assert created.needs_review is False


@pytest.mark.parametrize("origin", ["PARTNER_PROJECT", "REFERRAL"])
def test_other_origins_give_everything_to_the_advisor(
    make_plan: PlanFactory,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    broker_user: User,
    origin: str,
) -> None:
    make_plan()
    application = make_disbursed(origin, origin_user=broker_user)
    make_disbursement(application)

    created = settle_application(application.pk).settlement

    assert list(shares_of(created)) == ["ADVISOR"]
    assert created.lead_origin_code == origin


def test_broker_origin_splits_between_advisor_and_broker(
    make_plan: PlanFactory,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    broker_user: User,
) -> None:
    make_plan()
    application = make_disbursed("BROKER", origin_user=broker_user)
    make_disbursement(application, amount=294_000_000)

    created = settle_application(application.pk).settlement

    assert shares_of(created) == {
        "ADVISOR": (Decimal("70.0000"), 2_058_000, "asesor@example.com"),
        "INDEPENDENT_BROKER": (Decimal("30.0000"), 882_000, "broker@example.com"),
    }
    assert sum(created.shares.values_list("amount_cop", flat=True)) == created.total_amount_cop


def test_half_pesos_round_up_and_the_parts_add_up(
    make_plan: PlanFactory,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    broker_user: User,
) -> None:
    make_plan(rate_pct=Decimal("1.0000"))
    application = make_disbursed("BROKER", origin_user=broker_user)
    make_disbursement(application, amount=450)  # 4,5 → 5; broker 30 % = 1,5 → 2.

    created = settle_application(application.pk).settlement

    assert created.total_amount_cop == 5
    assert {role: amount for role, (_, amount, _) in shares_of(created).items()} == {
        "ADVISOR": 3,
        "INDEPENDENT_BROKER": 2,
    }


def test_broker_origin_without_origin_user_needs_review(
    make_plan: PlanFactory, make_disbursed: AppFactory, make_disbursement: DisbursementFactory
) -> None:
    make_plan()
    application = make_disbursed("BROKER")
    make_disbursement(application)

    created = settle_application(application.pk).settlement

    assert created.needs_review is True
    assert shares_of(created)["ADVISOR"][:2] == (Decimal("100"), created.total_amount_cop)


def test_a_plan_without_broker_share_gives_everything_to_the_advisor(
    make_plan: PlanFactory,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    broker_user: User,
) -> None:
    make_plan(advisor_share_pct=Decimal("100"), broker_share_pct=Decimal("0"))
    application = make_disbursed("BROKER", origin_user=broker_user)
    make_disbursement(application)

    created = settle_application(application.pk).settlement

    assert list(shares_of(created)) == ["ADVISOR"]
    assert created.needs_review is False


# --- Plan por fecha de desembolso -------------------------------------------------------


@pytest.mark.parametrize(
    ("received_at", "rate"),
    [
        # 23:59 del 31 de diciembre en Bogotá (04:59 UTC del 1 de enero): plan viejo.
        (datetime(2026, 1, 1, 4, 59, tzinfo=UTC), Decimal("1.0000")),
        # 00:00 del 1 de enero en Bogotá: plan nuevo (el fin del viejo es exclusivo).
        (datetime(2026, 1, 1, 5, 0, tzinfo=UTC), Decimal("2.0000")),
        (datetime(2025, 3, 1, 12, tzinfo=UTC), Decimal("1.0000")),
    ],
)
def test_the_plan_is_the_one_valid_on_the_disbursement_date(
    make_plan: PlanFactory,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    received_at: datetime,
    rate: Decimal,
) -> None:
    make_plan(valid_from=date(2025, 1, 1), valid_until=date(2026, 1, 1), rate_pct=Decimal("1"))
    make_plan(valid_from=date(2026, 1, 1), rate_pct=Decimal("2"))
    application = make_disbursed()
    make_disbursement(application, received_at=received_at)

    assert settle_application(application.pk).settlement.rate_pct == rate


def test_without_a_valid_plan_nothing_is_created(
    make_plan: PlanFactory, make_disbursed: AppFactory, make_disbursement: DisbursementFactory
) -> None:
    make_plan(valid_from=date(2026, 6, 1))
    application = make_disbursed()
    make_disbursement(application, received_at=datetime(2026, 5, 31, 12, tzinfo=UTC))

    with pytest.raises(CommissionPlanNotFound):
        settle_application(application.pk)
    assert not CommissionSettlement.objects.exists()


def test_the_plan_is_the_one_of_the_filed_product(
    make_plan: PlanFactory, make_disbursed: AppFactory, make_disbursement: DisbursementFactory
) -> None:
    from tests.applications.conftest import seeded_product

    make_plan(bank_product=seeded_product("FNA"))
    application = make_disbursed()
    make_disbursement(application)  # Radicada con el producto de Bancolombia.

    with pytest.raises(CommissionPlanNotFound):
        settle_application(application.pk)


# --- Estado e idempotencia --------------------------------------------------------------


def test_only_disbursed_applications_are_settled(
    make_plan: PlanFactory, make_disbursed: AppFactory, make_disbursement: DisbursementFactory
) -> None:
    make_plan()
    legalization = make_disbursed(status=ApplicationStatus.LEGALIZATION)
    make_disbursement(legalization)
    without_response = make_disbursed()

    with pytest.raises(ApplicationNotDisbursed):
        settle_application(legalization.pk)
    with pytest.raises(ApplicationNotDisbursed):
        settle_application(without_response.pk)


def test_settling_twice_creates_a_single_settlement(
    make_plan: PlanFactory, make_disbursed: AppFactory, make_disbursement: DisbursementFactory
) -> None:
    make_plan()
    application = make_disbursed()
    response = make_disbursement(application)

    first = settle_application(application.pk, response=response)
    second = settle_application(application.pk, response=response)

    assert (first.created, second.created) == (True, False)
    assert first.settlement.pk == second.settlement.pk
    assert CommissionSettlement.objects.count() == 1


def test_the_latest_uncorrected_disbursement_is_used(
    make_plan: PlanFactory, make_disbursed: AppFactory, make_disbursement: DisbursementFactory
) -> None:
    make_plan()
    application = make_disbursed()
    old = make_disbursement(application, amount=100_000_000)
    make_disbursement(application, amount=200_000_000, filing=old.filing, corrects_response=old)

    assert settle_application(application.pk).settlement.base_amount_cop == 200_000_000


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_simultaneous_settlements_create_only_one(
    make_plan: PlanFactory,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dos hilos, dos conexiones: el primero retiene el bloqueo de la solicitud mientras
    crea; el segundo espera, ve la liquidación vigente y la devuelve."""
    make_plan()
    application = make_disbursed()
    make_disbursement(application)
    original = settlement._create

    def slow_create(*args: Any, **kwargs: Any) -> CommissionSettlement:
        created = original(*args, **kwargs)
        time.sleep(0.5)  # Con el bloqueo tomado y sin confirmar.
        return created

    monkeypatch.setattr(settlement, "_create", slow_create)
    barrier = threading.Barrier(2)
    results: list[settlement.SettlementResult] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            barrier.wait(timeout=10)
            results.append(settle_application(application.pk))
        except BaseException as exc:  # pragma: no cover - se reporta abajo
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert sorted(result.created for result in results) == [False, True]
    assert len({result.settlement.pk for result in results}) == 1
    assert CommissionSettlement.objects.filter(application=application).count() == 1


# --- Corrección del desembolso ----------------------------------------------------------


@pytest.fixture
def settled(
    make_plan: PlanFactory,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    broker_user: User,
) -> CommissionSettlement:
    make_plan()
    application = make_disbursed("BROKER", origin_user=broker_user)
    make_disbursement(application, amount=294_000_000)
    return settle_application(application.pk).settlement


def correct(
    previous: CommissionSettlement, make_disbursement: DisbursementFactory, amount: int
) -> FilingResponse:
    old = previous.filing_response
    return make_disbursement(
        previous.application, amount=amount, filing=old.filing, corrects_response=old
    )


def test_a_correction_without_payments_replaces_the_settlement(
    settled: CommissionSettlement,
    make_disbursement: DisbursementFactory,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    fixed = correct(settled, make_disbursement, amount=300_000_000)

    with django_capture_on_commit_callbacks(execute=True):
        result = settle_application(settled.application_id, response=fixed)

    settled.refresh_from_db()
    assert (settled.status, settled.void_reason) == (
        SettlementStatus.VOIDED,
        "Corrección del desembolso",
    )
    assert set(settled.shares.values_list("status", flat=True)) == {ShareStatus.VOIDED}
    assert result.created is True
    assert (result.settlement.filing_response, result.settlement.total_amount_cop) == (
        fixed,
        3_000_000,
    )
    assert ActivityLog.objects.filter(
        event_type=ActivityEventType.COMMISSION_SETTLEMENT_VOIDED
    ).exists()


def test_a_correction_with_a_payment_only_flags_review(
    settled: CommissionSettlement, make_disbursement: DisbursementFactory, admin_user: User
) -> None:
    CommissionShare.objects.filter(settlement=settled, beneficiary_role="ADVISOR").update(
        status=ShareStatus.PAID, paid_at=date(2026, 11, 1), paid_by=admin_user
    )
    fixed = correct(settled, make_disbursement, amount=300_000_000)

    result = settle_application(settled.application_id, response=fixed)

    assert (result.created, result.settlement.pk) == (False, settled.pk)
    settled.refresh_from_db()
    assert (settled.status, settled.needs_review, settled.total_amount_cop) == (
        SettlementStatus.ACTIVE,
        True,
        2_940_000,
    )


# --- Anulación --------------------------------------------------------------------------


def test_void_without_payments(settled: CommissionSettlement, admin_user: User) -> None:
    voided = void_settlement(settled, actor=admin_user, reason="Error de producto")

    assert (voided.status, voided.voided_by, voided.void_reason) == (
        SettlementStatus.VOIDED,
        admin_user,
        "Error de producto",
    )
    assert voided.voided_at is not None
    assert set(voided.shares.values_list("status", flat=True)) == {ShareStatus.VOIDED}
    # Anular otra vez la devuelve igual; después se puede liquidar de nuevo.
    assert void_settlement(settled, actor=admin_user, reason="otra").void_reason == (
        "Error de producto"
    )
    again = settle_application(settled.application_id)
    assert again.created is True


def test_void_with_payments_is_rejected(settled: CommissionSettlement, admin_user: User) -> None:
    settled.shares.filter(beneficiary_role="INDEPENDENT_BROKER").update(
        status=ShareStatus.PAID, paid_at=date(2026, 11, 1)
    )

    with pytest.raises(SettlementHasPayments):
        void_settlement(settled, actor=admin_user, reason="x")


# --- Disparo por la señal ---------------------------------------------------------------


def send(response: FilingResponse, actor: User) -> None:
    filing_response_recorded.send(
        sender=FilingResponse,
        response=response,
        filing=response.filing,
        application=response.filing.application,
        status_changed=True,
        actor=actor,
    )


def test_a_disbursement_response_settles_and_records_activity_and_audit(
    make_plan: PlanFactory,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    advisor_user: User,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    make_plan()
    application = make_disbursed()
    response = make_disbursement(application)

    with django_capture_on_commit_callbacks(execute=True):
        send(response, advisor_user)
        send(response, advisor_user)  # Un evento repetido no duplica.

    created = CommissionSettlement.objects.get()
    assert created.filing_response == response
    activity = ActivityLog.objects.get(event_type=ActivityEventType.COMMISSION_SETTLED)
    assert (activity.title, activity.application_id) == ("Comisión liquidada", application.pk)
    assert "2" not in activity.title and activity.message == ""
    event = AuditEvent.objects.get(action=AuditAction.COMMISSION_SETTLED)
    assert event.resource_id == created.pk
    assert "amount" not in str(event.metadata) and "2940000" not in str(event.metadata)


def test_other_responses_do_not_settle(
    make_plan: PlanFactory,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    advisor_user: User,
) -> None:
    make_plan()
    application = make_disbursed()
    response = make_disbursement(application)
    response.response_type_item = catalog_item("filing_response_type", "OTHER")

    send(response, advisor_user)

    assert not CommissionSettlement.objects.exists()


def test_without_a_plan_the_signal_records_activity_and_a_warning(
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    advisor_user: User,
    caplog: pytest.LogCaptureFixture,
) -> None:
    application = make_disbursed()
    response = make_disbursement(application)

    with caplog.at_level(logging.WARNING, logger="apps.commissions.receivers"):
        send(response, advisor_user)

    assert not CommissionSettlement.objects.exists()
    missing = ActivityLog.objects.get(event_type=ActivityEventType.COMMISSION_PLAN_MISSING)
    assert missing.application_id == application.pk
    assert "Sin plan de comisión vigente" in caplog.text
    assert application.opportunity.client.full_name not in caplog.text


def test_an_unexpected_error_in_the_receiver_is_only_logged(
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    advisor_user: User,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("falla")

    monkeypatch.setattr(receivers, "settle_application", broken)
    response = make_disbursement(make_disbursed())

    with caplog.at_level(logging.ERROR, logger="apps.commissions.receivers"):
        send(response, advisor_user)

    assert "No se pudo liquidar la comisión" in caplog.text


# --- Endpoints --------------------------------------------------------------------------


def settle_url(application: CreditApplication) -> str:
    return f"/api/v1/applications/{application.pk}/commission-settlement"


def void_url(target: CommissionSettlement) -> str:
    return f"/api/v1/commission-settlements/{target.pk}/void"


def test_manual_settlement_endpoint(
    admin_client: APIClient,
    make_plan: PlanFactory,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
    broker_user: User,
) -> None:
    plan = make_plan()
    application = make_disbursed("BROKER", origin_user=broker_user)
    response = make_disbursement(application)

    first = admin_client.post(settle_url(application), headers={"Idempotency-Key": "liq-1"})
    again = admin_client.post(settle_url(application))

    assert first.status_code == 201, first.content
    body = first.json()
    assert body["application"] == {"id": str(application.pk), "code": application.code}
    assert (body["filing_response_id"], body["plan_id"]) == (str(response.pk), str(plan.pk))
    assert (body["lead_origin_code"], body["lead_origin_label"]) == (
        "BROKER",
        "Broker independiente",
    )
    assert (body["base_amount_cop"], body["rate_pct"], body["total_amount_cop"]) == (
        294_000_000,
        "1.0000",
        2_940_000,
    )
    assert (body["status"], body["status_label"], body["needs_review"]) == (
        "ACTIVE",
        "Vigente",
        False,
    )
    roles = {share["beneficiary_role"]: share for share in body["shares"]}
    assert roles["INDEPENDENT_BROKER"]["beneficiary_role_label"] == "Broker independiente"
    assert roles["ADVISOR"]["status_label"] == "Pendiente de pago"
    assert (again.status_code, again.json()["id"]) == (200, body["id"])
    replay = admin_client.post(settle_url(application), headers={"Idempotency-Key": "liq-1"})
    assert (replay.status_code, replay.json()["id"]) == (201, body["id"])


def test_manual_settlement_errors(
    admin_client: APIClient,
    make_disbursed: AppFactory,
    make_disbursement: DisbursementFactory,
) -> None:
    not_disbursed = make_disbursed(status=ApplicationStatus.LEGALIZATION)
    without_plan = make_disbursed()
    make_disbursement(without_plan)

    assert_error(admin_client.post(settle_url(not_disbursed)), 409, "APPLICATION_NOT_DISBURSED")
    assert_error(admin_client.post(settle_url(without_plan)), 422, "COMMISSION_PLAN_NOT_FOUND")
    missing = CreditApplication(pk="8f9b8f5e-0000-4000-8000-000000000000")
    assert_error(admin_client.post(settle_url(missing)), 404, "RESOURCE_NOT_FOUND")


def test_void_endpoint(
    admin_client: APIClient,
    settled: CommissionSettlement,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    assert_error(admin_client.post(void_url(settled), {}, format="json"), 400, "VALIDATION_ERROR")

    with django_capture_on_commit_callbacks(execute=True):
        response = admin_client.post(
            void_url(settled), {"reason": "Producto errado"}, format="json"
        )

    assert response.status_code == 200, response.content
    body = response.json()
    assert (body["status"], body["void_reason"]) == ("VOIDED", "Producto errado")
    assert {share["status"] for share in body["shares"]} == {"VOIDED"}
    event = AuditEvent.objects.get(action=AuditAction.COMMISSION_SETTLEMENT_VOIDED)
    assert event.metadata["reason"] == "Producto errado"


def test_void_endpoint_with_payments(
    admin_client: APIClient, settled: CommissionSettlement
) -> None:
    settled.shares.filter(beneficiary_role="ADVISOR").update(
        status=ShareStatus.PAID, paid_at=date(2026, 11, 1)
    )

    response = admin_client.post(void_url(settled), {"reason": "x"}, format="json")

    assert_error(response, 409, "COMMISSION_SETTLEMENT_HAS_PAYMENTS")


@pytest.mark.parametrize("client_name", ["advisor_client", "broker_client", "partner_client"])
def test_only_the_admin_settles_and_voids(
    request: pytest.FixtureRequest, client_name: str, settled: CommissionSettlement
) -> None:
    client: APIClient = request.getfixturevalue(client_name)

    assert_error(client.post(settle_url(settled.application)), 403, "PERMISSION_DENIED")
    assert_error(
        client.post(void_url(settled), {"reason": "x"}, format="json"), 403, "PERMISSION_DENIED"
    )


# --- De punta a punta por la API de radicación ------------------------------------------


def test_recording_the_disbursement_through_the_api_settles(
    advisor_client: APIClient, make_plan: PlanFactory, filed: Filing
) -> None:
    make_plan()
    application = filed.application
    recorded(advisor_client, filed, "APPROVED", **APPROVED_BODY)
    application.refresh_from_db()
    assert (
        transition(
            advisor_client, application, "LEGALIZATION", version=application.version
        ).status_code
        == 200
    )

    disbursed = recorded(advisor_client, filed, "DISBURSED", **DISBURSED_BODY)

    created = CommissionSettlement.objects.get(application=application)
    assert (created.filing_response, created.base_amount_cop, created.total_amount_cop) == (
        disbursed,
        294_000_000,
        2_940_000,
    )


def test_a_disbursement_without_amount_is_not_settled(
    make_plan: PlanFactory, make_disbursed: AppFactory, make_disbursement: DisbursementFactory
) -> None:
    make_plan()
    application = make_disbursed()
    make_disbursement(application, amount=None)

    with pytest.raises(ApplicationNotDisbursed):
        settle_application(application.pk)
