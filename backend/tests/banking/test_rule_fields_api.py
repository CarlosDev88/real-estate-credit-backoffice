"""Reglas bancarias (TAREA-brechas-3-demo, parte 1): `GET /bank-policy-rules/fields` con la
lista blanca de campos (la misma con la que se validan las condiciones), y las etiquetas
del estado, la severidad y el resultado de una prueba."""

from collections.abc import Callable

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.banking.models import BankPolicyRule
from apps.banking.rule_fields import RULE_FIELDS, FieldInputType, FieldType
from apps.catalogs.models import Catalog, CatalogItem
from apps.catalogs.services import available_items
from tests.banking.conftest import RULES_URL
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

FIELDS_URL = f"{RULES_URL}/fields"


def fields_by_code(client: APIClient) -> dict[str, dict[str, object]]:
    response = client.get(FIELDS_URL)
    assert response.status_code == 200
    return {field["code"]: field for field in response.json()}


# --- Lista blanca de campos -------------------------------------------------------------


def test_every_field_has_a_label_and_every_code_field_a_real_catalog() -> None:
    for name, field in RULE_FIELDS.items():
        assert field.label, name
        if field.type == FieldType.STRING:
            assert field.catalog and Catalog.objects.filter(code=field.catalog).exists(), name
        else:
            assert field.catalog is None, name


def test_the_fields_come_from_the_whitelist(advisor_client: APIClient) -> None:
    fields = fields_by_code(advisor_client)

    assert list(fields) == list(RULE_FIELDS)
    assert set(fields["financing.term_months"]) == {
        "code",
        "label",
        "description",
        "type",
        "catalog",
        "options",
    }
    assert fields["financing.term_months"]["type"] == FieldInputType.NUMBER
    assert fields["financing.term_months"]["label"] == "Plazo (meses)"
    assert fields["financing.requested_amount_cop"]["type"] == FieldInputType.MONEY
    assert fields["financing.uses_severance_funds"]["type"] == FieldInputType.BOOLEAN
    assert fields["financing.uses_severance_funds"]["options"] is None


def test_choice_fields_bring_the_current_options_of_their_catalog(
    admin_client: APIClient,
) -> None:
    fields = fields_by_code(admin_client)

    purpose = fields["application.purpose_code"]
    assert (purpose["type"], purpose["catalog"]) == (FieldInputType.CHOICE, "loan_purpose")
    catalog = Catalog.objects.get(code="loan_purpose")
    assert purpose["options"] == [
        {"code": item.code, "label": item.label} for item in available_items(catalog)
    ]
    # Un catálogo bajo demanda no viaja aquí: se pide en `/metadata/catalogs/{code}`.
    city = fields["property.city_code"]
    assert (city["type"], city["catalog"], city["options"]) == (
        FieldInputType.CHOICE,
        "municipality",
        None,
    )


def test_an_inactive_option_is_not_offered(admin_client: APIClient) -> None:
    item = CatalogItem.objects.filter(catalog__code="property_type").first()
    assert item is not None
    item.is_active = False
    item.save()

    options = fields_by_code(admin_client)["property.property_type_code"]["options"]

    assert isinstance(options, list)
    assert item.code not in {option["code"] for option in options}


def test_the_field_list_queries_do_not_grow_with_the_options(admin_client: APIClient) -> None:
    def measure() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert admin_client.get(FIELDS_URL).status_code == 200
        return len(queries)

    one = measure()
    catalog = Catalog.objects.get(code="contract_type")
    for index in range(5):
        CatalogItem.objects.create(catalog=catalog, code=f"EXTRA_{index}", label=f"Extra {index}")

    assert measure() == one


def test_the_field_list_needs_the_rule_read_permission(
    broker_client: APIClient, partner_client: APIClient
) -> None:
    assert_error(broker_client.get(FIELDS_URL), 403, "PERMISSION_DENIED")
    assert_error(partner_client.get(FIELDS_URL), 403, "PERMISSION_DENIED")


# --- Etiquetas de la regla y del resultado de una prueba ---------------------------------


def test_the_rule_brings_the_labels_of_its_status_and_severity(
    advisor_client: APIClient, make_rule: Callable[..., BankPolicyRule]
) -> None:
    rule = make_rule(status="ACTIVE", severity="WARNING")

    body = advisor_client.get(f"{RULES_URL}/{rule.pk}").json()
    listed = advisor_client.get(RULES_URL).json()["items"][0]

    for data in (body, listed):
        assert (data["status"], data["status_label"]) == ("ACTIVE", "Activa")
        assert (data["severity"], data["severity_label"]) == ("WARNING", "Advertencia")


def test_the_test_run_brings_the_label_of_each_outcome(
    admin_client: APIClient, make_rule: Callable[..., BankPolicyRule]
) -> None:
    rule = make_rule()
    within = {
        "financing": {"requested_amount_cop": 200_000_000},
        "property": {"estimated_value_cop": 300_000_000},
    }
    above = {
        "financing": {"requested_amount_cop": 250_000_000},
        "property": {"estimated_value_cop": 300_000_000},
    }

    response = admin_client.post(
        f"{RULES_URL}/{rule.pk}/test",
        {
            "cases": [
                {"context": within},
                {"context": above},
                {"context": {"financing": {"requested_amount_cop": 1}}},
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    assert [(r["outcome"], r["outcome_label"]) for r in response.json()["results"]] == [
        ("PASSED", "Cumple"),
        ("FAILED", "No cumple"),
        ("MISSING_DATA", "Faltan datos"),
    ]
