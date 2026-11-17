"""Parte 3 del módulo 14: consulta de la auditoría y retención."""

import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.audit.actions import AuditAction as A
from apps.audit.actions import AuditResult as R
from apps.audit.models import AuditEvent
from apps.audit.retention import AUDIT_RETENTION_DAYS
from apps.audit.services import record_audit
from apps.identity.models import BuyerSession, User
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

URL = "/api/v1/audit-events"


def items(response: Any) -> list[dict[str, Any]]:
    assert response.status_code == 200, response.content
    return list(response.json()["items"])


def actions(response: Any) -> list[str]:
    return [item["action"] for item in items(response)]


@pytest.fixture
def seeded(admin_user: User, advisor_user: User, buyer_session: BuyerSession) -> dict[str, Any]:
    """Tres eventos fuera del cliente de prueba, con fechas distintas."""
    resource = uuid.uuid4()
    with freeze_time("2026-11-10 15:00:00"):
        record_audit(A.USER_CHANGED, ("users", advisor_user.pk), actor=admin_user)
    with freeze_time("2026-11-12 04:30:00"):  # 23:30 del 11 en Bogotá.
        record_audit(A.DOCUMENT_DOWNLOADED, ("document_files", resource), actor=advisor_user)
    with freeze_time("2026-11-13 12:00:00"):
        record_audit(
            A.BUYER_LINK_FAILED,
            "buyer_access_links",
            R.FAILED,
            actor=buyer_session,
            metadata={"code": "MAGIC_LINK_EXPIRED"},
        )
    return {"resource": resource}


def mine(response: Any) -> list[str]:
    """Las acciones sin el inicio de sesión del cliente de prueba ni los accesos denegados."""
    return [a for a in actions(response) if a not in (A.AUTH_LOGIN, A.ACCESS_DENIED)]


def test_admin_lists_newest_first_with_labels_and_actors(
    admin_client: APIClient, seeded: dict[str, Any], admin_user: User, buyer_session: BuyerSession
) -> None:
    body = items(admin_client.get(URL, {"result": "FAILED"}))

    (failed,) = body
    assert failed == {
        "id": failed["id"],
        "created_at": failed["created_at"],
        "action": "BUYER_LINK_FAILED",
        "action_label": "Enlace de acceso rechazado",
        "result": "FAILED",
        "result_label": "Fallido",
        "resource_type": "buyer_access_links",
        "resource_id": None,
        "actor": {
            "id": str(buyer_session.pk),
            "name": f"Comprador (sesión {str(buyer_session.pk)[:8]})",
        },
        "request_id": failed["request_id"],
        "ip_address": None,  # Registrado fuera de una petición.
        "metadata": {"code": "MAGIC_LINK_EXPIRED"},
    }
    assert mine(admin_client.get(URL))[:3] == [
        A.BUYER_LINK_FAILED,
        A.DOCUMENT_DOWNLOADED,
        A.USER_CHANGED,
    ]
    detail = admin_client.get(f"{URL}/{failed['id']}").json()
    assert detail == failed
    changed = items(admin_client.get(URL, {"action": "USER_CHANGED"}))[0]
    assert changed["actor"] == {"id": str(admin_user.pk), "name": admin_user.get_full_name()}


