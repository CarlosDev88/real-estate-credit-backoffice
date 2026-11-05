from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.banking.models import BankProductPurpose
from apps.documents.models import SCOPE_FIELDS, DocumentRequirement, DocumentType
from apps.documents.services import _scope_of
from apps.documents.signals import document_requirement_status_changed
from tests.documents.conftest import (
    REQUIREMENTS_URL,
    catalog_item,
    seeded_product,
    seeded_type,
)
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db


def requirement_url(requirement: DocumentRequirement | str, action: str = "") -> str:
    requirement_id = requirement if isinstance(requirement, str) else requirement.id
    return f"{REQUIREMENTS_URL}/{requirement_id}{'/' + action if action else ''}"


def create(api: APIClient, document_type: DocumentType, **payload: Any) -> Any:
    return api.post(
        REQUIREMENTS_URL, {"document_type_id": str(document_type.id), **payload}, format="json"
    )


def patch(api: APIClient, requirement: DocumentRequirement, **payload: Any) -> Any:
    return api.patch(requirement_url(requirement), payload, format="json")


def versions(requirement: DocumentRequirement) -> list[tuple[int, str]]:
    return list(
        DocumentRequirement.objects.filter(
            document_type=requirement.document_type,
            bank_product=requirement.bank_product,
            participant_role=requirement.participant_role,
        )
        .order_by("version")
        .values_list("version", "status")
    )


def codes(response: Any) -> list[str]:
    assert response.status_code == 200, response.content
    return [item["document_type"]["code"] for item in response.json()["items"]]


@pytest.fixture
def status_events() -> Iterator[list[dict[str, Any]]]:
    received: list[dict[str, Any]] = []

    def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    document_requirement_status_changed.connect(handler)
    try:
        yield received
    finally:
        document_requirement_status_changed.disconnect(handler)


@pytest.fixture
def active_requirement(
    make_requirement: Callable[..., DocumentRequirement],
) -> DocumentRequirement:
    return make_requirement(status="ACTIVE", sort_order=5)


# --- Acceso -----------------------------------------------------------------------------


def test_advisor_reads_but_cannot_write(
    advisor_client: APIClient, document_type: DocumentType
) -> None:
    listing = advisor_client.get(REQUIREMENTS_URL)

    assert listing.status_code == 200
    assert listing.json()["total"] == 9
    assert_error(create(advisor_client, document_type), 403, "PERMISSION_DENIED")


@pytest.mark.parametrize("client_fixture", ["broker_client", "partner_client"])
def test_broker_and_partner_cannot_read(
    request: pytest.FixtureRequest, client_fixture: str
) -> None:
    api: APIClient = request.getfixturevalue(client_fixture)
    requirement = DocumentRequirement.objects.first()
    assert requirement is not None

    assert_error(api.get(REQUIREMENTS_URL), 403, "PERMISSION_DENIED")
    assert_error(api.get(requirement_url(requirement)), 403, "PERMISSION_DENIED")


# --- Listado ----------------------------------------------------------------------------


def test_list_filters(admin_client: APIClient) -> None:
    bancolombia = seeded_product("BANCOLOMBIA")
    fna = seeded_product("FNA")

    def listing(**params: Any) -> list[str]:
        return codes(admin_client.get(REQUIREMENTS_URL, params))

    assert len(listing(bank_product_id=str(bancolombia.id))) == 9
    assert listing(bank_id=str(fna.bank_id)) == []
    assert listing(employment_profile="EMPLOYEE") == ["EMPLOYMENT_CERTIFICATE", "PAYROLL_SLIP"]
    assert listing(alternative_group_code="INCOME_TAX_PROOF") == [
        "INCOME_RETENTION_CERTIFICATE",
        "INCOME_TAX_RETURN",
    ]
    assert listing(document_type_code="BANK_STATEMENT") == ["BANK_STATEMENT"]
    assert listing(general="true") == []
    assert listing(status="DRAFT") == []


def test_list_rejects_invalid_filters(admin_client: APIClient) -> None:
    for params in (
        {"status": "PUBLISHED"},
        {"participant_role": "OWNER"},
        {"bank_product_id": "no-uuid"},
        {"ordering": "document_type"},
    ):
        assert_error(admin_client.get(REQUIREMENTS_URL, params), 400, "VALIDATION_ERROR")


