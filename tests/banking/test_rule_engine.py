from typing import Any

import pytest

from apps.banking.rule_engine import (
    MAX_DEPTH,
    MAX_NODES,
    ConditionError,
    Outcome,
    evaluate_condition,
    validate_condition,
    validate_context,
)
from apps.banking.rule_fields import RULE_FIELDS, FieldType, RuleField
from tests.banking.conftest import MAX_LTV_CONDITION


def field(name: str) -> dict[str, str]:
    return {"field": name}


AMOUNT = field("financing.requested_amount_cop")
VALUE = field("property.estimated_value_cop")
PROFILE = field("applicant.employment_profile_code")


def outcome(condition: Any, context: dict[str, Any]) -> Outcome:
    return evaluate_condition(condition, context).outcome


# --- Validación -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "condition",
    [
        MAX_LTV_CONDITION,
        {"operator": "gte", "left": field("financing.term_months"), "right": 12},
        {"operator": "eq", "left": field("financing.uses_severance_funds"), "right": True},
        {"operator": "eq", "left": PROFILE, "right": "EMPLOYEE"},
        {"operator": "in", "left": PROFILE, "right": ["EMPLOYEE", "PENSIONER"]},
        {"operator": "in", "left": field("financing.term_months"), "right": [120, 240]},
        {
            "operator": "lte",
            "left": AMOUNT,
            "right": {
                "operator": "sum",
                "fields": ["financing.own_resources_cop", "financing.severance_funds_cop"],
            },
        },
        {
            "operator": "and",
            "conditions": [
                {"operator": "gte", "left": AMOUNT, "right": 0},
                {
                    "operator": "or",
                    "conditions": [
                        {"operator": "eq", "left": PROFILE, "right": "EMPLOYEE"},
                        {"operator": "eq", "left": field("application.is_joint"), "right": True},
                    ],
                },
            ],
        },
    ],
)
def test_valid_conditions(condition: Any) -> None:
    validate_condition(condition)


@pytest.mark.parametrize(
    ("condition", "path"),
    [
        ("lte", "condition"),
        ({"left": AMOUNT, "right": 1}, "condition"),
        ({"operator": "lt", "left": AMOUNT, "right": 1}, "condition.operator"),
        ({"operator": "__import__", "left": AMOUNT, "right": 1}, "condition.operator"),
        ({"operator": "lte", "left": AMOUNT}, "condition"),
        ({"operator": "lte", "left": AMOUNT, "right": 1, "extra": 1}, "condition"),
        ({"operator": "lte", "left": field("os.system"), "right": 1}, "condition.left.field"),
        ({"operator": "lte", "left": field("__class__"), "right": 1}, "condition.left.field"),
        ({"operator": "lte", "left": PROFILE, "right": 1}, "condition"),
        ({"operator": "eq", "left": PROFILE, "right": 1}, "condition"),
        ({"operator": "eq", "left": AMOUNT, "right": True}, "condition"),
        ({"operator": "lte", "left": AMOUNT, "right": None}, "condition.right"),
        ({"operator": "lte", "left": AMOUNT, "right": [1]}, "condition.right"),
        ({"operator": "lte", "left": AMOUNT, "right": float("nan")}, "condition.right"),
        ({"operator": "lte", "left": AMOUNT, "right": "x" * 201}, "condition.right"),
        ({"operator": "in", "left": PROFILE, "right": []}, "condition.right"),
        ({"operator": "in", "left": PROFILE, "right": ["EMPLOYEE", 3]}, "condition.right.1"),
        (
            {"operator": "in", "left": field("application.is_joint"), "right": [True]},
            "condition.left",
        ),
        ({"operator": "and", "conditions": []}, "condition.conditions"),
        ({"operator": "and", "conditions": [AMOUNT]}, "condition.conditions.0"),
        (
            {
                "operator": "lte",
                "left": {"operator": "sum", "fields": ["financing.term_months"]},
                "right": 1,
            },
            "condition.left.fields",
        ),
        (
            {
                "operator": "lte",
                "left": {
                    "operator": "sum",
                    "fields": ["financing.term_months", "property.city_code"],
                },
                "right": 1,
            },
            "condition.left.fields.1",
        ),
        (
            {
                "operator": "lte",
                "left": {
                    "operator": "ratio",
                    "numerator_field": "financing.requested_amount_cop",
                    "denominator_field": "property.city_code",
                },
                "right": 1,
            },
            "condition.left.denominator_field",
        ),
        (
            {"operator": "lte", "left": {"operator": "max", "fields": []}, "right": 1},
            "condition.left",
        ),
    ],
)
def test_invalid_conditions_point_to_the_node(condition: Any, path: str) -> None:
    with pytest.raises(ConditionError) as exc_info:
        validate_condition(condition)
    assert exc_info.value.path == path


def test_depth_is_limited() -> None:
    condition: dict[str, Any] = {"operator": "gte", "left": AMOUNT, "right": 0}
    for _ in range(MAX_DEPTH):
        condition = {"operator": "and", "conditions": [condition]}

    with pytest.raises(ConditionError, match="niveles"):
        validate_condition(condition)