def test_filters(
    admin_client: APIClient,
    seeded: dict[str, Any],
    advisor_user: User,
    buyer_session: BuyerSession,
) -> None:
    def only(**params: Any) -> list[str]:
        return mine(admin_client.get(URL, params))

    assert only(actor_user_id=str(advisor_user.pk)) == [A.DOCUMENT_DOWNLOADED]
    assert only(actor_buyer_session_id=str(buyer_session.pk)) == [A.BUYER_LINK_FAILED]
    both = admin_client.get(f"{URL}?action=USER_CHANGED&action=BUYER_LINK_FAILED")
    assert mine(both) == [A.BUYER_LINK_FAILED, A.USER_CHANGED]
    assert only(resource_type="document_files") == [A.DOCUMENT_DOWNLOADED]
    assert only(resource_id=str(seeded["resource"])) == [A.DOCUMENT_DOWNLOADED]
    # Fechas de Bogotá: el 11 incluye la descarga de las 23:30 (04:30 UTC del 12).
    assert only(created_from="2026-11-11", created_to="2026-11-11") == [A.DOCUMENT_DOWNLOADED]
    assert only(created_to="2026-11-10T10:00:00-05:00") == [A.USER_CHANGED]
    assert only(created_from="2026-11-13T00:00:00") == [
        a for a in mine(admin_client.get(URL)) if a != A.USER_CHANGED and a != A.DOCUMENT_DOWNLOADED
    ]
    request_id = AuditEvent.objects.get(action=A.USER_CHANGED).request_id
    assert A.USER_CHANGED in only(request_id=request_id)


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"action": "INVENTED"}, "action"),
        ({"result": "MAYBE"}, "result"),
        ({"actor_user_id": "no-uuid"}, "actor_user_id"),
        ({"resource_id": "no-uuid"}, "resource_id"),
        ({"created_from": "ayer"}, "created_from"),
        ({"created_to": "2026-13-45"}, "created_to"),
    ],
)
def test_invalid_filters_respond_400(
    admin_client: APIClient, params: dict[str, str], field: str
) -> None:
    error = assert_error(admin_client.get(URL, params), 400, "VALIDATION_ERROR")
    assert error["details"][0]["field"] == field


@pytest.mark.parametrize(
    "client_name", ["advisor_client", "broker_client", "partner_client", "portal"]
)
def test_only_the_admin_reads_and_the_attempt_is_audited(
    request: pytest.FixtureRequest, client_name: str
) -> None:
    client: APIClient = request.getfixturevalue(client_name)

    response = client.get(URL)

    assert response.status_code in (401, 403)
    if response.status_code == 403:
        denied = AuditEvent.objects.get(action=A.ACCESS_DENIED)
        assert denied.metadata["path"] == URL


def test_unknown_event_is_not_found(admin_client: APIClient) -> None:
    assert_error(admin_client.get(f"{URL}/{uuid.uuid4()}"), 404, "RESOURCE_NOT_FOUND")


def test_an_event_without_actor_has_a_null_actor(admin_client: APIClient) -> None:
    record_audit(A.AUTH_LOGIN_FAILED, "auth", R.FAILED)

    failed = items(admin_client.get(URL, {"action": "AUTH_LOGIN_FAILED"}))[0]
    assert failed["actor"] is None


def test_list_queries_do_not_grow(admin_client: APIClient, advisor_user: User) -> None:
    def measure() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert admin_client.get(URL).status_code == 200
        return len(queries)

    record_audit(A.USER_CHANGED, advisor_user, actor=advisor_user)
    one = measure()
    for _ in range(20):
        record_audit(A.USER_CHANGED, advisor_user, actor=advisor_user)

    # La consulta anterior dejó su propio inicio de sesión y nada más: igual cantidad.
    assert measure() == one


# --- Retención --------------------------------------------------------------------------


def test_purge_deletes_only_what_is_older_than_the_retention() -> None:
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    with freeze_time(now - timedelta(days=AUDIT_RETENTION_DAYS + 1)):
        record_audit(A.AUTH_LOGIN, "auth")
    with freeze_time(now - timedelta(days=AUDIT_RETENTION_DAYS - 1)):
        record_audit(A.AUTH_LOGOUT, "auth")

    out = io.StringIO()
    with freeze_time(now):
        call_command("purge_audit_events", stdout=out)

    assert list(AuditEvent.objects.values_list("action", flat=True)) == [A.AUTH_LOGOUT]
    assert "Eventos de auditoría borrados: 1" in out.getvalue()


def test_purge_accepts_fewer_days_and_rejects_zero() -> None:
    with freeze_time(datetime.now(UTC) - timedelta(days=3)):
        record_audit(A.AUTH_LOGIN, "auth")

    call_command("purge_audit_events", days=2, stdout=io.StringIO())
    assert not AuditEvent.objects.exists()
    with pytest.raises(CommandError):
        call_command("purge_audit_events", days=0)
