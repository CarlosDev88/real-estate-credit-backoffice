import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.banking.models import Bank, BankProduct, BankProductPurpose
from apps.banking.services import available_products
from tests.banking.conftest import PRODUCTS_URL, catalog_item
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db


def product_url(product: BankProduct | str) -> str:
    product_id = product if isinstance(product, str) else product.id
    return f"{PRODUCTS_URL}/{product_id}"


def ids(response: Any) -> set[str]:
    assert response.status_code == 200, response.content
    return {item["id"] for item in response.json()["items"]}


def purpose_codes(body: dict[str, Any]) -> list[str]:
    return [purpose["code"] for purpose in body["purposes"]]


@pytest.fixture
def fna() -> Bank:
    return Bank.objects.get(code="FNA")


def create(api: APIClient, bank: Bank, **payload: Any) -> Any:
    return api.post(
        PRODUCTS_URL,
        {
            "bank_id": str(bank.id),
            "code": "HOUSING_LEASING",
            "name": "Leasing habitacional",
            "product_type_code": "HOUSING_LEASING",
            **payload,
        },
        format="json",
    )


# --- Crear ------------------------------------------------------------------------------


def test_admin_creates_product_with_purposes(admin_client: APIClient, fna: Bank) -> None:
    response = create(
        admin_client,
        fna,
        min_amount_cop=20_000_000,
        max_amount_cop=500_000_000,
        min_term_months=60,
        max_term_months=360,
        valid_from="2026-07-01",
        purpose_codes=["PURCHASE_USED", "PURCHASE_NEW"],
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["bank"] == {
        "id": str(fna.id),
        "code": "FNA",
        "name": "Fondo Nacional del Ahorro",
        "short_name": "FNA",
    }
    assert body["product_type"] == {"code": "HOUSING_LEASING", "label": "Leasing habitacional"}
    assert body["status"] == "ACTIVE"
    assert (body["min_amount_cop"], body["max_amount_cop"]) == (20_000_000, 500_000_000)
    assert body["valid_from"] == "2026-07-01"
    assert purpose_codes(body) == ["PURCHASE_NEW", "PURCHASE_USED"]


def test_valid_from_defaults_to_today(admin_client: APIClient, fna: Bank) -> None:
    body = create(admin_client, fna).json()

    assert body["valid_from"] == date.today().isoformat()
    assert body["purposes"] == []


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"min_amount_cop": 10, "max_amount_cop": 5}, "max_amount_cop"),
        ({"min_amount_cop": -1}, "min_amount_cop"),
        ({"min_term_months": 0}, "min_term_months"),
        ({"min_term_months": 120, "max_term_months": 60}, "max_term_months"),
        ({"max_term_months": 601}, "max_term_months"),
        ({"valid_from": "2026-07-01", "valid_to": "2026-06-30"}, "valid_to"),
        ({"product_type_code": "PERSONAL_LOAN"}, "product_type_code"),
        ({"purpose_codes": ["PURCHASE_NEW", "PURCHASE_NEW"]}, "purpose_codes"),
        ({"purpose_codes": ["CARTERA"]}, "purpose_codes.0"),
        ({"bank_id": str(uuid.uuid4())}, "bank_id"),
        ({"code": "leasing"}, "code"),
    ],
)
def test_create_product_validates_input(
    admin_client: APIClient, fna: Bank, payload: dict[str, Any], field: str
) -> None:
    body = assert_error(create(admin_client, fna, **payload), 400, "VALIDATION_ERROR")
    assert field in {detail["field"] for detail in body["details"]}


def test_product_code_is_unique_per_bank(admin_client: APIClient, fna: Bank) -> None:
    assert_error(create(admin_client, fna, code="MORTGAGE"), 409, "DUPLICATE_CODE")
    # El mismo código en otro banco sí se permite.
    other = Bank.objects.create(code="DAVIVIENDA", name="Davivienda")
    assert create(admin_client, other, code="MORTGAGE").status_code == 201


def test_advisor_cannot_create_products(advisor_client: APIClient, fna: Bank) -> None:
    assert_error(create(advisor_client, fna), 403, "PERMISSION_DENIED")


# --- Consultar --------------------------------------------------------------------------


def test_advisor_reads_product_detail(advisor_client: APIClient, fna: Bank) -> None:
    product = BankProduct.objects.get(bank=fna)

    body = advisor_client.get(product_url(product)).json()

    assert body["name"] == "Crédito hipotecario"
    assert purpose_codes(body) == ["PURCHASE_NEW", "PURCHASE_USED", "HOME_IMPROVEMENT"]


def test_unknown_product_is_not_found(advisor_client: APIClient) -> None:
    assert_error(advisor_client.get(product_url(str(uuid.uuid4()))), 404, "RESOURCE_NOT_FOUND")


