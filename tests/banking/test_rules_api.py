import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.banking.models import BankPolicyRule, BankProduct
from apps.banking.rule_engine import Outcome
from apps.banking.rule_fields import RULE_FIELDS
from apps.banking.services import applicable_rules, evaluate_rules
from apps.banking.signals import bank_policy_rule_status_changed
from apps.identity.models import User
from tests.banking.conftest import MAX_LTV_CONDITION, RULES_URL, catalog_item
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

PROFILE_CONDITION = {
    "operator": "in",
    "left": {"field": "applicant.employment_profile_code"},
    "right": ["EMPLOYEE", "PENSIONER"],
}


def rule_url(rule: BankPolicyRule | str) -> str:
    rule_id = rule if isinstance(rule, str) else rule.id
    return f"{RULES_URL}/{rule_id}"


def create(api: APIClient, product: BankProduct, **payload: Any) -> Any:
    return api.post(
        RULES_URL,
        {
            "bank_product_id": str(product.id),
            "purpose_code": "PURCHASE_NEW",
            "code": "MAX_LTV_NEW_HOME",
            "severity": "BLOCKING",
            "condition": MAX_LTV_CONDITION,
            "message": "El monto solicitado no puede superar el 70% del valor del inmueble.",
            **payload,
        },
        format="json",
    )


def patch(api: APIClient, rule: BankPolicyRule | str, **payload: Any) -> Any:
    return api.patch(rule_url(rule), payload, format="json")


def versions(rule: BankPolicyRule) -> list[tuple[int, str]]:
    return list(
        BankPolicyRule.objects.filter(bank_product=rule.bank_product, code=rule.code)
        .order_by("version")
        .values_list("version", "status")
    )


@pytest.fixture
def status_events() -> Iterator[list[dict[str, Any]]]:
    received: list[dict[str, Any]] = []

    def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    bank_policy_rule_status_changed.connect(handler)
    try:
        yield received
    finally:
        bank_policy_rule_status_changed.disconnect(handler)


@pytest.fixture
def active_rule(make_rule: Callable[..., BankPolicyRule]) -> BankPolicyRule:
    return make_rule(status="ACTIVE")


# --- Crear ------------------------------------------------------------------------------


def test_create_rule_as_draft_version_one(
    admin_client: APIClient, admin_user: User, product: BankProduct
) -> None:
    response = create(admin_client, product)

    assert response.status_code == 201, response.content
    body = response.json()
    assert (body["code"], body["version"], body["status"]) == ("MAX_LTV_NEW_HOME", 1, "DRAFT")
    assert body["bank_product"]["id"] == str(product.id)
    assert body["bank_product"]["bank"]["code"] == "BANCO_PRUEBA"
    assert body["purpose"] == {"code": "PURCHASE_NEW", "label": "Compra de vivienda nueva"}
    assert body["condition"] == MAX_LTV_CONDITION
    assert body["created_by"]["id"] == str(admin_user.id)
    assert body["valid_from"] is not None


def test_rule_without_purpose_applies_to_all(admin_client: APIClient, product: BankProduct) -> None:
    body = create(admin_client, product, purpose_code=None, code="PROFILE").json()

    assert body["purpose"] is None


def test_rule_code_is_unique_per_product(admin_client: APIClient, product: BankProduct) -> None:
    create(admin_client, product)

    assert_error(create(admin_client, product), 409, "DUPLICATE_CODE")


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"condition": {"operator": "eval", "left": 1, "right": 1}}, "condition.operator"),
        (
            {"condition": {"operator": "lte", "left": {"field": "bank.secret"}, "right": 1}},
            "condition.left.field",
        ),
        ({"condition": "1 < 2"}, "condition"),
        ({"severity": "INFO"}, "severity"),
        ({"code": "max_ltv"}, "code"),
        ({"purpose_code": "CARTERA"}, "purpose_code"),
        ({"bank_product_id": str(uuid.uuid4())}, "bank_product_id"),
        (
            {"valid_from": "2026-07-01T00:00:00Z", "valid_to": "2026-06-01T00:00:00Z"},
            "valid_to",
        ),
        ({"status": "ACTIVE"}, "status"),  # Campo no permitido: nace en borrador.
        ({"version": 3}, "version"),
    ],
)
def test_create_rule_validates_input(
    admin_client: APIClient, product: BankProduct, payload: dict[str, Any], field: str
) -> None:
    body = assert_error(create(admin_client, product, **payload), 400, "VALIDATION_ERROR")
    assert field in {detail["field"] for detail in body["details"]}


# --- Versionado -------------------------------------------------------------------------


