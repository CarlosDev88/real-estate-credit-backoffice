"""Intérprete de las condiciones de las reglas bancarias (sección 23.3 de la API).

La condición es un JSON. Este módulo lo recorre como un árbol y solo reconoce los
operadores de la gramática. No usa ``eval``, ``exec``, ``compile`` ni ``getattr``
sobre datos del JSON: un operador desconocido es un error, nunca código.

Gramática::

    condición   := comparación | pertenencia | lógica
    comparación := {"operator": "eq" | "gte" | "lte", "left": valor, "right": valor}
    pertenencia := {"operator": "in", "left": valor, "right": [literal, ...]}
    lógica      := {"operator": "and" | "or", "conditions": [condición, ...]}
    valor       := literal | campo | suma | razón
    campo       := {"field": "<campo de la lista blanca>"}
    suma        := {"operator": "sum", "fields": ["<campo numérico>", ...]}   (2 o más)
    razón       := {"operator": "ratio", "numerator_field": "<campo numérico>",
                    "denominator_field": "<campo numérico>"}
    literal     := número | texto | booleano

Tipos: ``gte`` y ``lte`` comparan números; ``eq`` compara valores del mismo tipo;
``in`` compara un número o un texto con una lista de literales del mismo tipo.
Los campos y sus tipos están en ``apps.banking.rule_fields.RULE_FIELDS``.

La condición describe lo que debe cumplirse. El resultado es:

- ``PASSED``: se cumple.
- ``FAILED``: no se cumple; la regla aplica su severidad y su mensaje.
- ``MISSING_DATA``: falta un dato (o un denominador vale cero) y no se puede decidir.
  ``and`` y ``or`` usan lógica de tres valores: ``and`` es falso si alguna parte es
  falsa aunque falten datos en otra, y ``or`` es verdadero si alguna parte lo es.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from apps.banking.rule_fields import RULE_FIELDS, FieldType, RuleField

MAX_DEPTH = 6
MAX_NODES = 60
MAX_LIST_ITEMS = 50
MAX_STRING_LENGTH = 200

LOGICAL_OPERATORS = frozenset({"and", "or"})
COMPARISON_OPERATORS = frozenset({"eq", "gte", "lte"})
ORDER_OPERATORS = frozenset({"gte", "lte"})

Fields = Mapping[str, RuleField]
Value = Decimal | str | bool

_TYPE_LABELS = {
    FieldType.NUMBER: "un número",
    FieldType.STRING: "un texto",
    FieldType.BOOLEAN: "un booleano",
}


class Outcome(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    MISSING_DATA = "MISSING_DATA"


class ConditionError(Exception):
    """Condición o contexto no válido. ``path`` señala el nodo, p. ej. ``condition.left``."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


@dataclass(frozen=True)
class ConditionResult:
    outcome: Outcome
    # Campos ausentes o que impiden el cálculo; solo con MISSING_DATA.
    unresolved_fields: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------
# Validación
# --------------------------------------------------------------------------------------


def _literal_type(node: Any, path: str) -> FieldType | None:
    """Tipo del literal, o ``None`` si el nodo no es un literal."""
    if isinstance(node, bool):
        return FieldType.BOOLEAN
    if isinstance(node, int | float):
        if isinstance(node, float) and not math.isfinite(node):
            raise ConditionError(path, "El número debe ser finito.")
        return FieldType.NUMBER
    if isinstance(node, str):
        if len(node) > MAX_STRING_LENGTH:
            raise ConditionError(path, f"El texto supera {MAX_STRING_LENGTH} caracteres.")
        return FieldType.STRING
    return None


def _expect_keys(node: Mapping[str, Any], keys: set[str], path: str) -> None:
    if set(node) != keys:
        expected = ", ".join(f"`{key}`" for key in sorted(keys))
        raise ConditionError(path, f"Claves esperadas: {expected}.")


def _expect_list(node: Any, path: str, *, min_items: int) -> list[Any]:
    if not isinstance(node, list) or len(node) < min_items:
        raise ConditionError(path, f"Debe ser una lista con al menos {min_items} elemento(s).")
    if len(node) > MAX_LIST_ITEMS:
        raise ConditionError(path, f"La lista supera {MAX_LIST_ITEMS} elementos.")
    return node


