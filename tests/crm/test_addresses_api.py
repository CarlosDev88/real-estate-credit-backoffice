from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.crm.models import Client, ClientAddress
from apps.identity.models import User
from tests.crm.conftest import client_url
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

ADDRESSES_URL = "/api/v1/client-addresses"

VALID_ADDRESS = {
    "address_type_code": "RESIDENCE",
    "city_code": "11001",
    "line1": "Calle 100 # 15-20",
}


@pytest.fixture
def own_client(advisor_user: User, make_client: Callable[..., Client]) -> Client:
    return make_client(created_by=advisor_user)


def add_address(api: APIClient, client: Client, **payload: Any) -> Any:
    return api.post(f"{client_url(client)}/addresses", {**VALID_ADDRESS, **payload})


def primary_lines(client: Client) -> list[str]:
    return list(client.addresses.filter(is_primary=True).values_list("line1", flat=True))


def test_first_address_becomes_primary(advisor_client: APIClient, own_client: Client) -> None:
    response = add_address(advisor_client, own_client, is_primary=False)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["is_primary"] is True
    assert body["client_id"] == str(own_client.id)
    assert body["address_type"] == {"code": "RESIDENCE", "label": "Residencia"}
    assert body["city"]["code"] == "11001"
    assert body["line2"] == ""


def test_new_primary_address_replaces_the_previous_one(
    advisor_client: APIClient, own_client: Client
) -> None:
    add_address(advisor_client, own_client)
    second = add_address(advisor_client, own_client, line1="Carrera 7 # 72-10")
    assert second.json()["is_primary"] is False

    add_address(advisor_client, own_client, line1="Avenida 68 # 1-1", is_primary=True)

    assert primary_lines(own_client) == ["Avenida 68 # 1-1"]
    listed = advisor_client.get(f"{client_url(own_client)}/addresses").json()["items"]
    assert listed[0]["line1"] == "Avenida 68 # 1-1"
    assert len(listed) == 3


def test_update_address_can_make_it_primary(advisor_client: APIClient, own_client: Client) -> None:
    add_address(advisor_client, own_client)
    other_id = add_address(advisor_client, own_client, line1="Carrera 7 # 72-10").json()["id"]

    response = advisor_client.patch(
        f"{ADDRESSES_URL}/{other_id}",
        {"is_primary": True, "city_code": "05001", "line2": "Apto 501"},
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["is_primary"] is True
    assert body["city"]["code"] == "05001"
    assert body["line2"] == "Apto 501"
    assert primary_lines(own_client) == ["Carrera 7 # 72-10"]


def test_delete_address(advisor_client: APIClient, own_client: Client) -> None:
    address_id = add_address(advisor_client, own_client).json()["id"]

    response = advisor_client.delete(f"{ADDRESSES_URL}/{address_id}")

    assert response.status_code == 204
    assert not ClientAddress.objects.exists()


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"city_code": "11"}, "city_code"),  # Departamento, no municipio.
        ({"address_type_code": "OFICINA"}, "address_type_code"),
        ({"line1": ""}, "line1"),
        ({"country": "CO"}, "country"),  # Campo no permitido.
    ],
)
def test_create_address_validates_input(
    advisor_client: APIClient, own_client: Client, payload: dict[str, Any], field: str
) -> None:
    body = assert_error(add_address(advisor_client, own_client, **payload), 400, "VALIDATION_ERROR")
    assert field in {detail["field"] for detail in body["details"]}


def test_addresses_of_clients_out_of_scope_are_not_found(
    advisor_client: APIClient,
    admin_client: APIClient,
    make_client: Callable[..., Client],
) -> None:
    foreign = make_client()
    address_id = add_address(admin_client, foreign).json()["id"]

    assert_error(advisor_client.get(f"{client_url(foreign)}/addresses"), 404, "RESOURCE_NOT_FOUND")
    assert_error(add_address(advisor_client, foreign), 404, "RESOURCE_NOT_FOUND")
    assert_error(
        advisor_client.patch(f"{ADDRESSES_URL}/{address_id}", {"line1": "X"}, format="json"),
        404,
        "RESOURCE_NOT_FOUND",
    )
    assert_error(advisor_client.delete(f"{ADDRESSES_URL}/{address_id}"), 404, "RESOURCE_NOT_FOUND")


def test_broker_cannot_manage_addresses(
    broker_client: APIClient, broker_user: User, make_client: Callable[..., Client]
) -> None:
    client = make_client(created_by=broker_user)

    assert_error(broker_client.get(f"{client_url(client)}/addresses"), 403, "PERMISSION_DENIED")
    assert_error(add_address(broker_client, client), 403, "PERMISSION_DENIED")