def test_size_is_limited() -> None:
    comparisons = [{"operator": "gte", "left": AMOUNT, "right": 0}] * (MAX_NODES // 3 + 1)

    with pytest.raises(ConditionError, match="nodos"):
        validate_condition({"operator": "and", "conditions": comparisons})


def test_fields_come_from_the_whitelist_passed() -> None:
    fields = {"custom.score": RuleField(FieldType.NUMBER, "Campo de prueba.")}
    condition = {"operator": "gte", "left": field("custom.score"), "right": 1}

    validate_condition(condition, fields)
    with pytest.raises(ConditionError):
        validate_condition(condition)  # No está en RULE_FIELDS.


def test_whitelist_names_are_dotted_paths() -> None:
    assert RULE_FIELDS
    assert all(name.count(".") == 1 for name in RULE_FIELDS)


# --- Evaluación -------------------------------------------------------------------------


def ltv_context(amount: int | None, value: int | None) -> dict[str, Any]:
    return {
        "financing": {"requested_amount_cop": amount},
        "property": {"estimated_value_cop": value},
    }


@pytest.mark.parametrize(
    ("amount", "value", "expected"),
    [
        (210_000_000, 300_000_000, Outcome.PASSED),  # Exactamente 70%.
        (150_000_000, 300_000_000, Outcome.PASSED),
        (210_000_001, 300_000_000, Outcome.FAILED),
        (None, 300_000_000, Outcome.MISSING_DATA),
        (210_000_000, 0, Outcome.MISSING_DATA),  # Denominador en cero.
    ],
)
def test_max_ltv_example(amount: int | None, value: int | None, expected: Outcome) -> None:
    assert outcome(MAX_LTV_CONDITION, ltv_context(amount, value)) == expected


def test_missing_data_reports_the_fields() -> None:
    result = evaluate_condition(MAX_LTV_CONDITION, {"financing": {}})

    assert result.outcome == Outcome.MISSING_DATA
    assert result.unresolved_fields == [
        "financing.requested_amount_cop",
        "property.estimated_value_cop",
    ]


def test_zero_denominator_is_reported_as_unresolved() -> None:
    result = evaluate_condition(MAX_LTV_CONDITION, ltv_context(1, 0))

    assert result.unresolved_fields == ["property.estimated_value_cop"]


def test_decimal_arithmetic_avoids_float_errors() -> None:
    # Con float, 0.1 + 0.2 > 0.3; con Decimal, son iguales.
    condition = {
        "operator": "eq",
        "left": {
            "operator": "sum",
            "fields": ["financing.own_resources_cop", "financing.severance_funds_cop"],
        },
        "right": 0.3,
    }
    context = {"financing": {"own_resources_cop": 0.1, "severance_funds_cop": 0.2}}

    assert outcome(condition, context) == Outcome.PASSED


def test_in_and_eq() -> None:
    allowed = {"operator": "in", "left": PROFILE, "right": ["EMPLOYEE", "PENSIONER"]}
    joint = {"operator": "eq", "left": field("application.is_joint"), "right": True}

    assert outcome(allowed, {"applicant": {"employment_profile_code": "PENSIONER"}}) == "PASSED"
    assert outcome(allowed, {"applicant": {"employment_profile_code": "INDEPENDENT"}}) == "FAILED"
    assert outcome(joint, {"application": {"is_joint": False}}) == Outcome.FAILED


TRUE = {"operator": "gte", "left": AMOUNT, "right": 0}
FALSE = {"operator": "lte", "left": AMOUNT, "right": 0}
UNKNOWN = {"operator": "gte", "left": VALUE, "right": 0}  # Sin valor en el contexto.


@pytest.mark.parametrize(
    ("operator", "conditions", "expected"),
    [
        ("and", [TRUE, TRUE], Outcome.PASSED),
        ("and", [TRUE, FALSE], Outcome.FAILED),
        ("and", [UNKNOWN, FALSE], Outcome.FAILED),  # Falso decide aunque falten datos.
        ("and", [TRUE, UNKNOWN], Outcome.MISSING_DATA),
        ("or", [FALSE, TRUE], Outcome.PASSED),
        ("or", [UNKNOWN, TRUE], Outcome.PASSED),  # Verdadero decide aunque falten datos.
        ("or", [FALSE, UNKNOWN], Outcome.MISSING_DATA),
        ("or", [FALSE, FALSE], Outcome.FAILED),
    ],
)
def test_three_valued_logic(operator: str, conditions: list[Any], expected: Outcome) -> None:
    context = {"financing": {"requested_amount_cop": 100}}
    result = evaluate_condition({"operator": operator, "conditions": conditions}, context)

    assert result.outcome == expected
    if expected != Outcome.MISSING_DATA:
        assert result.unresolved_fields == []


def test_evaluation_validates_the_condition_first() -> None:
    with pytest.raises(ConditionError):
        evaluate_condition({"operator": "exec", "left": AMOUNT, "right": 1}, {})


def test_evaluation_rejects_values_of_the_wrong_type() -> None:
    with pytest.raises(ConditionError) as exc_info:
        evaluate_condition(TRUE, {"financing": {"requested_amount_cop": "100"}})
    assert exc_info.value.path == "context.financing.requested_amount_cop"


# --- Contexto ---------------------------------------------------------------------------


def test_valid_context() -> None:
    validate_context(
        {
            "financing": {"requested_amount_cop": 1, "uses_severance_funds": False},
            "property": {"estimated_value_cop": None},
            "applicant": None,
        }
    )


@pytest.mark.parametrize(
    ("context", "path"),
    [
        ([], "context"),
        ({"bank": {}}, "context.bank"),
        ({"financing": {"interest_rate": 1}}, "context.financing.interest_rate"),
        ({"financing": {"requested_amount_cop": "1"}}, "context.financing.requested_amount_cop"),
        ({"financing": {"uses_severance_funds": 1}}, "context.financing.uses_severance_funds"),
        ({"financing": 1}, "context.financing"),
    ],
)
def test_invalid_context(context: Any, path: str) -> None:
    with pytest.raises(ConditionError) as exc_info:
        validate_context(context)
    assert exc_info.value.path == path
