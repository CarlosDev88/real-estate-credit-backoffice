"""Nombre corto del banco (``banks.short_name``): opcional, editable y en las referencias."""

import importlib
from collections.abc import Callable
from typing import Any

import pytest
from django.apps import apps as django_apps
from rest_framework.test import APIClient

from apps.banking.models import Bank, BankProduct
from tests.banking.conftest import BANKS_URL, PRODUCTS_URL
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

FNA = "FNA"


def create(client: APIClient, **payload: Any) -> Any:
    return client.post(BANKS_URL, {"code": "DAVIVIENDA", "name": "Davivienda", **payload})


def test_create_with_and_without_short_name(admin_client: APIClient) -> None:
    with_short = create(admin_client, short_name="  DVV  ")
    without = create(admin_client, code="SCOTIABANK", name="Scotiabank Colpatria")

    assert with_short.status_code == 201, with_short.content
    assert with_short.json()["short_name"] == "DVV"  # Sin espacios de más.
    assert without.status_code == 201, without.content
    assert without.json()["short_name"] == ""
    assert Bank.objects.get(code="SCOTIABANK").short_name == ""


def test_update_sets_and_clears_short_name(
    admin_client: APIClient, make_bank: Callable[..., Bank]
) -> None:
    bank = make_bank()
    url = f"{BANKS_URL}/{bank.id}"

    assert admin_client.patch(url, {"short_name": "BDP"}).json()["short_name"] == "BDP"
    assert admin_client.patch(url, {"name": "Banco de Prueba S.A."}).json()["short_name"] == "BDP"
    assert admin_client.patch(url, {"short_name": ""}).json()["short_name"] == ""
    bank.refresh_from_db()
    assert bank.short_name == ""


def test_short_name_is_at_most_30_characters(
    admin_client: APIClient, make_bank: Callable[..., Bank]
) -> None:
    assert create(admin_client, short_name="x" * 30).status_code == 201

    for response in (
        create(admin_client, code="OTRO_BANCO", short_name="x" * 31),
        admin_client.patch(f"{BANKS_URL}/{make_bank().id}", {"short_name": "x" * 31}),
    ):
        body = assert_error(response, 400, "VALIDATION_ERROR")
        assert [detail["field"] for detail in body["details"]] == ["short_name"]


def seeded_short_names() -> dict[str, str]:
    return dict(Bank.objects.values_list("code", "short_name"))


def test_only_the_fna_is_seeded_with_a_short_name() -> None:
    assert seeded_short_names() == {"BANCOLOMBIA": "", "FNA": "FNA", "BANCO_BOGOTA": ""}


def test_fna_short_name_migration_is_reversible() -> None:
    seed = importlib.import_module("apps.banking.migrations.0004_seed_fna_short_name")
    # El banco se busca por código: renombrarlo no cambia a cuál se le aplica.
    Bank.objects.filter(code=FNA).update(name="FNA renombrado")

    seed.clear_fna_short_name(django_apps, None)
    assert seeded_short_names() == {"BANCOLOMBIA": "", "FNA": "", "BANCO_BOGOTA": ""}

    seed.set_fna_short_name(django_apps, None)
    assert seeded_short_names() == {"BANCOLOMBIA": "", "FNA": "FNA", "BANCO_BOGOTA": ""}


def test_short_name_in_bank_list_detail_and_product_refs(advisor_client: APIClient) -> None:
    bank = Bank.objects.get(code=FNA)
    product = BankProduct.objects.filter(bank=bank).first()
    assert product is not None

    listed = {item["code"]: item for item in advisor_client.get(BANKS_URL).json()["items"]}
    detail = advisor_client.get(f"{BANKS_URL}/{bank.id}").json()
    product_body = advisor_client.get(f"{PRODUCTS_URL}/{product.id}").json()

    assert listed[FNA]["short_name"] == "FNA"
    assert detail["short_name"] == "FNA"
    assert product_body["bank"] == {
        "id": str(bank.id),
        "code": FNA,
        "name": "Fondo Nacional del Ahorro",
        "short_name": "FNA",
    }
