"""Consumo de recursos (OWASP API4:2023; ``specs/TAREA-seguridad.md``, Parte 4.8).

- ``page_size`` tiene tope (100) en **todos** los listados paginados.
- Reportes y dashboard: rango máximo de 366 días.
- Textos libres: todo campo de texto de las escrituras tiene longitud máxima.
- Exportaciones simultáneas (3 por usuario): ya lo prueba
  ``tests/reporting/test_export_jobs.py::test_a_fourth_active_export_is_rejected``.
"""

import bz2
import json
from typing import Any

import pytest
import rest_framework
from django.utils import timezone

from tests.security import access_matrix as m
from tests.security.conftest import ADMIN, ADVISOR_OWNER, BROKER_OWNER, BUYER_OWNER, World
from tests.security.requests import CONTRACT, client_for, send, url_for

pytestmark = pytest.mark.django_db

MEGABYTE = "x" * (1024 * 1024)


def _paginated_operations() -> list[str]:
    spec = json.loads(CONTRACT.read_text(encoding="utf-8"))
    return [
        f"GET {path}"
        for path, item in spec["paths"].items()
        if "get" in item
        and any(param.get("name") == "page_size" for param in item["get"].get("parameters", []))
    ]


@pytest.mark.parametrize("operation", _paginated_operations())
def test_page_size_is_capped(world: World, operation: str) -> None:
    actor = next(a for a in m.ACTORS if a != "anon" and m.expected(operation, a) == m.ALLOW)
    response = client_for(world, actor).get(url_for(world, operation), {"page_size": 100000})
    assert response.status_code in (200, 400), response.content[:200]
    if response.status_code == 200:
        body = response.json()
        if isinstance(body, list):
            # `available-actions` responde una lista aunque el contrato diga página (SEC-13).
            assert len(body) <= 100
            return
        assert body["page_size"] <= 100
        assert len(body["items"]) <= 100


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/reports/applications",
        "/api/v1/reports/applications.csv",
        "/api/v1/reports/funnel",
        "/api/v1/dashboard/summary",
        "/api/v1/dashboard/funnel",
        "/api/v1/dashboard/bank-results",
        "/api/v1/dashboard/workload",
    ],
)
def test_report_range_is_capped(world: World, path: str) -> None:
    today = timezone.localdate()
    response = client_for(world, ADMIN).get(
        path, {"date_from": "2000-01-01", "date_to": today.isoformat()}
    )
    assert response.status_code == 400, response.content[:200]


def _text_cases(world: World) -> list[tuple[str, str, str, dict[str, Any], str]]:
    a = world.a
    now = timezone.now().isoformat()
    version = a.application.version
    return [
        (
            ADVISOR_OWNER,
            "post",
            f"/api/v1/applications/{a.application.pk}/notes",
            {"body": MEGABYTE},
            "body",
        ),
        (
            ADVISOR_OWNER,
            "post",
            "/api/v1/tasks",
            {"title": "t", "description": MEGABYTE, "application_id": str(a.application.pk)},
            "description",
        ),
        (
            ADVISOR_OWNER,
            "post",
            f"/api/v1/applications/{a.draft.pk}/status-transitions",
            {"target_status": "WAITING_BUYER_DATA", "expected_version": 1, "comment": MEGABYTE},
            "comment",
        ),
        (
            ADVISOR_OWNER,
            "post",
            f"/api/v1/filings/{a.filing.pk}/responses",
            {
                "response_type": "OTHER",
                "received_at": now,
                "internal_comment": MEGABYTE,
                "expected_version": version,
            },
            "internal_comment",
        ),
        (
            ADVISOR_OWNER,
            "post",
            f"/api/v1/filings/{a.filing.pk}/responses",
            {
                "response_type": "OTHER",
                "received_at": now,
                "internal_comment": "x",
                "public_message": MEGABYTE,
                "expected_version": version,
            },
            "public_message",
        ),
        (
            ADVISOR_OWNER,
            "patch",
            f"/api/v1/document-slots/{a.slot.pk}/review",
            {"decision": "REJECTED", "reason_code": "ILLEGIBLE", "buyer_comment": MEGABYTE},
            "buyer_comment",
        ),
        (
            ADVISOR_OWNER,
            "post",
            "/api/v1/clients",
            {
                "document_type_code": "CC",
                "document_number": "77",
                "first_names": MEGABYTE,
                "last_names": "x",
            },
            "first_names",
        ),
        (
            BROKER_OWNER,
            "post",
            "/api/v1/clients",
            {
                "document_type_code": "CC",
                "document_number": "78",
                "first_names": "x",
                "last_names": "x",
                "phone": MEGABYTE,
            },
            "phone",
        ),
        (
            BUYER_OWNER,
            "post",
            f"/api/v1/buyer/applications/{a.application.pk}/withdrawals",
            {"reason_code": "BUYER_DESISTED", "comment": MEGABYTE},
            "comment",
        ),
    ]


