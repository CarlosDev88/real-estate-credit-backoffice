"""Configuración e inventario (OWASP API8 y API9; ``specs/TAREA-seguridad.md``,
Partes 4.9 y 4.10)."""

import json
import re
from collections.abc import Sequence
from pathlib import Path

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIClient

from tests.security.requests import CONTRACT, contract_operations

pytestmark = pytest.mark.django_db

API_DOC = CONTRACT.parents[1] / "docs" / "API_REST_MVP_CREDITO.md"
if not API_DOC.exists():  # En el contenedor de pruebas, `docs/` puede no estar montado.
    API_DOC = Path("/docs/API_REST_MVP_CREDITO.md")
INFRASTRUCTURE = {"/health", "/ready", "/openapi.json", "/docs"}
# Fuera del contrato a propósito: la URL firmada del almacenamiento en disco (solo local).
EXCLUDED_FROM_CONTRACT = {"/api/v1/storage/objects/{token}"}


def test_health_and_ready_expose_nothing_internal(api_client: APIClient) -> None:
    assert api_client.get("/health").json() == {"status": "ok"}
    assert api_client.get("/ready").json() == {"status": "ready"}


@pytest.mark.xfail(strict=True, reason="SEC-18")
def test_django_admin_login_is_rate_limited(api_client: APIClient) -> None:
    """`/admin/` vive en el mismo host que la API y su login no tiene límite de intentos."""
    statuses = [
        api_client.post(
            "/admin/login/", {"username": "admin@example.com", "password": f"mala-{i}"}
        ).status_code
        for i in range(8)
    ]
    assert 429 in statuses


@pytest.mark.xfail(strict=True, reason="SEC-19")
@pytest.mark.parametrize("path", ["/openapi.json", "/docs"])
def test_api_schema_and_docs_need_a_session(api_client: APIClient, path: str) -> None:
    assert api_client.get(path).status_code in (401, 403, 404)


def _routes(patterns: Sequence[URLPattern | URLResolver], prefix: str = "") -> set[str]:
    found: set[str] = set()
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            found |= _routes(pattern.url_patterns, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern):
            found.add("/" + re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", prefix + str(pattern.pattern)))
    return found


def test_every_api_route_is_in_the_contract_and_back() -> None:
    routes = {r for r in _routes(get_resolver().url_patterns) if not r.startswith("/admin/")}
    contract = set(json.loads(CONTRACT.read_text(encoding="utf-8"))["paths"])
    assert routes - contract - INFRASTRUCTURE == EXCLUDED_FROM_CONTRACT
    assert contract - routes == set()


def _normalized(operation: str) -> str:
    method, path = operation.split(" ", 1)
    return f"{method} " + re.sub(r"\{[^}]+\}", "{}", path.removeprefix("/api/v1"))


@pytest.mark.xfail(strict=True, reason="SEC-20")
def test_every_documented_route_exists() -> None:
    if not API_DOC.exists():
        pytest.fail("No se encontró docs/API_REST_MVP_CREDITO.md")
    text = API_DOC.read_text(encoding="utf-8")
    documented = {
        _normalized(f"{method} {path.split('?')[0]}")
        for method, path in re.findall(
            r"\|\s*`(GET|POST|PUT|PATCH|DELETE)`\s*\|\s*`(/[^`]+)`", text
        )
    }
    documented = {op for op in documented if op.split(" ", 1)[1] not in INFRASTRUCTURE}
    implemented = {_normalized(op) for op in contract_operations()}
    assert sorted(documented - implemented) == []
