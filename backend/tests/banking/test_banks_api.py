import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.banking.models import Bank, BankProduct
from apps.banking.signals import bank_status_changed
from tests.banking.conftest import BANKS_URL
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db


def bank_url(bank: Bank | str) -> str:
    bank_id = bank if isinstance(bank, str) else bank.id
    return f"{BANKS_URL}/{bank_id}"


def codes(response: Any) -> list[str]:
    assert response.status_code == 200, response.content
    return [item["code"] for item in response.json()["items"]]


@pytest.fixture
def status_events() -> Iterator[list[dict[str, Any]]]:
    received: list[dict[str, Any]] = []

    def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    bank_status_changed.connect(handler)
    try:
        yield received
    finally:
        bank_status_changed.disconnect(handler)


# --- Acceso -----------------------------------------------------------------------------


def test_advisor_reads_banks(advisor_client: APIClient) -> None:
    assert codes(advisor_client.get(BANKS_URL)) == ["BANCO_BOGOTA", "BANCOLOMBIA", "FNA"]


def test_advisor_cannot_write_banks(
    advisor_client: APIClient, make_bank: Callable[..., Bank]
) -> None:
    bank = make_bank()

    assert_error(
        advisor_client.post(BANKS_URL, {"code": "X1", "name": "X"}), 403, "PERMISSION_DENIED"
    )
    assert_error(
        advisor_client.patch(bank_url(bank), {"name": "Otro"}, format="json"),
        403,
        "PERMISSION_DENIED",
    )
    assert_error(advisor_client.post(f"{bank_url(bank)}/deactivate"), 403, "PERMISSION_DENIED")


@pytest.mark.parametrize("client_fixture", ["broker_client", "partner_client"])
def test_broker_and_partner_do_not_see_banks(
    request: pytest.FixtureRequest, client_fixture: str
) -> None:
    api: APIClient = request.getfixturevalue(client_fixture)

    assert_error(api.get(BANKS_URL), 403, "PERMISSION_DENIED")
    assert_error(api.get("/api/v1/bank-products"), 403, "PERMISSION_DENIED")
    assert_error(api.get("/api/v1/bank-policy-rules"), 403, "PERMISSION_DENIED")


def test_banks_require_authentication(api_client: APIClient) -> None:
    assert_error(api_client.get(BANKS_URL), 401, "NOT_AUTHENTICATED")


# --- Crear y editar ---------------------------------------------------------------------


def test_admin_creates_bank(admin_client: APIClient) -> None:
    response = admin_client.post(
        BANKS_URL,
        {
            "code": "DAVIVIENDA",
            "name": "Davivienda",
            "tax_id": "860.034.313-7",
            "operational_notes": "Radicación por correo del gerente de zona.",
        },
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["code"] == "DAVIVIENDA"
    assert body["tax_id"] == "860034313-7"
    assert body["status"] == "ACTIVE"
    assert Bank.objects.filter(code="DAVIVIENDA").exists()


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"code": "davivienda"}, "code"),
        ({"code": "1BANCO"}, "code"),
        ({"name": ""}, "name"),
        ({"tax_id": "860034313-1"}, "tax_id"),  # Dígito de verificación incorrecto.
        ({"status": "INACTIVE"}, "status"),  # Campo no permitido.
    ],
)
def test_create_bank_validates_input(
    admin_client: APIClient, payload: dict[str, Any], field: str
) -> None:
    body = assert_error(
        admin_client.post(BANKS_URL, {"code": "DAVIVIENDA", "name": "Davivienda", **payload}),
        400,
        "VALIDATION_ERROR",
    )
    assert field in {detail["field"] for detail in body["details"]}


def test_bank_code_is_unique(admin_client: APIClient) -> None:
    assert_error(
        admin_client.post(BANKS_URL, {"code": "FNA", "name": "Otro FNA"}), 409, "DUPLICATE_CODE"
    )


def test_bank_detail_lists_its_products(advisor_client: APIClient) -> None:
    bank = Bank.objects.get(code="FNA")

    body = advisor_client.get(bank_url(bank)).json()

    assert body["name"] == "Fondo Nacional del Ahorro"
    assert [(item["code"], item["status"]) for item in body["products"]] == [("MORTGAGE", "ACTIVE")]


def test_unknown_bank_is_not_found(advisor_client: APIClient) -> None:
    assert_error(advisor_client.get(bank_url(str(uuid.uuid4()))), 404, "RESOURCE_NOT_FOUND")


def test_update_bank_but_not_its_code(admin_client: APIClient) -> None:
    bank = Bank.objects.get(code="FNA")

    response = admin_client.patch(
        bank_url(bank), {"operational_notes": "Oficina Bogotá centro.", "tax_id": ""}, format="json"
    )
    assert response.status_code == 200, response.content
    assert response.json()["operational_notes"] == "Oficina Bogotá centro."

    body = assert_error(
        admin_client.patch(bank_url(bank), {"code": "FNA2"}, format="json"), 400, "VALIDATION_ERROR"
    )
    assert body["details"][0]["field"] == "code"


def test_list_banks_filters(admin_client: APIClient, make_bank: Callable[..., Bank]) -> None:
    make_bank(code="INACTIVO", name="Banco Inactivo", status="INACTIVE")

    assert codes(admin_client.get(BANKS_URL, {"status": "INACTIVE"})) == ["INACTIVO"]
    assert codes(admin_client.get(BANKS_URL, {"search": "bogot"})) == ["BANCO_BOGOTA"]
    assert_error(admin_client.get(BANKS_URL, {"status": "X"}), 400, "VALIDATION_ERROR")


# --- Activar y desactivar ---------------------------------------------------------------


def test_deactivate_and_activate_bank(
    admin_client: APIClient, admin_user: Any, status_events: list[dict[str, Any]]
) -> None:
    bank = Bank.objects.get(code="BANCOLOMBIA")

    response = admin_client.post(f"{bank_url(bank)}/deactivate", {"reason": "Convenio en revisión"})
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "INACTIVE"
    # El producto conserva su estado; deja de estar disponible por el banco.
    assert BankProduct.objects.get(bank=bank).status == "ACTIVE"

    # Repetir no cambia nada ni emite otro evento.
    admin_client.post(f"{bank_url(bank)}/deactivate")
    assert admin_client.post(f"{bank_url(bank)}/activate").json()["status"] == "ACTIVE"

    assert [(e["from_status"], e["to_status"], e["reason"]) for e in status_events] == [
        ("ACTIVE", "INACTIVE", "Convenio en revisión"),
        ("INACTIVE", "ACTIVE", ""),
    ]
    assert status_events[0]["actor"] == admin_user
