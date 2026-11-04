"""Comportamiento transversal: request_id, formato de error y endpoints públicos."""

import uuid

import pytest

from tests.helpers import ME_URL, assert_error

pytestmark = pytest.mark.django_db


def test_every_response_has_a_generated_request_id(api_client):
    response = api_client.get("/health")
    assert uuid.UUID(response["X-Request-ID"])


def test_valid_incoming_request_id_is_preserved(api_client):
    response = api_client.get("/health", HTTP_X_REQUEST_ID="frontend-req-12345")
    assert response["X-Request-ID"] == "frontend-req-12345"


def test_unsafe_incoming_request_id_is_replaced(api_client):
    response = api_client.get("/health", HTTP_X_REQUEST_ID="malo\r\nSet-Cookie: x=1")
    assert uuid.UUID(response["X-Request-ID"])


def test_error_body_includes_the_request_id(api_client):
    response = api_client.get(ME_URL, HTTP_X_REQUEST_ID="frontend-req-12345")
    body = assert_error(response, 401, "NOT_AUTHENTICATED")
    assert body["request_id"] == "frontend-req-12345"


def test_unknown_api_route_returns_404(api_client):
    assert api_client.get("/api/v1/no-existe").status_code == 404


def test_openapi_schema_is_public_and_documents_auth(api_client):
    response = api_client.get("/openapi.json", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in (
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/auth/password-reset-requests",
        "/api/v1/auth/password-resets/confirm",
        "/api/v1/auth/change-password",
    ):
        assert path in paths, path
