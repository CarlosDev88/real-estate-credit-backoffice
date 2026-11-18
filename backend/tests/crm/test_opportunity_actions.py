"""Brechas de oportunidades (TAREA-brechas-2, parte 1): acciones con tipo y motivo,
`status_label`, historial de asesores tipado, `notes` al crear y asignación automática
cuando la crea un asesor."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.activity.models import ActivityEventType, ActivityLog, ActivityVisibility
from apps.catalogs.models import CatalogItem, WorkflowTransition
from apps.catalogs.workflow import ActionKind, FlowType, OpportunityStatus
from apps.crm.actions import ACTION_KIND_BY_TARGET_STATUS, action_kind, reason_required
from apps.crm.models import Client, Opportunity, OpportunityAssignment
from apps.crm.services import SELF_ASSIGNMENT_REASON
from apps.crm.signals import opportunity_assigned, opportunity_created, opportunity_status_changed
from apps.identity.models import User
from tests.crm.conftest import OPPORTUNITIES_URL, opportunity_url
from tests.crm.test_opportunity_workflow import captured
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db


def create(api: APIClient, client: Client, **payload: Any) -> Any:
    return api.post(
        OPPORTUNITIES_URL,
        {"client_id": str(client.id), "origin_type": "DIRECT", **payload},
        format="json",
    )


def actions(body: dict[str, Any]) -> list[tuple[str, str, bool]]:
    return [(a["code"], a["kind"], a["reason_required"]) for a in body["available_actions"]]


@pytest.fixture
def created_events() -> Iterator[list[dict[str, Any]]]:
    yield from captured(opportunity_created)


@pytest.fixture
def assigned_events() -> Iterator[list[dict[str, Any]]]:
    yield from captured(opportunity_assigned)


@pytest.fixture
def status_events() -> Iterator[list[dict[str, Any]]]:
    yield from captured(opportunity_status_changed)


# --- Tipo y motivo de cada acción -------------------------------------------------------


def test_every_status_has_a_kind() -> None:
    assert set(ACTION_KIND_BY_TARGET_STATUS) == set(OpportunityStatus.values)


def test_every_seeded_transition_has_the_expected_kind_and_reason() -> None:
    seeded = WorkflowTransition.objects.filter(flow_type=FlowType.OPPORTUNITY)

    got = {t.code: (action_kind(t), reason_required(t)) for t in seeded}

    open_statuses = ["NEW", "ASSIGNED", "CONTACTED", "IN_PROGRESS"]
    assert got == {
        "ASSIGN": (ActionKind.SECONDARY, False),
        "MARK_CONTACTED": (ActionKind.SECONDARY, False),
        "START_PROGRESS": (ActionKind.SECONDARY, False),
        **{f"CONVERT_{s}": (ActionKind.PRIMARY, False) for s in open_statuses[1:]},
        **{f"MARK_LOST_{s}": (ActionKind.DESTRUCTIVE, True) for s in open_statuses},
        **{f"CANCEL_{s}": (ActionKind.DESTRUCTIVE, False) for s in open_statuses},
    }


def test_actions_are_ordered_by_kind_with_labels(
    admin_client: APIClient,
    advisor_user: User,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> None:
    opportunity = make_opportunity(
        make_client(), assigned_advisor=advisor_user, status=OpportunityStatus.CONTACTED
    )

    body = admin_client.get(opportunity_url(opportunity)).json()

    assert actions(body) == [
        ("CONVERT_CONTACTED", "primary", False),
        ("START_PROGRESS", "secondary", False),
        ("CANCEL_CONTACTED", "destructive", False),
        ("MARK_LOST_CONTACTED", "destructive", True),
    ]
    assert body["available_actions"][0] == {
        "code": "CONVERT_CONTACTED",
        "label": "Convertir en solicitud",
        "kind": "primary",
        "target_status": "CONVERTED",
        "target_status_label": "Convertida",
        "reason_required": False,
    }


def test_actions_are_filtered_by_role(
    broker_client: APIClient,
    advisor_client: APIClient,
    advisor_user: User,
    broker_user: User,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> None:
    # Una transición sin el rol del asesor no le aparece.
    WorkflowTransition.objects.get(flow_type=FlowType.OPPORTUNITY, code="START_PROGRESS").roles.set(
        []
    )
    opportunity = make_opportunity(
        make_client(),
        origin_user=broker_user,
        assigned_advisor=advisor_user,
        status=OpportunityStatus.CONTACTED,
    )

    body = advisor_client.get(opportunity_url(opportunity)).json()

    assert [a["code"] for a in body["available_actions"]] == [
        "CONVERT_CONTACTED",
        "CANCEL_CONTACTED",
        "MARK_LOST_CONTACTED",
    ]
    # El broker recibe el resumen, sin acciones.
    assert "available_actions" not in broker_client.get(opportunity_url(opportunity)).json()


# --- status_label -----------------------------------------------------------------------


def test_status_label_comes_from_the_status_catalog(
    admin_client: APIClient,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> None:
    labels = dict(
        CatalogItem.objects.filter(catalog__code="opportunity_status").values_list("code", "label")
    )
    # Las etiquetas del catálogo y las del código son las mismas (una sola fuente visible).
    assert labels == {str(value): str(label) for value, label in OpportunityStatus.choices}

    for index, status in enumerate(OpportunityStatus.values):
        make_opportunity(
            make_client(document_number=f"10324459{index:02d}"),
            status=status,
            lost_reason_item=CatalogItem.objects.get(
                catalog__code="opportunity_lost_reason", code="OTHER"
            )
            if status == OpportunityStatus.LOST
            else None,
        )

    items = admin_client.get(OPPORTUNITIES_URL, {"page_size": 50}).json()["items"]

    assert {item["status"]: item["status_label"] for item in items} == labels


def test_list_queries_do_not_grow_with_the_rows(
    admin_client: APIClient,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> None:
    make_opportunity(make_client(document_number="1032445901"))
    with CaptureQueriesContext(connection) as one:
        assert admin_client.get(OPPORTUNITIES_URL).status_code == 200
    for index in range(2, 6):
        make_opportunity(make_client(document_number=f"103244590{index}"))
    with CaptureQueriesContext(connection) as five:
        assert admin_client.get(OPPORTUNITIES_URL).status_code == 200

    assert len(five) == len(one)


# --- Crear: notas y asignación automática -----------------------------------------------


def test_advisor_who_creates_it_is_assigned_in_the_same_transaction(
    advisor_client: APIClient,
    advisor_user: User,
    make_client: Callable[..., Client],
    created_events: list[dict[str, Any]],
    assigned_events: list[dict[str, Any]],
    status_events: list[dict[str, Any]],
) -> None:
    client = make_client(created_by=advisor_user)

    response = create(advisor_client, client)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "ASSIGNED"
    assert body["status_label"] == "Asignada"
    assert body["origin_user"]["id"] == str(advisor_user.id)
    assert body["assigned_advisor"]["id"] == str(advisor_user.id)
    assert body["assignments"] == [
        {
            "id": body["assignments"][0]["id"],
            "advisor": {"id": str(advisor_user.id), "name": advisor_user.get_full_name()},
            "assigned_by": {"id": str(advisor_user.id), "name": advisor_user.get_full_name()},
            "reason": SELF_ASSIGNMENT_REASON,
            "created_at": body["assignments"][0]["created_at"],
            "ended_at": None,
        }
    ]
    assert "ASSIGN" not in [a["code"] for a in body["available_actions"]]
    assert "MARK_CONTACTED" in [a["code"] for a in body["available_actions"]]

    opportunity = Opportunity.objects.get()
    assert OpportunityAssignment.objects.get(opportunity=opportunity).advisor == advisor_user
    assert [e["notes"] for e in created_events] == [""]
    assert [(e["previous_advisor_id"], e["advisor_id"]) for e in assigned_events] == [
        (None, advisor_user.id)
    ]
    assert [(e["from_status"], e["to_status"], e["transition_code"]) for e in status_events] == [
        ("NEW", "ASSIGNED", "ASSIGN")
    ]


def test_broker_and_admin_create_new_opportunities_without_advisor(
    admin_client: APIClient,
    broker_client: APIClient,
    broker_user: User,
    make_client: Callable[..., Client],
    assigned_events: list[dict[str, Any]],
) -> None:
    by_broker = create(broker_client, make_client(created_by=broker_user))
    by_admin = create(admin_client, make_client(document_number="1032445909"))

    assert by_broker.status_code == 201, by_broker.content
    assert by_broker.json()["status"] == "NEW"
    assert by_broker.json()["advisor_name"] is None
    assert by_admin.json()["status"] == "NEW"
    assert by_admin.json()["assignments"] == []
    assert not OpportunityAssignment.objects.exists()
    assert assigned_events == []


def test_without_the_assign_transition_nothing_is_created(
    advisor_client: APIClient, advisor_user: User, make_client: Callable[..., Client]
) -> None:
    WorkflowTransition.objects.filter(flow_type=FlowType.OPPORTUNITY, code="ASSIGN").update(
        is_active=False
    )

    response = create(advisor_client, make_client(created_by=advisor_user))

    assert_error(response, 409, "INVALID_STATE_TRANSITION")
    assert not Opportunity.objects.exists()


def test_notes_become_the_first_internal_note(
    broker_client: APIClient, broker_user: User, make_client: Callable[..., Client]
) -> None:
    response = create(
        broker_client, make_client(created_by=broker_user), notes="Interesada en vivienda nueva"
    )

    assert response.status_code == 201, response.content
    note = ActivityLog.objects.get(event_type=ActivityEventType.NOTE_ADDED)
    assert str(note.opportunity_id) == response.json()["id"]
    assert note.client_id == Opportunity.objects.get().client_id
    assert note.application_id is None
    assert note.visibility == ActivityVisibility.INTERNAL
    assert note.message == "Interesada en vivienda nueva"
    assert note.actor_user == broker_user
    assert note.title == f"Nota de {broker_user.get_full_name()}"


def test_without_notes_no_note_is_recorded(
    admin_client: APIClient, make_client: Callable[..., Client]
) -> None:
    assert create(admin_client, make_client(), notes="").status_code == 201
    assert create(admin_client, make_client(document_number="1032445909")).status_code == 201

    assert not ActivityLog.objects.filter(event_type=ActivityEventType.NOTE_ADDED).exists()


def test_notes_are_limited_to_2000_characters(
    admin_client: APIClient, make_client: Callable[..., Client]
) -> None:
    body = assert_error(
        create(admin_client, make_client(), notes="x" * 2001), 400, "VALIDATION_ERROR"
    )

    assert body["details"][0]["field"] == "notes"
    assert not Opportunity.objects.exists()
