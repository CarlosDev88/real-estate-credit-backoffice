import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.dispatch import Signal
from rest_framework.test import APIClient

from apps.crm.models import Client, Opportunity, OpportunityAssignment
from apps.crm.signals import opportunity_assigned, opportunity_status_changed
from apps.identity.models import User
from tests.crm.conftest import catalog_item, opportunity_url
from tests.helpers import assert_error
from tests.partners.conftest import client_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def opportunity(
    make_client: Callable[..., Client], make_opportunity: Callable[..., Opportunity]
) -> Opportunity:
    return make_opportunity(make_client())


def captured(signal: Signal) -> Iterator[list[dict[str, Any]]]:
    received: list[dict[str, Any]] = []

    def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    signal.connect(handler)
    try:
        yield received
    finally:
        signal.disconnect(handler)


@pytest.fixture
def assigned_events() -> Iterator[list[dict[str, Any]]]:
    yield from captured(opportunity_assigned)


@pytest.fixture
def status_events() -> Iterator[list[dict[str, Any]]]:
    yield from captured(opportunity_status_changed)


def assign(api: APIClient, opportunity: Opportunity, advisor: User | str, **payload: Any) -> Any:
    advisor_id = advisor if isinstance(advisor, str) else str(advisor.id)
    return api.post(
        f"{opportunity_url(opportunity)}/assignments", {"advisor_id": advisor_id, **payload}
    )


def transition(api: APIClient, opportunity: Opportunity, target: str, **payload: Any) -> Any:
    return api.post(
        f"{opportunity_url(opportunity)}/transitions", {"target_status": target, **payload}
    )


# --- Asignación -------------------------------------------------------------------------


def test_assigning_a_new_opportunity_moves_it_to_assigned(
    admin_client: APIClient,
    admin_user: User,
    advisor_user: User,
    opportunity: Opportunity,
    assigned_events: list[dict[str, Any]],
    status_events: list[dict[str, Any]],
) -> None:
    response = assign(admin_client, opportunity, advisor_user, reason="Zona norte")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == "ASSIGNED"
    assert body["assigned_advisor"]["id"] == str(advisor_user.id)
    assert [
        (item["advisor"]["id"], item["reason"], item["ended_at"]) for item in body["assignments"]
    ] == [(str(advisor_user.id), "Zona norte", None)]
    assert body["assignments"][0]["assigned_by"]["id"] == str(admin_user.id)
    assert "MARK_CONTACTED" in body["available_actions"]

    assert [(e["previous_advisor_id"], e["advisor_id"], e["actor"]) for e in assigned_events] == [
        (None, advisor_user.id, admin_user)
    ]
    assert isinstance(assigned_events[0]["advisor_id"], uuid.UUID)
    assert "advisor" not in assigned_events[0]
    assert [(e["from_status"], e["to_status"], e["transition_code"]) for e in status_events] == [
        ("NEW", "ASSIGNED", "ASSIGN")
    ]


def test_reassignment_keeps_the_history(
    admin_client: APIClient,
    advisor_user: User,
    other_advisor: User,
    opportunity: Opportunity,
    assigned_events: list[dict[str, Any]],
    status_events: list[dict[str, Any]],
) -> None:
    assign(admin_client, opportunity, advisor_user)

    body = assign(admin_client, opportunity, other_advisor, reason="Vacaciones").json()

    assert body["status"] == "ASSIGNED"
    assert body["assigned_advisor"]["id"] == str(other_advisor.id)
    history = OpportunityAssignment.objects.filter(opportunity=opportunity).order_by("created_at")
    assert [(a.advisor_id, a.ended_at is None) for a in history] == [
        (advisor_user.id, False),
        (other_advisor.id, True),
    ]
    # RF-11: la reasignación queda disponible para la bitácora.
    last_event = assigned_events[-1]
    assert (last_event["previous_advisor_id"], last_event["advisor_id"]) == (
        advisor_user.id,
        other_advisor.id,
    )
    assert isinstance(last_event["previous_advisor_id"], uuid.UUID)
    assert last_event["reason"] == "Vacaciones"
    # Solo la primera asignación cambió el estado.
    assert len(status_events) == 1