# --- Crear ------------------------------------------------------------------------------


def test_create_general_requirement_as_draft_v1(
    admin_client: APIClient, document_type: DocumentType
) -> None:
    response = create(admin_client, document_type, alternative_group_code="")

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["bank_product"] is None
    assert body["document_type"]["code"] == "TEST_DOCUMENT"
    assert (body["version"], body["status"]) == (1, "DRAFT")
    assert (body["is_required"], body["is_waivable"], body["minimum_files"]) == (True, False, 1)
    assert body["alternative_group_code"] is None
    for field in ("purpose", "employment_profile", "participant_role", "property_condition"):
        assert body[field] is None


def test_create_with_full_scope(admin_client: APIClient, document_type: DocumentType) -> None:
    fna = seeded_product("FNA")

    response = create(
        admin_client,
        document_type,
        bank_product_id=str(fna.id),
        purpose_code="HOME_IMPROVEMENT",
        employment_profile_code="INDEPENDENT",
        participant_role="CO_APPLICANT",
        property_condition_code="USED",
        is_waivable=True,
        validity_days=60,
        sort_order=40,
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["bank_product"]["bank"]["code"] == "FNA"
    assert body["purpose"] == {
        "code": "HOME_IMPROVEMENT",
        "label": "Remodelación o mejora de vivienda",
    }
    assert body["employment_profile"]["code"] == "INDEPENDENT"
    assert body["participant_role"] == "CO_APPLICANT"
    assert body["property_condition"]["code"] == "USED"
    assert (body["is_waivable"], body["validity_days"], body["sort_order"]) == (True, 60, 40)


def test_purpose_must_be_admitted_by_the_product(
    admin_client: APIClient, document_type: DocumentType
) -> None:
    fna = seeded_product("FNA")
    BankProductPurpose.objects.filter(
        bank_product=fna, purpose_item__code="HOME_IMPROVEMENT"
    ).update(is_active=False)

    response = create(
        admin_client, document_type, bank_product_id=str(fna.id), purpose_code="HOME_IMPROVEMENT"
    )

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "purpose_code"


def test_several_files_need_a_repeatable_type(
    admin_client: APIClient, document_type: DocumentType
) -> None:
    rejected = create(admin_client, document_type, minimum_files=3)
    accepted = create(admin_client, seeded_type("PAYROLL_SLIP"), minimum_files=6)

    body = assert_error(rejected, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "minimum_files"
    assert accepted.status_code == 201, accepted.content


def test_existing_scope_is_rejected_with_latest_version(
    admin_client: APIClient, make_requirement: Callable[..., DocumentRequirement]
) -> None:
    make_requirement(status="INACTIVE")
    latest = make_requirement(version=2, status="ACTIVE")

    response = create(admin_client, latest.document_type)

    body = assert_error(response, 409, "REQUIREMENT_SCOPE_EXISTS")
    assert body["details"][0]["resource_id"] == str(latest.id)


def test_same_type_with_another_scope_is_another_requirement(
    admin_client: APIClient, active_requirement: DocumentRequirement
) -> None:
    response = create(admin_client, active_requirement.document_type, participant_role="PRIMARY")

    assert response.status_code == 201, response.content
    assert response.json()["version"] == 1


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"purpose_code": "EMPLOYEE"}, "purpose_code"),
        ({"employment_profile_code": "PURCHASE_NEW"}, "employment_profile_code"),
        ({"participant_role": "OWNER"}, "participant_role"),
        ({"bank_product_id": "00000000-0000-0000-0000-000000000000"}, "bank_product_id"),
        ({"minimum_files": 0}, "minimum_files"),
        ({"validity_days": 0}, "validity_days"),
        ({"alternative_group_code": "uno-de-estos"}, "alternative_group_code"),
        ({"status": "ACTIVE"}, "status"),
        ({"version": 4}, "version"),
    ],
)
def test_create_validates_fields(
    admin_client: APIClient, document_type: DocumentType, payload: dict[str, Any], field: str
) -> None:
    body = assert_error(create(admin_client, document_type, **payload), 400, "VALIDATION_ERROR")
    assert field in {detail["field"] for detail in body["details"]}