class _Validator:
    def __init__(self, fields: Fields) -> None:
        self.fields = fields
        self.nodes = 0

    def _visit(self, path: str) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise ConditionError(path, f"La condición supera {MAX_NODES} nodos.")

    def condition(self, node: Any, path: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise ConditionError(path, f"La condición supera {MAX_DEPTH} niveles.")
        self._visit(path)
        if not isinstance(node, dict) or not isinstance(node.get("operator"), str):
            raise ConditionError(path, "Debe ser un objeto con `operator`.")
        operator = node["operator"]

        if operator in LOGICAL_OPERATORS:
            _expect_keys(node, {"operator", "conditions"}, path)
            children = _expect_list(node["conditions"], f"{path}.conditions", min_items=1)
            for index, child in enumerate(children):
                self.condition(child, f"{path}.conditions.{index}", depth + 1)
            return

        if operator in COMPARISON_OPERATORS:
            _expect_keys(node, {"operator", "left", "right"}, path)
            left = self.value(node["left"], f"{path}.left")
            right = self.value(node["right"], f"{path}.right")
            if operator in ORDER_OPERATORS:
                if left != FieldType.NUMBER or right != FieldType.NUMBER:
                    raise ConditionError(path, f"`{operator}` compara números.")
            elif left != right:
                raise ConditionError(path, "`eq` compara valores del mismo tipo.")
            return

        if operator == "in":
            _expect_keys(node, {"operator", "left", "right"}, path)
            left = self.value(node["left"], f"{path}.left")
            if left == FieldType.BOOLEAN:
                raise ConditionError(f"{path}.left", "`in` compara números o textos.")
            options = _expect_list(node["right"], f"{path}.right", min_items=1)
            for index, option in enumerate(options):
                option_path = f"{path}.right.{index}"
                if _literal_type(option, option_path) != left:
                    raise ConditionError(option_path, f"Debe ser {_TYPE_LABELS[left]}.")
            return

        raise ConditionError(f"{path}.operator", f"Operador no permitido: {operator}.")

    def value(self, node: Any, path: str) -> FieldType:
        self._visit(path)
        literal = _literal_type(node, path)
        if literal is not None:
            return literal
        if not isinstance(node, dict):
            raise ConditionError(path, "Debe ser un literal o un objeto `field`, `sum` o `ratio`.")
        if "field" in node:
            _expect_keys(node, {"field"}, path)
            return self.field(node["field"], f"{path}.field")
        operator = node.get("operator")
        if operator == "sum":
            _expect_keys(node, {"operator", "fields"}, path)
            names = _expect_list(node["fields"], f"{path}.fields", min_items=2)
            for index, name in enumerate(names):
                self.numeric_field(name, f"{path}.fields.{index}")
            return FieldType.NUMBER
        if operator == "ratio":
            _expect_keys(node, {"operator", "numerator_field", "denominator_field"}, path)
            self.numeric_field(node["numerator_field"], f"{path}.numerator_field")
            self.numeric_field(node["denominator_field"], f"{path}.denominator_field")
            return FieldType.NUMBER
        raise ConditionError(path, "Debe ser un literal o un objeto `field`, `sum` o `ratio`.")

    def field(self, name: Any, path: str) -> FieldType:
        if not isinstance(name, str) or name not in self.fields:
            raise ConditionError(path, f"Campo no permitido: {name}.")
        return self.fields[name].type

    def numeric_field(self, name: Any, path: str) -> None:
        if self.field(name, path) != FieldType.NUMBER:
            raise ConditionError(path, f"El campo {name} no es numérico.")


def validate_condition(condition: Any, fields: Fields = RULE_FIELDS) -> None:
    """Valida la estructura, los operadores, los campos y los tipos de una condición."""
    _Validator(fields).condition(condition, "condition", depth=1)


def validate_context(context: Any, fields: Fields = RULE_FIELDS, path: str = "context") -> None:
    """Valida un contexto de evaluación: solo campos de la lista blanca, con su tipo.

    Un campo puede faltar o valer ``null``: la evaluación lo reporta como dato faltante.
    """
    _validate_context_node(context, "", fields, path)


def _validate_context_node(node: Any, prefix: str, fields: Fields, path: str) -> None:
    if not isinstance(node, dict):
        raise ConditionError(path, "Debe ser un objeto.")
    for key, value in node.items():
        name = f"{prefix}{key}"
        child_path = f"{path}.{key}"
        if name in fields:
            expected = fields[name].type
            if value is not None and _literal_type(value, child_path) != expected:
                raise ConditionError(child_path, f"Debe ser {_TYPE_LABELS[expected]}.")
        elif any(known.startswith(f"{name}.") for known in fields):
            if value is not None:
                _validate_context_node(value, f"{name}.", fields, child_path)
        else:
            raise ConditionError(child_path, "Campo no permitido.")


# --------------------------------------------------------------------------------------
# Evaluación
# --------------------------------------------------------------------------------------


def _to_decimal(value: int | float) -> Decimal:
    # `str` evita arrastrar el error binario del float: 0.7 es Decimal("0.7").
    return Decimal(str(value)) if isinstance(value, float) else Decimal(value)


class _Evaluation:
    def __init__(self, context: Mapping[str, Any], fields: Fields) -> None:
        self.context = context
        self.fields = fields
        self.unresolved: list[str] = []

    def _note(self, name: str) -> None:
        if name not in self.unresolved:
            self.unresolved.append(name)

    def field(self, name: str) -> Value | None:
        node: Any = self.context
        for part in name.split("."):
            if not isinstance(node, Mapping) or node.get(part) is None:
                self._note(name)
                return None
            node = node[part]
        expected = self.fields[name].type
        if _literal_type(node, f"context.{name}") != expected:
            raise ConditionError(f"context.{name}", f"Debe ser {_TYPE_LABELS[expected]}.")
        if expected == FieldType.NUMBER:
            return _to_decimal(node)
        return node  # Texto o booleano, ya comprobado arriba.

    def number(self, name: str) -> Decimal | None:
        value = self.field(name)
        assert value is None or isinstance(value, Decimal)
        return value

    def value(self, node: Any) -> Value | None:
        if isinstance(node, bool | str):
            return node
        if isinstance(node, int | float):
            return _to_decimal(node)
        if "field" in node:
            return self.field(node["field"])
        if node["operator"] == "sum":
            # Se evalúan todos para reportar todos los datos que faltan.
            terms = [self.number(name) for name in node["fields"]]
            if any(term is None for term in terms):
                return None
            return sum((term for term in terms if term is not None), Decimal(0))
        numerator = self.number(node["numerator_field"])
        denominator = self.number(node["denominator_field"])
        if numerator is None or denominator is None:
            return None
        if denominator == 0:
            self._note(node["denominator_field"])
            return None
        return numerator / denominator

    def condition(self, node: Mapping[str, Any]) -> bool | None:
        operator = node["operator"]
        if operator in LOGICAL_OPERATORS:
            results = [self.condition(child) for child in node["conditions"]]
            decisive = operator == "or"  # `or` se decide con un True; `and`, con un False.
            if any(result is decisive for result in results):
                return decisive
            if any(result is None for result in results):
                return None
            return not decisive

        left = self.value(node["left"])
        if operator == "in":
            if left is None:
                return None
            return left in [self.value(option) for option in node["right"]]

        right = self.value(node["right"])
        if left is None or right is None:
            return None
        if operator == "eq":
            return left == right
        # gte/lte: la validación garantiza números en ambos lados.
        assert isinstance(left, Decimal) and isinstance(right, Decimal)
        return left >= right if operator == "gte" else left <= right


def evaluate_condition(
    condition: Any, context: Mapping[str, Any], fields: Fields = RULE_FIELDS
) -> ConditionResult:
    """Evalúa una condición contra un contexto. Valida la condición antes de recorrerla."""
    validate_condition(condition, fields)
    evaluation = _Evaluation(context, fields)
    result = evaluation.condition(condition)
    if result is None:
        return ConditionResult(Outcome.MISSING_DATA, evaluation.unresolved)
    return ConditionResult(Outcome.PASSED if result else Outcome.FAILED)
