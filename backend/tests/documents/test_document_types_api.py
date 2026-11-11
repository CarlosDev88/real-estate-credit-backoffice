from collections.abc import Iterator
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.documents.constants import JPEG, MAX_FILE_SIZE_BYTES, PDF, PNG
from apps.documents.models import DocumentRequirement, DocumentType
from apps.documents.signals import document_type_status_changed
from tests.documents.conftest import TYPES_URL, seeded_type
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db


def type_url(document_type: DocumentType | str, action: str = "") -> str:
    type_id = document_type if isinstance(document_type, str) else document_type.id
    return f"{TYPES_URL}/{type_id}{'/' + action if action else ''}"


def create(api: APIClient, **payload: Any) -> Any:
    return api.post(
        TYPES_URL,
        {
            "code": "PROPERTY_PHOTOS",
            "name": "Fotografías del inmueble",
            "allowed_mime_types": [JPEG, PNG],
            "max_size_bytes": 5 * 1024 * 1024,
            **payload,
        },
        format="json",
    )


@pytest.fixture
def status_events() -> Iterator[list[dict[str, Any]]]:
    received: list[dict[str, Any]] = []

    def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    document_type_status_changed.connect(handler)
    try:
        yield received
    finally:
        document_type_status_changed.disconnect(handler)


# --- Acceso -----------------------------------------------------------------------------


def test_admin_and_advisor_can_read(admin_client: APIClient, advisor_client: APIClient) -> None:
    identity = seeded_type("IDENTITY_DOCUMENT")
    for api in (admin_client, advisor_client):
        listing = api.get(TYPES_URL)
        assert listing.status_code == 200
        assert listing.json()["total"] == 17
        detail = api.get(type_url(identity))
        assert detail.status_code == 200
        assert detail.json()["code"] == "IDENTITY_DOCUMENT"


@pytest.mark.parametrize("client_fixture", ["broker_client", "partner_client"])
def test_broker_and_partner_cannot_read(
    request: pytest.FixtureRequest, client_fixture: str
) -> None:
    api: APIClient = request.getfixturevalue(client_fixture)
    identity = seeded_type("IDENTITY_DOCUMENT")

    assert_error(api.get(TYPES_URL), 403, "PERMISSION_DENIED")
    assert_error(api.get(type_url(identity)), 403, "PERMISSION_DENIED")


def test_anonymous_is_rejected(api_client: APIClient) -> None:
    assert_error(api_client.get(TYPES_URL), 401, "NOT_AUTHENTICATED")


def test_advisor_cannot_write(advisor_client: APIClient) -> None:
    identity = seeded_type("IDENTITY_DOCUMENT")

    assert_error(create(advisor_client), 403, "PERMISSION_DENIED")
    assert_error(
        advisor_client.patch(type_url(identity), {"name": "X"}, format="json"),
        403,
        "PERMISSION_DENIED",
    )
    assert_error(advisor_client.post(type_url(identity, "deactivate")), 403, "PERMISSION_DENIED")


# --- Listado ----------------------------------------------------------------------------


def test_list_filters_and_search(admin_client: APIClient) -> None:
    DocumentType.objects.filter(code="REMODELING_BUDGET").update(is_active=False)

    inactive = admin_client.get(TYPES_URL, {"is_active": "false"}).json()["items"]
    repeatable = admin_client.get(TYPES_URL, {"is_repeatable": "true"}).json()["items"]
    search = admin_client.get(TYPES_URL, {"search": "pensión"}).json()["items"]

    assert [item["code"] for item in inactive] == ["REMODELING_BUDGET"]
    assert {item["code"] for item in repeatable} == {
        "PAYROLL_SLIP",
        "BANK_STATEMENT",
        "PENSION_PAYMENT_SLIP",
    }
    assert {item["code"] for item in search} == {"PENSION_CERTIFICATE", "PENSION_PAYMENT_SLIP"}


def test_list_rejects_invalid_filters(admin_client: APIClient) -> None:
    assert_error(admin_client.get(TYPES_URL, {"is_active": "quizas"}), 400, "VALIDATION_ERROR")
    assert_error(
        admin_client.get(TYPES_URL, {"ordering": "max_size_bytes"}), 400, "VALIDATION_ERROR"
    )


# --- Crear ------------------------------------------------------------------------------


def test_admin_creates_a_type(admin_client: APIClient) -> None:
    response = create(admin_client, default_validity_days=90, is_repeatable=True)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["code"] == "PROPERTY_PHOTOS"
    assert body["allowed_mime_types"] == [JPEG, PNG]
    assert body["max_size_bytes"] == 5 * 1024 * 1024
    assert body["default_validity_days"] == 90
    assert body["is_repeatable"] is True
    assert body["is_active"] is True
    assert body["description"] == ""