TEXT_CASE_IDS = [
    "nota",
    "tarea",
    "cambio-de-estado",
    "respuesta-interna",
    "respuesta-publica",
    "revision",
    "cliente-nombre",
    "cliente-telefono-broker",
    "desistimiento-comprador",
]


@pytest.mark.parametrize("index", range(len(TEXT_CASE_IDS)), ids=TEXT_CASE_IDS)
def test_free_text_fields_have_a_maximum_length(world: World, index: int) -> None:
    actor, method, url, body, field = _text_cases(world)[index]
    response = getattr(client_for(world, actor), method)(
        url, body, format="json", HTTP_IF_MATCH='"1"'
    )
    assert response.status_code == 400, response.content[:200]
    assert {"field": field, "code": "MAX_LENGTH"}.items() <= next(
        d for d in response.json()["details"] if d["field"] == field
    ).items()


def test_bank_operational_notes_have_a_maximum_length(world: World) -> None:
    """Solo el administrador escribe la configuración de bancos; aun así, un texto de 1 MB
    no se guarda (SEC-17, ``max_length=4000`` al crear y al editar)."""
    response = client_for(world, ADMIN).post(
        "/api/v1/banks",
        {"code": "ZZ", "name": "Banco Z", "tax_id": "900123456-8", "operational_notes": MEGABYTE},
        format="json",
    )
    assert response.status_code == 400
    assert any(d["field"] == "operational_notes" for d in response.json()["details"])


def test_bank_operational_notes_are_capped_on_update_too(world: World) -> None:
    operation = "PATCH /api/v1/banks/{bank_id}"
    response = send(
        client_for(world, ADMIN),
        operation,
        url_for(world, operation),
        {"operational_notes": "x" * 4001},
    )
    assert response.status_code == 400, response.content[:200]
    assert any(d["field"] == "operational_notes" for d in response.json()["details"])


# --- SEC-04: DRF 3.18.2 o posterior -------------------------------------------------------


def test_a_compressed_charset_is_not_expanded(api_client: Any) -> None:
    """CVE-2026-114136 (SEC-04): ~100 bytes con ``charset=bz2_codec`` se expandían a un
    correo de 5 MB que llegaba al serializer (``400 VALIDATION_ERROR``). Con DRF 3.18.2 el
    parser rechaza el ``charset`` sin descomprimir."""
    raw = json.dumps({"email": "a" * (5 * 1024 * 1024) + "@x.co", "password": "x"}).encode()
    body = bz2.compress(raw)
    assert len(body) < 200
    response = api_client.generic(
        "POST",
        "/api/v1/auth/login",
        body,
        content_type="application/json; charset=bz2_codec",
    )
    assert response.status_code == 400, response.content[:200]
    assert response.json()["code"] == "MALFORMED_REQUEST"


def test_drf_has_the_fix_of_both_cves() -> None:
    """CVE-2026-114138 (el `Accept` cuadrático) no se reproduce con el cliente de pruebas:
    lo cubre la versión. La medición contra el servidor está en la ficha."""
    major, minor, patch = (int(part) for part in rest_framework.VERSION.split(".")[:3])
    assert (major, minor, patch) >= (3, 18, 2)
