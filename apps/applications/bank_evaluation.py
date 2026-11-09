"""Evaluación de las reglas bancarias de un producto sobre una solicitud (API §18.2).

Se aplican dos tipos de reglas:

- ``RULE``: las versiones publicadas y vigentes que configuró el administrador
  (``banking.services.evaluate_rules``).
- ``SYSTEM``: los rangos del producto, siempre ``BLOCKING``. ``PRODUCT_AMOUNT_RANGE``
  compara ``financing.requested_amount_cop`` con ``min/max_amount_cop`` y
  ``PRODUCT_TERM_RANGE`` compara ``financing.term_months`` con ``min/max_term_months``.
  Si el producto no define el rango, la regla no aparece; si falta el dato, da
  ``MISSING_DATA``.

Falla cerrada: una regla ``BLOCKING`` con ``FAILED`` o ``MISSING_DATA`` deja la
evaluación no elegible. Las ``WARNING`` se reportan, pero no afectan la elegibilidad.

Cada regla evaluada es una fila del ``result_snapshot`` (``SnapshotRow``), con la versión
exacta aplicada. La respuesta de la API se reconstruye siempre desde esas filas, para no
reinterpretar el pasado con reglas nuevas.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from apps.applications.models import BankRuleEvaluation, CreditApplication
from apps.applications.rule_context import RuleContext, build_rule_context
from apps.banking.models import BankProduct, RuleSeverity
from apps.banking.rule_engine import Outcome
from apps.banking.services import RuleResult, evaluate_rules
from apps.catalogs.models import CatalogItem
from apps.identity.models import BuyerSession, User

SOURCE_RULE = "RULE"
SOURCE_SYSTEM = "SYSTEM"

PRODUCT_AMOUNT_RANGE = "PRODUCT_AMOUNT_RANGE"
PRODUCT_TERM_RANGE = "PRODUCT_TERM_RANGE"
AMOUNT_FIELD = "financing.requested_amount_cop"
TERM_FIELD = "financing.term_months"

# Fila del snapshot: rule_id, code, version, severity, message, outcome,
# unresolved_fields, field y source. Solo tipos JSON.
SnapshotRow = dict[str, Any]


@dataclass(frozen=True)
class EvaluationSummary:
    eligible: bool
    blocking_count: int
    warning_count: int


# --------------------------------------------------------------------------------------
# Filas del snapshot
# --------------------------------------------------------------------------------------


def _row(
    *,
    code: str,
    severity: str,
    message: str,
    outcome: Outcome,
    source: str,
    unresolved_fields: list[str],
    fields: list[str],
    rule_id: str | None = None,
    version: int | None = None,
) -> SnapshotRow:
    # El dato que se señala: el primero que falta o, si se incumple, el primero citado.
    if outcome == Outcome.MISSING_DATA:
        field = unresolved_fields[0] if unresolved_fields else None
    else:
        field = fields[0] if fields else None
    return {
        "rule_id": rule_id,
        "code": code,
        "version": version,
        "severity": severity,
        "message": message,
        "outcome": outcome.value,
        "unresolved_fields": unresolved_fields,
        "field": field,
        "source": source,
    }


def _configured_row(result: RuleResult) -> SnapshotRow:
    return _row(
        rule_id=str(result.rule_id),
        code=result.code,
        version=result.version,
        severity=result.severity,
        message=result.message,
        outcome=result.outcome,
        source=SOURCE_RULE,
        unresolved_fields=list(result.unresolved_fields),
        fields=list(result.fields),
    )


def _cop(value: int) -> str:
    return "$" + f"{value:,}".replace(",", ".")


def _months(value: int) -> str:
    return f"{value} meses"


def _range_text(low: int | None, high: int | None, fmt: Callable[[int], str]) -> str:
    if low is not None and high is not None:
        return f"estar entre {fmt(low)} y {fmt(high)}"
    if low is not None:
        return f"ser de al menos {fmt(low)}"
    assert high is not None
    return f"ser como máximo de {fmt(high)}"


def _range_row(
    code: str,
    field: str,
    label: str,
    value: int | None,
    low: int | None,
    high: int | None,
    fmt: Callable[[int], str],
) -> SnapshotRow | None:
    if low is None and high is None:
        return None
    if value is None:
        outcome = Outcome.MISSING_DATA
    elif (low is not None and value < low) or (high is not None and value > high):
        outcome = Outcome.FAILED
    else:
        outcome = Outcome.PASSED
    return _row(
        code=code,
        severity=RuleSeverity.BLOCKING,
        message=f"{label} debe {_range_text(low, high, fmt)} para este producto.",
        outcome=outcome,
        source=SOURCE_SYSTEM,
        unresolved_fields=[field] if outcome == Outcome.MISSING_DATA else [],
        fields=[field],
    )


def _system_rows(product: BankProduct, context: RuleContext) -> list[SnapshotRow]:
    financing = context["financing"]
    rows = [
        _range_row(
            PRODUCT_AMOUNT_RANGE,
            AMOUNT_FIELD,
            "El monto solicitado",
            financing["requested_amount_cop"],
            product.min_amount_cop,
            product.max_amount_cop,
            _cop,
        ),
        _range_row(
            PRODUCT_TERM_RANGE,
            TERM_FIELD,
            "El plazo",
            financing["term_months"],
            product.min_term_months,
            product.max_term_months,
            _months,
        ),
    ]
    return [row for row in rows if row is not None]


def evaluate_product(
    product: BankProduct, context: RuleContext, *, purpose: CatalogItem
) -> list[SnapshotRow]:
    """Reglas configuradas (ordenadas por código) y, después, las del sistema."""
    rows = [_configured_row(result) for result in evaluate_rules(product, context, purpose=purpose)]
    return rows + _system_rows(product, context)


# --------------------------------------------------------------------------------------
# Resumen y respuesta
# --------------------------------------------------------------------------------------


def _is_issue(row: Mapping[str, Any]) -> bool:
    return bool(row["outcome"] != Outcome.PASSED)


def blocking_rows(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [r for r in rows if _is_issue(r) and r["severity"] == RuleSeverity.BLOCKING]


def warning_rows(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [r for r in rows if _is_issue(r) and r["severity"] == RuleSeverity.WARNING]


def summarize(rows: list[SnapshotRow]) -> EvaluationSummary:
    blocking = len(blocking_rows(rows))
    return EvaluationSummary(
        eligible=blocking == 0, blocking_count=blocking, warning_count=len(warning_rows(rows))
    )


def issue(row: Mapping[str, Any]) -> dict[str, Any]:
    """Ítem de ``blocking``/``warnings``. Con ``MISSING_DATA`` el mensaje es del sistema:
    el de la regla describe un incumplimiento que todavía no se puede afirmar."""
    unresolved: list[str] = list(row["unresolved_fields"])
    message = row["message"]
    if row["outcome"] == Outcome.MISSING_DATA:
        message = f"Faltan datos para evaluar la regla: {', '.join(unresolved)}."
    return {
        "rule_code": row["code"],
        "outcome": row["outcome"],
        "message": message,
        "field": row["field"],
        "unresolved_fields": unresolved,
    }


def is_current(evaluation: BankRuleEvaluation, application: CreditApplication) -> bool:
    """La evaluación corresponde a la versión y al producto actuales de la solicitud."""
    return (
        evaluation.application_version == application.version
        and evaluation.bank_product_id == application.bank_product_id
    )


# --------------------------------------------------------------------------------------
# Evaluación guardada
# --------------------------------------------------------------------------------------


def save_evaluation(actor: User | BuyerSession, locked: CreditApplication) -> BankRuleEvaluation:
    """Evalúa el producto elegido y guarda el resultado con la versión actual.

    Llamar dentro de una transacción, con la solicitud bloqueada y con producto. Si el
    actor es el comprador, ``evaluated_by`` queda vacío: el esquema solo admite usuarios.
    """
    product = locked.bank_product
    assert product is not None, "save_evaluation exige un producto elegido."
    context = build_rule_context(locked)
    rows = evaluate_product(product, context, purpose=locked.purpose_item)
    summary = summarize(rows)
    return BankRuleEvaluation.objects.create(
        application=locked,
        bank_product=product,
        application_version=locked.version,
        is_eligible=summary.eligible,
        blocking_count=summary.blocking_count,
        warning_count=summary.warning_count,
        result_snapshot={"rules": rows, "context": context},
        evaluated_by=actor if isinstance(actor, User) else None,
    )