def test_duplicate_code_is_rejected(admin_client: APIClient) -> None:
    assert_error(create(admin_client, code="IDENTITY_DOCUMENT"), 409, "DUPLICATE_CODE")


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"allowed_mime_types": ["text/html"]}, "allowed_mime_types"),
        ({"allowed_mime_types": []}, "allowed_mime_types"),
        ({"allowed_mime_types": [PDF, PDF]}, "allowed_mime_types"),
        ({"max_size_bytes": MAX_FILE_SIZE_BYTES + 1}, "max_size_bytes"),
        ({"max_size_bytes": 0}, "max_size_bytes"),
        ({"default_validity_days": 0}, "default_validity_days"),
        ({"code": "foto-inmueble"}, "code"),
        ({"is_active": False}, "is_active"),
    ],
)
def test_create_validates_fields(
    admin_client: APIClient, payload: dict[str, Any], field: str
) -> None:
    body = assert_error(create(admin_client, **payload), 400, "VALIDATION_ERROR")
    assert field in {detail["field"].split(".")[0] for detail in body["details"]}


# --- Editar -----------------------------------------------------------------------------


def test_admin_updates_metadata(admin_client: APIClient) -> None:
    identity = seeded_type("IDENTITY_DOCUMENT")

    response = admin_client.patch(
        type_url(identity),
        {
            "name": "Documento de identidad",
            "allowed_mime_types": [PDF],
            "default_validity_days": 365,
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    identity.refresh_from_db()
    assert identity.name == "Documento de identidad"
    assert identity.allowed_mime_types == [PDF]
    assert identity.default_validity_days == 365


def test_code_is_not_editable(admin_client: APIClient) -> None:
    identity = seeded_type("IDENTITY_DOCUMENT")

    response = admin_client.patch(type_url(identity), {"code": "ID"}, format="json")

    assert_error(response, 400, "VALIDATION_ERROR")


def test_type_with_multi_file_requirements_must_stay_repeatable(admin_client: APIClient) -> None:
    payroll = seeded_type("PAYROLL_SLIP")

    response = admin_client.patch(type_url(payroll), {"is_repeatable": False}, format="json")

    assert_error(response, 400, "VALIDATION_ERROR")
    payroll.refresh_from_db()
    assert payroll.is_repeatable is True


def test_type_can_stop_being_repeatable_when_no_live_requirement_needs_it(
    admin_client: APIClient,
) -> None:
    payroll = seeded_type("PAYROLL_SLIP")
    DocumentRequirement.objects.filter(document_type=payroll).update(status="INACTIVE")

    response = admin_client.patch(type_url(payroll), {"is_repeatable": False}, format="json")

    assert response.status_code == 200, response.content
    assert response.json()["is_repeatable"] is False


def test_unknown_type_returns_404(admin_client: APIClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert_error(admin_client.get(type_url(missing)), 404, "RESOURCE_NOT_FOUND")


# --- Activar y desactivar ---------------------------------------------------------------


def test_deactivate_and_activate_emit_events(
    admin_client: APIClient, status_events: list[dict[str, Any]]
) -> None:
    budget = seeded_type("REMODELING_BUDGET")

    off = admin_client.post(type_url(budget, "deactivate"), {"reason": "Sin anexo"}, format="json")
    again = admin_client.post(type_url(budget, "deactivate"))
    on = admin_client.post(type_url(budget, "activate"))

    assert off.status_code == 200
    assert off.json()["is_active"] is False
    assert again.status_code == 200
    assert on.json()["is_active"] is True
    assert [(event["is_active"], event["reason"]) for event in status_events] == [
        (False, "Sin anexo"),
        (True, ""),
    ]


# --- Titular del documento (holder_scope) -----------------------------------------------


def test_holder_scope_defaults_to_participant_and_can_be_application(
    admin_client: APIClient,
) -> None:
    default = create(admin_client)
    assert default.status_code == 201, default.content
    assert default.json()["holder_scope"] == "PARTICIPANT"

    photos = create(admin_client, code="PROPERTY_PHOTOS_2", holder_scope="APPLICATION")
    assert photos.status_code == 201, photos.content
    assert photos.json()["holder_scope"] == "APPLICATION"

    body = assert_error(
        create(admin_client, code="OTHER", holder_scope="BANK"), 400, "VALIDATION_ERROR"
    )
    assert body["details"][0]["field"] == "holder_scope"


def test_holder_scope_cannot_change_while_the_type_has_live_requirements(
    admin_client: APIClient,
) -> None:
    identity = seeded_type("IDENTITY_DOCUMENT")

    response = admin_client.patch(
        type_url(identity), {"holder_scope": "APPLICATION"}, format="json"
    )

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "holder_scope"
    identity.refresh_from_db()
    assert identity.holder_scope == "PARTICIPANT"

    # Repetir el valor actual no es un cambio.
    same = admin_client.patch(type_url(identity), {"holder_scope": "PARTICIPANT"}, format="json")
    assert same.status_code == 200, same.content


def test_holder_scope_changes_when_no_requirement_is_live(admin_client: APIClient) -> None:
    identity = seeded_type("IDENTITY_DOCUMENT")
    DocumentRequirement.objects.filter(document_type=identity).update(status="INACTIVE")

    response = admin_client.patch(
        type_url(identity), {"holder_scope": "APPLICATION"}, format="json"
    )

    assert response.status_code == 200, response.content
    assert response.json()["holder_scope"] == "APPLICATION"