def test_patch_on_draft_edits_in_place(
    admin_client: APIClient, make_rule: Callable[..., BankPolicyRule]
) -> None:
    draft = make_rule()

    response = patch(admin_client, draft, severity="WARNING", message="Revisar LTV.")

    assert response.status_code == 200, response.content
    assert response.json()["id"] == str(draft.id)
    assert response.json()["version"] == 1
    assert response.json()["severity"] == "WARNING"
    assert versions(draft) == [(1, "DRAFT")]


def test_patch_on_published_creates_a_new_draft_version(
    admin_client: APIClient,
    admin_user: User,
    make_user: Callable[..., User],
    make_rule: Callable[..., BankPolicyRule],
) -> None:
    author = make_user(email="autor@example.com", role_code="ADMIN")
    published = make_rule(status="ACTIVE", created_by=author)

    response = patch(admin_client, published, condition=PROFILE_CONDITION)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["id"] != str(published.id)
    assert (body["version"], body["status"]) == (2, "DRAFT")
    assert body["condition"] == PROFILE_CONDITION
    assert body["message"] == published.message  # Copia lo que no cambió.
    assert body["created_by"]["id"] == str(admin_user.id)

    # La versión publicada no se toca.
    before = published.updated_at
    published.refresh_from_db()
    assert published.condition == MAX_LTV_CONDITION
    assert published.updated_at == before
    assert versions(published) == [(1, "ACTIVE"), (2, "DRAFT")]


def test_inactive_versions_also_branch_into_a_draft(
    admin_client: APIClient, make_rule: Callable[..., BankPolicyRule]
) -> None:
    make_rule(version=1, status="INACTIVE")
    active = make_rule(version=2, status="ACTIVE")
    old = BankPolicyRule.objects.get(version=1)

    body = patch(admin_client, old, severity="WARNING").json()

    assert body["version"] == 3  # Siempre la siguiente a la mayor.
    assert versions(active) == [(1, "INACTIVE"), (2, "ACTIVE"), (3, "DRAFT")]


def test_only_one_draft_per_rule(admin_client: APIClient, active_rule: BankPolicyRule) -> None:
    draft_id = patch(admin_client, active_rule, severity="WARNING").json()["id"]

    body = assert_error(
        patch(admin_client, active_rule, message="Otro cambio"), 409, "RULE_DRAFT_EXISTS"
    )

    assert body["details"] == [
        {
            "field": None,
            "code": "EXISTING_DRAFT",
            "message": "Edita el borrador v2.",
            "resource_id": draft_id,
        }
    ]
    assert patch(admin_client, draft_id, message="Otro cambio").status_code == 200
    assert versions(active_rule) == [(1, "ACTIVE"), (2, "DRAFT")]


def test_empty_patch_on_published_creates_nothing(
    admin_client: APIClient, active_rule: BankPolicyRule
) -> None:
    response = patch(admin_client, active_rule)

    assert response.status_code == 200, response.content
    assert versions(active_rule) == [(1, "ACTIVE")]


