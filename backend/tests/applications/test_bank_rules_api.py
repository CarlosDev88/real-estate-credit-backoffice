"""Reglas bancarias de la solicitud (API §18.2): evaluación guardada, última evaluación,
productos elegibles y evaluación automática al elegir producto."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import (
    BankRuleEvaluation,
    CreditApplication,
    FinancialProfile,
    ParticipantRole,
)
from apps.banking.models import BankPolicyRule, BankProduct, BankStatus, RuleStatus
from apps.catalogs.workflow import ApplicationStatus
from apps.identity.models import User
from tests.applications.conftest import application_url, catalog_item, seeded_product
from tests.applications.test_property_financing_api import PROPERTY, bank_credit, put
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

MAX_LTV: dict[str, Any] = {
    "operator": "lte",
    "left": {
        "operator": "ratio",
        "numerator_field": "financing.requested_amount_cop",
        "denominator_field": "property.estimated_value_cop",
    },
    "right": 0.7,
}
EMPLOYEE_ONLY: dict[str, Any] = {
    "operator": "in",
    "left": {"field": "applicant.employment_profile_code"},
    "right": ["EMPLOYEE"],
}
MIN_TERM: dict[str, Any] = {
    "operator": "gte",
    "left": {"field": "financing.term_months"},
    "right": 300,
}


@pytest.fixture
def make_rule(admin_user: User) -> Callable[..., BankPolicyRule]:
    """Regla publicada y vigente sobre el producto sembrado de Bancolombia."""

    def _make_rule(**extra: Any) -> BankPolicyRule:
        extra.setdefault("bank_product", seeded_product())
        extra.setdefault("code", "MAX_LTV")
        extra.setdefault("version", 1)
        extra.setdefault("severity", "BLOCKING")
        extra.setdefault("condition", MAX_LTV)
        extra.setdefault("message", "El monto no puede superar el 70% del valor del inmueble.")
        extra.setdefault("status", RuleStatus.ACTIVE)
        extra.setdefault("valid_from", timezone.now() - timedelta(days=1))
        extra.setdefault("created_by", admin_user)
        return BankPolicyRule.objects.create(**extra)

    return _make_rule


def with_product(application: CreditApplication, product: BankProduct | None = None) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(
        bank_product=product or seeded_product()
    )


def evaluate(client: APIClient, application: CreditApplication) -> Any:
    return client.post(application_url(application, "/bank-rule-evaluations"))


def latest(client: APIClient, application: CreditApplication) -> Any:
    return client.get(application_url(application, "/bank-rule-evaluations/latest"))


def eligible(client: APIClient, application: CreditApplication) -> Any:
    return client.get(application_url(application, "/eligible-bank-products"))


@pytest.fixture
def ready(advisor_client: APIClient, application: CreditApplication) -> CreditApplication:
    """Solicitud con inmueble y crédito bancario (Bancolombia): versión 3."""
    assert put(advisor_client, application, "property", PROPERTY).status_code == 201
    assert put(advisor_client, application, "financing", bank_credit(), '"2"').status_code == 201
    application.refresh_from_db()
    return application


# --- POST /bank-rule-evaluations --------------------------------------------------------


def test_evaluation_requires_a_product(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = evaluate(advisor_client, application)

    assert_error(response, 422, "BANK_PRODUCT_REQUIRED")
    assert not BankRuleEvaluation.objects.exists()


def test_evaluation_without_rules_is_eligible_and_keeps_the_version(
    advisor_client: APIClient, advisor_user: User, ready: CreditApplication
) -> None:
    response = evaluate(advisor_client, ready)

    assert response.status_code == 201, response.content
    assert response["ETag"] == '"3"'
    body = response.json()
    evaluation = BankRuleEvaluation.objects.latest("created_at")
    assert body == {
        "id": str(evaluation.id),
        "bank_product_id": str(seeded_product().id),
        "application_version": 3,
        "is_current": True,
        "eligible": True,
        "blocking": [],
        "warnings": [],
        "evaluated_at": body["evaluated_at"],
    }
    assert evaluation.evaluated_by == advisor_user
    assert evaluation.result_snapshot["rules"] == []
    assert evaluation.result_snapshot["context"]["financing"]["requested_amount_cop"] == 294_000_000
    ready.refresh_from_db()
    assert ready.version == 3


def test_failed_blocking_rule_makes_it_ineligible(
    advisor_client: APIClient, ready: CreditApplication, make_rule: Callable[..., BankPolicyRule]
) -> None:
    rule = make_rule()  # 294 / 420 = 0.7: se cumple. Se sube el monto.
    put(advisor_client, ready, "financing", bank_credit(requested_amount_cop=300_000_000), '"3"')

    body = evaluate(advisor_client, ready).json()

    assert body["eligible"] is False
    assert body["blocking"] == [
        {
            "rule_code": "MAX_LTV",
            "outcome": "FAILED",
            "outcome_label": "No cumple",
            "message": "El monto no puede superar el 70% del valor del inmueble.",
            "field": "financing.requested_amount_cop",
            "unresolved_fields": [],
        }
    ]
    evaluation = BankRuleEvaluation.objects.latest("created_at")
    assert (evaluation.is_eligible, evaluation.blocking_count, evaluation.warning_count) == (
        False,
        1,
        0,
    )
    assert evaluation.result_snapshot["rules"] == [
        {
            "rule_id": str(rule.id),
            "code": "MAX_LTV",
            "version": 1,
            "severity": "BLOCKING",
            "message": rule.message,
            "outcome": "FAILED",
            "unresolved_fields": [],
            "field": "financing.requested_amount_cop",
            "source": "RULE",
        }
    ]


def test_blocking_rule_with_missing_data_fails_closed(
    advisor_client: APIClient, ready: CreditApplication, make_rule: Callable[..., BankPolicyRule]
) -> None:
    make_rule(code="EMPLOYEE_ONLY", condition=EMPLOYEE_ONLY, message="Solo empleados.")

    body = evaluate(advisor_client, ready).json()

    assert body["eligible"] is False
    assert body["blocking"] == [
        {
            "rule_code": "EMPLOYEE_ONLY",
            "outcome": "MISSING_DATA",
            "outcome_label": "Faltan datos",
            "message": "Faltan datos para evaluar la regla: applicant.employment_profile_code.",
            "field": "applicant.employment_profile_code",
            "unresolved_fields": ["applicant.employment_profile_code"],
        }
    ]


def test_warnings_do_not_affect_eligibility(
    advisor_client: APIClient, ready: CreditApplication, make_rule: Callable[..., BankPolicyRule]
) -> None:
    make_rule(code="LONG_TERM", condition=MIN_TERM, severity="WARNING", message="Plazo corto.")
    make_rule()  # Se cumple: no aparece en la respuesta, pero sí en el snapshot.

    body = evaluate(advisor_client, ready).json()

    assert body["eligible"] is True
    assert body["blocking"] == []
    assert [(w["rule_code"], w["outcome"], w["message"]) for w in body["warnings"]] == [
        ("LONG_TERM", "FAILED", "Plazo corto.")
    ]
    evaluation = BankRuleEvaluation.objects.latest("created_at")
    assert evaluation.warning_count == 1
    assert [row["outcome"] for row in evaluation.result_snapshot["rules"]] == ["FAILED", "PASSED"]


def test_only_published_rules_for_the_purpose_apply(
    advisor_client: APIClient, ready: CreditApplication, make_rule: Callable[..., BankPolicyRule]
) -> None:
    failing = {"condition": EMPLOYEE_ONLY}
    make_rule(code="DRAFT", status=RuleStatus.DRAFT, **failing)
    make_rule(code="USED", purpose_item=catalog_item("loan_purpose", "PURCHASE_USED"), **failing)
    make_rule(code="FUTURE", valid_from=timezone.now() + timedelta(days=1), **failing)
    make_rule(code="OTHER_BANK", bank_product=seeded_product("FNA"), **failing)
    make_rule(code="NEW", purpose_item=catalog_item("loan_purpose", "PURCHASE_NEW"), **failing)

    body = evaluate(advisor_client, ready).json()

    assert [item["rule_code"] for item in body["blocking"]] == ["NEW"]


@pytest.fixture
def ranged_product() -> BankProduct:
    product = seeded_product()
    BankProduct.objects.filter(pk=product.pk).update(
        min_amount_cop=50_000_000,
        max_amount_cop=250_000_000,
        min_term_months=60,
        max_term_months=360,
    )
    return product


def test_product_ranges_are_system_blocking_rules(
    advisor_client: APIClient, ready: CreditApplication, ranged_product: BankProduct
) -> None:
    body = evaluate(advisor_client, ready).json()

    assert body["eligible"] is False
    assert body["blocking"] == [
        {
            "rule_code": "PRODUCT_AMOUNT_RANGE",
            "outcome": "FAILED",
            "outcome_label": "No cumple",
            "message": (
                "El monto solicitado debe estar entre $50.000.000 y $250.000.000 para este "
                "producto."
            ),
            "field": "financing.requested_amount_cop",
            "unresolved_fields": [],
        }
    ]
    rows = BankRuleEvaluation.objects.latest("created_at").result_snapshot["rules"]
    assert [(r["code"], r["outcome"], r["source"], r["rule_id"], r["version"]) for r in rows] == [
        ("PRODUCT_AMOUNT_RANGE", "FAILED", "SYSTEM", None, None),
        ("PRODUCT_TERM_RANGE", "PASSED", "SYSTEM", None, None),
    ]


def test_missing_term_blocks_when_the_product_limits_it(
    advisor_client: APIClient, ready: CreditApplication
) -> None:
    BankProduct.objects.filter(pk=seeded_product().pk).update(max_term_months=240)
    put(advisor_client, ready, "financing", bank_credit(term_months=None), '"3"')

    body = evaluate(advisor_client, ready).json()

    assert body["blocking"] == [
        {
            "rule_code": "PRODUCT_TERM_RANGE",
            "outcome": "MISSING_DATA",
            "outcome_label": "Faltan datos",
            "message": "Faltan datos para evaluar la regla: financing.term_months.",
            "field": "financing.term_months",
            "unresolved_fields": ["financing.term_months"],
        }
    ]
    row = BankRuleEvaluation.objects.latest("created_at").result_snapshot["rules"][0]
    assert row["message"] == "El plazo debe ser como máximo de 240 meses para este producto."


def test_term_below_the_minimum_fails(advisor_client: APIClient, ready: CreditApplication) -> None:
    BankProduct.objects.filter(pk=seeded_product().pk).update(min_term_months=300)

    body = evaluate(advisor_client, ready).json()

    assert [(b["rule_code"], b["message"]) for b in body["blocking"]] == [
        ("PRODUCT_TERM_RANGE", "El plazo debe ser de al menos 300 meses para este producto.")
    ]


def test_missing_financing_blocks_the_amount_range(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    with_product(application)
    BankProduct.objects.filter(pk=seeded_product().pk).update(min_amount_cop=50_000_000)

    body = evaluate(advisor_client, application).json()

    assert [(b["rule_code"], b["outcome"]) for b in body["blocking"]] == [
        ("PRODUCT_AMOUNT_RANGE", "MISSING_DATA")
    ]


def test_evaluation_uses_the_participants_and_profiles(
    advisor_client: APIClient,
    ready: CreditApplication,
    make_rule: Callable[..., BankPolicyRule],
) -> None:
    make_rule(code="EMPLOYEE_ONLY", condition=EMPLOYEE_ONLY, message="Solo empleados.")
    FinancialProfile.objects.create(
        participant=ready.participants.get(role=ParticipantRole.PRIMARY),
        employment_profile_item=catalog_item("employment_profile", "EMPLOYEE"),
    )

    assert evaluate(advisor_client, ready).json()["eligible"] is True


def test_evaluation_only_before_filing(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    with_product(application)
    CreditApplication.objects.filter(pk=application.pk).update(status=ApplicationStatus.FILED)

    assert_error(evaluate(advisor_client, application), 409, "APPLICATION_NOT_EDITABLE")


def test_admin_can_evaluate(admin_client: APIClient, ready: CreditApplication) -> None:
    assert evaluate(admin_client, ready).status_code == 201


# --- GET /bank-rule-evaluations/latest --------------------------------------------------


def test_latest_is_404_until_the_first_evaluation(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    assert_error(latest(advisor_client, application), 404, "RESOURCE_NOT_FOUND")


def test_latest_returns_the_most_recent_and_flags_it_stale_after_changes(
    advisor_client: APIClient, ready: CreditApplication, make_rule: Callable[..., BankPolicyRule]
) -> None:
    evaluate(advisor_client, ready)
    make_rule(code="EMPLOYEE_ONLY", condition=EMPLOYEE_ONLY, message="Solo empleados.")
    second = evaluate(advisor_client, ready).json()

    response = latest(advisor_client, ready)
    assert response.status_code == 200
    assert response.json() == second
    assert second["is_current"] is True

    put(advisor_client, ready, "property", {**PROPERTY, "estimated_value_cop": 1}, '"3"')
    stale = latest(advisor_client, ready)

    assert stale["ETag"] == '"4"'
    assert stale.json() == {**second, "is_current": False}


def test_latest_is_stale_when_the_product_changes(
    advisor_client: APIClient, ready: CreditApplication
) -> None:
    evaluate(advisor_client, ready)
    # Sin pasar por la API: misma versión, otro producto.
    with_product(ready, seeded_product("FNA"))

    assert latest(advisor_client, ready).json()["is_current"] is False


# --- Evaluación automática al elegir producto ------------------------------------------


def test_choosing_a_product_with_patch_saves_an_evaluation(
    advisor_client: APIClient, advisor_user: User, application: CreditApplication
) -> None:
    response = advisor_client.patch(
        application_url(application),
        {"bank_product_id": str(seeded_product().id)},
        format="json",
        headers={"If-Match": '"1"'},
    )

    assert response.status_code == 200, response.content
    evaluation = BankRuleEvaluation.objects.get()
    assert evaluation.application_version == 2
    assert evaluation.bank_product == seeded_product()
    assert evaluation.evaluated_by == advisor_user
    assert latest(advisor_client, application).json()["is_current"] is True


def test_clearing_the_product_or_changing_the_purpose_does_not_evaluate(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    with_product(application)
    url = application_url(application)
    headers = {"If-Match": '"1"'}

    advisor_client.patch(url, {"purpose_code": "PURCHASE_USED"}, format="json", headers=headers)
    advisor_client.patch(url, {"bank_product_id": None}, format="json", headers={"If-Match": '"2"'})

    application.refresh_from_db()
    assert (application.version, application.bank_product) == (3, None)
    assert not BankRuleEvaluation.objects.exists()


def test_financing_evaluates_only_when_the_product_changes(
    advisor_client: APIClient, ready: CreditApplication
) -> None:
    # El PUT que creó la financiación eligió el producto: una evaluación con la versión 3.
    assert list(BankRuleEvaluation.objects.values_list("application_version", flat=True)) == [3]

    put(advisor_client, ready, "financing", bank_credit(term_months=180), '"3"')
    assert BankRuleEvaluation.objects.count() == 1

    fna = seeded_product("FNA")
    put(advisor_client, ready, "financing", bank_credit(fna), '"4"')
    evaluation = BankRuleEvaluation.objects.latest("created_at")
    assert (evaluation.application_version, evaluation.bank_product) == (5, fna)

    own_funds = {"financing_mode_code": "OWN_FUNDS", "own_resources_cop": 420_000_000}
    put(advisor_client, ready, "financing", own_funds, '"5"')
    assert BankRuleEvaluation.objects.count() == 2


# --- GET /eligible-bank-products --------------------------------------------------------


def test_eligible_products_lists_available_products_with_an_unsaved_evaluation(
    advisor_client: APIClient,
    application: CreditApplication,
    make_rule: Callable[..., BankPolicyRule],
    new_home_only_product: BankProduct,
) -> None:
    make_rule(code="EMPLOYEE_ONLY", condition=EMPLOYEE_ONLY, message="Solo empleados.")
    make_rule(
        code="LONG_TERM",
        condition=MIN_TERM,
        severity="WARNING",
        message="Plazo corto.",
        bank_product=seeded_product("FNA"),
    )
    BankProduct.objects.filter(pk=seeded_product("BANCO_BOGOTA").pk).update(
        status=BankStatus.INACTIVE
    )

    response = eligible(advisor_client, application)

    assert response.status_code == 200, response.content
    assert response["ETag"] == '"1"'
    items = response.json()["items"]
    assert [(item["bank"]["code"], item["code"]) for item in items] == [
        ("BANCO_PRUEBA", "MORTGAGE"),
        ("BANCOLOMBIA", "MORTGAGE"),
        ("FNA", "MORTGAGE"),
    ]
    bancolombia = items[1]
    assert bancolombia == {
        "id": str(seeded_product().id),
        "code": "MORTGAGE",
        "name": bancolombia["name"],
        "bank": {
            "id": str(seeded_product().bank_id),
            "code": "BANCOLOMBIA",
            "name": "Bancolombia",
            "short_name": "",
        },
        "product_type_code": "MORTGAGE",
        "product_type_label": "Crédito hipotecario",
        "min_amount_cop": None,
        "max_amount_cop": None,
        "min_term_months": None,
        "max_term_months": None,
        "evaluation": {"eligible": False, "blocking_count": 1, "warning_count": 0},
    }
    assert items[2]["evaluation"] == {"eligible": True, "blocking_count": 0, "warning_count": 1}
    assert items[0]["evaluation"] == {"eligible": True, "blocking_count": 0, "warning_count": 0}
    assert not BankRuleEvaluation.objects.exists()


def test_eligible_products_filter_by_purpose_and_include_ranges(
    advisor_client: APIClient,
    application: CreditApplication,
    new_home_only_product: BankProduct,
) -> None:
    BankProduct.objects.filter(pk=seeded_product().pk).update(min_amount_cop=1)
    CreditApplication.objects.filter(pk=application.pk).update(
        purpose_item=catalog_item("loan_purpose", "PURCHASE_USED")
    )

    items = eligible(advisor_client, application).json()["items"]

    assert "BANCO_PRUEBA" not in [item["bank"]["code"] for item in items]
    bancolombia = next(item for item in items if item["bank"]["code"] == "BANCOLOMBIA")
    # Sin financiación, el monto falta y el rango del producto bloquea.
    assert bancolombia["evaluation"] == {
        "eligible": False,
        "blocking_count": 1,
        "warning_count": 0,
    }


def test_eligible_products_are_paginated(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = advisor_client.get(
        application_url(application, "/eligible-bank-products"), {"page_size": 1}
    )

    body = response.json()
    assert (body["total"], len(body["items"])) == (3, 1)


# --- Acceso -----------------------------------------------------------------------------


ENDPOINTS = ["eligible", "evaluate", "latest"]


def call(endpoint: str, client: APIClient, application: CreditApplication) -> Any:
    return {"eligible": eligible, "evaluate": evaluate, "latest": latest}[endpoint](
        client, application
    )


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_broker_and_partner_have_no_access(
    endpoint: str,
    broker_client: APIClient,
    partner_client: APIClient,
    application: CreditApplication,
) -> None:
    assert call(endpoint, broker_client, application).status_code == 403
    assert call(endpoint, partner_client, application).status_code == 403


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_application_out_of_scope_is_404(
    endpoint: str, other_advisor_client: APIClient, application: CreditApplication
) -> None:
    with_product(application)

    assert_error(call(endpoint, other_advisor_client, application), 404, "RESOURCE_NOT_FOUND")


def test_unauthenticated_is_rejected(application: CreditApplication) -> None:
    assert evaluate(APIClient(), application).status_code == 401
