from datetime import date

import pytest

from apps.banking.models import Bank, BankPolicyRule, BankProduct
from apps.banking.services import active_purpose_items, available_products
from tests.banking.conftest import catalog_item
from tests.helpers import role_permissions

pytestmark = pytest.mark.django_db

READ = {"banks.read", "bank_rules.read"}
WRITE = {
    "banks.create",
    "banks.update",
    "bank_rules.create",
    "bank_rules.update",
    "bank_rules.publish",
}


def test_three_test_banks_with_one_mortgage_product_each() -> None:
    products = {
        product.bank.code: product
        for product in BankProduct.objects.select_related("bank", "product_type_item")
    }

    assert set(Bank.objects.values_list("code", "name", "status")) == {
        ("BANCOLOMBIA", "Bancolombia", "ACTIVE"),
        ("FNA", "Fondo Nacional del Ahorro", "ACTIVE"),
        ("BANCO_BOGOTA", "Banco de Bogotá", "ACTIVE"),
    }
    assert {code: product.name for code, product in products.items()} == {
        "BANCOLOMBIA": "Crédito hipotecario",
        "FNA": "Crédito hipotecario",
        "BANCO_BOGOTA": "Crédito de vivienda",
    }
    for product in products.values():
        assert product.code == "MORTGAGE"
        assert product.product_type_item.code == "MORTGAGE"
        assert product.status == "ACTIVE"
        assert (product.min_amount_cop, product.max_amount_cop) == (None, None)
        assert (product.min_term_months, product.max_term_months) == (None, None)
        assert product.valid_from == date(2026, 1, 1)
        assert {item.code for item in active_purpose_items(product)} == {
            "PURCHASE_NEW",
            "PURCHASE_USED",
            "HOME_IMPROVEMENT",
        }


def test_no_rules_are_seeded() -> None:
    assert not BankPolicyRule.objects.exists()


def test_seeded_products_are_available_for_every_purpose() -> None:
    for code in ("PURCHASE_NEW", "PURCHASE_USED", "HOME_IMPROVEMENT"):
        purpose = catalog_item("loan_purpose", code)
        assert available_products(on=date(2026, 6, 1), purpose=purpose).count() == 3


@pytest.mark.parametrize(
    ("role_code", "expected"),
    [
        ("ADMIN", READ | WRITE),
        ("ADVISOR", READ),
        ("INDEPENDENT_BROKER", set()),
        ("CONSTRUCTION_PARTNER", set()),
    ],
)
def test_banking_permissions_by_role(role_code: str, expected: set[str]) -> None:
    granted = {
        code for code in role_permissions(role_code) if code.startswith(("banks.", "bank_rules."))
    }
    assert granted == expected
