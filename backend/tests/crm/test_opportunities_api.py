import uuid
from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.catalogs.workflow import ProjectStatus
from apps.crm.models import Client, Opportunity
from apps.identity.models import User
from apps.partners.models import Project
from tests.crm.conftest import BROKER_OPPORTUNITIES_URL, OPPORTUNITIES_URL, opportunity_url
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

BROKER_OPPORTUNITY_FIELDS = {
    "id",
    "client_id",
    "client_name",
    "project_id",
    "project_name",
    "status",
    "advisor_name",
    "created_at",
    "updated_at",
}


def ids(response: Any) -> list[str]:
    assert response.status_code == 200, response.content
    return [item["id"] for item in response.json()["items"]]


def create(api: APIClient, client: Client, **payload: Any) -> Any:
    return api.post(
        OPPORTUNITIES_URL,
        {"client_id": str(client.id), "origin_type": "BROKER", **payload},
        format="json",
    )


# --- Crear ------------------------------------------------------------------------------


def test_admin_creates_new_opportunity_with_project(
    admin_client: APIClient,
    admin_user: User,
    make_client: Callable[..., Client],
    active_project: Project,
) -> None:
    client = make_client()

    response = create(admin_client, client, project_id=str(active_project.id))

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "NEW"
    assert body["client"] == {"id": str(client.id), "full_name": "Laura Gómez Vélez"}
    assert body["project"] == {
        "id": str(active_project.id),
        "name": "Verona 118",
        "partner_name": str(active_project.partner),
    }
    assert body["origin"]["code"] == "BROKER"
    assert body["origin_user"]["id"] == str(admin_user.id)
    assert body["assigned_advisor"] is None
    assert body["assignments"] == []
    assert body["available_actions"] == ["ASSIGN", "CANCEL_NEW", "MARK_LOST_NEW"]


def test_broker_creates_opportunity_for_own_contact(
    broker_client: APIClient, broker_user: User, make_client: Callable[..., Client]
) -> None:
    client = make_client(created_by=broker_user)

    response = create(broker_client, client)

    assert response.status_code == 201, response.content
    body = response.json()
    assert set(body) == BROKER_OPPORTUNITY_FIELDS
    assert body["status"] == "NEW"
    assert body["project_id"] is None
    assert Opportunity.objects.get().origin_user == broker_user


def test_client_must_be_visible(
    advisor_client: APIClient, make_client: Callable[..., Client]
) -> None:
    body = assert_error(create(advisor_client, make_client()), 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "client_id"


def test_project_must_be_active(
    admin_client: APIClient,
    make_client: Callable[..., Client],
    make_project: Callable[..., Project],
) -> None:
    draft = make_project(status=ProjectStatus.DRAFT)

    assert_error(
        create(admin_client, make_client(), project_id=str(draft.id)), 422, "PROJECT_NOT_ACTIVE"
    )


def test_unknown_project_is_a_validation_error(
    admin_client: APIClient, make_client: Callable[..., Client]
) -> None:
    body = assert_error(
        create(admin_client, make_client(), project_id=str(uuid.uuid4())), 400, "VALIDATION_ERROR"
    )
    assert body["details"][0]["field"] == "project_id"


def test_one_open_opportunity_per_client_and_project(
    admin_client: APIClient,
    make_client: Callable[..., Client],
    make_project: Callable[..., Project],
    active_project: Project,
) -> None:
    client = make_client()
    first_id = create(admin_client, client, project_id=str(active_project.id)).json()["id"]

    assert_error(
        create(admin_client, client, project_id=str(active_project.id)),
        409,
        "DUPLICATE_OPPORTUNITY",
    )

    # RF-12: otro proyecto es otra oportunidad independiente.
    other_project = make_project(name="Altos del Parque")
    assert create(admin_client, client, project_id=str(other_project.id)).status_code == 201

    # Cerrada la primera, se puede abrir de nuevo.
    admin_client.post(f"{opportunity_url(first_id)}/transitions", {"target_status": "CANCELLED"})
    assert create(admin_client, client, project_id=str(active_project.id)).status_code == 201


def test_one_open_opportunity_without_project(
    admin_client: APIClient, make_client: Callable[..., Client]
) -> None:
    client = make_client()
    create(admin_client, client)

    assert_error(create(admin_client, client), 409, "DUPLICATE_OPPORTUNITY")


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"origin_type": "INVENTADO"}, "origin_type"),
        ({"client_id": "no-uuid"}, "client_id"),
        ({"status": "CONVERTED"}, "status"),  # Campo no permitido: siempre nace NEW.
    ],
)
def test_create_opportunity_validates_input(
    admin_client: APIClient,
    make_client: Callable[..., Client],
    payload: dict[str, Any],
    field: str,
) -> None:
    body = assert_error(create(admin_client, make_client(), **payload), 400, "VALIDATION_ERROR")
    assert [detail["field"] for detail in body["details"]] == [field]


