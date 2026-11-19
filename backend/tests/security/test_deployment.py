"""Configuración de despliegue (Fase B, Parte 3).

- SEC-01/02: ``config.settings.production`` (``DEBUG`` fijo, HTTPS, cookies ``Secure``) y
  los puntos de entrada que la usan por defecto.
- SEC-03: el *system check* de las claves (error sin ``DEBUG``, aviso con ``DEBUG``).
- SEC-05: el compose publica los puertos solo en ``127.0.0.1``.
- SEC-06: la imagen fija la base por digest y ``pip``, y su etapa ``production`` corre
  gunicorn sin pruebas ni scripts.
- SEC-13: el contrato documenta 400/404/428 con el esquema de error común.
- SEC-21: las respuestas por rol son `anyOf` (una página vacía valía para las dos formas).
"""

import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from django.core.checks import Error, Warning
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import override_settings

from apps.identity.checks import check_signing_keys
from tests.security.requests import CONTRACT

BACKEND = Path(__file__).resolve().parents[2]
STRONG_SECRET = "s3cr3t-" + "abcdefghijklmnopqrstuvwxyz0123456789-ABCDEFGHIJ"
STRONG_JWT = "jwt-key-" + "x1y2z3" * 6


# --- SEC-01 y SEC-02: production.py ------------------------------------------------------


@pytest.fixture(scope="module")
def production() -> Any:
    return importlib.import_module("config.settings.production")


def test_production_never_runs_with_debug(production: Any) -> None:
    assert production.DEBUG is False
    assert production.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend"
    renderers = production.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"]
    assert renderers == ["rest_framework.renderers.JSONRenderer"]


def test_production_hardens_https(production: Any) -> None:
    assert production.SECURE_HSTS_SECONDS >= 3600
    assert production.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert production.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert production.SECURE_SSL_REDIRECT is True
    assert production.SESSION_COOKIE_SECURE is True
    assert production.CSRF_COOKIE_SECURE is True
    assert production.AUTH_COOKIE_SECURE is True


@pytest.mark.parametrize("entry_point", ["config/wsgi.py", "config/asgi.py", "config/celery.py"])
def test_entry_points_default_to_production(entry_point: str) -> None:
    source = (BACKEND / entry_point).read_text(encoding="utf-8")
    assert 'setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")' in source


def test_manage_py_keeps_local() -> None:
    source = (BACKEND / "manage.py").read_text(encoding="utf-8")
    assert 'setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")' in source


# --- SEC-03: claves ----------------------------------------------------------------------


def _ids(messages: list[Any]) -> list[str]:
    return sorted(message.id for message in messages)


@override_settings(DEBUG=False, AUTH_JWT_SIGNING_KEY="k" * 31, SECRET_KEY="a" * 49)
def test_weak_keys_are_errors_without_debug() -> None:
    messages = check_signing_keys()
    assert _ids(messages) == ["identity.E001", "identity.E002"]
    assert all(isinstance(message, Error) for message in messages)
    with pytest.raises(SystemCheckError):
        call_command("check")


@override_settings(DEBUG=True, AUTH_JWT_SIGNING_KEY="k" * 31, SECRET_KEY="a" * 49)
def test_weak_keys_are_warnings_with_debug() -> None:
    messages = check_signing_keys()
    assert _ids(messages) == ["identity.W001", "identity.W002"]
    assert all(isinstance(message, Warning) for message in messages)


@pytest.mark.parametrize(
    "secret_key",
    ["a" * 60, "abcd" * 15, "django-insecure-" + "abcdefghijklmnopqrstuvwxyz0123456789"],
)
@override_settings(DEBUG=False, AUTH_JWT_SIGNING_KEY=STRONG_JWT)
def test_secret_key_rule_is_the_one_of_django(secret_key: str) -> None:
    """Menos de 5 caracteres distintos o el prefijo ``django-insecure-`` también fallan."""
    with override_settings(SECRET_KEY=secret_key):
        assert _ids(check_signing_keys()) == ["identity.E002"]


@override_settings(DEBUG=False, AUTH_JWT_SIGNING_KEY=STRONG_JWT, SECRET_KEY=STRONG_SECRET)
def test_strong_keys_pass() -> None:
    assert check_signing_keys() == []


def test_the_jwt_key_is_measured_in_bytes() -> None:
    """31 caracteres con una tilde son 32 bytes: pasa."""
    with override_settings(
        DEBUG=False, AUTH_JWT_SIGNING_KEY="ñ" + "k" * 30, SECRET_KEY=STRONG_SECRET
    ):
        assert check_signing_keys() == []


# --- SEC-05: compose ---------------------------------------------------------------------


def test_compose_publishes_ports_only_on_localhost() -> None:
    compose = (BACKEND / "docker-compose.yml").read_text(encoding="utf-8")
    published = re.findall(r'^\s*-\s*"([^"]*:\d+)"\s*$', compose, flags=re.MULTILINE)
    published = [port for port in published if re.search(r":\d+$", port) and "HOST_PORT" in port]
    assert len(published) == 4
    assert all(port.startswith("127.0.0.1:") for port in published), published


