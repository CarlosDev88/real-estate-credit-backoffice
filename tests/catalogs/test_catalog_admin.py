import uuid

import pytest
from rest_framework.test import APIClient

from apps.catalogs.models import Catalog, CatalogItem
from tests.helpers import assert_error, csrf_token, login

pytestmark = pytest.mark.django_db

CATALOGS_URL = "/api/v1/catalogs"


def catalog_url(catalog: Catalog) -> str:
    return f"{CATALOGS_URL}/{catalog.id}"


def items_url(catalog: Catalog) -> str:
    return f"{CATALOGS_URL}/{catalog.id}/items"


def item_url(item: CatalogItem) -> str:
    return f"/api/v1/catalog-items/{item.id}"


# --- Autenticación y permisos -----------------------------------------------------------


def test_catalogs_require_authentication(api_client, db):
    assert_error(api_client.get(CATALOGS_URL), 401, "NOT_AUTHENTICATED")


def test_catalogs_require_permission(advisor_client):
    assert_error(advisor_client.get(CATALOGS_URL), 403, "PERMISSION_DENIED")
    response = advisor_client.post(CATALOGS_URL, {"code": "x_y", "name": "X"})
    assert_error(response, 403, "PERMISSION_DENIED")


def test_permission_is_checked_per_method(make_user):
    """Con `catalogs.read`, pero sin `catalogs.create`, se puede leer y no crear."""
    make_user(email="lector@example.com", role_code="ADVISOR", permissions=["catalogs.read"])
    client = APIClient()
    login(client, email="lector@example.com")

    assert client.get(CATALOGS_URL).status_code == 200
    response = client.post(CATALOGS_URL, {"code": "nuevo", "name": "Nuevo"})
    assert_error(response, 403, "PERMISSION_DENIED")


def test_unsupported_method_returns_405(admin_client, manageable_catalog):
    assert_error(admin_client.delete(catalog_url(manageable_catalog)), 405, "METHOD_NOT_ALLOWED")


def test_writes_require_csrf_token(make_user):
    make_user(email="admin@example.com", role_code="ADMIN")
    client = APIClient(enforce_csrf_checks=True)
    login(client, email="admin@example.com")
    payload = {"code": "notary", "name": "Notaría"}

    assert_error(client.post(CATALOGS_URL, payload), 403, "CSRF_FAILED")
    response = client.post(CATALOGS_URL, payload, HTTP_X_CSRFTOKEN=csrf_token(client))
    assert response.status_code == 201


# --- Catálogos --------------------------------------------------------------------------


def test_list_catalogs_is_paginated(admin_client):
    response = admin_client.get(CATALOGS_URL, {"page_size": 5})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "page", "page_size", "total", "next", "previous"}
    assert body["page"] == 1
    assert body["page_size"] == 5
    assert body["total"] == Catalog.objects.count()
    assert len(body["items"]) == 5
    assert body["next"] == "/api/v1/catalogs?page=2&page_size=5"
    assert body["previous"] is None

    second = admin_client.get(body["next"]).json()
    assert second["previous"] == "/api/v1/catalogs?page_size=5"


def test_list_catalogs_includes_seeded_data(admin_client):
    body = admin_client.get(CATALOGS_URL, {"search": "loan_purpose"}).json()
    assert [catalog["code"] for catalog in body["items"]] == ["loan_purpose"]
    catalog = body["items"][0]
    assert catalog["items_count"] == 3
    assert catalog["is_manageable"] is True
    assert catalog["version"] == 1


def test_list_catalogs_filters_and_orders(admin_client):
    body = admin_client.get(CATALOGS_URL, {"is_public": "false", "ordering": "-code"}).json()
    codes = [catalog["code"] for catalog in body["items"]]
    assert "loan_purpose" not in codes
    assert codes == sorted(codes, reverse=True)


def test_list_catalogs_rejects_unknown_ordering(admin_client):
    body = assert_error(
        admin_client.get(CATALOGS_URL, {"ordering": "description"}), 400, "VALIDATION_ERROR"
    )
    assert body["details"][0]["field"] == "ordering"


def test_list_catalogs_rejects_invalid_boolean(admin_client):
    assert_error(admin_client.get(CATALOGS_URL, {"is_public": "quizas"}), 400, "VALIDATION_ERROR")


