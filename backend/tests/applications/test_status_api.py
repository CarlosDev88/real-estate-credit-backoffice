"""Estados de la solicitud (API §16.3): transiciones, guarda `APPLICATION_READY_TO_FILE`,
desistimiento, historial, acciones disponibles y completitud."""

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications import services
from apps.applications.models import (
    ApplicationParticipant,
    ApplicationStatusHistory,
    BankRuleEvaluation,
    CreditApplication,
    FinancialProfile,
    FinancingPreference,
    ParticipantRole,
)
from apps.applications.signals import application_status_changed
from apps.banking.models import BankPolicyRule, RuleStatus
from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client
from apps.documents.models import ApplicationDocumentSlot, SlotStatus
from apps.documents.verification import NOT_CONFIGURED_MESSAGE, check_dossier
from apps.identity.models import User
from tests.applications.conftest import application_url, catalog_item, seeded_product
from tests.applications.dossier.conftest import approve_required_slots
from tests.applications.test_property_financing_api import PROPERTY, bank_credit, put
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

EMPLOYEE_ONLY: dict[str, Any] = {
    "operator": "in",
    "left": {"field": "applicant.employment_profile_code"},
    "right": ["EMPLOYEE"],
}


def transition(
    client: APIClient,
    application: CreditApplication,
    target: str,
    version: int | None = 1,
    **extra: Any,
) -> Any:
    body: dict[str, Any] = {"target_status": target, **extra}
    if version is not None:
        body["expected_version"] = version
    return client.post(application_url(application, "/status-transitions"), body, format="json")


def withdraw(
    client: APIClient, application: CreditApplication, version: int = 1, **extra: Any
) -> Any:
    body = {"reason_code": "BUYER_DECISION", "expected_version": version, **extra}
    return client.post(application_url(application, "/withdrawals"), body, format="json")


def set_status(application: CreditApplication, status: str) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(status=status)
    application.refresh_from_db()


def add_financing(application: CreditApplication, mode: str, **extra: Any) -> None:
    extra.setdefault("requested_amount_cop", 0)
    FinancingPreference.objects.create(
        application=application, financing_mode_item=catalog_item("financing_mode", mode), **extra
    )


@pytest.fixture
def status_events() -> Iterator[list[dict[str, Any]]]:
    received: list[dict[str, Any]] = []

    def on_changed(**kwargs: Any) -> None:
        received.append(kwargs)

    application_status_changed.connect(on_changed)
    yield received
    application_status_changed.disconnect(on_changed)


@pytest.fixture
def blocking_rule(admin_user: User) -> BankPolicyRule:
    return BankPolicyRule.objects.create(
        bank_product=seeded_product(),
        code="EMPLOYEE_ONLY",
        version=1,
        severity="BLOCKING",
        condition=EMPLOYEE_ONLY,
        message="Solo empleados.",
        status=RuleStatus.ACTIVE,
        valid_from=timezone.now() - timedelta(days=1),
        created_by=admin_user,
    )


@pytest.fixture
def in_review(advisor_client: APIClient, application: CreditApplication) -> CreditApplication:
    """Inmueble y crédito bancario (versión 3, con evaluación vigente) en revisión."""
    assert put(advisor_client, application, "property", PROPERTY).status_code == 201
    assert put(advisor_client, application, "financing", bank_credit(), '"2"').status_code == 201
    set_status(application, ApplicationStatus.DOCUMENTS_REVIEW)
    return application


@pytest.fixture
def documents_ok(in_review: CreditApplication) -> None:
    """Expediente documental real con todos los obligatorios aprobados (paso 10)."""
    assert approve_required_slots(in_review)


# --- POST /status-transitions -----------------------------------------------------------


