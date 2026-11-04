from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalogs.models import Catalog, CatalogItem
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

BOOTSTRAP_URL = "/api/v1/metadata/bootstrap"


def test_bootstrap_requires_authentication(api_client, db):
    assert_error(api_client.get(BOOTSTRAP_URL), 401, "NOT_AUTHENTICATED")


def test_bootstrap_returns_catalogs_permissions_and_features(advisor_client):
    response = advisor_client.get(BOOTSTRAP_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["actor"] == "ADVISOR"
    assert body["permissions"] == []
    assert body["features"] == {"manual_filing": True, "buyer_magic_link": True}
    assert body["on_demand_catalogs"] == ["municipality"]
    assert body["metadata_version"] == sum(
        Catalog.objects.exclude(code="municipality").values_list("version", flat=True)
    )

    assert "municipality" not in body["catalogs"]
    assert [item["code"] for item in body["catalogs"]["loan_purpose"]] == [
        "PURCHASE_NEW",
        "PURCHASE_USED",
        "HOME_IMPROVEMENT",
    ]
    item = body["catalogs"]["loan_purpose"][0]
    assert set(item) == {
        "id",
        "code",
        "label",
        "description",
        "order",
        "active",
        "parent_id",
        "parent_code",
        "metadata",
    }
    assert len(body["catalogs"]["application_status"]) == 17


def test_bootstrap_includes_admin_permissions(admin_client):
    body = admin_client.get(BOOTSTRAP_URL).json()
    assert body["actor"] == "ADMIN"
    assert "catalogs.read" in body["permissions"]
    assert "workflow.publish" in body["permissions"]


def test_bootstrap_hides_inactive_and_out_of_validity_items(advisor_client):
    today = timezone.localdate()
    purposes = CatalogItem.objects.filter(catalog__code="loan_purpose")
    purposes.filter(code="PURCHASE_NEW").update(is_active=False)
    purposes.filter(code="PURCHASE_USED").update(valid_from=today + timedelta(days=1))
    purposes.filter(code="HOME_IMPROVEMENT").update(valid_to=today - timedelta(days=1))

    body = advisor_client.get(BOOTSTRAP_URL).json()
    assert body["catalogs"]["loan_purpose"] == []


def test_bootstrap_supports_conditional_requests(advisor_client):
    first = advisor_client.get(BOOTSTRAP_URL)
    etag = first["ETag"]
    assert first["Cache-Control"] == "private, no-cache"

    not_modified = advisor_client.get(BOOTSTRAP_URL, HTTP_IF_NONE_MATCH=etag)
    assert not_modified.status_code == 304
    assert not_modified.content == b""
    assert not_modified["ETag"] == etag

    CatalogItem.objects.filter(catalog__code="loan_purpose", code="PURCHASE_NEW").update(
        label="Vivienda nueva"
    )
    changed = advisor_client.get(BOOTSTRAP_URL, HTTP_IF_NONE_MATCH=etag)
    assert changed.status_code == 200
    assert changed["ETag"] != etag


def test_bootstrap_etag_depends_on_the_user_permissions(advisor_client, admin_client):
    assert advisor_client.get(BOOTSTRAP_URL)["ETag"] != admin_client.get(BOOTSTRAP_URL)["ETag"]


def test_metadata_catalog_filters_by_parent_code(advisor_client):
    response = advisor_client.get("/api/v1/metadata/catalogs/municipality", {"parent_code": "05"})

    assert response.status_code == 200
    body = response.json()
    assert body["catalog"] == "municipality"
    assert [(item["code"], item["label"]) for item in body["items"]] == [("05001", "Medellín")]
    assert body["items"][0]["parent_code"] == "05"


def test_metadata_catalog_lists_all_capitals(advisor_client):
    body = advisor_client.get("/api/v1/metadata/catalogs/municipality").json()
    codes = {item["code"] for item in body["items"]}
    assert len(codes) == 32
    assert "11001" in codes


def test_metadata_catalog_unknown_code_returns_404(advisor_client):
    response = advisor_client.get("/api/v1/metadata/catalogs/no_existe")
    assert_error(response, 404, "RESOURCE_NOT_FOUND")


def test_metadata_catalog_supports_conditional_requests(advisor_client):
    url = "/api/v1/metadata/catalogs/loan_purpose"
    etag = advisor_client.get(url)["ETag"]
    assert advisor_client.get(url, HTTP_IF_NONE_MATCH=f"W/{etag}").status_code == 304
