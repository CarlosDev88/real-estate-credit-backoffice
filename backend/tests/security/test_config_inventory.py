"""Configuración e inventario (OWASP API8 y API9; ``specs/TAREA-seguridad.md``,
Partes 4.9 y 4.10)."""

import json
import re
from collections.abc import Sequence
from pathlib import Path

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIClient

from config.settings import base
from tests.helpers import urls_with
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


def test_django_admin_is_not_published_by_default(api_client: APIClient) -> None:
    """Sin `DEBUG` ni `ADMIN_ENABLED`, `/admin/` no existe (SEC-18)."""
    assert api_client.get("/admin/").status_code == 404
    assert api_client.post("/admin/login/", {"username": "a", "password": "b"}).status_code == 404


def test_django_admin_login_is_rate_limited(api_client: APIClient) -> None:
    """Encendido (y en otra ruta), su login tiene un límite por IP: 10 intentos en 15 min."""
    with urls_with(ADMIN_ENABLED=True, ADMIN_URL_PATH="gestion-interna/"):
        assert api_client.get("/admin/login/").status_code == 404
        statuses = [
            api_client.post(
                "/gestion-interna/login/",
                {"username": "admin@example.com", "password": f"mala-{i}"},
            ).status_code
            for i in range(11)
        ]
        assert statuses[:10] == [200] * 10  # El formulario con el error.
        assert statuses[10] == 429
        # Otra IP no está afectada.
        other = api_client.post(
            "/gestion-interna/login/",
            {"username": "admin@example.com", "password": "mala"},
            REMOTE_ADDR="10.0.9.1",
        )
        assert other.status_code == 200


def test_the_admin_login_rate_is_the_agreed_one() -> None:
    assert base.AUTH_RATE_LIMITS["admin_login"] == "10/15m"
    assert (base.ADMIN_ENABLED, base.ADMIN_URL_PATH, base.API_DOCS_PUBLIC) == (
        False,
        "admin/",
        False,
    )


@pytest.mark.parametrize("path", ["/openapi.json", "/docs"])
def test_api_schema_and_docs_need_a_session(api_client: APIClient, path: str) -> None:
    """Sin `DEBUG` ni `API_DOCS_PUBLIC`, no se publican (SEC-19)."""
    assert api_client.get(path).status_code in (401, 403, 404)


@pytest.mark.parametrize("path", ["/openapi.json", "/docs"])
def test_api_schema_and_docs_can_be_published_on_purpose(api_client: APIClient, path: str) -> None:
    with urls_with(API_DOCS_PUBLIC=True):
        assert api_client.get(path).status_code == 200


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
