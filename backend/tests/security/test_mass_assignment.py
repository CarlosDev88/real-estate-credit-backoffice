"""Asignación masiva (OWASP API3:2023; ``specs/TAREA-seguridad.md``, Parte 4.5).

A cada escritura del contrato con cuerpo se le mandan los campos sensibles que su
esquema de entrada **no** declara (``status``, ``version``, ``is_superuser``, ``roles``,
montos, ``scan_status``, ``paid_at``…), como el actor que la puede usar según la matriz.
La API debe rechazarlos con ``400 UNKNOWN_FIELD`` (``config/serializers.StrictSerializer``)
o, como mínimo, ignorarlos; nunca aplicarlos.
"""

import json
from typing import Any

import pytest

from tests.security import access_matrix as m
from tests.security.conftest import World
from tests.security.requests import CONTRACT, MULTIPART_OPERATIONS, client_for, send, url_for

pytestmark = pytest.mark.django_db

SENSITIVE: dict[str, Any] = {
    "status": "APPROVED",
    "version": 999,
    "assigned_advisor": "00000000-0000-0000-0000-000000000001",
    "assigned_advisor_id": "00000000-0000-0000-0000-000000000001",
    "is_active": False,
    "is_superuser": True,
    "is_staff": True,
    "roles": ["ADMIN"],
    "role_codes": ["ADMIN"],
    "permissions": ["users.create"],
    "client_id": "00000000-0000-0000-0000-000000000002",
    "application_id": "00000000-0000-0000-0000-000000000003",
    "approved_amount_cop": 1,
    "disbursed_amount_cop": 1,
    "requested_amount_cop": 1,
    "public_status": "APPROVED",
    "review_status": "APPROVED",
    "scan_status": "CLEAN",
    "paid_at": "2020-01-01",
    "created_by": "00000000-0000-0000-0000-000000000004",
    "deleted_at": None,
    "password": "Otra-Clave-Larga-2030",
}


def _write_operations() -> list[tuple[str, set[str]]]:
    spec = json.loads(CONTRACT.read_text(encoding="utf-8"))
    schemas = spec["components"]["schemas"]
    found = []
    for path, item in spec["paths"].items():
        for method in ("post", "put", "patch"):
            content = item.get(method, {}).get("requestBody", {}).get("content", {})
            media = content.get("application/json") or content.get("multipart/form-data")
            if not media:
                continue
            name = media["schema"]["$ref"].rsplit("/", 1)[-1]
            found.append((f"{method.upper()} {path}", set(schemas[name].get("properties", {}))))
    return found


WRITES = _write_operations()


def _actor(operation: str) -> str | None:
    allowed = [a for a in m.ACTORS if a != "anon" and m.expected(operation, a) == m.ALLOW]
    return allowed[0] if allowed else None


def _unknown_fields(response: Any) -> set[str]:
    try:
        details = response.json().get("details", [])
    except ValueError:
        return set()
    return {d.get("field") for d in details if d.get("code") == "UNKNOWN_FIELD"}


@pytest.mark.parametrize(("operation", "declared"), WRITES, ids=[op for op, _ in WRITES])
def test_undeclared_sensitive_fields_are_rejected(
    world: World, operation: str, declared: set[str]
) -> None:
    actor = _actor(operation)
    if actor is None:
        pytest.skip("ningún actor puede usar la operación")
    extra = {key: value for key, value in SENSITIVE.items() if key not in declared}
    if operation in MULTIPART_OPERATIONS:
        extra = {key: str(value) for key, value in extra.items() if value is not None}
    response = send(client_for(world, actor), operation, url_for(world, operation), extra)

    assert not 200 <= response.status_code < 300, (
        f"{operation} como {actor} aceptó campos no declarados: {response.content[:300]!r}"
    )
    if response.status_code == 400:
        assert _unknown_fields(response) >= set(extra), response.content[:400]
