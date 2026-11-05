from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.banking.models import BankProduct
from apps.catalogs.models import CatalogItem
from apps.documents.constants import MAX_FILE_SIZE_BYTES, PDF
from apps.documents.models import DocumentRequirement, DocumentType
from apps.identity.models import User
from apps.partners.models import Partner, PartnerMembership
from tests.partners.conftest import client_for

TYPES_URL = "/api/v1/document-types"
REQUIREMENTS_URL = "/api/v1/document-requirements"
PREVIEW_URL = f"{REQUIREMENTS_URL}/preview"


def catalog_item(catalog_code: str, code: str) -> CatalogItem:
    return CatalogItem.objects.get(catalog__code=catalog_code, code=code)


def seeded_product(bank_code: str) -> BankProduct:
    return BankProduct.objects.select_related("bank").get(bank__code=bank_code, code="MORTGAGE")


def seeded_type(code: str) -> DocumentType:
    return DocumentType.objects.get(code=code)


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


# --- Tipos y requisitos -----------------------------------------------------------------


@pytest.fixture
def make_type(db: Any) -> Callable[..., DocumentType]:
    def _make_type(**extra: Any) -> DocumentType:
        extra.setdefault("code", "TEST_DOCUMENT")
        extra.setdefault("name", "Documento de prueba")
        extra.setdefault("allowed_mime_types", [PDF])
        extra.setdefault("max_size_bytes", MAX_FILE_SIZE_BYTES)
        return DocumentType.objects.create(**extra)

    return _make_type


@pytest.fixture
def document_type(make_type: Callable[..., DocumentType]) -> DocumentType:
    return make_type()


@pytest.fixture
def make_requirement(document_type: DocumentType) -> Callable[..., DocumentRequirement]:
    def _make_requirement(**extra: Any) -> DocumentRequirement:
        extra.setdefault("document_type", document_type)
        extra.setdefault("version", 1)
        extra.setdefault("valid_from", timezone.now())
        return DocumentRequirement.objects.create(**extra)

    return _make_requirement
