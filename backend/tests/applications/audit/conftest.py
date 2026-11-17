"""Fixtures de la auditoría (módulo 14).

``no_forbidden_data`` corre después de cada prueba de esta carpeta: recorre todos los
eventos que quedaron y falla si alguno guarda algo prohibido (una clave prohibida, una URL
con consulta, un número largo que parezca un documento o un texto de más de 500).
"""

import re
from collections.abc import Iterator
from typing import Any

import pytest

from apps.audit.models import AuditEvent
from apps.audit.sanitize import MAX_TEXT_LENGTH, URL_WITH_QUERY, is_forbidden_key
from tests.applications.filings.conftest import (
    accept_consents,
    approve_stored,
    buyer_client,
    buyer_csrf_client,
    buyer_session,
    make_document_file,
    make_file_object,
    make_filing,
    make_link,
    make_session,
    make_slot,
    package_dossier,
    portal,
    waive_slot,
)

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
LONG_NUMBER = re.compile(r"\d{6,}")


def problems(value: Any, path: str = "metadata") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if is_forbidden_key(str(key)):
                found.append(f"{path}.{key}: clave prohibida")
            found += problems(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found += problems(item, f"{path}[{index}]")
    elif isinstance(value, str):
        if URL_WITH_QUERY.search(value):
            found.append(f"{path}: URL con consulta")
        if len(value) > MAX_TEXT_LENGTH:
            found.append(f"{path}: texto largo")
        if LONG_NUMBER.search(UUID.sub("", value)):
            found.append(f"{path}: número que parece un documento ({value})")
    return found


def all_events(request: pytest.FixtureRequest) -> list[AuditEvent]:
    """Los eventos de la conexión normal y, si la prueba la declara, los de ``audit``."""
    events = list(AuditEvent.objects.all())
    marker = request.node.get_closest_marker("django_db")
    if marker is not None and "audit" in (marker.kwargs.get("databases") or []):
        events += list(AuditEvent.objects.using("audit").all())
    return events


@pytest.fixture(autouse=True)
def no_forbidden_data(db: None, request: pytest.FixtureRequest) -> Iterator[None]:
    """Depende de ``db`` para revisar antes de que se deshaga la transacción de la prueba."""
    yield
    found = [
        f"{event.action}: {problem}"
        for event in all_events(request)
        for problem in problems(event.metadata)
    ]
    assert not found, found


__all__ = [
    "accept_consents",
    "approve_stored",
    "buyer_client",
    "buyer_csrf_client",
    "buyer_session",
    "make_document_file",
    "make_file_object",
    "make_filing",
    "make_link",
    "make_session",
    "make_slot",
    "package_dossier",
    "portal",
    "waive_slot",
]
