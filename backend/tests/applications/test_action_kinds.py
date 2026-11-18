"""Tipo de cada acción disponible (`kind`) y orden de la lista: principales,
secundarias y destructivas."""

import pytest
from rest_framework.test import APIClient

from apps.applications.actions import (
    ACTION_KIND_BY_TARGET_STATUS,
    BACKWARD_TRANSITION_CODES,
    ActionKind,
    action_kind,
    reason_required,
)
from apps.applications.models import CreditApplication
from apps.catalogs.models import WorkflowTransition
from apps.catalogs.workflow import ApplicationStatus, FlowType
from tests.applications.conftest import application_url

pytestmark = pytest.mark.django_db

PRIMARY = ActionKind.PRIMARY
SECONDARY = ActionKind.SECONDARY
DESTRUCTIVE = ActionKind.DESTRUCTIVE

OPEN = ["DRAFT", "WAITING_BUYER_DATA", "WAITING_DOCUMENTS", "DOCUMENTS_REVIEW", "READY_TO_FILE"]
WITHDRAWABLE = [
    *OPEN,
    "FILED",
    "FILING_VALIDATION",
    "CREDIT_ANALYSIS",
    "BANK_OBSERVATION",
    "APPROVED",
    "LEGALIZATION",
]

# Todas las transiciones manuales sembradas de la solicitud, con su tipo esperado.
EXPECTED_KINDS: dict[str, ActionKind] = {
    "REQUEST_BUYER_DATA": PRIMARY,
    "REQUEST_DOCUMENTS_FROM_DRAFT": PRIMARY,
    "REQUEST_DOCUMENTS": PRIMARY,
    "START_DOCUMENTS_REVIEW": PRIMARY,
    "MARK_READY_TO_FILE": PRIMARY,
    "MARK_READY_TO_REFILE": PRIMARY,
    "START_LEGALIZATION": PRIMARY,
    "RETURN_TO_DOCUMENTS": SECONDARY,
    "REOPEN_REVIEW": SECONDARY,
    **{f"MARK_OWN_FUNDS_{status}": SECONDARY for status in OPEN},
    **{f"MARK_EXTERNAL_CREDIT_{status}": SECONDARY for status in OPEN},
    **{f"CANCEL_{status}": DESTRUCTIVE for status in OPEN},
    **{f"WITHDRAW_{status}": DESTRUCTIVE for status in WITHDRAWABLE},
}


def set_status(application: CreditApplication, status: str) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(status=status)


def kinds(client: APIClient, application: CreditApplication) -> list[tuple[str, str]]:
    response = client.get(application_url(application, "/available-actions"))
    assert response.status_code == 200, response.content
    return [(action["code"], action["kind"]) for action in response.json()]


def test_every_status_has_a_kind() -> None:
    assert set(ACTION_KIND_BY_TARGET_STATUS) == set(ApplicationStatus.values)


def test_every_seeded_manual_transition_has_the_expected_kind() -> None:
    manual = WorkflowTransition.objects.filter(
        flow_type=FlowType.APPLICATION, system_only=False
    ).order_by("code")

    assert {transition.code for transition in manual} == set(EXPECTED_KINDS)
    assert {t.code: action_kind(t) for t in manual} == EXPECTED_KINDS
    assert BACKWARD_TRANSITION_CODES <= set(EXPECTED_KINDS)


def test_draft_actions_are_ordered_by_kind(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    assert kinds(advisor_client, application) == [
        ("REQUEST_BUYER_DATA", "primary"),
        ("REQUEST_DOCUMENTS_FROM_DRAFT", "primary"),
        ("MARK_EXTERNAL_CREDIT_DRAFT", "secondary"),
        ("MARK_OWN_FUNDS_DRAFT", "secondary"),
        ("CANCEL_DRAFT", "destructive"),
        ("WITHDRAW_DRAFT", "destructive"),
    ]


def test_backward_action_is_secondary_and_detail_keeps_the_order(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.DOCUMENTS_REVIEW)

    listed = kinds(advisor_client, application)

    assert listed == [
        ("MARK_READY_TO_FILE", "primary"),
        ("MARK_EXTERNAL_CREDIT_DOCUMENTS_REVIEW", "secondary"),
        ("MARK_OWN_FUNDS_DOCUMENTS_REVIEW", "secondary"),
        ("RETURN_TO_DOCUMENTS", "secondary"),
        ("CANCEL_DOCUMENTS_REVIEW", "destructive"),
        ("WITHDRAW_DOCUMENTS_REVIEW", "destructive"),
    ]
    detail = advisor_client.get(application_url(application)).json()
    assert [(a["code"], a["kind"]) for a in detail["available_actions"]] == listed


def test_admin_gets_the_same_order(admin_client: APIClient, application: CreditApplication) -> None:
    set_status(application, ApplicationStatus.READY_TO_FILE)

    assert kinds(admin_client, application) == [
        ("MARK_EXTERNAL_CREDIT_READY_TO_FILE", "secondary"),
        ("MARK_OWN_FUNDS_READY_TO_FILE", "secondary"),
        ("REOPEN_REVIEW", "secondary"),
        ("CANCEL_READY_TO_FILE", "destructive"),
        ("WITHDRAW_READY_TO_FILE", "destructive"),
    ]


def test_reason_is_required_for_closures_with_reason_and_withdrawals() -> None:
    manual = WorkflowTransition.objects.filter(flow_type=FlowType.APPLICATION, system_only=False)

    required = {t.code for t in manual if reason_required(t)}

    assert required == {
        code
        for code in EXPECTED_KINDS
        if code.startswith(("CANCEL_", "WITHDRAW_", "MARK_OWN_FUNDS_", "MARK_EXTERNAL_CREDIT_"))
    }


def test_available_actions_carry_reason_required(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = advisor_client.get(application_url(application, "/available-actions"))

    assert [(a["code"], a["reason_required"]) for a in response.json()] == [
        ("REQUEST_BUYER_DATA", False),
        ("REQUEST_DOCUMENTS_FROM_DRAFT", False),
        ("MARK_EXTERNAL_CREDIT_DRAFT", True),
        ("MARK_OWN_FUNDS_DRAFT", True),
        ("CANCEL_DRAFT", True),
        ("WITHDRAW_DRAFT", True),
    ]
