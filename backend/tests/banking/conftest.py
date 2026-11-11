from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.banking.models import Bank, BankPolicyRule, BankProduct, BankProductPurpose
from apps.catalogs.models import CatalogItem
from apps.identity.models import User
from apps.partners.models import Partner, PartnerMembership
from tests.partners.conftest import client_for

BANKS_URL = "/api/v1/banks"
PRODUCTS_URL = "/api/v1/bank-products"
RULES_URL = "/api/v1/bank-policy-rules"

# Ejemplo de la sección 23.3: el monto no supera el 70% del valor del inmueble.
MAX_LTV_CONDITION: dict[str, Any] = {
    "operator": "lte",
    "left": {
        "operator": "ratio",
        "numerator_field": "financing.requested_amount_cop",
        "denominator_field": "property.estimated_value_cop",
    },
    "right": 0.7,
}


def catalog_item(catalog_code: str, code: str) -> CatalogItem:
    return CatalogItem.objects.get(catalog__code=catalog_code, code=code)


# --- Usuarios ---------------------------------------------------------------------------


@pytest.fixture
def admin_user(make_user: Callable[..., User]) -> User:
    return make_user(email="admin@example.com", role_code="ADMIN")


@pytest.fixture
def admin_client(admin_user: User) -> APIClient:
    return client_for(admin_user)


@pytest.fixture
def advisor_client(make_user: Callable[..., User]) -> APIClient:
    return client_for(make_user(email="asesor@example.com", role_code="ADVISOR"))


@pytest.fixture
def broker_client(make_user: Callable[..., User]) -> APIClient:
    return client_for(make_user(email="broker@example.com", role_code="INDEPENDENT_BROKER"))


@pytest.fixture
def partner_client(make_user: Callable[..., User]) -> APIClient:
    user = make_user(email="constructora@example.com", role_code="CONSTRUCTION_PARTNER")
    partner = Partner.objects.create(legal_name="Constructora Andina S.A.S.", tax_id="900123456-8")
    PartnerMembership.objects.create(partner=partner, user=user, started_at=date(2026, 1, 1))
    return client_for(user)


# --- Bancos, productos y reglas ---------------------------------------------------------


@pytest.fixture
def make_bank(db: Any) -> Callable[..., Bank]:
    def _make_bank(**extra: Any) -> Bank:
        extra.setdefault("code", "BANCO_PRUEBA")
        extra.setdefault("name", "Banco de Prueba")
        return Bank.objects.create(**extra)

    return _make_bank


@pytest.fixture
def make_product(make_bank: Callable[..., Bank]) -> Callable[..., BankProduct]:
    def _make_product(
        bank: Bank | None = None, purposes: list[str] | None = None, **extra: Any
    ) -> BankProduct:
        extra.setdefault("code", "MORTGAGE")
        extra.setdefault("name", "Crédito hipotecario")
        extra.setdefault("product_type_item", catalog_item("bank_product_type", "MORTGAGE"))
        extra.setdefault("valid_from", date(2026, 1, 1))
        if bank is None:
            bank = Bank.objects.filter(code="BANCO_PRUEBA").first() or make_bank()
        product = BankProduct.objects.create(bank=bank, **extra)
        for code in purposes if purposes is not None else ["PURCHASE_NEW"]:
            BankProductPurpose.objects.create(
                bank_product=product, purpose_item=catalog_item("loan_purpose", code)
            )
        return product

    return _make_product


@pytest.fixture
def product(make_product: Callable[..., BankProduct]) -> BankProduct:
    return make_product()


@pytest.fixture
def make_rule(admin_user: User, product: BankProduct) -> Callable[..., BankPolicyRule]:
    def _make_rule(**extra: Any) -> BankPolicyRule:
        extra.setdefault("bank_product", product)
        extra.setdefault("code", "MAX_LTV")
        extra.setdefault("version", 1)
        extra.setdefault("severity", "BLOCKING")
        extra.setdefault("condition", MAX_LTV_CONDITION)
        extra.setdefault("message", "El monto no puede superar el 70% del valor del inmueble.")
        extra.setdefault("valid_from", timezone.now())
        extra.setdefault("created_by", admin_user)
        return BankPolicyRule.objects.create(**extra)

    return _make_rule
