import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.crm.models import Client, Opportunity
from apps.identity.models import User
from tests.crm.conftest import CLIENTS_URL, catalog_item, client_url
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

VALID_CLIENT = {
    "document_type_code": "CC",
    "document_number": "1032445908",
    "first_names": "Laura",
    "last_names": "Gómez Vélez",
    "email": "laura.gomez@email.com",
    "phone": "+573104458821",
    "origin_type": "BROKER",
}

BROKER_CLIENT_FIELDS = {
    "id",
    "document_type",
    "document_number",
    "first_names",
    "last_names",
    "full_name",
    "email",
    "phone",
    "created_at",
    "updated_at",
}


def ids(response: Any) -> list[str]:
    assert response.status_code == 200, response.content
    return [item["id"] for item in response.json()["items"]]


# --- Crear ------------------------------------------------------------------------------


def test_advisor_creates_client_with_normalized_data(
    advisor_client: APIClient, advisor_user: User
) -> None:
    response = advisor_client.post(
        CLIENTS_URL,
        {
            **VALID_CLIENT,
            "document_number": "1.032.445.908",
            "email": "Laura.Gomez@Email.com",
            "phone": "+57 310 445 8821",
        },
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["document_type"] == {"code": "CC", "label": "Cédula de ciudadanía"}
    assert body["document_number"] == "1032445908"
    assert body["full_name"] == "Laura Gómez Vélez"
    assert body["email"] == "laura.gomez@email.com"
    assert body["phone"] == "+573104458821"
    assert body["origin"]["code"] == "BROKER"
    assert body["created_by"]["id"] == str(advisor_user.id)
    assert Client.objects.get().created_by == advisor_user


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"document_type_code": "XX"}, "document_type_code"),
        ({"document_number": "ABC123"}, "document_number"),  # La CC solo admite dígitos.
        ({"document_number": "123"}, "document_number"),
        ({"phone": "3104458821"}, "phone"),  # Sin indicativo de país.
        ({"email": "no-es-correo"}, "email"),
        ({"origin_type": "INVENTADO"}, "origin_type"),
        ({"birth_date": (date.today() + timedelta(days=1)).isoformat()}, "birth_date"),
        ({"first_names": ""}, "first_names"),
        ({"created_by": str(uuid.uuid4())}, "created_by"),  # Campo no permitido.
    ],
)
def test_create_client_validates_input(
    advisor_client: APIClient, payload: dict[str, Any], field: str
) -> None:
    response = advisor_client.post(CLIENTS_URL, {**VALID_CLIENT, **payload})

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert field in {detail["field"] for detail in body["details"]}


def test_create_client_requires_identity(advisor_client: APIClient) -> None:
    body = assert_error(
        advisor_client.post(CLIENTS_URL, {"email": "laura@example.com"}), 400, "VALIDATION_ERROR"
    )
    assert {detail["field"] for detail in body["details"]} >= {
        "document_type_code",
        "document_number",
        "first_names",
        "last_names",
    }


def test_alphanumeric_documents_are_uppercased(advisor_client: APIClient) -> None:
    response = advisor_client.post(
        CLIENTS_URL, {**VALID_CLIENT, "document_type_code": "PA", "document_number": "ax-12 345"}
    )

    assert response.status_code == 201, response.content
    assert response.json()["document_number"] == "AX12345"


def test_duplicate_document_returns_existing_client_when_visible(
    advisor_client: APIClient,
) -> None:
    existing_id = advisor_client.post(CLIENTS_URL, VALID_CLIENT).json()["id"]

    # Mismo documento con otro formato.
    response = advisor_client.post(
        CLIENTS_URL, {**VALID_CLIENT, "document_number": "1032-445-908", "first_names": "Otra"}
    )

    body = assert_error(response, 409, "DUPLICATE_CLIENT_DOCUMENT")
    assert body["details"] == [
        {
            "field": "document_number",
            "code": "EXISTING_CLIENT",
            "message": "Usa el cliente existente.",
            "resource_id": existing_id,
        }
    ]


def test_duplicate_document_does_not_reveal_a_client_out_of_scope(
    broker_client: APIClient, make_client: Callable[..., Client]
) -> None:
    make_client()

    body = assert_error(
        broker_client.post(CLIENTS_URL, VALID_CLIENT), 409, "DUPLICATE_CLIENT_DOCUMENT"
    )
    assert body["details"] == []


