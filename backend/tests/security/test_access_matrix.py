"""Matriz de acceso: cada operación del contrato contra cada actor (BOLA / BFLA).

``specs/TAREA-seguridad.md``, Parte 3.3. Lo esperado está en ``access_matrix.py``; el
mundo, en ``conftest.py``. Cada caso corre en su propia transacción (se revierte).

- Escrituras permitidas: basta con que no sea 401/403/404; el efecto lo prueban los
  módulos.
- En los ``ALLOW`` del broker y del comprador, además, la respuesta no trae campos
  prohibidos (``FORBIDDEN_FIELDS_BY_ACTOR``) y el documento llega enmascarado al broker.
- Una brecha real va en ``KNOWN_GAPS`` y queda ``xfail(strict=True, reason="SEC-NN")``.
"""

from typing import Any

import pytest

from tests.security import access_matrix as m
from tests.security.conftest import World
from tests.security.requests import client_for, contract_operations, send, url_for

pytestmark = pytest.mark.django_db


def _cases() -> list[Any]:
    cases = []
    for operation in m.MATRIX:
        for actor in m.ACTORS:
            marks = []
            gap = m.KNOWN_GAPS.get(operation, {}).get(actor)
            if gap:
                marks.append(pytest.mark.xfail(strict=True, reason=gap))
            cases.append(pytest.param(operation, actor, marks=marks, id=f"{operation}-{actor}"))
    return cases


def _walk(value: Any, path: str = "") -> list[tuple[str, str, Any]]:
    """(ruta, clave, valor) de cada clave del JSON, a cualquier profundidad."""
    found: list[tuple[str, str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.append((f"{path}.{key}", key, item))
            found.extend(_walk(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_walk(item, f"{path}[{index}]"))
    return found


def _field_problems(operation: str, actor: str, body: Any) -> list[str]:
    forbidden = m.FORBIDDEN_FIELDS_BY_ACTOR.get(actor, frozenset())
    forbidden -= m.FIELD_EXCEPTIONS.get(operation, frozenset())
    masked = m.MASKED_FIELDS_BY_ACTOR.get(actor, frozenset())
    problems = []
    for path, key, value in _walk(body):
        if key in forbidden:
            problems.append(f"campo prohibido {path}")
        if (
            key in masked
            and isinstance(value, str)
            and value
            and not value.startswith(m.MASK_PREFIX)
        ):
            problems.append(f"documento sin enmascarar en {path}")
    return problems


def test_matrix_covers_every_operation_of_the_contract() -> None:
    """El inventario (spec §3.1) es exactamente el contrato: ni de más ni de menos."""
    assert sorted(m.MATRIX) == sorted(contract_operations())
    for operation, pattern in m.MATRIX.items():
        assert len(pattern) == len(m.ACTORS) and set(pattern) <= set(m.LETTERS), operation


@pytest.mark.parametrize(("operation", "actor"), _cases())
def test_access(world: World, operation: str, actor: str) -> None:
    expected = m.expected(operation, actor)
    response = send(client_for(world, actor), operation, url_for(world, operation))

    assert m.status_matches(expected, response.status_code), (
        f"{operation} como {actor}: se esperaba {expected} y llegó {response.status_code} "
        f"{response.content[:300]!r}"
    )
    is_json = response.get("Content-Type", "").startswith("application/json")
    if expected == m.ALLOW and 200 <= response.status_code < 300 and is_json:
        problems = _field_problems(operation, actor, response.json())
        assert not problems, f"{operation} como {actor}: {problems}"
