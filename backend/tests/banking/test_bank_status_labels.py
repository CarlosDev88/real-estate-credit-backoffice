"""`status_label` de bancos y productos (TAREA-brechas-3-demo, parte 2): el activo/inactivo
sale de la API, como en constructoras."""

from collections.abc import Callable

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.banking.models import Bank, BankProduct
from tests.banking.conftest import BANKS_URL, PRODUCTS_URL

pytestmark = pytest.mark.django_db


def test_banks_and_products_bring_the_label_of_their_status(
    advisor_client: APIClient,
    make_bank: Callable[..., Bank],
    make_product: Callable[..., BankProduct],
) -> None:
    bank = make_bank(status="INACTIVE")
    product = make_product(bank=bank)

    listed = advisor_client.get(BANKS_URL, {"search": bank.code}).json()["items"]
    detail = advisor_client.get(f"{BANKS_URL}/{bank.pk}").json()
    products = advisor_client.get(PRODUCTS_URL, {"bank_id": str(bank.pk)}).json()["items"]
    product_detail = advisor_client.get(f"{PRODUCTS_URL}/{product.pk}").json()

    assert [row["status_label"] for row in listed] == ["Inactivo"]
    assert detail["status_label"] == "Inactivo"
    assert [(p["status"], p["status_label"]) for p in detail["products"]] == [("ACTIVE", "Activo")]
    assert [row["status_label"] for row in products] == ["Activo"]
    assert product_detail["status_label"] == "Activo"


def test_the_bank_list_queries_do_not_grow(
    advisor_client: APIClient, make_bank: Callable[..., Bank]
) -> None:
    def measure() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert advisor_client.get(BANKS_URL).status_code == 200
        return len(queries)

    one = measure()
    for index in range(4):
        make_bank(code=f"BANCO_EXTRA_{index}", name=f"Banco extra {index}")

    assert measure() == one
