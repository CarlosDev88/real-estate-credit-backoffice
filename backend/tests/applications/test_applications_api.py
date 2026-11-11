"""Solicitud principal (API §16.1 y §16.2): creación, alcance, detalle, edición y resumen."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import (
    ApplicationAssignment,
    ApplicationStatusHistory,
    CreditApplication,
    Property,
)
from apps.applications.signals import application_created, application_updated
from apps.banking.models import BankProduct, BankStatus
from apps.catalogs.workflow import ApplicationStatus, OpportunityStatus, ProjectStatus
from apps.crm.models import Client, Opportunity
from apps.crm.signals import opportunity_status_changed
from apps.identity.models import User
from apps.partners.models import Project
from tests.applications.conftest import (
    APPLICATIONS_URL,
    application_url,
    catalog_item,
    seeded_product,
)
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

PROPERTY: dict[str, Any] = {
    "property_type_code": "APARTMENT",
    "condition_code": "NEW",
    "city_code": "11001",
    "estimated_value_cop": 420_000_000,
}
USED_PROPERTY: dict[str, Any] = {
    **PROPERTY,
    "condition_code": "USED",
    "address": "Calle 93 # 11-20",
}
SUMMARY_KEYS = {
    "id",
    "code",
    "status",
    "status_label",
    "opportunity_id",
    "purpose",
    "client_name",
    "client_document_number",
    "bank_name",
    "product_name",
    "advisor_name",
    "current_stage_started_at",
    "days_in_stage",
    "created_at",
    "updated_at",
}


def create(client: APIClient, opportunity: Opportunity, **overrides: Any) -> Any:
    payload: dict[str, Any] = {
        "opportunity_id": str(opportunity.id),
        "purpose_code": "PURCHASE_NEW",
        "property": PROPERTY,
        **overrides,
    }
    return client.post(APPLICATIONS_URL, payload, format="json")


def patch(
    client: APIClient,
    application: CreditApplication,
    data: dict[str, Any],
    if_match: str | None = '"1"',
) -> Any:
    headers = {} if if_match is None else {"If-Match": if_match}
    return client.patch(application_url(application), data, format="json", headers=headers)


def set_status(application: CreditApplication, status: str) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(status=status)


# --- Creación ---------------------------------------------------------------------------


def test_create_builds_the_whole_application_atomically(
    advisor_client: APIClient, advisor_user: User, opportunity: Opportunity, buyer: Client
) -> None:
    response = create(advisor_client, opportunity)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["code"].startswith("SOL-")
    assert body["status"] == ApplicationStatus.DRAFT
    assert body["version"] == 1
    assert response["ETag"] == '"1"'
    assert body["purpose"] == {"code": "PURCHASE_NEW", "label": "Compra de vivienda nueva"}
    assert body["assigned_advisor"]["id"] == str(advisor_user.id)
    assert body["applicant"]["id"] == str(buyer.id)
    assert body["bank_product"] is None
    assert body["property"]["estimated_value_cop"] == 420_000_000
    assert body["property"]["condition"]["code"] == "NEW"

    application = CreditApplication.objects.get(pk=body["id"])
    primary = application.participants.get()
    assert (primary.client_id, primary.role, primary.is_active) == (buyer.pk, "PRIMARY", True)
    assignment = ApplicationAssignment.objects.get(application=application)
    assert (assignment.advisor, assignment.assigned_by, assignment.ended_at) == (
        advisor_user,
        advisor_user,
        None,
    )
    history = ApplicationStatusHistory.objects.get(application=application)
    assert (history.from_status, history.to_status, history.application_version) == (
        None,
        ApplicationStatus.DRAFT,
        1,
    )
    assert history.actor_user == advisor_user

    opportunity.refresh_from_db()
    assert opportunity.status == OpportunityStatus.CONVERTED
    assert opportunity.converted_at is not None


def test_create_sends_events_after_commit(
    advisor_client: APIClient,
    opportunity: Opportunity,
    django_capture_on_commit_callbacks: Any,
) -> None:
    received: list[str] = []

    def on_converted(**kwargs: Any) -> None:
        received.append(f"opportunity:{kwargs['transition_code']}")

    def on_created(**kwargs: Any) -> None:
        received.append(f"application:{kwargs['application'].code}")

    opportunity_status_changed.connect(on_converted)
    application_created.connect(on_created)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            body = create(advisor_client, opportunity).json()
    finally:
        opportunity_status_changed.disconnect(on_converted)
        application_created.disconnect(on_created)

    assert sorted(received) == sorted(
        [f"application:{body['code']}", "opportunity:CONVERT_ASSIGNED"]
    )


def test_create_without_property(advisor_client: APIClient, opportunity: Opportunity) -> None:
    response = create(advisor_client, opportunity, property=None)

    assert response.status_code == 201, response.content
    assert response.json()["property"] is None
    assert not Property.objects.exists()


def test_create_uses_the_opportunity_advisor_by_default(
    admin_client: APIClient, advisor_user: User, opportunity: Opportunity
) -> None:
    body = create(admin_client, opportunity).json()
    assert body["assigned_advisor"]["id"] == str(advisor_user.id)


def test_create_with_another_advisor(
    advisor_client: APIClient, other_advisor: User, opportunity: Opportunity
) -> None:
    response = create(advisor_client, opportunity, assigned_advisor_id=str(other_advisor.id))

    # Se responde con lo creado aunque el creador ya no sea el asesor asignado.
    assert response.status_code == 201, response.content
    assert response.json()["assigned_advisor"]["id"] == str(other_advisor.id)
    assert advisor_client.get(application_url(response.json()["id"])).status_code == 404


def test_advisor_must_be_eligible(
    admin_client: APIClient, broker_user: User, opportunity: Opportunity
) -> None:
    response = create(admin_client, opportunity, assigned_advisor_id=str(broker_user.id))
    assert_error(response, 422, "ADVISOR_NOT_ELIGIBLE")


@pytest.mark.parametrize("status", ["ASSIGNED", "CONTACTED", "IN_PROGRESS"])
def test_managed_opportunities_are_converted(
    admin_client: APIClient,
    make_opportunity: Callable[..., Opportunity],
    buyer: Client,
    status: str,
) -> None:
    opportunity = make_opportunity(buyer, status=status)

    assert create(admin_client, opportunity).status_code == 201
    opportunity.refresh_from_db()
    assert opportunity.status == OpportunityStatus.CONVERTED


def test_new_opportunity_without_advisor_needs_one(
    admin_client: APIClient, make_opportunity: Callable[..., Opportunity], buyer: Client
) -> None:
    opportunity = make_opportunity(buyer, status=OpportunityStatus.NEW, assigned_advisor=None)

    body = assert_error(create(admin_client, opportunity), 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "assigned_advisor_id"


@pytest.mark.parametrize("status", ["NEW", "LOST", "CANCELLED"])
def test_opportunity_must_be_convertible(
    admin_client: APIClient,
    advisor_user: User,
    make_opportunity: Callable[..., Opportunity],
    buyer: Client,
    status: str,
) -> None:
    extra = {"lost_reason_item": catalog_item("opportunity_lost_reason", "OTHER")}
    opportunity = make_opportunity(buyer, status=status, **(extra if status == "LOST" else {}))

    response = create(admin_client, opportunity, assigned_advisor_id=str(advisor_user.id))

    assert_error(response, 409, "INVALID_STATE_TRANSITION")
    assert not CreditApplication.objects.exists()
    opportunity.refresh_from_db()
    assert opportunity.status == status


def test_only_one_open_application_per_opportunity(
    advisor_client: APIClient, opportunity: Opportunity
) -> None:
    first = create(advisor_client, opportunity).json()

    body = assert_error(create(advisor_client, opportunity), 409, "APPLICATION_ALREADY_OPEN")
    assert body["details"][0]["resource_id"] == first["id"]
    assert CreditApplication.objects.count() == 1


@pytest.mark.parametrize("failed_status", ["REJECTED", "CANCELLED"])
def test_a_new_attempt_after_a_failed_application(
    advisor_client: APIClient, opportunity: Opportunity, failed_status: str
) -> None:
    first = CreditApplication.objects.get(pk=create(advisor_client, opportunity).json()["id"])
    set_status(first, failed_status)

    response = create(advisor_client, opportunity)

    assert response.status_code == 201, response.content
    assert CreditApplication.objects.filter(opportunity=opportunity).count() == 2


@pytest.mark.parametrize("finished_status", ["DISBURSED", "OWN_FUNDS"])
def test_no_new_attempt_after_a_successful_application(
    advisor_client: APIClient, opportunity: Opportunity, finished_status: str
) -> None:
    first = CreditApplication.objects.get(pk=create(advisor_client, opportunity).json()["id"])
    set_status(first, finished_status)

    assert_error(create(advisor_client, opportunity), 409, "INVALID_STATE_TRANSITION")


def test_opportunity_must_be_visible(
    other_advisor_client: APIClient, opportunity: Opportunity
) -> None:
    body = assert_error(create(other_advisor_client, opportunity), 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "opportunity_id"


def test_purpose_must_exist(advisor_client: APIClient, opportunity: Opportunity) -> None:
    body = assert_error(
        create(advisor_client, opportunity, purpose_code="BUY_PORTFOLIO"), 400, "VALIDATION_ERROR"
    )
    assert body["details"][0]["field"] == "purpose_code"


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "READY_TO_FILE"},
        {"bank_product_id": None},
        {"property": {**PROPERTY, "project_id": None}},
    ],
)
def test_unknown_fields_are_rejected(
    advisor_client: APIClient, opportunity: Opportunity, overrides: dict[str, Any]
) -> None:
    assert_error(create(advisor_client, opportunity, **overrides), 400, "VALIDATION_ERROR")


# --- Inmueble inicial: reglas por finalidad ---------------------------------------------


def test_new_home_can_belong_to_an_active_project(
    advisor_client: APIClient, opportunity: Opportunity, active_project: Project
) -> None:
    response = create(advisor_client, opportunity, project_id=str(active_project.id))

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["project"] == {"id": str(active_project.id), "name": "Verona 118"}
    assert body["property"]["project"]["id"] == str(active_project.id)


def test_project_must_be_active(
    advisor_client: APIClient, opportunity: Opportunity, make_project: Callable[..., Project]
) -> None:
    draft = make_project(status=ProjectStatus.DRAFT)
    assert_error(
        create(advisor_client, opportunity, project_id=str(draft.id)), 422, "PROJECT_NOT_ACTIVE"
    )


def test_project_requires_the_property(
    advisor_client: APIClient, opportunity: Opportunity, active_project: Project
) -> None:
    response = create(advisor_client, opportunity, project_id=str(active_project.id), property=None)
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "project_id"


def test_only_new_homes_admit_a_project(
    advisor_client: APIClient, opportunity: Opportunity, active_project: Project
) -> None:
    response = create(
        advisor_client,
        opportunity,
        purpose_code="PURCHASE_USED",
        project_id=str(active_project.id),
        property=USED_PROPERTY,
    )
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert {detail["field"] for detail in body["details"]} == {"project_id"}


def test_used_home_requires_an_address(advisor_client: APIClient, opportunity: Opportunity) -> None:
    response = create(
        advisor_client,
        opportunity,
        purpose_code="PURCHASE_USED",
        property={**PROPERTY, "condition_code": "USED"},
    )
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert {detail["field"] for detail in body["details"]} == {"property.address"}

    ok = create(advisor_client, opportunity, purpose_code="PURCHASE_USED", property=USED_PROPERTY)
    assert ok.status_code == 201, ok.content


def test_home_improvement_requires_address_and_ownership(
    advisor_client: APIClient, opportunity: Opportunity
) -> None:
    response = create(advisor_client, opportunity, purpose_code="HOME_IMPROVEMENT")
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert {detail["field"] for detail in body["details"]} == {
        "property.address",
        "property.is_owned_by_applicant",
    }
    assert not CreditApplication.objects.exists()
    opportunity.refresh_from_db()
    assert opportunity.status == OpportunityStatus.ASSIGNED

    response = create(
        advisor_client,
        opportunity,
        purpose_code="HOME_IMPROVEMENT",
        property={**USED_PROPERTY, "is_owned_by_applicant": True},
    )
    assert response.status_code == 201, response.content


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("estimated_value_cop", -1),
        ("city_code", "99999"),
        ("property_type_code", "CASTLE"),
    ],
)
def test_property_values_are_validated(
    advisor_client: APIClient, opportunity: Opportunity, field: str, value: Any
) -> None:
    response = create(advisor_client, opportunity, property={**PROPERTY, field: value})
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == f"property.{field}"


# --- Permisos de creación ---------------------------------------------------------------


def test_broker_and_partner_cannot_create(
    broker_client: APIClient, partner_client: APIClient, opportunity: Opportunity
) -> None:
    assert_error(create(broker_client, opportunity), 403, "PERMISSION_DENIED")
    assert_error(create(partner_client, opportunity), 403, "PERMISSION_DENIED")


# --- Alcance y lista --------------------------------------------------------------------


@pytest.fixture
def two_applications(
    make_application: Callable[..., CreditApplication],
    make_opportunity: Callable[..., Opportunity],
    make_client: Callable[..., Client],
    other_advisor: User,
    broker_user: User,
) -> tuple[CreditApplication, CreditApplication]:
    """Una del asesor (originada por el broker) y otra de la segunda asesora."""
    mine = make_application(
        make_opportunity(make_client(), origin_user=broker_user),
    )
    theirs = make_application(
        make_opportunity(
            make_client(document_number="80123456", first_names="Mateo"),
            assigned_advisor=other_advisor,
        ),
        assigned_advisor=other_advisor,
        purpose_item=catalog_item("loan_purpose", "PURCHASE_USED"),
    )
    return mine, theirs


def list_ids(client: APIClient, **params: Any) -> set[str]:
    response = client.get(APPLICATIONS_URL, params)
    assert response.status_code == 200, response.content
    return {item["id"] for item in response.json()["items"]}


def test_admin_sees_every_application(
    admin_client: APIClient, two_applications: tuple[CreditApplication, CreditApplication]
) -> None:
    assert list_ids(admin_client) == {str(app.id) for app in two_applications}


def test_advisor_sees_only_assigned_applications(
    advisor_client: APIClient, two_applications: tuple[CreditApplication, CreditApplication]
) -> None:
    mine, theirs = two_applications

    assert list_ids(advisor_client) == {str(mine.id)}
    assert_error(advisor_client.get(application_url(theirs)), 404, "RESOURCE_NOT_FOUND")


def test_broker_sees_only_the_summary_of_originated_applications(
    broker_client: APIClient, two_applications: tuple[CreditApplication, CreditApplication]
) -> None:
    mine, theirs = two_applications

    body = broker_client.get(APPLICATIONS_URL).json()
    assert [item["id"] for item in body["items"]] == [str(mine.id)]
    item = body["items"][0]
    assert set(item) == SUMMARY_KEYS
    assert item["client_document_number"] != "1032445908"
    assert item["client_document_number"].endswith("5908")

    detail = broker_client.get(application_url(mine))
    assert detail.status_code == 200
    assert set(detail.json()) == SUMMARY_KEYS
    assert_error(broker_client.get(application_url(theirs)), 404, "RESOURCE_NOT_FOUND")


def test_partner_has_no_access(
    partner_client: APIClient, two_applications: tuple[CreditApplication, CreditApplication]
) -> None:
    assert_error(partner_client.get(APPLICATIONS_URL), 403, "PERMISSION_DENIED")
    mine, _ = two_applications
    assert_error(partner_client.get(application_url(mine)), 403, "PERMISSION_DENIED")


def test_list_filters(
    admin_client: APIClient,
    two_applications: tuple[CreditApplication, CreditApplication],
    other_advisor: User,
    active_project: Project,
) -> None:
    mine, theirs = two_applications
    product = seeded_product()
    CreditApplication.objects.filter(pk=mine.pk).update(bank_product=product)
    Property.objects.create(
        application=mine,
        project=active_project,
        property_type_item=catalog_item("property_type", "APARTMENT"),
        condition_item=catalog_item("property_condition", "NEW"),
        city_item=catalog_item("municipality", "11001"),
        estimated_value_cop=420_000_000,
    )
    set_status(theirs, ApplicationStatus.WAITING_DOCUMENTS)

    assert list_ids(admin_client, status="WAITING_DOCUMENTS") == {str(theirs.id)}
    assert list_ids(admin_client, purpose="PURCHASE_USED") == {str(theirs.id)}
    assert list_ids(admin_client, advisor_id=str(other_advisor.id)) == {str(theirs.id)}
    assert list_ids(admin_client, bank_id=str(product.bank_id)) == {str(mine.id)}
    assert list_ids(admin_client, product_id=str(product.id)) == {str(mine.id)}
    assert list_ids(admin_client, project_id=str(active_project.id)) == {str(mine.id)}
    assert list_ids(admin_client, origin="DIRECT") == {str(mine.id), str(theirs.id)}
    assert list_ids(admin_client, search="Mateo") == {str(theirs.id)}
    assert list_ids(admin_client, search=mine.code) == {str(mine.id)}


@pytest.mark.parametrize(
    "params",
    [{"status": "PAUSED"}, {"advisor_id": "no-es-uuid"}, {"ordering": "assigned_advisor"}],
)
def test_list_rejects_unknown_filters(admin_client: APIClient, params: dict[str, str]) -> None:
    assert_error(admin_client.get(APPLICATIONS_URL, params), 400, "VALIDATION_ERROR")


# --- Detalle ----------------------------------------------------------------------------


def test_detail_includes_property_assignments_and_etag(
    advisor_client: APIClient, opportunity: Opportunity
) -> None:
    created = create(advisor_client, opportunity).json()

    response = advisor_client.get(application_url(created["id"]))

    assert response.status_code == 200
    assert response["ETag"] == '"1"'
    body = response.json()
    assert body["property"]["city"]["code"] == "11001"
    assert [item["advisor"]["name"] for item in body["assignments"]] == ["Andrea García"]
    assert body["origin"]["code"] == "DIRECT"


def test_etag_is_readable_by_the_frontend(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = advisor_client.get(
        application_url(application), headers={"Origin": "http://localhost:3000"}
    )

    exposed = {name.strip() for name in response["Access-Control-Expose-Headers"].split(",")}
    assert "ETag" in exposed


def test_unknown_application_returns_404(admin_client: APIClient) -> None:
    assert_error(
        admin_client.get(application_url("00000000-0000-0000-0000-000000000000")),
        404,
        "RESOURCE_NOT_FOUND",
    )


# --- Edición con If-Match ---------------------------------------------------------------


def test_patch_requires_if_match(advisor_client: APIClient, application: CreditApplication) -> None:
    response = patch(advisor_client, application, {"purpose_code": "PURCHASE_USED"}, None)
    assert_error(response, 428, "PRECONDITION_REQUIRED")


@pytest.mark.parametrize("value", ["abc", '"0"', '"-1"'])
def test_patch_rejects_a_malformed_if_match(
    advisor_client: APIClient, application: CreditApplication, value: str
) -> None:
    response = patch(advisor_client, application, {"purpose_code": "PURCHASE_USED"}, value)
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "If-Match"


def test_stale_version_is_rejected_with_the_current_one(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(version=4)

    response = patch(advisor_client, application, {"purpose_code": "PURCHASE_USED"}, '"3"')

    body = assert_error(response, 409, "STALE_VERSION")
    assert body["details"][0]["current_version"] == 4
    application.refresh_from_db()
    assert application.purpose_item.code == "PURCHASE_NEW"


@pytest.mark.parametrize("if_match", ['"1"', "1", 'W/"1"'])
def test_patch_selects_a_product_and_bumps_the_version(
    advisor_client: APIClient, application: CreditApplication, if_match: str
) -> None:
    product = seeded_product()

    response = patch(advisor_client, application, {"bank_product_id": str(product.id)}, if_match)

    assert response.status_code == 200, response.content
    assert response["ETag"] == '"2"'
    body = response.json()
    assert body["version"] == 2
    assert body["bank_product"]["bank"]["name"] == "Bancolombia"


def test_patch_without_real_changes_keeps_the_version(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = patch(advisor_client, application, {"purpose_code": "PURCHASE_NEW"})

    assert response.status_code == 200
    assert response.json()["version"] == 1


def test_patch_sends_the_changed_fields(
    advisor_client: APIClient, advisor_user: User, application: CreditApplication
) -> None:
    received: list[dict[str, Any]] = []

    def on_updated(**kwargs: Any) -> None:
        received.append(kwargs)

    application_updated.connect(on_updated)
    try:
        patch(
            advisor_client,
            application,
            {"purpose_code": "PURCHASE_USED", "bank_product_id": str(seeded_product().id)},
        )
    finally:
        application_updated.disconnect(on_updated)

    assert [(event["fields"], event["actor"]) for event in received] == [
        (["bank_product", "purpose_item"], advisor_user)
    ]


def test_product_can_be_cleared(advisor_client: APIClient, application: CreditApplication) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(bank_product=seeded_product())

    response = patch(advisor_client, application, {"bank_product_id": None})

    assert response.status_code == 200
    assert response.json()["bank_product"] is None


def test_product_must_admit_the_purpose(
    advisor_client: APIClient,
    application: CreditApplication,
    new_home_only_product: BankProduct,
) -> None:
    response = patch(
        advisor_client,
        application,
        {"purpose_code": "PURCHASE_USED", "bank_product_id": str(new_home_only_product.id)},
    )
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "bank_product_id"


def test_purpose_change_must_fit_the_selected_product(
    advisor_client: APIClient,
    application: CreditApplication,
    new_home_only_product: BankProduct,
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(bank_product=new_home_only_product)

    response = patch(advisor_client, application, {"purpose_code": "PURCHASE_USED"})

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "purpose_code"


def test_product_must_be_active(advisor_client: APIClient, application: CreditApplication) -> None:
    product = seeded_product()
    BankProduct.objects.filter(pk=product.pk).update(status=BankStatus.INACTIVE)

    response = patch(advisor_client, application, {"bank_product_id": str(product.id)})

    assert_error(response, 400, "VALIDATION_ERROR")


def test_unknown_product_is_rejected(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = patch(
        advisor_client, application, {"bank_product_id": "00000000-0000-0000-0000-000000000000"}
    )
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "bank_product_id"


def test_purpose_change_must_fit_the_registered_property(
    advisor_client: APIClient, opportunity: Opportunity
) -> None:
    created = create(advisor_client, opportunity).json()
    application = CreditApplication.objects.get(pk=created["id"])

    # La vivienda nueva no tiene dirección: no sirve para remodelación.
    response = patch(advisor_client, application, {"purpose_code": "HOME_IMPROVEMENT"})

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "purpose_code"


@pytest.mark.parametrize("status", ["FILED", "BANK_OBSERVATION", "CANCELLED"])
def test_data_cannot_change_after_filing(
    advisor_client: APIClient, application: CreditApplication, status: str
) -> None:
    set_status(application, status)

    response = patch(advisor_client, application, {"purpose_code": "PURCHASE_USED"})

    assert_error(response, 409, "APPLICATION_NOT_EDITABLE")


@pytest.mark.parametrize(
    "data",
    [
        {"status": "READY_TO_FILE"},
        {"assigned_advisor_id": "00000000-0000-0000-0000-000000000000"},
        {"requested_amount_cop": 1},
    ],
)
def test_patch_rejects_fields_out_of_its_scope(
    advisor_client: APIClient, application: CreditApplication, data: dict[str, Any]
) -> None:
    assert_error(patch(advisor_client, application, data), 400, "VALIDATION_ERROR")


def test_broker_cannot_patch(
    broker_client: APIClient, two_applications: tuple[CreditApplication, CreditApplication]
) -> None:
    mine, _ = two_applications
    response = patch(broker_client, mine, {"purpose_code": "PURCHASE_USED"})
    assert_error(response, 403, "PERMISSION_DENIED")


def test_out_of_scope_patch_returns_404(
    other_advisor_client: APIClient, application: CreditApplication
) -> None:
    response = patch(other_advisor_client, application, {"purpose_code": "PURCHASE_USED"})
    assert_error(response, 404, "RESOURCE_NOT_FOUND")


# --- Resumen ----------------------------------------------------------------------------


def test_summary_has_no_financial_data(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(
        bank_product=seeded_product(),
        current_stage_started_at=timezone.now() - timedelta(days=3, hours=1),
    )

    response = advisor_client.get(application_url(application, "/summary"))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == SUMMARY_KEYS
    assert body["status_label"] == "Borrador"
    assert (body["bank_name"], body["product_name"]) == ("Bancolombia", "Crédito hipotecario")
    assert body["advisor_name"] == "Andrea García"
    assert body["days_in_stage"] == 3


def test_summary_scope(
    broker_client: APIClient,
    partner_client: APIClient,
    two_applications: tuple[CreditApplication, CreditApplication],
) -> None:
    mine, theirs = two_applications

    assert broker_client.get(application_url(mine, "/summary")).status_code == 200
    assert_error(broker_client.get(application_url(theirs, "/summary")), 404, "RESOURCE_NOT_FOUND")
    assert_error(partner_client.get(application_url(mine, "/summary")), 403, "PERMISSION_DENIED")