def test_assigning_the_same_advisor_does_nothing(
    admin_client: APIClient,
    advisor_user: User,
    opportunity: Opportunity,
    assigned_events: list[dict[str, Any]],
) -> None:
    assign(admin_client, opportunity, advisor_user)

    response = assign(admin_client, opportunity, advisor_user)

    assert response.status_code == 200, response.content
    assert OpportunityAssignment.objects.count() == 1
    assert len(assigned_events) == 1


def test_assigned_advisor_gains_access_to_opportunity_and_client(
    admin_client: APIClient, advisor_user: User, opportunity: Opportunity
) -> None:
    advisor_api = client_for(advisor_user)
    assert advisor_api.get(opportunity_url(opportunity)).status_code == 404

    assign(admin_client, opportunity, advisor_user)

    assert advisor_api.get(opportunity_url(opportunity)).status_code == 200
    assert advisor_api.get(f"/api/v1/clients/{opportunity.client_id}").status_code == 200


def test_advisor_who_hands_over_an_opportunity_loses_access(
    advisor_client: APIClient,
    advisor_user: User,
    other_advisor: User,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> None:
    opportunity = make_opportunity(make_client(), assigned_advisor=advisor_user, status="ASSIGNED")

    response = assign(advisor_client, opportunity, other_advisor)

    assert response.status_code == 204
    opportunity.refresh_from_db()
    assert opportunity.assigned_advisor == other_advisor
    assert_error(advisor_client.get(opportunity_url(opportunity)), 404, "RESOURCE_NOT_FOUND")


@pytest.mark.parametrize("role_code", ["INDEPENDENT_BROKER", "ADMIN"])
def test_only_advisors_can_be_responsible(
    admin_client: APIClient,
    make_user: Callable[..., User],
    opportunity: Opportunity,
    role_code: str,
) -> None:
    candidate = make_user(email="candidato@example.com", role_code=role_code)

    assert_error(assign(admin_client, opportunity, candidate), 422, "ADVISOR_NOT_ELIGIBLE")


def test_inactive_advisors_cannot_be_responsible(
    admin_client: APIClient, other_advisor: User, opportunity: Opportunity
) -> None:
    other_advisor.is_active = False
    other_advisor.save()

    assert_error(assign(admin_client, opportunity, other_advisor), 422, "ADVISOR_NOT_ELIGIBLE")


def test_unknown_advisor_is_a_validation_error(
    admin_client: APIClient, opportunity: Opportunity
) -> None:
    body = assert_error(
        assign(admin_client, opportunity, str(uuid.uuid4())), 400, "VALIDATION_ERROR"
    )
    assert body["details"][0]["field"] == "advisor_id"


def test_closed_opportunities_cannot_be_assigned(
    admin_client: APIClient,
    advisor_user: User,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> None:
    opportunity = make_opportunity(make_client(), status="CANCELLED")

    assert_error(assign(admin_client, opportunity, advisor_user), 409, "OPPORTUNITY_NOT_EDITABLE")


def test_broker_cannot_assign(
    broker_client: APIClient,
    broker_user: User,
    advisor_user: User,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> None:
    opportunity = make_opportunity(make_client(), origin_user=broker_user)

    assert_error(assign(broker_client, opportunity, advisor_user), 403, "PERMISSION_DENIED")


# --- Transiciones -----------------------------------------------------------------------


@pytest.fixture
def assigned(
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    advisor_user: User,
) -> Opportunity:
    return make_opportunity(make_client(), assigned_advisor=advisor_user, status="ASSIGNED")


def test_advisor_moves_opportunity_through_the_flow(
    advisor_client: APIClient,
    advisor_user: User,
    assigned: Opportunity,
    status_events: list[dict[str, Any]],
) -> None:
    contacted = transition(advisor_client, assigned, "CONTACTED", comment="Llamada inicial")
    assert contacted.status_code == 200, contacted.content
    assert contacted.json()["status"] == "CONTACTED"
    assert "START_PROGRESS" in contacted.json()["available_actions"]

    in_progress = transition(advisor_client, assigned, "IN_PROGRESS")
    assert in_progress.json()["status"] == "IN_PROGRESS"

    assert [
        (e["from_status"], e["to_status"], e["transition_code"], e["actor"], e["comment"])
        for e in status_events
    ] == [
        ("ASSIGNED", "CONTACTED", "MARK_CONTACTED", advisor_user, "Llamada inicial"),
        ("CONTACTED", "IN_PROGRESS", "START_PROGRESS", advisor_user, ""),
    ]


def test_skipping_a_state_is_rejected(admin_client: APIClient, opportunity: Opportunity) -> None:
    assert_error(
        transition(admin_client, opportunity, "CONTACTED"), 409, "INVALID_STATE_TRANSITION"
    )
    opportunity.refresh_from_db()
    assert opportunity.status == "NEW"


def test_assigned_is_reached_only_through_assignments(
    admin_client: APIClient, opportunity: Opportunity
) -> None:
    body = assert_error(transition(admin_client, opportunity, "ASSIGNED"), 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "target_status"


def test_conversion_is_not_available_yet(admin_client: APIClient, assigned: Opportunity) -> None:
    # La agrega el módulo de solicitudes: se convierte al crear la solicitud.
    assert_error(transition(admin_client, assigned, "CONVERTED"), 409, "INVALID_STATE_TRANSITION")


def test_lost_requires_a_reason(admin_client: APIClient, assigned: Opportunity) -> None:
    body = assert_error(transition(admin_client, assigned, "LOST"), 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "reason_code"

    response = transition(admin_client, assigned, "LOST", reason_code="NO_RESPONSE")

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "LOST"
    assert response.json()["lost_reason"]["code"] == "NO_RESPONSE"
    assert response.json()["available_actions"] == []
    assigned.refresh_from_db()
    assert assigned.lost_reason_item == catalog_item("opportunity_lost_reason", "NO_RESPONSE")


def test_reason_only_applies_to_lost(admin_client: APIClient, assigned: Opportunity) -> None:
    body = assert_error(
        transition(admin_client, assigned, "CANCELLED", reason_code="NO_RESPONSE"),
        400,
        "VALIDATION_ERROR",
    )
    assert body["details"][0]["field"] == "reason_code"


@pytest.mark.parametrize("closed_status", ["LOST", "CANCELLED"])
def test_closed_opportunities_do_not_transition(
    admin_client: APIClient,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    closed_status: str,
) -> None:
    reason = catalog_item("opportunity_lost_reason", "OTHER") if closed_status == "LOST" else None
    opportunity = make_opportunity(make_client(), status=closed_status, lost_reason_item=reason)

    assert_error(
        transition(admin_client, opportunity, "CANCELLED"), 409, "INVALID_STATE_TRANSITION"
    )


def test_broker_cannot_transition(
    broker_client: APIClient,
    broker_user: User,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> None:
    opportunity = make_opportunity(make_client(), origin_user=broker_user)

    assert_error(transition(broker_client, opportunity, "CANCELLED"), 403, "PERMISSION_DENIED")


def test_transition_requires_an_allowed_role(
    make_user: Callable[..., User],
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> None:
    """Con el permiso pero sin un rol de la transición: 403, no 409."""
    broker = make_user(
        email="broker@example.com",
        role_code="INDEPENDENT_BROKER",
        permissions=["opportunities.transition"],
    )
    opportunity = make_opportunity(make_client(), origin_user=broker)

    assert_error(transition(client_for(broker), opportunity, "CANCELLED"), 403, "PERMISSION_DENIED")
    opportunity.refresh_from_db()
    assert opportunity.status == "NEW"
