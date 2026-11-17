"""``GET /buyer/metadata/catalogs/{catalog_code}``: catálogos de los formularios del portal."""

import re
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from apps.catalogs.models import Catalog, CatalogItem
from apps.identity.buyer_portal import BUYER_CATALOG_CODES
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

BACKEND = Path(__file__).resolve().parents[3]
# Serializers de los formularios del comprador: los propios del portal y los internos que
# el portal reutiliza (perfil, ingresos, inmueble, financiación y desistimiento).
BUYER_FORM_SERIALIZERS = (
    "apps/identity/buyer_profile_serializers.py",
    "apps/identity/buyer_financing_serializers.py",
)
REUSED_SERIALIZERS = {
    "FinancialProfileInputSerializer",
    "IncomeSourceCreateSerializer",
    "IncomeSourceUpdateSerializer",
    "PropertyInputSerializer",
    "FinancingInputSerializer",
    "WithdrawalSerializer",
}


def catalog_url(code: str) -> str:
    return f"/api/v1/buyer/metadata/catalogs/{code}"


def _catalog_codes(source: str) -> set[str]:
    return set(re.findall(r'catalog_code="([a-z_]+)"', source))


def _class_body(source: str, name: str) -> str:
    match = re.search(rf"^class {name}\(.*?(?=^class |\Z)", source, re.S | re.M)
    assert match is not None, name
    return match.group(0)


def test_the_allowed_list_is_what_the_buyer_forms_validate() -> None:
    """Los códigos que validan los serializers del comprador, más el padre de
    `municipality` (los departamentos)."""
    codes: set[str] = set()
    for path in BUYER_FORM_SERIALIZERS:
        codes |= _catalog_codes((BACKEND / path).read_text(encoding="utf-8"))
    internal = (BACKEND / "apps/applications/serializers.py").read_text(encoding="utf-8")
    for name in REUSED_SERIALIZERS:
        codes |= _catalog_codes(_class_body(internal, name))
    parents = set(
        CatalogItem.objects.filter(catalog__code="municipality", parent_item__isnull=False)
        .values_list("parent_item__catalog__code", flat=True)
        .distinct()
    )
    assert parents == {"department"}
    assert codes | parents == BUYER_CATALOG_CODES
    assert set(
        Catalog.objects.filter(code__in=BUYER_CATALOG_CODES).values_list("code", flat=True)
    ) == (BUYER_CATALOG_CODES)


def test_an_allowed_catalog_answers_like_the_internal_one(
    portal: APIClient, admin_client: APIClient
) -> None:
    response = portal.get(catalog_url("property_type"))

    assert response.status_code == 200, response.content
    internal = admin_client.get("/api/v1/metadata/catalogs/property_type")
    assert response.json() == internal.json()
    assert response["ETag"] == internal["ETag"]
    assert response["Cache-Control"] == "private, no-cache"
    assert {item["code"] for item in response.json()["items"]} == {"HOUSE", "APARTMENT"}

    cached = portal.get(catalog_url("property_type"), HTTP_IF_NONE_MATCH=response["ETag"])
    assert cached.status_code == 304
    assert cached["ETag"] == response["ETag"]


def test_municipality_filters_by_parent_code(portal: APIClient) -> None:
    response = portal.get(catalog_url("municipality"), {"parent_code": "11"})

    assert response.status_code == 200, response.content
    items = response.json()["items"]
    assert [item["code"] for item in items] == ["11001"]
    assert items[0]["parent_code"] == "11"


@pytest.mark.parametrize("code", ["loan_purpose", "identity_document_type", "no_existe"])
def test_a_catalog_outside_the_list_or_missing_is_not_found(portal: APIClient, code: str) -> None:
    assert_error(portal.get(catalog_url(code)), 404, "RESOURCE_NOT_FOUND")


def test_without_a_buyer_session_it_answers_401(
    api_client: APIClient, admin_client: APIClient
) -> None:
    assert_error(api_client.get(catalog_url("property_type")), 401, "NOT_AUTHENTICATED")
    # La sesión interna tampoco sirve: el portal solo acepta la cookie del comprador.
    assert admin_client.get(catalog_url("property_type")).status_code == 401