def test_create_rejects_unknown_type_and_reversed_validity(
    admin_client: APIClient, document_type: DocumentType
) -> None:
    now = timezone.now()
    missing = admin_client.post(
        REQUIREMENTS_URL,
        {"document_type_id": "00000000-0000-0000-0000-000000000000"},
        format="json",
    )
    reversed_validity = create(
        admin_client,
        document_type,
        valid_from=now.isoformat(),
        valid_to=(now - timedelta(days=1)).isoformat(),
    )

    assert_error(missing, 400, "VALIDATION_ERROR")
    body = assert_error(reversed_validity, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "valid_to"


# --- Editar y versionar -----------------------------------------------------------------


def test_patch_edits_a_draft_in_place(
    admin_client: APIClient, make_requirement: Callable[..., DocumentRequirement]
) -> None:
    draft = make_requirement()

    response = patch(admin_client, draft, is_required=False, sort_order=70)

    assert response.status_code == 200, response.content
    assert response.json()["id"] == str(draft.id)
    assert versions(draft) == [(1, "DRAFT")]
    draft.refresh_from_db()
    assert (draft.is_required, draft.sort_order) == (False, 70)


def test_patch_on_published_version_creates_next_draft(
    admin_client: APIClient, active_requirement: DocumentRequirement
) -> None:
    response = patch(admin_client, active_requirement, validity_days=45)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["id"] != str(active_requirement.id)
    assert (body["version"], body["status"]) == (2, "DRAFT")
    assert (body["validity_days"], body["sort_order"]) == (45, 5)
    assert body["document_type"]["id"] == str(active_requirement.document_type_id)
    assert versions(active_requirement) == [(1, "ACTIVE"), (2, "DRAFT")]
    active_requirement.refresh_from_db()
    assert active_requirement.validity_days is None


def test_only_one_draft_per_scope(
    admin_client: APIClient, active_requirement: DocumentRequirement
) -> None:
    draft_id = patch(admin_client, active_requirement, sort_order=1).json()["id"]

    response = patch(admin_client, active_requirement, sort_order=2)

    body = assert_error(response, 409, "REQUIREMENT_DRAFT_EXISTS")
    assert body["details"][0]["resource_id"] == draft_id


def test_new_draft_takes_the_highest_version_plus_one(
    admin_client: APIClient, make_requirement: Callable[..., DocumentRequirement]
) -> None:
    old = make_requirement(status="INACTIVE")
    make_requirement(version=2, status="ACTIVE")

    response = patch(admin_client, old, is_waivable=True)

    assert response.status_code == 201, response.content
    assert response.json()["version"] == 3


@pytest.mark.parametrize(
    "field",
    [
        "bank_product_id",
        "document_type_id",
        "purpose_code",
        "employment_profile_code",
        "participant_role",
        "property_condition_code",
    ],
)
def test_scope_is_not_editable(
    admin_client: APIClient, active_requirement: DocumentRequirement, field: str
) -> None:
    body = assert_error(
        patch(admin_client, active_requirement, **{field: None}), 400, "VALIDATION_ERROR"
    )
    assert body["details"][0]["field"] == field
    assert versions(active_requirement) == [(1, "ACTIVE")]


def test_patch_checks_minimum_files_and_validity(
    admin_client: APIClient, make_requirement: Callable[..., DocumentRequirement]
) -> None:
    draft = make_requirement()

    many_files = patch(admin_client, draft, minimum_files=2)
    reversed_validity = patch(
        admin_client, draft, valid_to=(draft.valid_from - timedelta(days=1)).isoformat()
    )

    assert_error(many_files, 400, "VALIDATION_ERROR")
    assert_error(reversed_validity, 400, "VALIDATION_ERROR")


# --- Publicar y desactivar --------------------------------------------------------------


def test_activate_replaces_the_previous_active_version(
    admin_client: APIClient,
    active_requirement: DocumentRequirement,
    status_events: list[dict[str, Any]],
) -> None:
    draft_id = patch(admin_client, active_requirement, sort_order=8).json()["id"]

    response = admin_client.post(requirement_url(draft_id, "activate"))

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "ACTIVE"
    assert versions(active_requirement) == [(1, "INACTIVE"), (2, "ACTIVE")]
    assert [(e["from_status"], e["to_status"]) for e in status_events] == [
        ("ACTIVE", "INACTIVE"),
        ("DRAFT", "ACTIVE"),
    ]


def test_activate_is_idempotent(
    admin_client: APIClient,
    active_requirement: DocumentRequirement,
    status_events: list[dict[str, Any]],
) -> None:
    response = admin_client.post(requirement_url(active_requirement, "activate"))

    assert response.status_code == 200
    assert status_events == []


def test_activate_requires_an_active_type(
    admin_client: APIClient, make_requirement: Callable[..., DocumentRequirement]
) -> None:
    draft = make_requirement()
    DocumentType.objects.filter(pk=draft.document_type_id).update(is_active=False)

    response = admin_client.post(requirement_url(draft, "activate"))

    assert_error(response, 422, "DOCUMENT_TYPE_INACTIVE")
    draft.refresh_from_db()
    assert draft.status == "DRAFT"


def test_activate_rejects_an_expired_version(
    admin_client: APIClient, make_requirement: Callable[..., DocumentRequirement]
) -> None:
    now = timezone.now()
    draft = make_requirement(valid_from=now - timedelta(days=10), valid_to=now - timedelta(days=1))

    assert_error(admin_client.post(requirement_url(draft, "activate")), 422, "REQUIREMENT_EXPIRED")


def test_deactivate_published_but_not_draft(
    admin_client: APIClient,
    active_requirement: DocumentRequirement,
    make_requirement: Callable[..., DocumentRequirement],
) -> None:
    draft = make_requirement(version=2)

    off = admin_client.post(requirement_url(active_requirement, "deactivate"))
    on_draft = admin_client.post(requirement_url(draft, "deactivate"))

    assert off.status_code == 200
    assert off.json()["status"] == "INACTIVE"
    assert_error(on_draft, 409, "INVALID_STATE_TRANSITION")


def test_advisor_cannot_publish(
    advisor_client: APIClient, make_requirement: Callable[..., DocumentRequirement]
) -> None:
    draft = make_requirement()
    assert_error(advisor_client.post(requirement_url(draft, "activate")), 403, "PERMISSION_DENIED")


# --- Restricciones de la base de datos --------------------------------------------------


def test_scope_columns_follow_scope_fields(active_requirement: DocumentRequirement) -> None:
    expected = set()
    for name in SCOPE_FIELDS:
        field = DocumentRequirement._meta.get_field(name)
        assert isinstance(field, models.Field)
        expected.add(field.column)
    assert set(_scope_of(active_requirement)) == expected


def test_database_allows_one_active_version_per_scope_even_with_nulls(
    make_requirement: Callable[..., DocumentRequirement],
) -> None:
    make_requirement(status="ACTIVE")

    with pytest.raises(IntegrityError), transaction.atomic():
        make_requirement(version=2, status="ACTIVE")


def test_database_allows_one_draft_per_scope_even_with_nulls(
    make_requirement: Callable[..., DocumentRequirement],
) -> None:
    make_requirement()

    with pytest.raises(IntegrityError), transaction.atomic():
        make_requirement(version=2)


def test_database_rejects_a_repeated_version_in_the_same_scope(
    make_requirement: Callable[..., DocumentRequirement],
) -> None:
    make_requirement(status="INACTIVE")

    with pytest.raises(IntegrityError), transaction.atomic():
        make_requirement(status="ACTIVE")


def test_database_rejects_unknown_participant_role(
    make_requirement: Callable[..., DocumentRequirement],
) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        make_requirement(participant_role="OWNER")


def test_scope_with_a_catalog_value_is_independent_from_the_null_scope(
    make_requirement: Callable[..., DocumentRequirement],
) -> None:
    make_requirement(status="ACTIVE")
    other = make_requirement(
        status="ACTIVE", employment_profile_item=catalog_item("employment_profile", "EMPLOYEE")
    )
    assert other.version == 1