@pytest.mark.parametrize("field", ["code", "bank_product_id", "version", "status"])
def test_identity_fields_are_not_editable(
    admin_client: APIClient, make_rule: Callable[..., BankPolicyRule], field: str
) -> None:
    body = assert_error(patch(admin_client, make_rule(), **{field: "X"}), 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == field


def test_patch_validates_the_new_condition(
    admin_client: APIClient, active_rule: BankPolicyRule
) -> None:
    body = assert_error(
        patch(admin_client, active_rule, condition={"operator": "and", "conditions": []}),
        400,
        "VALIDATION_ERROR",
    )
    assert body["details"][0]["field"] == "condition.conditions"
    assert versions(active_rule) == [(1, "ACTIVE")]


def test_patch_validates_validity_against_current_values(
    admin_client: APIClient, make_rule: Callable[..., BankPolicyRule]
) -> None:
    draft = make_rule()

    body = assert_error(
        patch(admin_client, draft, valid_to=(draft.valid_from - timedelta(days=1)).isoformat()),
        400,
        "VALIDATION_ERROR",
    )
    assert body["details"][0]["field"] == "valid_to"


# --- Publicar y desactivar --------------------------------------------------------------


def test_activating_a_version_retires_the_previous_one(
    admin_client: APIClient,
    admin_user: User,
    active_rule: BankPolicyRule,
    status_events: list[dict[str, Any]],
) -> None:
    draft_id = patch(admin_client, active_rule, severity="WARNING").json()["id"]

    response = admin_client.post(f"{rule_url(draft_id)}/activate")

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "ACTIVE"
    assert versions(active_rule) == [(1, "INACTIVE"), (2, "ACTIVE")]
    assert [(e["rule"].version, e["from_status"], e["to_status"]) for e in status_events] == [
        (1, "ACTIVE", "INACTIVE"),
        (2, "DRAFT", "ACTIVE"),
    ]
    assert status_events[0]["actor"] == admin_user


def test_activating_an_active_version_is_a_no_op(
    admin_client: APIClient, active_rule: BankPolicyRule, status_events: list[dict[str, Any]]
) -> None:
    response = admin_client.post(f"{rule_url(active_rule)}/activate")

    assert response.json()["status"] == "ACTIVE"
    assert status_events == []


def test_an_inactive_version_can_be_published_again(
    admin_client: APIClient, make_rule: Callable[..., BankPolicyRule]
) -> None:
    old = make_rule(version=1, status="INACTIVE")
    make_rule(version=2, status="ACTIVE")

    admin_client.post(f"{rule_url(old)}/activate")

    assert versions(old) == [(1, "ACTIVE"), (2, "INACTIVE")]


def test_deactivate_stops_the_published_version(
    admin_client: APIClient, active_rule: BankPolicyRule
) -> None:
    response = admin_client.post(f"{rule_url(active_rule)}/deactivate")

    assert response.json()["status"] == "INACTIVE"
    assert not applicable_rules(active_rule.bank_product).exists()


def test_a_draft_cannot_be_deactivated(
    admin_client: APIClient, make_rule: Callable[..., BankPolicyRule]
) -> None:
    assert_error(
        admin_client.post(f"{rule_url(make_rule())}/deactivate"), 409, "INVALID_STATE_TRANSITION"
    )


def test_expired_rules_cannot_be_published(
    admin_client: APIClient, make_rule: Callable[..., BankPolicyRule]
) -> None:
    now = timezone.now()
    draft = make_rule(valid_from=now - timedelta(days=10), valid_to=now - timedelta(days=1))

    assert_error(admin_client.post(f"{rule_url(draft)}/activate"), 422, "RULE_EXPIRED")


def test_publishing_revalidates_against_the_current_whitelist(
    admin_client: APIClient,
    make_rule: Callable[..., BankPolicyRule],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = make_rule()
    # Simula que el paso 8 retira un campo de la lista blanca.
    monkeypatch.delitem(RULE_FIELDS, "property.estimated_value_cop")

    body = assert_error(
        admin_client.post(f"{rule_url(draft)}/activate"), 422, "RULE_CONDITION_INVALID"
    )
    assert body["details"][0]["field"] == "condition.left.denominator_field"
    draft.refresh_from_db()
    assert draft.status == "DRAFT"


# --- Consultar --------------------------------------------------------------------------


def test_versions_history_is_newest_first(
    advisor_client: APIClient, make_rule: Callable[..., BankPolicyRule]
) -> None:
    make_rule(version=1, status="INACTIVE")
    current = make_rule(version=2, status="ACTIVE")
    make_rule(code="OTRA", version=1)

    body = advisor_client.get(f"{rule_url(current)}/versions").json()

    assert [(item["version"], item["status"]) for item in body["items"]] == [
        (2, "ACTIVE"),
        (1, "INACTIVE"),
    ]


def test_list_rules_filters(
    advisor_client: APIClient,
    make_rule: Callable[..., BankPolicyRule],
    make_product: Callable[..., BankProduct],
    product: BankProduct,
) -> None:
    ltv = make_rule(status="ACTIVE", purpose_item=catalog_item("loan_purpose", "PURCHASE_NEW"))
    profile = make_rule(code="PROFILE", severity="WARNING", condition=PROFILE_CONDITION)
    other_product = make_product(code="LEASING")
    elsewhere = make_rule(bank_product=other_product, code="MAX_LTV")

    def ids(params: dict[str, str]) -> set[str]:
        response = advisor_client.get(RULES_URL, params)
        assert response.status_code == 200, response.content
        return {item["id"] for item in response.json()["items"]}

    assert ids({"bank_product_id": str(product.id)}) == {str(ltv.id), str(profile.id)}
    assert ids({"status": "ACTIVE"}) == {str(ltv.id)}
    assert ids({"severity": "WARNING"}) == {str(profile.id)}
    assert ids({"code": "MAX_LTV"}) == {str(ltv.id), str(elsewhere.id)}
    assert ids({"purpose": "PURCHASE_NEW"}) == {str(ltv.id)}
    assert ids({"bank_id": str(product.bank_id)}) == {
        str(ltv.id),
        str(profile.id),
        str(elsewhere.id),
    }
    assert_error(advisor_client.get(RULES_URL, {"status": "X"}), 400, "VALIDATION_ERROR")


def test_advisor_reads_but_cannot_write_rules(
    advisor_client: APIClient, product: BankProduct, active_rule: BankPolicyRule
) -> None:
    assert advisor_client.get(rule_url(active_rule)).status_code == 200

    assert_error(create(advisor_client, product, code="NUEVA"), 403, "PERMISSION_DENIED")
    assert_error(patch(advisor_client, active_rule, severity="WARNING"), 403, "PERMISSION_DENIED")
    assert_error(
        advisor_client.post(f"{rule_url(active_rule)}/deactivate"), 403, "PERMISSION_DENIED"
    )
    assert_error(
        advisor_client.post(
            f"{rule_url(active_rule)}/test", {"cases": [{"context": {}}]}, format="json"
        ),
        403,
        "PERMISSION_DENIED",
    )


# --- Casos de prueba --------------------------------------------------------------------


def test_run_test_cases_without_touching_the_rule(
    admin_client: APIClient, make_rule: Callable[..., BankPolicyRule]
) -> None:
    draft = make_rule()
    before = draft.updated_at

    response = admin_client.post(
        f"{rule_url(draft)}/test",
        {
            "cases": [
                {
                    "name": "Dentro del 70%",
                    "context": {
                        "financing": {"requested_amount_cop": 200_000_000},
                        "property": {"estimated_value_cop": 300_000_000},
                    },
                    "expected": "PASSED",
                },
                {
                    "name": "Supera el 70%",
                    "context": {
                        "financing": {"requested_amount_cop": 250_000_000},
                        "property": {"estimated_value_cop": 300_000_000},
                    },
                    "expected": "PASSED",
                },
                {"context": {"financing": {"requested_amount_cop": 1}}},
            ]
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["rule"] == {"id": str(draft.id), "code": "MAX_LTV", "version": 1}
    assert [
        (r["name"], r["outcome"], r["expected"], r["matches_expected"]) for r in body["results"]
    ] == [
        ("Dentro del 70%", "PASSED", "PASSED", True),
        ("Supera el 70%", "FAILED", "PASSED", False),
        ("", "MISSING_DATA", None, None),
    ]
    assert body["results"][2]["unresolved_fields"] == ["property.estimated_value_cop"]
    draft.refresh_from_db()
    assert draft.updated_at == before


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"cases": []}, "cases"),
        ({"cases": [{"context": {"bank": {"x": 1}}}]}, "cases.0.context.bank"),
        (
            {"cases": [{"context": {"financing": {"requested_amount_cop": "mucho"}}}]},
            "cases.0.context.financing.requested_amount_cop",
        ),
        ({"cases": [{"context": {}, "expected": "MAYBE"}]}, "cases.0.expected"),
        ({"cases": [{"context": {}, "extra": 1}]}, "cases.0.extra"),
        ({"cases": [{"context": {}}] * 21}, "cases"),
    ],
)
def test_test_cases_are_validated(
    admin_client: APIClient,
    make_rule: Callable[..., BankPolicyRule],
    payload: dict[str, Any],
    field: str,
) -> None:
    body = assert_error(
        admin_client.post(f"{rule_url(make_rule())}/test", payload, format="json"),
        400,
        "VALIDATION_ERROR",
    )
    assert field in {detail["field"] for detail in body["details"]}