def test_compose_pins_the_settings_module_of_every_django_service() -> None:
    compose = (BACKEND / "docker-compose.yml").read_text(encoding="utf-8")
    assert compose.count("dockerfile: Dockerfile") == 3
    assert compose.count("target: dev") == 3
    assert compose.count("DJANGO_SETTINGS_MODULE: config.settings.local") == 3


# --- SEC-06: imagen ----------------------------------------------------------------------


def test_the_image_is_reproducible_and_production_runs_gunicorn() -> None:
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^FROM python:3\.11-slim@sha256:[0-9a-f]{64} AS base$", dockerfile, re.M)
    assert re.search(r"pip install pip==\d+\.\d+", dockerfile)
    assert "FROM base AS dev" in dockerfile and "FROM base AS production" in dockerfile
    production = dockerfile.split("FROM base AS production", 1)[1]
    assert "ENV DJANGO_SETTINGS_MODULE=config.settings.production" in production
    assert "gunicorn -c config/gunicorn.py config.wsgi" in production
    assert "manage.py check" in production
    assert "USER app" in production
    copied = re.findall(r"^COPY --chown=app:app (\S+)", production, re.M)
    assert copied == ["manage.py", "config", "apps"]


def test_gunicorn_takes_its_workers_from_the_environment_and_has_no_access_log() -> None:
    config = (BACKEND / "config" / "gunicorn.py").read_text(encoding="utf-8")
    assert 'os.environ.get("GUNICORN_WORKERS"' in config
    assert re.search(r"^accesslog = None$", config, re.M)


# --- SEC-13: contrato ----------------------------------------------------------------------

METHODS = ("get", "put", "post", "patch", "delete")


def _operations() -> list[tuple[str, str, dict[str, Any]]]:
    spec = json.loads(CONTRACT.read_text(encoding="utf-8"))
    return [
        (method, path, item[method])
        for path, item in spec["paths"].items()
        for method in METHODS
        if method in item
    ]


def _is_error(response: dict[str, Any]) -> bool:
    schema = response.get("content", {}).get("application/json", {}).get("schema", {})
    return schema == {"$ref": "#/components/schemas/Error"}


def _if_match_required(operation: dict[str, Any]) -> bool:
    return any(
        p.get("in") == "header" and p.get("name", "").lower() == "if-match" and p.get("required")
        for p in operation.get("parameters", [])
    )


def test_every_operation_documents_its_common_errors() -> None:
    missing = []
    for method, path, operation in _operations():
        responses = operation["responses"]
        expected = []
        query = [p["name"] for p in operation.get("parameters", []) if p.get("in") == "query"]
        if "requestBody" in operation or query:
            expected.append("400")
        if "{" in path or "page" in query:
            expected.append("404")
        if _if_match_required(operation):
            expected.append("428")
        for code in expected:
            if code not in responses or not _is_error(responses[code]):
                missing.append(f"{method.upper()} {path} {code}")
        if "428" in responses and not _if_match_required(operation):
            missing.append(f"{method.upper()} {path} If-Match")
    assert missing == []


def test_available_actions_is_a_plain_list_in_the_contract() -> None:
    operation = next(
        op
        for method, path, op in _operations()
        if method == "get" and path.endswith("/available-actions")
    )
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["type"] == "array"
    assert {p["name"] for p in operation.get("parameters", [])} == {"application_id"}


@pytest.mark.parametrize(
    ("schema", "field"),
    [
        ("Client", "email"),
        ("ClientDetail", "email"),
        ("BrokerClient", "email"),
        ("BuyerProfile", "email"),
        ("Partner", "contact_email"),
        ("PartnerDetail", "contact_email"),
    ],
)
def test_emails_that_can_be_blank_have_no_email_format(schema: str, field: str) -> None:
    """El modelo admite vacío (``EmailField(blank=True)``) y ``""`` no cumple
    ``format: email``: un cliente sin correo hacía que la respuesta no validara."""
    spec = json.loads(CONTRACT.read_text(encoding="utf-8"))
    prop = spec["components"]["schemas"][schema]["properties"][field]
    assert prop["type"] == "string"
    assert "format" not in prop


def test_role_dependent_responses_use_any_of() -> None:
    """SEC-21: una página vacía de ``GET /applications`` (o de clientes u oportunidades)
    valía para las dos formas del ``oneOf`` (asesor y broker), y ``oneOf`` exige exactamente
    una: la respuesta no validaba. Con ``anyOf`` valida."""
    spec = json.loads(CONTRACT.read_text(encoding="utf-8"))
    by_role = {n: s for n, s in spec["components"]["schemas"].items() if n.endswith("ByRole")}
    assert len(by_role) >= 7
    assert all("anyOf" in s and "oneOf" not in s for s in by_role.values()), sorted(by_role)