def test_transition_changes_the_status_and_records_the_history(
    advisor_client: APIClient,
    advisor_user: User,
    application: CreditApplication,
    status_events: list[dict[str, Any]],
) -> None:
    started = application.current_stage_started_at

    response = transition(
        advisor_client,
        application,
        "WAITING_BUYER_DATA",
        reason_code="BUYER_DATA_REQUESTED",
        comment="Se pidió el certificado laboral.",
    )

    assert response.status_code == 200, response.content
    assert response["ETag"] == '"2"'
    body = response.json()
    assert body == {
        "application_id": str(application.id),
        "previous_status": "DRAFT",
        "previous_status_label": "Borrador",
        "status": "WAITING_BUYER_DATA",
        "status_label": "Esperando datos del comprador",
        "version": 2,
        "transitioned_at": body["transitioned_at"],
    }
    application.refresh_from_db()
    assert (application.status, application.version) == ("WAITING_BUYER_DATA", 2)
    assert application.current_stage_started_at > started
    assert application.closed_at is None
    history = ApplicationStatusHistory.objects.select_related("transition").get(
        application=application
    )
    assert history.transition is not None
    assert (history.from_status, history.to_status, history.transition.code) == (
        "DRAFT",
        "WAITING_BUYER_DATA",
        "REQUEST_BUYER_DATA",
    )
    assert history.reason_item == catalog_item(
        "application_transition_reason", "BUYER_DATA_REQUESTED"
    )
    assert (history.comment, history.actor_user, history.application_version) == (
        "Se pidió el certificado laboral.",
        advisor_user,
        2,
    )
    assert len(status_events) == 1
    event = status_events[0]
    assert {key: event[key] for key in ("from_status", "to_status", "transition_code")} == {
        "from_status": "DRAFT",
        "to_status": "WAITING_BUYER_DATA",
        "transition_code": "REQUEST_BUYER_DATA",
    }
    assert (event["reason_code"], event["actor"]) == ("BUYER_DATA_REQUESTED", advisor_user)


