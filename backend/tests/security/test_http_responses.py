"""Respuestas HTTP de la API (Fase B, Parte 2).

- SEC-07: ``OPTIONS`` ya no describe campos (``DEFAULT_METADATA_CLASS = None``): ninguna
  ruta da 5xx, con o sin sesión, y el *preflight* de CORS sigue funcionando.
- SEC-08: ``Cache-Control: no-store`` y ``Vary: Cookie`` en ``/api/v1/`` salvo que la
  vista ponga su propio ``Cache-Control``.
- SEC-11: un cuerpo de más de 2,5 MB es ``413 PAYLOAD_TOO_LARGE``, no un 500.
- SEC-12: las rutas inexistentes de ``/api/`` responden el formato de error de la API.
"""

import json
from typing import Any

import pytest
from django.test import RequestFactory
from rest_framework.test import APIClient

from config.views import server_error
from tests.helpers import LOGIN_URL, ME_URL, assert_error
from tests.security.conftest import ADMIN, ADVISOR_OWNER, ANON, World
from tests.security.requests import CONTRACT, client_for, url_for

pytestmark = pytest.mark.django_db

API = "/api/v1"
FRONTEND = "http://localhost:3000"


def _vary(response: Any) -> set[str]:
    return {value.strip().lower() for value in response.get("Vary", "").split(",") if value}


# --- SEC-08: caché ---------------------------------------------------------------------


def test_personal_data_responses_are_not_stored(world: World) -> None:
    client = client_for(world, ADVISOR_OWNER)
    for url in (
        f"{API}/clients",
        f"{API}/clients/{world.a.client.pk}",
        ME_URL,
        f"{API}/applications/{world.a.application.pk}",
    ):
        response = client.get(url)
        assert response.status_code == 200, (url, response.content[:200])
        assert response["Cache-Control"] == "no-store", url
        assert "cookie" in _vary(response), url


def test_the_reports_csv_is_not_stored(world: World) -> None:
    response = client_for(world, ADMIN).get(f"{API}/reports/applications.csv")
    assert response.status_code == 200, response.content[:200]
    assert response["Content-Type"].startswith("text/csv")
    assert response["Cache-Control"] == "no-store"
    assert "cookie" in _vary(response)


def test_errors_are_not_stored_either(api_client: APIClient) -> None:
    response = api_client.get(ME_URL)
    assert response.status_code == 401
    assert response["Cache-Control"] == "no-store"


def test_a_view_with_its_own_cache_control_keeps_it(world: World) -> None:
    """Los catálogos con ETag se revalidan (``private, no-cache``); el middleware no los
    pisa, pero sí agrega ``Vary: Cookie``."""
    response = client_for(world, ADVISOR_OWNER).get(f"{API}/metadata/catalogs/municipality")
    assert response.status_code == 200, response.content[:200]
    assert response["Cache-Control"] == "private, no-cache"
    assert response.has_header("ETag")
    assert "cookie" in _vary(response)


def test_outside_the_api_nothing_changes(api_client: APIClient) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200
    assert not response.has_header("Cache-Control")


# --- SEC-07: OPTIONS ---------------------------------------------------------------------


def _contract_paths() -> list[str]:
    return sorted(json.loads(CONTRACT.read_text(encoding="utf-8"))["paths"])


@pytest.mark.parametrize("actor", [ANON, ADMIN])
def test_options_never_answers_5xx(world: World, actor: str) -> None:
    client = client_for(world, actor)
    failures = []
    for path in _contract_paths():
        response = client.options(url_for(world, f"OPTIONS {path}"))
        if response.status_code >= 500:
            failures.append((path, response.status_code))
    assert failures == []


def test_options_does_not_describe_the_view(world: World) -> None:
    """Antes respondía el nombre de la vista, los *renderers* y los campos (o un 500)."""
    response = client_for(world, ADMIN).options(f"{API}/clients")
    assert_error(response, 405, "METHOD_NOT_ALLOWED")


def test_cors_preflight_still_works_from_the_frontend(api_client: APIClient) -> None:
    for path, method in ((LOGIN_URL, "POST"), (f"{API}/invitations/accept", "POST")):
        response = api_client.options(
            path,
            HTTP_ORIGIN=FRONTEND,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD=method,
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-csrftoken",
        )
        assert response.status_code == 200, (path, response.status_code)
        assert response["Access-Control-Allow-Origin"] == FRONTEND
        assert response["Access-Control-Allow-Credentials"] == "true"
        assert "x-csrftoken" in response["Access-Control-Allow-Headers"].lower()


# --- SEC-11: cuerpo demasiado grande -------------------------------------------------------

THREE_MEGABYTES = "x" * (3 * 1024 * 1024)


def test_a_large_body_without_session_is_413(api_client: APIClient) -> None:
    response = api_client.post(
        LOGIN_URL, {"email": "a@example.com", "password": THREE_MEGABYTES}, format="json"
    )
    body = assert_error(response, 413, "PAYLOAD_TOO_LARGE")
    assert body["message"] == "El cuerpo de la solicitud es demasiado grande."


def test_a_large_body_with_session_is_413(world: World) -> None:
    response = client_for(world, ADVISOR_OWNER).post(
        f"{API}/clients", {"first_names": THREE_MEGABYTES}, format="json"
    )
    assert_error(response, 413, "PAYLOAD_TOO_LARGE")


# --- SEC-12: rutas inexistentes ----------------------------------------------------------


@pytest.mark.parametrize(
    "path", [f"{API}/no-existe", f"{API}/applications/abc", f"{API}/clients/123/addresses"]
)
def test_unknown_api_routes_answer_the_api_error_format(api_client: APIClient, path: str) -> None:
    response = api_client.get(path, HTTP_X_REQUEST_ID="sec12-request-0001")
    assert response["Content-Type"] == "application/json"
    body = assert_error(response, 404, "RESOURCE_NOT_FOUND")
    assert body["request_id"] == "sec12-request-0001"


def test_unknown_routes_outside_the_api_keep_the_django_page(api_client: APIClient) -> None:
    response = api_client.get("/no-existe")
    assert response.status_code == 404
    assert response["Content-Type"].startswith("text/html")


def test_server_errors_in_the_api_answer_the_api_error_format() -> None:
    response = server_error(RequestFactory().get(f"{API}/clients"))
    assert response.status_code == 500
    body = json.loads(response.content)
    assert body["code"] == "INTERNAL_ERROR"
    assert set(body) == {"code", "message", "details", "request_id"}


def test_server_errors_outside_the_api_keep_the_django_page() -> None:
    response = server_error(RequestFactory().get("/otra"))
    assert response.status_code == 500
    assert response["Content-Type"].startswith("text/html")
