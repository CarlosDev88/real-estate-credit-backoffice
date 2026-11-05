"""Inmueble y financiación de la solicitud (API §18.1 y §18.2), `include` del detalle
(API §16.1) y la coherencia entre el producto del `PATCH` y la modalidad."""

from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancingPreference,
    ParticipantRole,
    Property,
)
from apps.applications.signals import application_updated
from apps.banking.models import BankProduct
from apps.catalogs.workflow import ApplicationStatus, ProjectStatus
from apps.crm.models import Client, Opportunity
from apps.identity.models import User
from apps.partners.models import Project
from tests.applications.conftest import application_url, catalog_item, seeded_product
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

PROPERTY: dict[str, Any] = {
    "property_type_code": "APARTMENT",
    "condition_code": "NEW",
    "unit_reference": "Torre 2 · Apto 803",
    "city_code": "11001",
    "address": "Carrera 11 # 118-40",
    "estimated_value_cop": 420_000_000,
    "is_owned_by_applicant": False,
}
USED_PROPERTY: dict[str, Any] = {
    "property_type_code": "HOUSE",
    "condition_code": "USED",
    "city_code": "11001",
    "address": "Calle 93 # 11-20",
    "estimated_value_cop": 380_000_000,
}


def bank_credit(product: BankProduct | None = None, **extra: Any) -> dict[str, Any]:
    product = product or seeded_product()
    return {
        "financing_mode_code": "BANK_CREDIT",
        "bank_product_id": str(product.id),
        "requested_amount_cop": 294_000_000,
        "term_months": 240,
        "currency_mode_code": "COP",
        "amortization_mode_code": "FIXED_PAYMENT",
        "own_resources_cop": 126_000_000,
        "uses_severance_funds": True,
        "severance_funds_cop": 30_000_000,
        **extra,
    }


def put(
    client: APIClient,
    application: CreditApplication,
    resource: str,
    data: dict[str, Any],
    if_match: str | None = '"1"',
) -> Any:
    headers = {} if if_match is None else {"If-Match": if_match}
    return client.put(
        application_url(application, f"/{resource}"), data, format="json", headers=headers
    )


def payload_for(resource: str) -> dict[str, Any]:
    return PROPERTY if resource == "property" else bank_credit()


def version_of(application: CreditApplication) -> int:
    application.refresh_from_db(fields=["version", "bank_product"])
    return application.version


@pytest.fixture
def updated_fields() -> Any:
    """Captura los ``fields`` de cada ``application_updated``."""
    received: list[list[str]] = []

    def on_updated(**kwargs: Any) -> None:
        received.append(kwargs["fields"])

    application_updated.connect(on_updated)
    yield received
    application_updated.disconnect(on_updated)