def test_partner_users_do_not_use_opportunities(partner_client: APIClient) -> None:
    assert_error(partner_client.get(OPPORTUNITIES_URL), 403, "PERMISSION_DENIED")


# --- Alcance y filtros ------------------------------------------------------------------


@pytest.fixture
def scoped_opportunities(
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    advisor_user: User,
    other_advisor: User,
    broker_user: User,
    other_broker: User,
    active_project: Project,
) -> dict[str, Opportunity]:
    client = make_client()
    return {
        "assigned_to_advisor": make_opportunity(
            client, assigned_advisor=advisor_user, status="ASSIGNED"
        ),
        "originated_by_advisor": make_opportunity(
            make_client(document_number="1000000002"), origin_user=advisor_user
        ),
        "from_broker": make_opportunity(
            make_client(document_number="1000000003", first_names="Pedro"),
            origin_user=broker_user,
            assigned_advisor=other_advisor,
            status="ASSIGNED",
            project=active_project,
        ),
        "from_other_broker": make_opportunity(
            make_client(document_number="1000000004"), origin_user=other_broker
        ),
    }


def test_admin_sees_every_opportunity(
    admin_client: APIClient, scoped_opportunities: dict[str, Opportunity]
) -> None:
    assert len(ids(admin_client.get(OPPORTUNITIES_URL))) == 4


def test_advisor_sees_assigned_and_originated_opportunities(
    advisor_client: APIClient, scoped_opportunities: dict[str, Opportunity]
) -> None:
    assert set(ids(advisor_client.get(OPPORTUNITIES_URL))) == {
        str(scoped_opportunities["assigned_to_advisor"].id),
        str(scoped_opportunities["originated_by_advisor"].id),
    }
    assert_error(
        advisor_client.get(opportunity_url(scoped_opportunities["from_broker"])),
        404,
        "RESOURCE_NOT_FOUND",
    )


def test_broker_sees_only_own_opportunities_as_summary(
    broker_client: APIClient, scoped_opportunities: dict[str, Opportunity]
) -> None:
    response = broker_client.get(OPPORTUNITIES_URL)

    assert ids(response) == [str(scoped_opportunities["from_broker"].id)]
    item = response.json()["items"][0]
    assert set(item) == BROKER_OPPORTUNITY_FIELDS
    assert item["client_name"] == "Pedro Gómez Vélez"
    assert item["project_name"] == "Verona 118"
    assert item["advisor_name"] == "Marta García"

    detail = broker_client.get(opportunity_url(scoped_opportunities["from_broker"])).json()
    assert set(detail) == BROKER_OPPORTUNITY_FIELDS
    assert_error(
        broker_client.get(opportunity_url(scoped_opportunities["from_other_broker"])),
        404,
        "RESOURCE_NOT_FOUND",
    )