def test_create_catalog(admin_client):
    response = admin_client.post(
        CATALOGS_URL,
        {"code": "notary", "name": "Notaría", "description": "Notarías de Colombia"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == "notary"
    assert body["is_manageable"] is True
    assert body["is_public"] is False
    assert body["version"] == 1
    assert body["items_count"] == 0


def test_create_catalog_validates_code_format(admin_client):
    body = assert_error(
        admin_client.post(CATALOGS_URL, {"code": "Notaría X", "name": "X"}),
        400,
        "VALIDATION_ERROR",
    )
    assert body["details"][0]["field"] == "code"


def test_create_catalog_rejects_duplicate_code(admin_client):
    response = admin_client.post(CATALOGS_URL, {"code": "loan_purpose", "name": "Otra"})
    assert_error(response, 409, "DUPLICATE_CODE")


def test_create_catalog_cannot_set_is_manageable(admin_client):
    response = admin_client.post(
        CATALOGS_URL, {"code": "notary", "name": "Notaría", "is_manageable": False}
    )
    assert_error(response, 400, "VALIDATION_ERROR")


def test_retrieve_unknown_catalog_returns_404(admin_client):
    assert_error(admin_client.get(f"{CATALOGS_URL}/{uuid.uuid4()}"), 404, "RESOURCE_NOT_FOUND")
    assert admin_client.get(f"{CATALOGS_URL}/no-es-uuid").status_code == 404


def test_update_catalog_bumps_version(admin_client, manageable_catalog):
    response = admin_client.patch(catalog_url(manageable_catalog), {"name": "Finalidad"})

    assert response.status_code == 200
    assert response.json()["name"] == "Finalidad"
    assert response.json()["version"] == 2


def test_update_catalog_code_is_not_allowed(admin_client, manageable_catalog):
    response = admin_client.patch(catalog_url(manageable_catalog), {"code": "otro"})
    assert_error(response, 400, "VALIDATION_ERROR")


def test_system_catalog_cannot_be_modified(admin_client, system_catalog):
    response = admin_client.patch(catalog_url(system_catalog), {"name": "Otro"})
    assert_error(response, 409, "CATALOG_NOT_MANAGEABLE")


# --- Valores ----------------------------------------------------------------------------


def test_list_items(admin_client, manageable_catalog):
    body = admin_client.get(items_url(manageable_catalog)).json()

    assert [item["code"] for item in body["items"]] == [
        "PURCHASE_NEW",
        "PURCHASE_USED",
        "HOME_IMPROVEMENT",
    ]
    assert body["items"][0]["catalog_code"] == "loan_purpose"


def test_list_items_filters_by_parent(admin_client):
    municipality = Catalog.objects.get(code="municipality")
    antioquia = CatalogItem.objects.get(catalog__code="department", code="05")

    body = admin_client.get(items_url(municipality), {"parent_id": str(antioquia.id)}).json()
    assert [item["code"] for item in body["items"]] == ["05001"]

    response = admin_client.get(items_url(municipality), {"parent_id": "no-uuid"})
    assert_error(response, 400, "VALIDATION_ERROR")


def test_create_item_appends_to_the_end_and_bumps_version(admin_client, manageable_catalog):
    response = admin_client.post(
        items_url(manageable_catalog),
        {"code": "LOT_PURCHASE", "label": "Compra de lote", "metadata": {"icon": "lote"}},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["sort_order"] == 40
    assert body["is_active"] is True
    assert body["metadata"] == {"icon": "lote"}
    manageable_catalog.refresh_from_db()
    assert manageable_catalog.version == 2


def test_create_item_with_parent(admin_client):
    municipality = Catalog.objects.get(code="municipality")
    antioquia = CatalogItem.objects.get(catalog__code="department", code="05")

    response = admin_client.post(
        items_url(municipality),
        {"code": "05360", "label": "Itagüí", "parent_id": str(antioquia.id)},
    )
    assert response.status_code == 201
    assert response.json()["parent_id"] == str(antioquia.id)


def test_create_item_rejects_unknown_parent(admin_client, manageable_catalog):
    response = admin_client.post(
        items_url(manageable_catalog),
        {"code": "X", "label": "X", "parent_id": str(uuid.uuid4())},
    )
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "parent_id"


def test_create_item_rejects_duplicate_code(admin_client, manageable_catalog):
    response = admin_client.post(
        items_url(manageable_catalog), {"code": "PURCHASE_NEW", "label": "Otra"}
    )
    assert_error(response, 409, "DUPLICATE_CODE")


def test_same_item_code_is_allowed_in_another_catalog(admin_client):
    other = Catalog.objects.create(code="custom", name="Personalizado")
    response = admin_client.post(items_url(other), {"code": "PURCHASE_NEW", "label": "Otra"})
    assert response.status_code == 201


@pytest.mark.parametrize(
    "payload",
    [
        {"code": "minusculas", "label": "X"},
        {"code": "X", "label": "X", "valid_from": "2026-12-31", "valid_to": "2026-01-01"},
        {"code": "X", "label": "X", "metadata": ["no", "es", "objeto"]},
        {"code": "X", "label": "X", "metadata": {"k": "x" * 5000}},
        {"code": "X"},
    ],
)
def test_create_item_validates_input(admin_client, manageable_catalog, payload):
    assert_error(admin_client.post(items_url(manageable_catalog), payload), 400, "VALIDATION_ERROR")


def test_items_of_system_catalog_cannot_be_created(admin_client, system_catalog):
    response = admin_client.post(items_url(system_catalog), {"code": "NEW_STATE", "label": "X"})
    assert_error(response, 409, "CATALOG_NOT_MANAGEABLE")


def test_update_item_label_metadata_and_validity(admin_client, manageable_catalog):
    item = manageable_catalog.items.get(code="PURCHASE_USED")

    response = admin_client.patch(
        item_url(item),
        {"label": "Vivienda usada", "metadata": {"badge": "popular"}, "valid_to": "2030-12-31"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["label"] == "Vivienda usada"
    assert body["metadata"] == {"badge": "popular"}
    assert body["valid_to"] == "2030-12-31"
    assert body["code"] == "PURCHASE_USED"


def test_item_code_cannot_be_renamed(admin_client, manageable_catalog):
    item = manageable_catalog.items.get(code="PURCHASE_USED")
    assert_error(admin_client.patch(item_url(item), {"code": "USED"}), 400, "VALIDATION_ERROR")


def test_update_item_checks_validity_against_stored_values(admin_client, manageable_catalog):
    item = manageable_catalog.items.get(code="PURCHASE_USED")
    item.valid_from = "2027-01-01"
    item.save()

    response = admin_client.patch(item_url(item), {"valid_to": "2026-06-30"})
    assert_error(response, 400, "VALIDATION_ERROR")


def test_deactivate_and_activate_item(admin_client, manageable_catalog):
    item = manageable_catalog.items.get(code="HOME_IMPROVEMENT")

    response = admin_client.post(f"{item_url(item)}/deactivate")
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    manageable_catalog.refresh_from_db()
    assert manageable_catalog.version == 2

    # Repetir la misma acción no cambia la versión.
    admin_client.post(f"{item_url(item)}/deactivate")
    manageable_catalog.refresh_from_db()
    assert manageable_catalog.version == 2

    assert admin_client.post(f"{item_url(item)}/activate").json()["is_active"] is True


def test_system_items_cannot_be_deactivated(admin_client, system_catalog):
    item = system_catalog.items.get(code="DRAFT")
    response = admin_client.post(f"{item_url(item)}/deactivate")
    assert_error(response, 409, "CATALOG_NOT_MANAGEABLE")


def test_reorder_items(admin_client, manageable_catalog):
    items = {item.code: item for item in manageable_catalog.items.all()}
    order = [items["HOME_IMPROVEMENT"].id, items["PURCHASE_NEW"].id, items["PURCHASE_USED"].id]

    response = admin_client.put(
        f"{items_url(manageable_catalog)}/order", {"item_ids": [str(i) for i in order]}
    )

    assert response.status_code == 200
    assert [item["code"] for item in response.json()] == [
        "HOME_IMPROVEMENT",
        "PURCHASE_NEW",
        "PURCHASE_USED",
    ]
    assert [item["sort_order"] for item in response.json()] == [10, 20, 30]


def test_reorder_requires_every_item_exactly_once(admin_client, manageable_catalog):
    item_ids = [str(item.id) for item in manageable_catalog.items.all()]
    url = f"{items_url(manageable_catalog)}/order"

    assert_error(admin_client.put(url, {"item_ids": item_ids[:2]}), 400, "VALIDATION_ERROR")
    assert_error(
        admin_client.put(url, {"item_ids": [*item_ids, item_ids[0]]}), 400, "VALIDATION_ERROR"
    )
    assert_error(
        admin_client.put(url, {"item_ids": [*item_ids[:2], str(uuid.uuid4())]}),
        400,
        "VALIDATION_ERROR",
    )


def test_retrieve_item(admin_client, manageable_catalog):
    item = manageable_catalog.items.get(code="PURCHASE_NEW")
    body = admin_client.get(item_url(item)).json()
    assert body["label"] == "Compra de vivienda nueva"
    assert body["description"] == "Incluye vivienda sobre planos."