# --- Reglas aplicables y evaluación (para el paso 8) ------------------------------------


def test_applicable_rules_respect_status_validity_and_purpose(
    make_rule: Callable[..., BankPolicyRule], product: BankProduct
) -> None:
    now = timezone.now()
    new_home = catalog_item("loan_purpose", "PURCHASE_NEW")
    used_home = catalog_item("loan_purpose", "PURCHASE_USED")
    for_all = make_rule(code="ALL", status="ACTIVE")
    for_new = make_rule(code="NEW_ONLY", status="ACTIVE", purpose_item=new_home)
    make_rule(code="DRAFT_ONLY")
    make_rule(code="FUTURE", status="ACTIVE", valid_from=now + timedelta(days=1))
    make_rule(
        code="EXPIRED",
        status="ACTIVE",
        valid_from=now - timedelta(days=10),
        valid_to=now - timedelta(days=1),
    )

    assert list(applicable_rules(product, purpose=new_home)) == [for_all, for_new]
    assert list(applicable_rules(product, purpose=used_home)) == [for_all]
    assert list(applicable_rules(product)) == [for_all]


def test_evaluate_rules_reports_outcome_with_exact_version(
    make_rule: Callable[..., BankPolicyRule], product: BankProduct
) -> None:
    make_rule(version=1, status="INACTIVE")
    current = make_rule(version=2, status="ACTIVE")
    make_rule(code="PROFILE", status="ACTIVE", severity="WARNING", condition=PROFILE_CONDITION)
    context = {
        "financing": {"requested_amount_cop": 250_000_000},
        "property": {"estimated_value_cop": 300_000_000},
    }

    results = evaluate_rules(product, context)

    assert [(r.code, r.version, r.severity, r.outcome) for r in results] == [
        ("MAX_LTV", 2, "BLOCKING", Outcome.FAILED),
        ("PROFILE", 1, "WARNING", Outcome.MISSING_DATA),
    ]
    assert results[0].rule_id == current.id
    assert results[1].unresolved_fields == ["applicant.employment_profile_code"]