def test_transition_requires_the_expected_version(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    missing = transition(advisor_client, application, "WAITING_BUYER_DATA", version=None)
    stale = transition(advisor_client, application, "WAITING_BUYER_DATA", version=3)

    assert "expected_version" in str(assert_error(missing, 400, "VALIDATION_ERROR")["details"])
    body = assert_error(stale, 409, "STALE_VERSION")
    assert body["details"][0]["current_version"] == 1


def test_transition_without_a_configured_path_is_rejected(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = transition(advisor_client, application, "FILED")

    assert_error(response, 409, "INVALID_STATE_TRANSITION")


def test_withdrawn_goes_through_withdrawals(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    body = assert_error(
        transition(advisor_client, application, "WITHDRAWN"), 400, "VALIDATION_ERROR"
    )

    assert body["details"][0]["field"] == "target_status"


@pytest.mark.parametrize("target", ["CANCELLED", "OWN_FUNDS", "EXTERNAL_CREDIT_APPROVED"])
def test_closing_requires_a_reason(
    target: str, advisor_client: APIClient, application: CreditApplication
) -> None:
    body = assert_error(transition(advisor_client, application, target), 400, "VALIDATION_ERROR")

    assert body["details"][0]["field"] == "reason_code"


def test_reason_must_be_an_active_catalog_item(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    CatalogItem.objects.filter(
        catalog__code="application_transition_reason", code="CLIENT_UNREACHABLE"
    ).update(is_active=False)

    inactive = transition(
        advisor_client, application, "CANCELLED", reason_code="CLIENT_UNREACHABLE"
    )
    unknown = transition(advisor_client, application, "CANCELLED", reason_code="NOPE")

    for response in (inactive, unknown):
        body = assert_error(response, 400, "VALIDATION_ERROR")
        assert body["details"][0]["field"] == "reason_code"


def test_cancelling_closes_the_application(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = transition(
        advisor_client, application, "CANCELLED", reason_code="CLIENT_UNREACHABLE"
    )

    assert response.status_code == 200, response.content
    application.refresh_from_db()
    assert application.status == "CANCELLED"
    assert application.closed_at is not None
    assert application.withdrawn_at is None


def test_closed_application_rejects_transitions_and_withdrawals(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.CANCELLED)

    assert_error(
        transition(advisor_client, application, "DRAFT", version=99), 409, "APPLICATION_CLOSED"
    )
    assert_error(withdraw(advisor_client, application), 409, "APPLICATION_CLOSED")


def test_comment_is_limited(advisor_client: APIClient, application: CreditApplication) -> None:
    response = transition(advisor_client, application, "WAITING_BUYER_DATA", comment="x" * 2001)

    assert_error(response, 400, "VALIDATION_ERROR")


# --- Cierres por modalidad --------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "mode"),
    [("OWN_FUNDS", "OWN_FUNDS"), ("EXTERNAL_CREDIT_APPROVED", "EXTERNAL_CREDIT")],
)
def test_closing_by_mode_requires_the_matching_financing(
    target: str, mode: str, advisor_client: APIClient, application: CreditApplication
) -> None:
    reason: dict[str, Any] = {"reason_code": "OTHER"}
    without = transition(advisor_client, application, target, **reason)
    body = assert_error(without, 422, "FINANCING_MODE_MISMATCH")
    assert body["details"][0]["field"] == "financing_mode_code"

    add_financing(application, "BANK_CREDIT", requested_amount_cop=1)
    assert_error(
        transition(advisor_client, application, target, **reason), 422, "FINANCING_MODE_MISMATCH"
    )

    FinancingPreference.objects.filter(application=application).update(
        financing_mode_item=catalog_item("financing_mode", mode)
    )
    response = transition(advisor_client, application, target, **reason)

    assert response.status_code == 200, response.content
    application.refresh_from_db()
    assert (application.status, application.closed_at is not None) == (target, True)


# --- Guarda APPLICATION_READY_TO_FILE ---------------------------------------------------


def test_ready_to_file_without_product_lists_every_reason(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.DOCUMENTS_REVIEW)

    body = assert_error(
        transition(advisor_client, application, "READY_TO_FILE"), 422, "APPLICATION_NOT_READY"
    )

    # Sin producto no hay requisitos: el expediente no tiene obligatorios.
    assert [(d["code"], d["field"]) for d in body["details"]] == [
        ("BANK_PRODUCT_REQUIRED", "bank_product_id"),
        ("DOCUMENTS_NOT_CONFIGURED", "documents"),
    ]
    application.refresh_from_db()
    assert (application.status, application.version) == ("DOCUMENTS_REVIEW", 1)
    assert not BankRuleEvaluation.objects.exists()
    assert not ApplicationStatusHistory.objects.exists()


def test_ready_to_file_reevaluates_and_keeps_the_evaluation_when_rejected(
    advisor_client: APIClient,
    in_review: CreditApplication,
    blocking_rule: BankPolicyRule,
) -> None:
    # La evaluación automática de la versión 3 se hizo antes de publicar la regla. Se
    # cambia el valor del inmueble: la versión 4 ya no tiene evaluación vigente.
    put(
        advisor_client,
        in_review,
        "property",
        {**PROPERTY, "estimated_value_cop": 500_000_000},
        '"3"',
    )
    assert BankRuleEvaluation.objects.count() == 1

    body = assert_error(
        transition(advisor_client, in_review, "READY_TO_FILE", version=4),
        422,
        "APPLICATION_NOT_READY",
    )

    assert body["details"][0] == {
        "field": "applicant.employment_profile_code",
        "code": "BANK_RULE_BLOCKED",
        "message": "Faltan datos para evaluar la regla: applicant.employment_profile_code.",
    }
    assert {d["code"] for d in body["details"][1:]} == {"DOCUMENT_PENDING"}
    evaluation = BankRuleEvaluation.objects.latest("created_at")
    assert (evaluation.application_version, evaluation.is_eligible) == (4, False)
    in_review.refresh_from_db()
    assert (in_review.status, in_review.version) == ("DOCUMENTS_REVIEW", 4)


def test_ready_to_file_reuses_a_current_evaluation(
    advisor_client: APIClient, in_review: CreditApplication
) -> None:
    body = assert_error(
        transition(advisor_client, in_review, "READY_TO_FILE", version=3),
        422,
        "APPLICATION_NOT_READY",
    )

    assert {d["code"] for d in body["details"]} == {"DOCUMENT_PENDING"}
    assert BankRuleEvaluation.objects.count() == 1


@pytest.mark.usefixtures("documents_ok")
def test_ready_to_file_sets_the_timestamp_and_reopening_clears_it(
    advisor_client: APIClient, in_review: CreditApplication
) -> None:
    ready = transition(advisor_client, in_review, "READY_TO_FILE", version=3)
    assert ready.status_code == 200, ready.content
    in_review.refresh_from_db()
    assert in_review.status == "READY_TO_FILE"
    assert in_review.ready_to_file_at is not None

    reopened = transition(advisor_client, in_review, "DOCUMENTS_REVIEW", version=4)
    assert reopened.status_code == 200, reopened.content
    in_review.refresh_from_db()
    assert in_review.ready_to_file_at is None

    transition(advisor_client, in_review, "READY_TO_FILE", version=5)
    transition(advisor_client, in_review, "CANCELLED", version=6, reason_code="OTHER")
    in_review.refresh_from_db()
    assert in_review.status == "CANCELLED"
    # Cerrar no borra el momento en que quedó lista.
    assert in_review.ready_to_file_at is not None


@pytest.mark.usefixtures("documents_ok")
def test_ready_to_file_blocked_by_a_rule_even_with_documents(
    advisor_client: APIClient, in_review: CreditApplication, blocking_rule: BankPolicyRule
) -> None:
    put(advisor_client, in_review, "financing", bank_credit(term_months=200), '"3"')

    body = assert_error(
        transition(advisor_client, in_review, "READY_TO_FILE", version=4),
        422,
        "APPLICATION_NOT_READY",
    )

    assert [d["code"] for d in body["details"]] == ["BANK_RULE_BLOCKED"]


# --- POST /withdrawals ------------------------------------------------------------------


def test_withdrawal_closes_the_application(
    advisor_client: APIClient,
    application: CreditApplication,
    status_events: list[dict[str, Any]],
) -> None:
    response = withdraw(advisor_client, application, comment="Compró con otra entidad.")

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "WITHDRAWN"
    application.refresh_from_db()
    reason = catalog_item("application_withdrawal_reason", "BUYER_DECISION")
    assert application.withdrawal_reason_item == reason
    assert application.withdrawn_at is not None
    assert application.closed_at == application.withdrawn_at
    history = ApplicationStatusHistory.objects.get(application=application)
    assert history.transition is not None
    assert (history.transition.code, history.reason_item) == ("WITHDRAW_DRAFT", reason)
    assert status_events[0]["reason_code"] == "BUYER_DECISION"


def test_withdrawal_is_allowed_after_filing(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.CREDIT_ANALYSIS)

    assert withdraw(advisor_client, application).status_code == 200


def test_withdrawal_requires_a_reason_and_the_version(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    url = application_url(application, "/withdrawals")

    no_reason = advisor_client.post(url, {"expected_version": 1}, format="json")
    wrong_catalog = withdraw(advisor_client, application, reason_code="CLIENT_UNREACHABLE")
    stale = withdraw(advisor_client, application, version=2)

    assert assert_error(no_reason, 400, "VALIDATION_ERROR")["details"][0]["field"] == "reason_code"
    assert_error(wrong_catalog, 400, "VALIDATION_ERROR")
    assert_error(stale, 409, "STALE_VERSION")


# --- GET /status-history ----------------------------------------------------------------


def test_status_history_is_newest_first(
    advisor_client: APIClient, advisor_user: User, application: CreditApplication
) -> None:
    ApplicationStatusHistory.objects.create(
        application=application,
        to_status=ApplicationStatus.DRAFT,
        actor_user=advisor_user,
        application_version=1,
    )
    transition(advisor_client, application, "WAITING_BUYER_DATA")
    transition(advisor_client, application, "CANCELLED", version=2, reason_code="OTHER")

    response = advisor_client.get(application_url(application, "/status-history"))

    assert response.status_code == 200
    assert response["ETag"] == '"3"'
    items = response.json()["items"]
    assert [(i["from_status"], i["to_status"]) for i in items] == [
        ("WAITING_BUYER_DATA", "CANCELLED"),
        ("DRAFT", "WAITING_BUYER_DATA"),
        (None, "DRAFT"),
    ]
    latest = items[0]
    assert latest == {
        "id": latest["id"],
        "from_status": "WAITING_BUYER_DATA",
        "from_status_label": "Esperando datos del comprador",
        "to_status": "CANCELLED",
        "to_status_label": "Cancelada",
        "transition_code": "CANCEL_WAITING_BUYER_DATA",
        "reason": {"code": "OTHER", "label": "Otro motivo"},
        "comment": "",
        "actor": {"id": str(advisor_user.id), "name": advisor_user.get_full_name()},
        "buyer_session_id": None,
        "application_version": 3,
        "created_at": latest["created_at"],
    }
    assert (items[2]["transition_code"], items[2]["reason"]) == (None, None)
    # El registro de creación no tiene estado de origen: tampoco etiqueta.
    assert (items[2]["from_status_label"], items[2]["to_status_label"]) == (None, "Borrador")


# --- Acciones disponibles ---------------------------------------------------------------


DRAFT_ACTIONS = [
    "CANCEL_DRAFT",
    "MARK_EXTERNAL_CREDIT_DRAFT",
    "MARK_OWN_FUNDS_DRAFT",
    "REQUEST_BUYER_DATA",
    "REQUEST_DOCUMENTS_FROM_DRAFT",
    "WITHDRAW_DRAFT",
]


def test_available_actions_endpoint_and_detail(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = advisor_client.get(application_url(application, "/available-actions"))

    assert response.status_code == 200
    assert response["ETag"] == '"1"'
    actions = response.json()
    assert [action["code"] for action in actions] == DRAFT_ACTIONS
    assert actions[3] == {
        "code": "REQUEST_BUYER_DATA",
        "label": "Solicitar datos al comprador",
        "target_status": "WAITING_BUYER_DATA",
        "target_status_label": "Esperando datos del comprador",
        "guard_code": "",
    }
    detail = advisor_client.get(application_url(application)).json()
    assert detail["available_actions"] == actions


def test_available_actions_show_the_guard_without_evaluating_it(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.DOCUMENTS_REVIEW)

    actions = advisor_client.get(application_url(application, "/available-actions")).json()

    ready = next(action for action in actions if action["code"] == "MARK_READY_TO_FILE")
    assert ready["guard_code"] == "APPLICATION_READY_TO_FILE"


def test_terminal_application_has_no_actions(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.CANCELLED)

    assert advisor_client.get(application_url(application, "/available-actions")).json() == []


def test_creation_returns_actions_and_records_the_first_history_row(
    advisor_client: APIClient, opportunity: Any
) -> None:
    response = advisor_client.post(
        "/api/v1/applications",
        {"opportunity_id": str(opportunity.id), "purpose_code": "PURCHASE_NEW"},
        format="json",
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert [a["code"] for a in body["available_actions"]] == DRAFT_ACTIONS
    history = advisor_client.get(f"/api/v1/applications/{body['id']}/status-history").json()
    assert [(i["from_status"], i["to_status"]) for i in history["items"]] == [(None, "DRAFT")]


# --- GET /completeness ------------------------------------------------------------------


def completeness(client: APIClient, application: CreditApplication) -> Any:
    response = client.get(application_url(application, "/completeness"))
    assert response.status_code == 200, response.content
    return response.json()


def test_new_application_is_incomplete(
    advisor_client: APIClient, application: CreditApplication, primary: ApplicationParticipant
) -> None:
    body = completeness(advisor_client, application)

    assert body == {
        "percentage": 0,
        "data_percentage": 0,
        "documents_percentage": 0,
        "ready_to_file": False,
        "ready_to_file_problems": [
            {
                "field": "bank_product_id",
                "code": "BANK_PRODUCT_REQUIRED",
                "message": "Elige un producto bancario.",
            },
            {
                "field": "documents",
                "code": "DOCUMENTS_NOT_CONFIGURED",
                "message": NOT_CONFIGURED_MESSAGE,
            },
        ],
        "items": [
            {
                "code": "property",
                "complete": False,
                "message": "Registra el inmueble.",
                "participant_id": None,
            },
            {
                "code": "financing",
                "complete": False,
                "message": "Registra la financiación.",
                "participant_id": None,
            },
            {
                "code": "bank_product",
                "complete": False,
                "message": "Elige un producto bancario.",
                "participant_id": None,
            },
            {
                "code": "bank_evaluation",
                "complete": False,
                "message": "Elige un producto para evaluar sus reglas.",
                "participant_id": None,
            },
            {
                "code": "financial_profile",
                "complete": False,
                "message": "Registra el perfil financiero de Laura Gómez Vélez.",
                "participant_id": str(primary.id),
            },
        ],
        "documents": {
            "verified": False,
            "required_total": 0,
            "completed_total": 0,
            "message": NOT_CONFIGURED_MESSAGE,
            "slots": [],
        },
    }


def test_complete_data_reaches_100_but_documents_keep_it_not_ready(
    advisor_client: APIClient, in_review: CreditApplication, primary: ApplicationParticipant
) -> None:
    FinancialProfile.objects.create(
        participant=primary,
        employment_profile_item=catalog_item("employment_profile", "EMPLOYEE"),
    )

    body = completeness(advisor_client, in_review)

    assert body["data_percentage"] == 100
    assert body["documents_percentage"] == 0
    assert body["percentage"] == 50
    assert body["ready_to_file"] is False
    assert all(item["complete"] for item in body["items"])


@pytest.mark.usefixtures("documents_ok")
def test_ready_to_file_when_data_and_documents_are_complete(
    advisor_client: APIClient, in_review: CreditApplication, primary: ApplicationParticipant
) -> None:
    FinancialProfile.objects.create(
        participant=primary,
        employment_profile_item=catalog_item("employment_profile", "EMPLOYEE"),
    )

    body = completeness(advisor_client, in_review)

    assert (body["ready_to_file"], body["documents"]["verified"]) == (True, True)
    assert body["percentage"] == body["documents_percentage"] == 100
    assert body["ready_to_file_problems"] == []


def test_own_funds_skips_the_bank_items(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    add_financing(application, "OWN_FUNDS")

    body = completeness(advisor_client, application)

    assert [item["code"] for item in body["items"]] == [
        "property",
        "financing",
        "financial_profile",
    ]
    assert body["data_percentage"] == 33
    assert body["percentage"] == 16


def test_bank_evaluation_item_explains_what_is_missing(
    advisor_client: APIClient, in_review: CreditApplication, blocking_rule: BankPolicyRule
) -> None:
    def evaluation_item() -> dict[str, Any]:
        items = completeness(advisor_client, in_review)["items"]
        return next(item for item in items if item["code"] == "bank_evaluation")

    # La evaluación automática (sin la regla todavía) está vigente y elegible.
    assert evaluation_item()["complete"] is True

    put(advisor_client, in_review, "property", {**PROPERTY, "estimated_value_cop": 1}, '"3"')
    assert evaluation_item()["message"] == (
        "La última evaluación no corresponde a los datos actuales: evalúa de nuevo."
    )

    advisor_client.post(application_url(in_review, "/bank-rule-evaluations"))
    assert evaluation_item() == {
        "code": "bank_evaluation",
        "complete": False,
        "message": "La última evaluación tiene reglas bloqueantes.",
        "participant_id": None,
    }

    BankRuleEvaluation.objects.all().delete()
    assert evaluation_item()["message"] == "Evalúa las reglas del banco."


def test_only_active_contributors_need_a_profile(
    advisor_client: APIClient,
    application: CreditApplication,
    make_client: Callable[..., Client],
) -> None:
    for number, extra in (
        ("79555111", {"contributes_income": False}),
        ("52444222", {"is_active": False}),
    ):
        ApplicationParticipant.objects.create(
            application=application,
            client=make_client(document_number=number),
            role=ParticipantRole.SOLIDARY_DEBTOR,
            **extra,
        )

    items = completeness(advisor_client, application)["items"]

    assert [item["code"] for item in items].count("financial_profile") == 1


# --- Acceso -----------------------------------------------------------------------------


def call(endpoint: str, client: APIClient, application: CreditApplication) -> Any:
    if endpoint == "transition":
        return transition(client, application, "WAITING_BUYER_DATA")
    if endpoint == "withdraw":
        return withdraw(client, application)
    return client.get(application_url(application, f"/{endpoint}"))


ENDPOINTS = ["transition", "withdraw", "status-history", "available-actions", "completeness"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_broker_and_partner_have_no_access(
    endpoint: str,
    broker_client: APIClient,
    partner_client: APIClient,
    application: CreditApplication,
) -> None:
    assert call(endpoint, broker_client, application).status_code == 403
    assert call(endpoint, partner_client, application).status_code == 403


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_application_out_of_scope_is_404(
    endpoint: str, other_advisor_client: APIClient, application: CreditApplication
) -> None:
    assert_error(call(endpoint, other_advisor_client, application), 404, "RESOURCE_NOT_FOUND")


def test_admin_can_transition(admin_client: APIClient, application: CreditApplication) -> None:
    assert transition(admin_client, application, "WAITING_BUYER_DATA").status_code == 200


# --- Guarda y completitud con el expediente real (paso 10, Tanda 4) ----------------------


def guard_details(client: APIClient, application: CreditApplication) -> list[dict[str, Any]]:
    """Intenta pasar a READY_TO_FILE y devuelve los `details` del 422."""
    application.refresh_from_db(fields=["version"])
    response = transition(client, application, "READY_TO_FILE", version=application.version)
    return list(assert_error(response, 422, "APPLICATION_NOT_READY")["details"])


def review_slot(client: APIClient, slot: ApplicationDocumentSlot, **data: Any) -> Any:
    response = client.patch(f"/api/v1/document-slots/{slot.id}/review", data, format="json")
    assert response.status_code == 200, response.content
    return response


def test_completeness_and_the_guard_agree_in_review(
    advisor_client: APIClient, in_review: CreditApplication, blocking_rule: BankPolicyRule
) -> None:
    # Versión 4 sin evaluación vigente: la completitud evalúa en memoria y no guarda.
    put(advisor_client, in_review, "financing", bank_credit(term_months=200), '"3"')
    evaluations = BankRuleEvaluation.objects.count()

    body = completeness(advisor_client, in_review)

    assert BankRuleEvaluation.objects.count() == evaluations
    assert body["ready_to_file"] is False
    codes = {problem["code"] for problem in body["ready_to_file_problems"]}
    assert codes == {"BANK_RULE_BLOCKED", "DOCUMENT_PENDING"}
    assert body["ready_to_file_problems"] == guard_details(advisor_client, in_review)
    # La guarda sí guarda la evaluación.
    assert BankRuleEvaluation.objects.count() == evaluations + 1


def test_a_ready_application_that_stops_complying_stays_ready(
    advisor_client: APIClient, in_review: CreditApplication, documents_ok: None
) -> None:
    slot = ApplicationDocumentSlot.objects.filter(application=in_review, is_required=True).first()
    assert slot is not None
    # Un obligatorio sin archivo: se exonera, y reabrirlo lo deja PENDING.
    ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(
        is_waivable=True, status=SlotStatus.PENDING, current_file=None
    )
    review_slot(advisor_client, slot, decision="WAIVED", reason_code="NOT_APPLICABLE")
    assert transition(advisor_client, in_review, "READY_TO_FILE", version=3).status_code == 200
    assert completeness(advisor_client, in_review)["ready_to_file"] is True

    review_slot(advisor_client, slot, decision="REOPENED", internal_comment="Se exoneró por error.")

    # Sigue en READY_TO_FILE y con la misma versión (decisión 29).
    in_review.refresh_from_db()
    assert (in_review.status, in_review.version) == ("READY_TO_FILE", 4)
    body = completeness(advisor_client, in_review)
    assert body["ready_to_file"] is False
    assert [(p["code"], p["resource_id"]) for p in body["ready_to_file_problems"]] == [
        ("DOCUMENT_PENDING", str(slot.pk))
    ]
    # La misma función, con los bloqueos de la guarda, dice lo mismo.
    with transaction.atomic():
        locked = CreditApplication.objects.select_for_update().get(pk=in_review.pk)
        problems = services.ready_to_file_problems(locked, dossier=check_dossier(locked, lock=True))
    assert problems == body["ready_to_file_problems"]
    # Al volver a revisión, la guarda no la deja pasar otra vez.
    assert transition(advisor_client, in_review, "DOCUMENTS_REVIEW", version=4).status_code == 200
    assert guard_details(advisor_client, in_review) == body["ready_to_file_problems"]


def test_completeness_lists_only_the_required_slots(
    advisor_client: APIClient, in_review: CreditApplication
) -> None:
    ApplicationDocumentSlot.objects.filter(application=in_review).update(is_required=False)
    first = ApplicationDocumentSlot.objects.filter(application=in_review).first()
    assert first is not None
    ApplicationDocumentSlot.objects.filter(pk=first.pk).update(is_required=True)

    documents = completeness(advisor_client, in_review)["documents"]

    assert [row["slot_id"] for row in documents["slots"]] == [str(first.pk)]
    row = documents["slots"][0]
    assert row.pop("label").startswith(first.document_type.name)
    assert row == {
        "slot_id": str(first.pk),
        "participant_id": str(first.participant_id) if first.participant_id else None,
        "document_type": {"code": first.document_type.code, "name": first.document_type.name},
        "status": "PENDING",
        "status_label": "Pendiente",
        "alternative_group_code": None,
        "expires_at": None,
        "complete": False,
    }
    assert (documents["required_total"], documents["completed_total"]) == (1, 0)