def test_same_number_with_another_document_type_is_allowed(
    advisor_client: APIClient, make_client: Callable[..., Client]
) -> None:
    make_client()

    response = advisor_client.post(CLIENTS_URL, {**VALID_CLIENT, "document_type_code": "CE"})

    assert response.status_code == 201, response.content


def test_partner_users_do_not_use_crm(partner_client: APIClient) -> None:
    assert_error(partner_client.get(CLIENTS_URL), 403, "PERMISSION_DENIED")
    assert_error(partner_client.post(CLIENTS_URL, VALID_CLIENT), 403, "PERMISSION_DENIED")


def test_clients_require_authentication(api_client: APIClient) -> None:
    assert_error(api_client.get(CLIENTS_URL), 401, "NOT_AUTHENTICATED")


# --- Alcance ----------------------------------------------------------------------------


@pytest.fixture
def scoped_clients(
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    advisor_user: User,
    other_advisor: User,
    broker_user: User,
) -> dict[str, Client]:
    """Un cliente por cada forma de entrar (o no) en el alcance de cada usuario."""
    created_by_advisor = make_client(document_number="1000000001", created_by=advisor_user)
    assigned_to_advisor = make_client(document_number="1000000002", created_by=other_advisor)
    make_opportunity(assigned_to_advisor, assigned_advisor=advisor_user, status="ASSIGNED")
    created_by_broker = make_client(document_number="1000000003", created_by=broker_user)
    other_advisor_only = make_client(document_number="1000000004", created_by=other_advisor)
    make_opportunity(other_advisor_only, assigned_advisor=other_advisor, status="ASSIGNED")
    return {
        "created_by_advisor": created_by_advisor,
        "assigned_to_advisor": assigned_to_advisor,
        "created_by_broker": created_by_broker,
        "other_advisor_only": other_advisor_only,
    }


def test_admin_sees_every_client(
    admin_client: APIClient, scoped_clients: dict[str, Client]
) -> None:
    assert set(ids(admin_client.get(CLIENTS_URL))) == {
        str(client.id) for client in scoped_clients.values()
    }


def test_advisor_sees_created_and_assigned_clients(
    advisor_client: APIClient, scoped_clients: dict[str, Client]
) -> None:
    assert set(ids(advisor_client.get(CLIENTS_URL))) == {
        str(scoped_clients["created_by_advisor"].id),
        str(scoped_clients["assigned_to_advisor"].id),
    }
    assert_error(
        advisor_client.get(client_url(scoped_clients["other_advisor_only"])),
        404,
        "RESOURCE_NOT_FOUND",
    )


def test_broker_sees_only_own_contacts_with_masked_document(
    broker_client: APIClient, scoped_clients: dict[str, Client]
) -> None:
    response = broker_client.get(CLIENTS_URL)

    assert ids(response) == [str(scoped_clients["created_by_broker"].id)]
    item = response.json()["items"][0]
    assert set(item) == BROKER_CLIENT_FIELDS
    assert item["document_type"] == "CC"
    assert item["document_number"] == "••••••0003"

    detail = broker_client.get(client_url(scoped_clients["created_by_broker"])).json()
    assert set(detail) == BROKER_CLIENT_FIELDS
    assert_error(
        broker_client.get(client_url(scoped_clients["created_by_advisor"])),
        404,
        "RESOURCE_NOT_FOUND",
    )


