"""Inyección (``specs/TAREA-seguridad.md``, Parte 4.4).

- SQL: el código no arma SQL con texto del usuario (revisado a mano: solo
  ``SELECT nextval(%s)`` con un parámetro constante y el ``cursor()`` del chequeo de
  salud; ningún ``raw``, ``extra``, ``RawSQL`` ni filtros con ``**query_params``).
- ``?ordering=``: todos los listados que lo aceptan rechazan campos fuera de su lista,
  incluidos los sensibles y los de relaciones.
- CSV: el reporte neutraliza fórmulas.
- Correo: la plantilla HTML escapa los datos del cliente.
- ``X-Request-ID``: solo se acepta un identificador corto y sin caracteres de control.
"""

import csv
import io
import json
import re
import uuid
from typing import Any

import pytest
from django.template.loader import render_to_string
from django.utils import timezone

from apps.crm.models import Client
from tests.security import access_matrix as m
from tests.security.conftest import ADMIN, World
from tests.security.requests import CONTRACT, client_for, url_for

pytestmark = pytest.mark.django_db


def _ordering_operations() -> list[str]:
    spec = json.loads(CONTRACT.read_text(encoding="utf-8"))
    return [
        f"GET {path}"
        for path, item in spec["paths"].items()
        if "get" in item
        and any(param.get("name") == "ordering" for param in item["get"].get("parameters", []))
    ]


FORBIDDEN_ORDERING = [
    "password",
    "-password",
    "assigned_advisor__password",
    "created_by__password",
    "user__password",
    "client__document_number",
    "token_hash",
    "id,password",
]


@pytest.mark.parametrize("operation", _ordering_operations())
def test_ordering_only_accepts_declared_fields(world: World, operation: str) -> None:
    # El primer actor que tiene acceso según la matriz (el broker en su listado propio).
    actor = next(a for a in m.ACTORS if m.expected(operation, a) == m.ALLOW and a != "anon")
    client = client_for(world, actor)
    url = url_for(world, operation)
    leaked = {}
    for value in FORBIDDEN_ORDERING:
        response = client.get(url, {"ordering": value})
        if response.status_code != 400:
            leaked[value] = response.status_code
    assert leaked == {}


def test_report_csv_neutralizes_formulas(world: World) -> None:
    Client.objects.filter(pk=world.a.client.pk).update(
        first_names='=HYPERLINK("http://evil.example")', last_names="+SUM(A1:A2)"
    )
    today = timezone.localdate()
    response = client_for(world, ADMIN).get(
        "/api/v1/reports/applications.csv",
        {"date_from": (today.replace(day=1)).isoformat(), "date_to": today.isoformat()},
    )
    assert response.status_code == 200, response.content[:200]
    raw = (
        b"".join(getattr(response, "streaming_content", []))
        if response.streaming
        else response.content
    )
    text = raw.decode("utf-8-sig")
    cells = [cell for row in csv.reader(io.StringIO(text)) for cell in row]
    dangerous = [cell for cell in cells if cell[:1] in ("=", "+", "-", "@", "\t", "\r")]
    assert dangerous == []
    assert any("HYPERLINK" in cell for cell in cells), "el cliente del lado A no salió en el CSV"


def test_notification_email_escapes_client_data() -> None:
    context: dict[str, Any] = {
        "first_names": '<script>alert("x")</script>',
        "title": "<img src=x onerror=alert(1)>",
        "message": "Línea 1\n<b>Línea 2</b>",
        "portal_line": "Entra a tu portal.",
    }
    html = render_to_string("notifications/email.html", context)
    assert "<script>" not in html and "<img" not in html and "<b>" not in html
    assert "&lt;script&gt;" in html and "<br>" in html


@pytest.mark.parametrize(
    "incoming",
    [
        "abc\r\nSet-Cookie: x=1",
        "abc\nX-Injected: 1",
        "a" * 65,
        "corto",
        "../../etc/passwd",
        "<script>",
    ],
    ids=["crlf", "lf", "65-caracteres", "corto", "ruta", "html"],
)
def test_request_id_from_the_client_is_validated(world: World, incoming: str) -> None:
    response = client_for(world, ADMIN).get("/api/v1/auth/me", HTTP_X_REQUEST_ID=incoming)
    returned = response["X-Request-ID"]
    assert returned != incoming
    assert uuid.UUID(returned)


def test_a_valid_request_id_is_kept(world: World) -> None:
    response = client_for(world, ADMIN).get("/api/v1/auth/me", HTTP_X_REQUEST_ID="trace-1234.abc_D")
    assert response["X-Request-ID"] == "trace-1234.abc_D"
    assert re.fullmatch(r"[A-Za-z0-9._-]{8,64}", response["X-Request-ID"])
