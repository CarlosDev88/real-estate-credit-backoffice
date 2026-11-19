"""Exposición de datos (OWASP API3:2023; ``specs/TAREA-seguridad.md``, Parte 4.6).

Las respuestas del broker y del comprador, campo por campo, ya las revisa la matriz
(``FORBIDDEN_FIELDS_BY_ACTOR``). Aquí: el log de peticiones y los errores que hablan de
datos de otro alcance.
"""

import logging

import pytest
from django.test import override_settings

from config.log_redaction import RedactObjectTokensFilter
from config.settings import base
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


def test_a_duplicate_document_is_an_accepted_409_without_the_other_client(world: World) -> None:
    """SEC-16, **aceptado** (decisión de producto, Fase B): el documento identifica a la
    persona y no se crea el mismo cliente una vez por broker; la unicidad es regla de
    negocio. El ``409`` confirma que la cédula existe, pero no trae nada del otro cliente
    (ni ``resource_id``, ni nombre, correo o teléfono) y SEC-10 limita cuántas veces se
    puede probar (120 escrituras por minuto). Esta prueba fija ese comportamiento: si
    cambia, hay que revisar la decisión en ``docs/SEGURIDAD.md``."""
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
    assert response.status_code == 409, response.content
    body = response.json()
    assert body["code"] == "DUPLICATE_CLIENT_DOCUMENT"
    assert set(body) == {"code", "message", "details", "request_id"}
    assert all("resource_id" not in detail for detail in body["details"])
    text = response.content.decode()
    for value in (client_a.pk, client_a.first_names, client_a.last_names, client_a.email):
        assert not value or str(value) not in text


@override_settings(AUTH_RATE_LIMITS={**base.AUTH_RATE_LIMITS, "general_write": "3/1m"})
def test_probing_documents_is_limited_by_the_general_write_limit(world: World) -> None:
    """La mitigación de SEC-16: probar cédulas una por una choca con el límite general de
    escrituras (SEC-10; aquí bajado a 3 por minuto)."""
    client = client_for(world, BROKER_OTHER)
    body = {"document_type_code": "CC", "first_names": "Otra", "last_names": "Persona"}
    statuses = [
        client.post(
            "/api/v1/clients", {**body, "document_number": f"80000000{i}"}, format="json"
        ).status_code
        for i in range(4)
    ]
    assert 429 not in statuses[:3]
    assert statuses[3] == 429