def test_broker_sees_clients_of_opportunities_they_originated(
    broker_client: APIClient,
    broker_user: User,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> None:
    client = make_client()
    make_opportunity(client, origin_user=broker_user)

    assert ids(broker_client.get(CLIENTS_URL)) == [str(client.id)]


def test_deleted_clients_are_hidden(
    admin_client: APIClient, make_client: Callable[..., Client]
) -> None:
    client = make_client(deleted_at=timezone.now())

    assert ids(admin_client.get(CLIENTS_URL)) == []
    assert_error(admin_client.get(client_url(client)), 404, "RESOURCE_NOT_FOUND")


def test_list_clients_filters_and_search(
    admin_client: APIClient, make_client: Callable[..., Client]
) -> None:
    laura = make_client(origin_item=catalog_item("lead_origin", "BROKER"))
    pedro = make_client(
        document_type_item=catalog_item("identity_document_type", "CE"),
        document_number="E998877",
        first_names="Pedro",
        last_names="Ruiz",
        email="pedro@example.com",
    )

    assert ids(admin_client.get(CLIENTS_URL, {"document_type": "CE"})) == [str(pedro.id)]
    assert ids(admin_client.get(CLIENTS_URL, {"origin": "BROKER"})) == [str(laura.id)]
    assert ids(admin_client.get(CLIENTS_URL, {"search": "ruiz"})) == [str(pedro.id)]
    assert ids(admin_client.get(CLIENTS_URL, {"search": "1032445908"})) == [str(laura.id)]
    assert ids(admin_client.get(CLIENTS_URL, {"ordering": "last_names"})) == [
        str(laura.id),
        str(pedro.id),
    ]


# --- Detalle y edición ------------------------------------------------------------------


def test_client_detail_includes_addresses(
    advisor_client: APIClient, advisor_user: User, make_client: Callable[..., Client]
) -> None:
    client = make_client(created_by=advisor_user)
    advisor_client.post(
        f"{client_url(client)}/addresses",
        {"address_type_code": "RESIDENCE", "city_code": "11001", "line1": "Calle 100 # 15-20"},
    )

    body = advisor_client.get(client_url(client)).json()

    assert body["id"] == str(client.id)
    assert [address["line1"] for address in body["addresses"]] == ["Calle 100 # 15-20"]
    assert body["addresses"][0]["city"]["code"] == "11001"


def test_advisor_updates_contact_and_corrects_document(
    advisor_client: APIClient, advisor_user: User, make_client: Callable[..., Client]
) -> None:
    client = make_client(created_by=advisor_user)

    response = advisor_client.patch(
        client_url(client),
        {"phone": "+57 300 111 2233", "document_number": "1.032.445.909"},
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["phone"] == "+573001112233"
    assert body["document_number"] == "1032445909"
    assert body["first_names"] == "Laura"
    client.refresh_from_db()
    assert client.document_number == "1032445909"


def test_changing_document_type_revalidates_the_number(
    advisor_client: APIClient, advisor_user: User, make_client: Callable[..., Client]
) -> None:
    client = make_client(created_by=advisor_user, document_number="AB1234")
    client.document_type_item = catalog_item("identity_document_type", "PA")
    client.save()

    # El número actual tiene letras: no es válido como cédula.
    body = assert_error(
        advisor_client.patch(client_url(client), {"document_type_code": "CC"}, format="json"),
        400,
        "VALIDATION_ERROR",
    )
    assert body["details"][0]["field"] == "document_number"


def test_update_to_an_existing_document_conflicts(
    advisor_client: APIClient, advisor_user: User, make_client: Callable[..., Client]
) -> None:
    existing = make_client(created_by=advisor_user)
    client = make_client(created_by=advisor_user, document_number="1032445909")

    body = assert_error(
        advisor_client.patch(client_url(client), {"document_number": "1032445908"}, format="json"),
        409,
        "DUPLICATE_CLIENT_DOCUMENT",
    )
    assert body["details"][0]["resource_id"] == str(existing.id)
    client.refresh_from_db()
    assert client.document_number == "1032445909"


def test_broker_updates_only_contact_fields(
    broker_client: APIClient, broker_user: User, make_client: Callable[..., Client]
) -> None:
    client = make_client(created_by=broker_user)

    response = broker_client.patch(
        client_url(client), {"email": "Nuevo@Example.com"}, format="json"
    )
    assert response.status_code == 200, response.content
    assert response.json()["email"] == "nuevo@example.com"
    assert set(response.json()) == BROKER_CLIENT_FIELDS

    body = assert_error(
        broker_client.patch(client_url(client), {"document_number": "1032445909"}, format="json"),
        400,
        "VALIDATION_ERROR",
    )
    assert body["details"][0]["field"] == "document_number"


def test_empty_update_changes_nothing(
    advisor_client: APIClient, advisor_user: User, make_client: Callable[..., Client]
) -> None:
    client = make_client(created_by=advisor_user)
    before = client.updated_at

    response = advisor_client.patch(client_url(client), {}, format="json")

    assert response.status_code == 200, response.content
    client.refresh_from_db()
    assert client.updated_at == before


def test_cannot_update_a_client_out_of_scope(
    advisor_client: APIClient, make_client: Callable[..., Client]
) -> None:
    client = make_client()

    assert_error(
        advisor_client.patch(client_url(client), {"first_names": "X"}, format="json"),
        404,
        "RESOURCE_NOT_FOUND",
    )
