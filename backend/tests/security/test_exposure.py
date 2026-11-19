"""Exposición de datos (OWASP API3:2023; ``specs/TAREA-seguridad.md``, Parte 4.6).

Las respuestas del broker y del comprador, campo por campo, ya las revisa la matriz
(``FORBIDDEN_FIELDS_BY_ACTOR``). Aquí: el log de peticiones y los errores que hablan de
datos de otro alcance.
"""

import logging

import pytest

from config.log_redaction import RedactObjectTokensFilter
from tests.security.conftest import BROKER_OTHER, World
from tests.security.requests import client_for

pytestmark = pytest.mark.django_db


def _access_log_line(path: str) -> str:
    record = logging.LogRecord(
        "django.server",
        logging.INFO,
        __file__,
        1,
        '"%s" %s %s',
        (f"GET {path} HTTP/1.1", 200, 10),
        None,
    )
    RedactObjectTokensFilter().filter(record)
    return record.getMessage()


def test_signed_storage_urls_are_redacted_from_the_access_log() -> None:
    line = _access_log_line("/api/v1/storage/objects/.eJwTOKEN-INVENTADO:firma")
    assert "INVENTADO" not in line and "/storage/objects/***" in line


def test_search_terms_are_not_written_to_the_access_log() -> None:
    """RNF-16: los logs no llevan PII completa. La búsqueda viaja en la URL
    (`?search=<documento o nombre>`); el filtro la escribe como `***` (SEC-15)."""
    line = _access_log_line("/api/v1/clients?search=1234567890&page=1")
    assert "1234567890" not in line
    assert "/api/v1/clients?search=***&page=1" in line


@pytest.mark.parametrize(
    "query",
    [
        "email=laura%40example.com",
        "document_number=1234567890",
        "q=laura+gomez",
        "page=2&SEARCH=laura",
    ],
)
def test_other_personal_query_values_are_redacted(query: str) -> None:
    line = _access_log_line(f"/api/v1/applications?{query}")
    for secret in ("laura", "1234567890"):
        assert secret not in line.lower()
    assert "=***" in line


def test_other_query_values_are_kept() -> None:
    line = _access_log_line("/api/v1/applications?status=FILED&page_size=25")
    assert "status=FILED&page_size=25" in line


def test_any_log_message_is_redacted() -> None:
    record = logging.LogRecord(
        "django.request", logging.WARNING, __file__, 1, "Not Found: %s", ("/x?search=ana",), None
    )
    RedactObjectTokensFilter().filter(record)
    assert record.getMessage() == "Not Found: /x?search=***"


def test_duplicate_document_never_reveals_the_other_client(world: World) -> None:
    client_a = world.a.client
    response = client_for(world, BROKER_OTHER).post(
        "/api/v1/clients",
        {
            "document_type_code": client_a.document_type_item.code,
            "document_number": client_a.document_number,
            "first_names": "Otra",
            "last_names": "Persona",
            "email": "otra.persona@example.com",
        },
        format="json",
    )
    assert response.status_code == 409, response.content
    body = response.content.decode()
    for value in (client_a.pk, client_a.first_names, client_a.email, client_a.phone):
        assert str(value) not in body
    assert all("resource_id" not in detail for detail in response.json()["details"])


@pytest.mark.xfail(strict=True, reason="SEC-16")
def test_a_broker_cannot_tell_whether_a_document_is_already_registered(world: World) -> None:
    """El 409 por sí solo confirma que esa cédula ya está en el CRM, aunque sea de un
    cliente que el broker no ve."""
    client_a = world.a.client
    response = client_for(world, BROKER_OTHER).post(
        "/api/v1/clients",
        {
            "document_type_code": client_a.document_type_item.code,
            "document_number": client_a.document_number,
            "first_names": "Otra",
            "last_names": "Persona",
        },
        format="json",
    )
    assert response.status_code != 409