def test_list_products_filters(
    admin_client: APIClient, fna: Bank, make_product: Callable[..., BankProduct]
) -> None:
    fna_mortgage = BankProduct.objects.get(bank=fna)
    leasing = make_product(
        bank=fna,
        code="LEASING",
        name="Leasing",
        product_type_item=catalog_item("bank_product_type", "HOUSING_LEASING"),
        purposes=["PURCHASE_USED"],
    )
    inactive = make_product(code="OLD", status="INACTIVE", purposes=["PURCHASE_USED"])
    expired = make_product(
        code="EXPIRED", valid_to=date.today() - timedelta(days=1), purposes=["PURCHASE_USED"]
    )

    assert ids(admin_client.get(PRODUCTS_URL, {"bank_id": str(fna.id)})) == {
        str(fna_mortgage.id),
        str(leasing.id),
    }
    assert ids(admin_client.get(PRODUCTS_URL, {"product_type": "HOUSING_LEASING"})) == {
        str(leasing.id)
    }
    assert ids(admin_client.get(PRODUCTS_URL, {"status": "INACTIVE"})) == {str(inactive.id)}
    with_used = ids(admin_client.get(PRODUCTS_URL, {"purpose": "PURCHASE_USED"}))
    assert {str(leasing.id), str(inactive.id), str(expired.id)} <= with_used

    available = ids(admin_client.get(PRODUCTS_URL, {"available": "true"}))
    assert str(leasing.id) in available
    assert str(inactive.id) not in available
    assert str(expired.id) not in available

    assert_error(admin_client.get(PRODUCTS_URL, {"bank_id": "x"}), 400, "VALIDATION_ERROR")


# --- Editar, activar y finalidades ------------------------------------------------------


def test_update_product_validates_against_current_values(
    admin_client: APIClient, fna: Bank
) -> None:
    product = BankProduct.objects.get(bank=fna)
    admin_client.patch(product_url(product), {"min_amount_cop": 50_000_000}, format="json")

    body = assert_error(
        admin_client.patch(product_url(product), {"max_amount_cop": 10_000_000}, format="json"),
        400,
        "VALIDATION_ERROR",
    )
    assert body["details"][0]["field"] == "max_amount_cop"

    response = admin_client.patch(
        product_url(product),
        {"name": "Hipotecario FNA", "max_amount_cop": 400_000_000, "min_amount_cop": None},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["name"] == "Hipotecario FNA"
    assert response.json()["min_amount_cop"] is None


def test_product_bank_and_code_are_not_editable(admin_client: APIClient, fna: Bank) -> None:
    product = BankProduct.objects.get(bank=fna)

    body = assert_error(
        admin_client.patch(
            product_url(product), {"code": "X", "bank_id": str(fna.id)}, format="json"
        ),
        400,
        "VALIDATION_ERROR",
    )
    assert {detail["field"] for detail in body["details"]} == {"code", "bank_id"}


def test_deactivated_product_is_not_available(admin_client: APIClient, fna: Bank) -> None:
    product = BankProduct.objects.get(bank=fna)

    response = admin_client.post(f"{product_url(product)}/deactivate", {"reason": "Sin cupo"})

    assert response.json()["status"] == "INACTIVE"
    assert product not in available_products()
    assert admin_client.post(f"{product_url(product)}/activate").json()["status"] == "ACTIVE"
    assert product in available_products()


def test_inactive_bank_hides_its_products(fna: Bank) -> None:
    fna.status = "INACTIVE"
    fna.save()

    assert not available_products().filter(bank=fna).exists()


def test_replace_purposes_keeps_history(admin_client: APIClient, fna: Bank) -> None:
    product = BankProduct.objects.get(bank=fna)

    response = admin_client.put(
        f"{product_url(product)}/purposes", {"purpose_codes": ["PURCHASE_NEW"]}, format="json"
    )

    assert response.status_code == 200, response.content
    assert purpose_codes(response.json()) == ["PURCHASE_NEW"]
    rows = BankProductPurpose.objects.filter(bank_product=product)
    assert rows.count() == 3  # Las que salen se desactivan, no se borran.
    assert rows.filter(is_active=True).count() == 1

    used = catalog_item("loan_purpose", "PURCHASE_USED")
    assert product not in available_products(purpose=used)

    # Volver a incluirla reactiva la fila existente.
    body = admin_client.put(
        f"{product_url(product)}/purposes",
        {"purpose_codes": ["PURCHASE_USED", "PURCHASE_NEW"]},
        format="json",
    ).json()
    assert purpose_codes(body) == ["PURCHASE_NEW", "PURCHASE_USED"]
    assert rows.count() == 3
    assert product in available_products(purpose=used)


def test_purposes_can_be_emptied(admin_client: APIClient, fna: Bank) -> None:
    product = BankProduct.objects.get(bank=fna)

    body = admin_client.put(
        f"{product_url(product)}/purposes", {"purpose_codes": []}, format="json"
    ).json()

    assert body["purposes"] == []


def test_advisor_cannot_change_purposes(advisor_client: APIClient, fna: Bank) -> None:
    product = BankProduct.objects.get(bank=fna)

    assert_error(
        advisor_client.put(
            f"{product_url(product)}/purposes", {"purpose_codes": []}, format="json"
        ),
        403,
        "PERMISSION_DENIED",
    )