@pytest.fixture
def used_application(
    make_application: Callable[..., CreditApplication],
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> CreditApplication:
    client = make_client(document_number="52123456")
    return make_application(
        make_opportunity(client), purpose_item=catalog_item("loan_purpose", "PURCHASE_USED")
    )


# --- Inmueble ---------------------------------------------------------------------------


def test_property_is_404_until_it_is_registered(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = advisor_client.get(application_url(application, "/property"))
    assert_error(response, 404, "RESOURCE_NOT_FOUND")


def test_put_creates_the_property(
    advisor_client: APIClient,
    application: CreditApplication,
    active_project: Project,
    updated_fields: list[list[str]],
) -> None:
    response = put(
        advisor_client,
        application,
        "property",
        {**PROPERTY, "project_id": str(active_project.id)},
    )

    assert response.status_code == 201, response.content
    assert response["ETag"] == '"2"'
    body = response.json()
    assert body["project"] == {"id": str(active_project.id), "name": "Verona 118"}
    assert body["condition"]["code"] == "NEW"
    assert body["unit_reference"] == "Torre 2 · Apto 803"
    assert body["is_owned_by_applicant"] is False
    assert version_of(application) == 2
    assert updated_fields == [["property"]]

    fetched = advisor_client.get(application_url(application, "/property"))
    assert fetched.status_code == 200
    assert fetched["ETag"] == '"2"'
    assert fetched.json()["id"] == body["id"]


def test_put_replaces_the_whole_property(
    advisor_client: APIClient, application: CreditApplication, active_project: Project
) -> None:
    put(advisor_client, application, "property", {**PROPERTY, "project_id": str(active_project.id)})

    response = put(
        advisor_client,
        application,
        "property",
        {**PROPERTY, "unit_reference": "", "estimated_value_cop": 450_000_000},
        '"2"',
    )

    assert response.status_code == 200, response.content
    assert response["ETag"] == '"3"'
    body = response.json()
    assert body["project"] is None
    assert body["unit_reference"] == ""
    assert body["estimated_value_cop"] == 450_000_000
    assert Property.objects.filter(application=application).count() == 1


def test_put_without_real_changes_keeps_the_version(
    advisor_client: APIClient, application: CreditApplication, updated_fields: list[list[str]]
) -> None:
    put(advisor_client, application, "property", PROPERTY)

    response = put(advisor_client, application, "property", PROPERTY, '"2"')

    assert response.status_code == 200
    assert response["ETag"] == '"2"'
    assert version_of(application) == 2
    assert updated_fields == [["property"]]


def test_property_put_requires_a_current_if_match(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    assert_error(
        put(advisor_client, application, "property", PROPERTY, None), 428, "PRECONDITION_REQUIRED"
    )
    body = assert_error(
        put(advisor_client, application, "property", PROPERTY, '"7"'), 409, "STALE_VERSION"
    )
    assert body["details"][0]["current_version"] == 1
    assert not Property.objects.filter(application=application).exists()


def test_project_must_be_active(
    advisor_client: APIClient, application: CreditApplication, make_project: Callable[..., Project]
) -> None:
    archived = make_project(name="Archivado", status=ProjectStatus.ARCHIVED)

    response = put(
        advisor_client, application, "property", {**PROPERTY, "project_id": str(archived.id)}
    )

    assert_error(response, 422, "PROJECT_NOT_ACTIVE")


def test_unknown_project_is_rejected(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = put(
        advisor_client,
        application,
        "property",
        {**PROPERTY, "project_id": "00000000-0000-0000-0000-000000000000"},
    )

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "project_id"


def test_only_new_homes_admit_a_project(
    advisor_client: APIClient, used_application: CreditApplication, active_project: Project
) -> None:
    response = put(
        advisor_client,
        used_application,
        "property",
        {**USED_PROPERTY, "project_id": str(active_project.id)},
    )

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert {item["field"] for item in body["details"]} == {"project_id"}


def test_used_homes_require_an_address(
    advisor_client: APIClient, used_application: CreditApplication
) -> None:
    response = put(advisor_client, used_application, "property", {**USED_PROPERTY, "address": ""})

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert {item["field"] for item in body["details"]} == {"address"}


def test_home_improvement_requires_the_ownership_declaration(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    application.purpose_item = catalog_item("loan_purpose", "HOME_IMPROVEMENT")
    application.save()

    response = put(advisor_client, application, "property", USED_PROPERTY)
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert {item["field"] for item in body["details"]} == {"is_owned_by_applicant"}

    accepted = put(
        advisor_client, application, "property", {**USED_PROPERTY, "is_owned_by_applicant": True}
    )
    assert accepted.status_code == 201, accepted.content


def test_property_rejects_unknown_fields(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = put(advisor_client, application, "property", {**PROPERTY, "relationship": "x"})
    assert_error(response, 400, "VALIDATION_ERROR")


# --- Financiación -----------------------------------------------------------------------


def test_financing_is_404_until_it_is_registered(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = advisor_client.get(application_url(application, "/financing"))
    assert_error(response, 404, "RESOURCE_NOT_FOUND")


def test_bank_credit_saves_the_financing_and_the_product(
    advisor_client: APIClient, application: CreditApplication, updated_fields: list[list[str]]
) -> None:
    product = seeded_product()

    response = put(advisor_client, application, "financing", bank_credit(product))

    assert response.status_code == 201, response.content
    assert response["ETag"] == '"2"'
    body = response.json()
    assert body["application_id"] == str(application.id)
    assert body["financing_mode"]["code"] == "BANK_CREDIT"
    assert body["bank_product"]["id"] == str(product.id)
    assert body["bank_product"]["bank"]["name"] == "Bancolombia"
    assert body["requested_amount_cop"] == 294_000_000
    assert body["term_months"] == 240
    assert body["currency_mode"]["code"] == "COP"
    assert body["amortization_mode"]["code"] == "FIXED_PAYMENT"
    assert body["severance_funds_cop"] == 30_000_000
    assert body["external_approved_amount_cop"] is None
    assert version_of(application) == 2
    assert application.bank_product_id == product.id
    assert updated_fields == [["bank_product", "financing"]]

    fetched = advisor_client.get(application_url(application, "/financing"))
    assert fetched.status_code == 200
    assert fetched["ETag"] == '"2"'
    assert fetched.json() == body


def test_financing_put_replaces_every_field(
    advisor_client: APIClient, application: CreditApplication, updated_fields: list[list[str]]
) -> None:
    put(advisor_client, application, "financing", bank_credit())

    response = put(
        advisor_client,
        application,
        "financing",
        {
            "financing_mode_code": "BANK_CREDIT",
            "bank_product_id": str(seeded_product().id),
            "requested_amount_cop": 300_000_000,
        },
        '"2"',
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["term_months"] is None
    assert body["currency_mode"] is None
    assert body["amortization_mode"] is None
    assert body["own_resources_cop"] == 0
    assert body["uses_severance_funds"] is False
    assert body["severance_funds_cop"] == 0
    assert version_of(application) == 3
    assert updated_fields[-1] == ["financing"]


def test_financing_put_without_real_changes_keeps_the_version(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    put(advisor_client, application, "financing", bank_credit())

    response = put(advisor_client, application, "financing", bank_credit(), '"2"')

    assert response.status_code == 200
    assert version_of(application) == 2


def test_changing_only_the_product_bumps_the_version(
    advisor_client: APIClient, application: CreditApplication, updated_fields: list[list[str]]
) -> None:
    put(advisor_client, application, "financing", bank_credit())

    response = put(
        advisor_client, application, "financing", bank_credit(seeded_product("FNA")), '"2"'
    )

    assert response.status_code == 200, response.content
    assert response.json()["bank_product"]["id"] == str(seeded_product("FNA").id)
    assert version_of(application) == 3
    assert updated_fields[-1] == ["bank_product"]


def test_bank_credit_requires_a_product_and_an_amount(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = put(
        advisor_client,
        application,
        "financing",
        bank_credit(bank_product_id=None, requested_amount_cop=None),
    )

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert {item["field"] for item in body["details"]} == {
        "bank_product_id",
        "requested_amount_cop",
    }
    assert not FinancingPreference.objects.filter(application=application).exists()


def test_bank_product_must_admit_the_purpose(
    advisor_client: APIClient,
    used_application: CreditApplication,
    new_home_only_product: BankProduct,
) -> None:
    response = put(
        advisor_client, used_application, "financing", bank_credit(new_home_only_product)
    )

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "bank_product_id"
    assert version_of(used_application) == 1


def test_unknown_bank_product_is_rejected(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = put(
        advisor_client,
        application,
        "financing",
        bank_credit(bank_product_id="00000000-0000-0000-0000-000000000000"),
    )

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "bank_product_id"


def test_own_funds_clears_the_product_and_the_requested_amount(
    advisor_client: APIClient, application: CreditApplication, updated_fields: list[list[str]]
) -> None:
    put(advisor_client, application, "financing", bank_credit())

    response = put(
        advisor_client,
        application,
        "financing",
        {"financing_mode_code": "OWN_FUNDS", "own_resources_cop": 420_000_000},
        '"2"',
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["financing_mode"]["code"] == "OWN_FUNDS"
    assert body["bank_product"] is None
    assert body["requested_amount_cop"] == 0
    assert version_of(application) == 3
    assert application.bank_product_id is None
    assert updated_fields[-1] == ["bank_product", "financing"]


@pytest.mark.parametrize("mode", ["OWN_FUNDS", "EXTERNAL_CREDIT"])
def test_non_bank_modes_reject_a_product_and_a_requested_amount(
    advisor_client: APIClient, application: CreditApplication, mode: str
) -> None:
    response = put(
        advisor_client,
        application,
        "financing",
        {
            "financing_mode_code": mode,
            "bank_product_id": str(seeded_product().id),
            "requested_amount_cop": 1_000_000,
            "external_approved_amount_cop": 300_000_000,
        },
    )

    body = assert_error(response, 400, "VALIDATION_ERROR")
    fields = {item["field"] for item in body["details"]}
    assert {"bank_product_id", "requested_amount_cop"} <= fields


def test_explicit_zero_amount_is_accepted_without_bank_credit(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = put(
        advisor_client,
        application,
        "financing",
        {"financing_mode_code": "OWN_FUNDS", "requested_amount_cop": 0},
    )

    assert response.status_code == 201, response.content


def test_external_credit_requires_the_approved_amount(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    missing = put(
        advisor_client, application, "financing", {"financing_mode_code": "EXTERNAL_CREDIT"}
    )
    body = assert_error(missing, 400, "VALIDATION_ERROR")
    assert {item["field"] for item in body["details"]} == {"external_approved_amount_cop"}

    response = put(
        advisor_client,
        application,
        "financing",
        {"financing_mode_code": "EXTERNAL_CREDIT", "external_approved_amount_cop": 300_000_000},
    )
    assert response.status_code == 201, response.content
    assert response.json()["external_approved_amount_cop"] == 300_000_000
    assert response.json()["bank_product"] is None


@pytest.mark.parametrize("mode", ["OWN_FUNDS", "BANK_CREDIT"])
def test_only_external_credit_takes_an_approved_amount(
    advisor_client: APIClient, application: CreditApplication, mode: str
) -> None:
    data = bank_credit() if mode == "BANK_CREDIT" else {"financing_mode_code": mode}

    response = put(
        advisor_client,
        application,
        "financing",
        {**data, "external_approved_amount_cop": 300_000_000},
    )

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert {item["field"] for item in body["details"]} == {"external_approved_amount_cop"}


def test_severance_amount_needs_the_severance_flag(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = put(
        advisor_client,
        application,
        "financing",
        bank_credit(uses_severance_funds=False, severance_funds_cop=30_000_000),
    )

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert {item["field"] for item in body["details"]} == {"severance_funds_cop"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("financing_mode_code", "LEASING"),
        ("currency_mode_code", "USD"),
        ("amortization_mode_code", "BALLOON"),
        ("term_months", 0),
        ("own_resources_cop", -1),
        ("product_id", "x"),
    ],
)
def test_financing_rejects_invalid_values(
    advisor_client: APIClient, application: CreditApplication, field: str, value: Any
) -> None:
    response = put(advisor_client, application, "financing", bank_credit(**{field: value}))

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == field


def test_financing_put_requires_a_current_if_match(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    assert_error(
        put(advisor_client, application, "financing", bank_credit(), None),
        428,
        "PRECONDITION_REQUIRED",
    )
    assert_error(
        put(advisor_client, application, "financing", bank_credit(), '"3"'), 409, "STALE_VERSION"
    )


# --- Estado, alcance y permisos ---------------------------------------------------------


@pytest.mark.parametrize("resource", ["property", "financing"])
def test_property_and_financing_are_frozen_from_filing(
    advisor_client: APIClient, application: CreditApplication, resource: str
) -> None:
    data = payload_for(resource)
    application.status = ApplicationStatus.FILED
    application.save()

    assert_error(put(advisor_client, application, resource, data), 409, "APPLICATION_NOT_EDITABLE")


@pytest.mark.parametrize("resource", ["property", "financing"])
def test_property_and_financing_are_hidden_from_brokers_and_other_advisors(
    broker_client: APIClient,
    broker_user: User,
    other_advisor_client: APIClient,
    application: CreditApplication,
    resource: str,
) -> None:
    data = payload_for(resource)
    opportunity = application.opportunity
    opportunity.origin_user = broker_user
    opportunity.save()
    url = application_url(application, f"/{resource}")

    assert_error(broker_client.get(url), 403, "PERMISSION_DENIED")
    assert_error(put(broker_client, application, resource, data), 403, "PERMISSION_DENIED")
    assert_error(other_advisor_client.get(url), 404, "RESOURCE_NOT_FOUND")
    assert_error(put(other_advisor_client, application, resource, data), 404, "RESOURCE_NOT_FOUND")


def test_admin_edits_any_application(
    admin_client: APIClient, application: CreditApplication
) -> None:
    assert put(admin_client, application, "property", PROPERTY).status_code == 201
    assert put(admin_client, application, "financing", bank_credit(), '"2"').status_code == 201


# --- Producto del PATCH frente a la modalidad -------------------------------------------


def patch(client: APIClient, application: CreditApplication, data: dict[str, Any]) -> Any:
    headers = {"If-Match": f'"{version_of(application)}"'}
    return client.patch(application_url(application), data, format="json", headers=headers)


def test_patch_cannot_add_a_product_without_bank_credit(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    put(advisor_client, application, "financing", {"financing_mode_code": "OWN_FUNDS"})

    response = patch(advisor_client, application, {"bank_product_id": str(seeded_product().id)})

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "bank_product_id"
    assert version_of(application) == 2


def test_patch_cannot_clear_the_product_of_a_bank_credit(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    put(advisor_client, application, "financing", bank_credit())

    response = patch(advisor_client, application, {"bank_product_id": None})

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "bank_product_id"
    assert application.bank_product_id == seeded_product().id


def test_patch_can_switch_the_product_of_a_bank_credit(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    put(advisor_client, application, "financing", bank_credit())
    other = seeded_product("FNA")

    response = patch(advisor_client, application, {"bank_product_id": str(other.id)})

    assert response.status_code == 200, response.content
    assert response.json()["bank_product"]["id"] == str(other.id)
    financing = advisor_client.get(application_url(application, "/financing")).json()
    assert financing["bank_product"]["id"] == str(other.id)


def test_patch_without_financing_keeps_working(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    selected = patch(advisor_client, application, {"bank_product_id": str(seeded_product().id)})
    assert selected.status_code == 200, selected.content

    cleared = patch(advisor_client, application, {"bank_product_id": None})
    assert cleared.status_code == 200, cleared.content
    assert cleared.json()["bank_product"] is None


def test_patch_of_the_purpose_ignores_the_financing_mode(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    put(advisor_client, application, "financing", {"financing_mode_code": "OWN_FUNDS"})

    response = patch(advisor_client, application, {"purpose_code": "PURCHASE_USED"})

    assert response.status_code == 200, response.content


# --- include del detalle ----------------------------------------------------------------


def test_detail_omits_optional_blocks_by_default(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    body = advisor_client.get(application_url(application)).json()

    assert "property" in body
    assert "assignments" in body
    assert "participants" not in body
    assert "financing" not in body


def test_detail_includes_participants_and_financing(
    advisor_client: APIClient,
    application: CreditApplication,
    primary: ApplicationParticipant,
    make_client: Callable[..., Client],
) -> None:
    retired = ApplicationParticipant.objects.create(
        application=application,
        client=make_client(document_number="79111222"),
        role=ParticipantRole.CO_APPLICANT,
        is_active=False,
    )
    put(advisor_client, application, "financing", bank_credit())

    response = advisor_client.get(
        application_url(application), {"include": "participants, financing,property"}
    )

    assert response.status_code == 200, response.content
    assert response["ETag"] == '"2"'
    body = response.json()
    assert [item["id"] for item in body["participants"]] == [str(primary.id)]
    assert str(retired.id) not in {item["id"] for item in body["participants"]}
    assert body["participants"][0]["role"] == "PRIMARY"
    assert body["financing"]["financing_mode"]["code"] == "BANK_CREDIT"
    assert body["financing"]["bank_product"]["id"] == str(seeded_product().id)


def test_included_financing_is_null_when_missing(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    body = advisor_client.get(application_url(application), {"include": "financing"}).json()

    assert body["financing"] is None
    assert "participants" not in body


@pytest.mark.parametrize("value", ["documents", "participants,history", "PARTICIPANTS"])
def test_detail_rejects_unknown_includes(
    advisor_client: APIClient, application: CreditApplication, value: str
) -> None:
    response = advisor_client.get(application_url(application), {"include": value})

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "include"


def test_brokers_ignore_include(
    broker_client: APIClient, broker_user: User, application: CreditApplication
) -> None:
    opportunity = application.opportunity
    opportunity.origin_user = broker_user
    opportunity.save()

    for value in ("participants,financing", "desconocido"):
        response = broker_client.get(application_url(application), {"include": value})
        assert response.status_code == 200, response.content
        body = response.json()
        assert "participants" not in body
        assert "financing" not in body
        assert "property" not in body
