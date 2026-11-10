"""Inmueble, financiación, productos elegibles y desistimiento del comprador (Parte 6)."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.applications.models import (
    ApplicationStatusHistory,
    BankRuleEvaluation,
    CreditApplication,
    FinancingPreference,
    Property,
)
from apps.applications.signals import application_status_changed
from apps.catalogs.models import WorkflowTransition
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, Opportunity
from apps.identity.models import BuyerSession
from apps.partners.models import Project
from tests.applications.buyer_access.conftest import if_match, set_status, version_of
from tests.applications.conftest import application_url, catalog_item, seeded_product
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

PROPERTY_BODY = {
    "property_type_code": "APARTMENT",
    "condition_code": "NEW",
    "city_code": "11001",
    "estimated_value_cop": 420_000_000,
}


def buyer_url(application: CreditApplication, suffix: str) -> str:
    return f"/api/v1/buyer/applications/{application.pk}/{suffix}"


def bank_credit(product_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "financing_mode_code": "BANK_CREDIT",
        "bank_product_id": product_id,
        "requested_amount_cop": 294_000_000,
        "term_months": 240,
        **extra,
    }


def withdraw(client: APIClient, application: CreditApplication, **payload: Any) -> Any:
    payload.setdefault("reason_code", "BUYER_DECISION")
    payload.setdefault("expected_version", version_of(application))
    return client.post(buyer_url(application, "withdrawals"), payload)


@pytest.fixture
def other_application(
    make_application: Callable[..., CreditApplication],
    make_opportunity: Callable[..., Opportunity],
    make_client: Callable[..., Client],
) -> CreditApplication:
    return make_application(make_opportunity(make_client(document_number="52000111")))


@pytest.fixture
def status_events() -> Iterator[list[dict[str, Any]]]:
    received: list[dict[str, Any]] = []

    def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    application_status_changed.connect(handler)
    yield received
    application_status_changed.disconnect(handler)


# --- Inmueble ---------------------------------------------------------------------------


def test_put_property(portal: APIClient, application: CreditApplication) -> None:
    url = buyer_url(application, "property")
    assert_error(portal.get(url), 404, "RESOURCE_NOT_FOUND")
    before = version_of(application)

    created = portal.put(url, PROPERTY_BODY, headers=if_match(application))

    assert created.status_code == 201, created.content
    assert created["ETag"] == f'"{before + 1}"'
    body = created.json()
    assert body["estimated_value_cop"] == 420_000_000
    assert body["project"] is None
    assert "ownership_notes" not in body

    updated = portal.put(
        url, {**PROPERTY_BODY, "unit_reference": "Apto 501"}, headers=if_match(application)
    )
    assert updated.status_code == 200
    assert portal.get(url).json()["unit_reference"] == "Apto 501"


@pytest.mark.parametrize("field", ["project_id", "ownership_notes"])
def test_property_rejects_fields_owned_by_the_advisor(
    portal: APIClient, application: CreditApplication, field: str
) -> None:
    response = portal.put(
        buyer_url(application, "property"),
        {**PROPERTY_BODY, field: None},
        headers=if_match(application),
    )

    assert_error(response, 400, "VALIDATION_ERROR")


def test_property_keeps_the_project_and_the_advisor_notes(
    portal: APIClient, application: CreditApplication, active_project: Project
) -> None:
    Property.objects.create(
        application=application,
        project=active_project,
        property_type_item=catalog_item("property_type", "APARTMENT"),
        condition_item=catalog_item("property_condition", "NEW"),
        city_item=catalog_item("municipality", "11001"),
        estimated_value_cop=400_000_000,
        ownership_notes="Nota interna del asesor",
    )

    response = portal.put(
        buyer_url(application, "property"), PROPERTY_BODY, headers=if_match(application)
    )

    assert response.status_code == 200, response.content
    assert response.json()["project"] == {"id": str(active_project.pk), "name": "Verona 118"}
    prop = Property.objects.get(application=application)
    assert prop.estimated_value_cop == 420_000_000
    assert prop.project_id == active_project.pk
    assert prop.ownership_notes == "Nota interna del asesor"


def test_property_follows_the_purpose_rules(
    portal: APIClient, application: CreditApplication
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(
        purpose_item=catalog_item("loan_purpose", "PURCHASE_USED")
    )

    response = portal.put(
        buyer_url(application, "property"), PROPERTY_BODY, headers=if_match(application)
    )

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert [d["field"] for d in body["details"]] == ["address"]


def test_property_requires_if_match_and_is_locked_after_filing(
    portal: APIClient, application: CreditApplication
) -> None:
    url = buyer_url(application, "property")
    assert_error(portal.put(url, PROPERTY_BODY), 428, "PRECONDITION_REQUIRED")

    set_status(application, ApplicationStatus.FILED)

    response = portal.put(url, PROPERTY_BODY, headers=if_match(application))
    assert_error(response, 409, "APPLICATION_NOT_EDITABLE")


# --- Financiación -----------------------------------------------------------------------


def test_put_financing_with_a_product_saves_an_evaluation_without_evaluator(
    portal: APIClient, application: CreditApplication
) -> None:
    product = seeded_product()
    url = buyer_url(application, "financing")
    assert_error(portal.get(url), 404, "RESOURCE_NOT_FOUND")

    response = portal.put(url, bank_credit(str(product.pk)), headers=if_match(application))

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["financing_mode"]["code"] == "BANK_CREDIT"
    assert body["bank_product"]["id"] == str(product.pk)
    application.refresh_from_db()
    assert application.bank_product_id == product.pk
    evaluation = BankRuleEvaluation.objects.get(application=application)
    assert evaluation.evaluated_by_id is None
    assert evaluation.application_version == application.version
    assert portal.get(url).json()["requested_amount_cop"] == 294_000_000


def test_financing_without_bank_clears_the_product(
    portal: APIClient, application: CreditApplication
) -> None:
    url = buyer_url(application, "financing")
    portal.put(url, bank_credit(str(seeded_product().pk)), headers=if_match(application))

    response = portal.put(url, {"financing_mode_code": "OWN_FUNDS"}, headers=if_match(application))

    assert response.status_code == 200, response.content
    assert response.json()["bank_product"] is None
    assert FinancingPreference.objects.get(application=application).requested_amount_cop == 0


def test_financing_follows_the_mode_rules(
    portal: APIClient, application: CreditApplication
) -> None:
    response = portal.put(
        buyer_url(application, "financing"),
        {"financing_mode_code": "BANK_CREDIT", "requested_amount_cop": 1},
        headers=if_match(application),
    )

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert [d["field"] for d in body["details"]] == ["bank_product_id"]


def test_financing_is_locked_after_filing(
    portal: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.FILED)

    response = portal.put(
        buyer_url(application, "financing"),
        {"financing_mode_code": "OWN_FUNDS"},
        headers=if_match(application),
    )

    assert_error(response, 409, "APPLICATION_NOT_EDITABLE")


# --- Productos elegibles ----------------------------------------------------------------


def test_eligible_bank_products_hide_the_rule_detail(
    portal: APIClient, application: CreditApplication
) -> None:
    response = portal.get(buyer_url(application, "eligible-bank-products"))

    assert response.status_code == 200, response.content
    assert "ETag" in response
    items = response.json()["items"]
    assert items
    assert set(items[0]) == {
        "id",
        "name",
        "bank",
        "min_amount_cop",
        "max_amount_cop",
        "min_term_months",
        "max_term_months",
        "eligible",
    }
    assert set(items[0]["bank"]) == {"id", "name"}
    assert all(isinstance(item["eligible"], bool) for item in items)
    assert str(seeded_product().pk) in {item["id"] for item in items}


def test_eligible_products_are_readable_with_pending_consents(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    assert buyer_client.get(buyer_url(application, "eligible-bank-products")).status_code == 200


# --- Desistimiento ----------------------------------------------------------------------


def test_withdrawal_by_the_buyer(
    portal: APIClient,
    advisor_client: APIClient,
    application: CreditApplication,
    status_events: list[dict[str, Any]],
) -> None:
    session = BuyerSession.objects.get(revoked_at__isnull=True)
    before = version_of(application)

    response = withdraw(portal, application, comment="Compramos con otra entidad")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["application_id"] == str(application.pk)
    assert body["previous_status"] == "DRAFT"
    assert body["status"] == "WITHDRAWN"
    assert body["version"] == before + 1
    assert response["ETag"] == f'"{before + 1}"'

    application.refresh_from_db()
    assert application.withdrawal_reason_item == catalog_item(
        "application_withdrawal_reason", "BUYER_DECISION"
    )
    assert application.withdrawn_at is not None
    history = ApplicationStatusHistory.objects.get(to_status=ApplicationStatus.WITHDRAWN)
    assert history.actor_user_id is None
    assert history.actor_buyer_session_id == session.pk
    assert history.comment == "Compramos con otra entidad"
    assert [event["actor"] for event in status_events] == [session]

    internal = advisor_client.get(application_url(application, "/status-history"))
    latest = internal.json()["items"][0]
    assert (latest["actor"], latest["buyer_session_id"]) == (None, str(session.pk))

    # La sesión sigue viva para consultar, pero ya no escribe.
    assert portal.get(f"/api/v1/buyer/applications/{application.pk}").status_code == 200
    assert_error(withdraw(portal, application), 409, "APPLICATION_CLOSED")


def test_withdrawal_after_filing(portal: APIClient, application: CreditApplication) -> None:
    set_status(application, ApplicationStatus.FILED)

    response = withdraw(portal, application)

    assert response.status_code == 200, response.content
    assert response.json()["previous_status"] == "FILED"


# Marca de los cuerpos que llevan la versión vigente, que no existe al parametrizar.
CURRENT = "current"


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_version": CURRENT},
        {"reason_code": "CLIENT_UNREACHABLE", "expected_version": CURRENT},
        {"reason_code": "BUYER_DECISION"},
    ],
)
def test_withdrawal_validation(
    portal: APIClient, application: CreditApplication, payload: dict[str, Any]
) -> None:
    body = {
        key: version_of(application) if value == CURRENT else value
        for key, value in payload.items()
    }

    response = portal.post(buyer_url(application, "withdrawals"), body)

    assert_error(response, 400, "VALIDATION_ERROR")
    assert not ApplicationStatusHistory.objects.filter(to_status="WITHDRAWN").exists()


def test_withdrawal_with_a_stale_version(portal: APIClient, application: CreditApplication) -> None:
    assert_error(withdraw(portal, application, expected_version=99), 409, "STALE_VERSION")


def test_withdrawal_without_an_active_transition(
    portal: APIClient, application: CreditApplication
) -> None:
    WorkflowTransition.objects.filter(code="WITHDRAW_DRAFT").update(is_active=False)

    assert_error(withdraw(portal, application), 409, "INVALID_STATE_TRANSITION")


def test_withdrawal_needs_the_consents(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    assert_error(withdraw(buyer_client, application), 403, "CONSENT_REQUIRED")


# --- Alcance ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "suffix", ["property", "financing", "eligible-bank-products", "withdrawals"]
)
def test_another_application_is_not_found(
    portal: APIClient, other_application: CreditApplication, suffix: str
) -> None:
    url = buyer_url(other_application, suffix)
    if suffix == "withdrawals":
        response = portal.post(url, {"reason_code": "BUYER_DECISION", "expected_version": 1})
    else:
        response = portal.get(url)

    assert_error(response, 404, "RESOURCE_NOT_FOUND")
    other_application.refresh_from_db()
    assert other_application.status == ApplicationStatus.DRAFT
