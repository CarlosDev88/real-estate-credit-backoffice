"""`Client.applications_count` (TAREA-brechas-2, parte 1): solicitudes visibles en las que
el cliente participa con un papel vigente, en el listado y el detalle de `/clients`."""

from collections.abc import Callable
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.applications.models import ApplicationParticipant, CreditApplication, ParticipantRole
from apps.crm.models import Client, Opportunity
from apps.identity.models import User
from tests.applications.conftest import application_url

pytestmark = pytest.mark.django_db

CLIENTS_URL = "/api/v1/clients"


def count_in_list(api: APIClient, client: Client) -> Any:
    response = api.get(CLIENTS_URL, {"page_size": 100})
    assert response.status_code == 200, response.content
    return next(item for item in response.json()["items"] if item["id"] == str(client.id)).get(
        "applications_count"
    )


def count_in_detail(api: APIClient, client: Client) -> Any:
    response = api.get(f"{CLIENTS_URL}/{client.id}")
    assert response.status_code == 200, response.content
    return response.json().get("applications_count")


def visible_applications(api: APIClient, client: Client) -> int:
    response = api.get(f"{CLIENTS_URL}/{client.id}/applications")
    assert response.status_code == 200, response.content
    return int(response.json()["total"])


@pytest.fixture
def three_applications(
    buyer: Client,
    other_advisor: User,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    make_application: Callable[..., CreditApplication],
) -> list[CreditApplication]:
    """El comprador es titular de dos solicitudes del asesor y codeudor en una de otra
    asesora; en una cuarta estuvo y se retiró (no cuenta)."""
    mine = [make_application(make_opportunity(buyer)) for _ in range(2)]
    other_buyer = make_client(document_number="1032445999", first_names="Ana")
    foreign = make_application(
        make_opportunity(other_buyer, assigned_advisor=other_advisor),
        assigned_advisor=other_advisor,
    )
    ApplicationParticipant.objects.create(
        application=foreign, client=buyer, role=ParticipantRole.CO_APPLICANT
    )
    withdrawn = make_application(make_opportunity(other_buyer))
    ApplicationParticipant.objects.create(
        application=withdrawn, client=buyer, role=ParticipantRole.CO_APPLICANT, is_active=False
    )
    return [*mine, foreign]


def test_count_follows_the_visible_applications(
    advisor_client: APIClient,
    admin_client: APIClient,
    buyer: Client,
    three_applications: list[CreditApplication],
) -> None:
    assert count_in_list(advisor_client, buyer) == 2
    assert count_in_detail(advisor_client, buyer) == 2
    assert visible_applications(advisor_client, buyer) == 2

    assert count_in_list(admin_client, buyer) == 3
    assert count_in_detail(admin_client, buyer) == 3
    assert visible_applications(admin_client, buyer) == 3


def test_client_without_applications_counts_zero(
    advisor_client: APIClient, advisor_user: User, make_client: Callable[..., Client]
) -> None:
    client = make_client(document_number="1032445000", created_by=advisor_user)

    assert count_in_list(advisor_client, client) == 0
    assert count_in_detail(advisor_client, client) == 0


def test_create_and_update_responses_carry_the_count(
    admin_client: APIClient, buyer: Client, three_applications: list[CreditApplication]
) -> None:
    created = admin_client.post(
        CLIENTS_URL,
        {
            "document_type_code": "CC",
            "document_number": "1032445777",
            "first_names": "Pedro",
            "last_names": "Ruiz",
        },
        format="json",
    )
    updated = admin_client.patch(f"{CLIENTS_URL}/{buyer.id}", {"phone": "+573104458821"})

    assert created.status_code == 201, created.content
    assert created.json()["applications_count"] == 0
    assert updated.status_code == 200, updated.content
    assert updated.json()["applications_count"] == 3


def test_broker_does_not_get_the_count(
    broker_client: APIClient, broker_user: User, make_client: Callable[..., Client]
) -> None:
    client = make_client(document_number="1032445001", created_by=broker_user)

    assert count_in_list(broker_client, client) is None
    assert count_in_detail(broker_client, client) is None


def test_participant_client_has_no_count(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = advisor_client.get(application_url(application), {"include": "participants"})

    assert response.status_code == 200, response.content
    assert "applications_count" not in response.json()["participants"][0]["client"]


def test_list_queries_do_not_grow_with_the_rows(
    admin_client: APIClient,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    make_application: Callable[..., CreditApplication],
) -> None:
    def add_client(index: int) -> None:
        client = make_client(document_number=f"10324451{index:02d}")
        make_application(make_opportunity(client))

    add_client(0)
    with CaptureQueriesContext(connection) as one:
        assert admin_client.get(CLIENTS_URL).status_code == 200
    for index in range(1, 5):
        add_client(index)
    with CaptureQueriesContext(connection) as five:
        response = admin_client.get(CLIENTS_URL)

    assert len(five) == len(one)
    assert [item["applications_count"] for item in response.json()["items"]] == [1] * 5