def test_list_opportunities_filters(
    admin_client: APIClient,
    scoped_opportunities: dict[str, Opportunity],
    advisor_user: User,
    broker_user: User,
    active_project: Project,
) -> None:
    from_broker = str(scoped_opportunities["from_broker"].id)
    assert ids(admin_client.get(OPPORTUNITIES_URL, {"broker_id": str(broker_user.id)})) == [
        from_broker
    ]
    assert ids(admin_client.get(OPPORTUNITIES_URL, {"project_id": str(active_project.id)})) == [
        from_broker
    ]
    assert ids(admin_client.get(OPPORTUNITIES_URL, {"advisor_id": str(advisor_user.id)})) == [
        str(scoped_opportunities["assigned_to_advisor"].id)
    ]
    assert len(ids(admin_client.get(OPPORTUNITIES_URL, {"status": "ASSIGNED"}))) == 2
    assert ids(admin_client.get(OPPORTUNITIES_URL, {"search": "pedro"})) == [from_broker]
    assert ids(admin_client.get(OPPORTUNITIES_URL, {"search": "verona"})) == [from_broker]

    assert_error(admin_client.get(OPPORTUNITIES_URL, {"status": "X"}), 400, "VALIDATION_ERROR")
    assert_error(
        admin_client.get(OPPORTUNITIES_URL, {"advisor_id": "no-uuid"}), 400, "VALIDATION_ERROR"
    )


def test_client_opportunities_respect_scope(
    advisor_client: APIClient,
    advisor_user: User,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> None:
    client = make_client()
    mine = make_opportunity(client, assigned_advisor=advisor_user, status="ASSIGNED")
    make_opportunity(client, status="LOST", lost_reason_item=None)  # Fuera del alcance.

    url = f"/api/v1/clients/{client.id}/opportunities"
    assert ids(advisor_client.get(url)) == [str(mine.id)]
    assert ids(advisor_client.get(url, {"status": "NEW"})) == []


# --- Editar -----------------------------------------------------------------------------


def test_update_origin_and_project(
    admin_client: APIClient,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    active_project: Project,
) -> None:
    opportunity = make_opportunity(make_client())

    response = admin_client.patch(
        opportunity_url(opportunity),
        {"origin_type": "REFERRAL", "project_id": str(active_project.id)},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["origin"]["code"] == "REFERRAL"
    assert response.json()["project"]["id"] == str(active_project.id)

    response = admin_client.patch(opportunity_url(opportunity), {"project_id": None}, format="json")
    assert response.json()["project"] is None


def test_update_cannot_create_a_duplicate(
    admin_client: APIClient,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    active_project: Project,
) -> None:
    client = make_client()
    make_opportunity(client, project=active_project)
    opportunity = make_opportunity(client)

    assert_error(
        admin_client.patch(
            opportunity_url(opportunity), {"project_id": str(active_project.id)}, format="json"
        ),
        409,
        "DUPLICATE_OPPORTUNITY",
    )


def test_closed_opportunities_are_not_editable(
    admin_client: APIClient,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> None:
    opportunity = make_opportunity(make_client(), status="CANCELLED")

    assert_error(
        admin_client.patch(opportunity_url(opportunity), {"origin_type": "DIRECT"}, format="json"),
        409,
        "OPPORTUNITY_NOT_EDITABLE",
    )


def test_status_is_not_editable_by_patch(
    admin_client: APIClient,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> None:
    opportunity = make_opportunity(make_client())

    body = assert_error(
        admin_client.patch(opportunity_url(opportunity), {"status": "LOST"}, format="json"),
        400,
        "VALIDATION_ERROR",
    )
    assert body["details"][0]["field"] == "status"


# --- Bandeja del broker -----------------------------------------------------------------


def test_broker_inbox_lists_own_prospects(
    broker_client: APIClient, scoped_opportunities: dict[str, Opportunity]
) -> None:
    response = broker_client.get(BROKER_OPPORTUNITIES_URL)

    assert ids(response) == [str(scoped_opportunities["from_broker"].id)]
    assert set(response.json()["items"][0]) == BROKER_OPPORTUNITY_FIELDS
    assert ids(broker_client.get(BROKER_OPPORTUNITIES_URL, {"status": "NEW"})) == []


def test_broker_inbox_is_only_for_brokers(advisor_client: APIClient) -> None:
    assert_error(advisor_client.get(BROKER_OPPORTUNITIES_URL), 403, "PERMISSION_DENIED")
