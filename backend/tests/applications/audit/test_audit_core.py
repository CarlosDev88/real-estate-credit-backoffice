"""Parte 1 del módulo 14: modelo inmutable, saneamiento y ``record_audit``."""

import logging
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from django.db import DatabaseError, connection, transaction
from django.http import HttpResponse
from django.test import RequestFactory

from apps.audit import services
from apps.audit.actions import AuditAction, AuditResult
from apps.audit.context import AuditContextMiddleware, get_client_ip
from apps.audit.models import AuditEvent, AuditImmutable, allow_purge
from apps.audit.sanitize import (
    MAX_TEXT_LENGTH,
    OMITTED_URL,
    mask_document,
    mask_email,
    sanitize_metadata,
)
from apps.audit.services import record_audit, resource_ref
from apps.identity.models import BuyerSession, User
from config.request_context import set_request_id
from tests.applications.audit.conftest import problems

pytestmark = pytest.mark.django_db

Capture = Callable[..., Any]


def only() -> AuditEvent:
    (event,) = AuditEvent.objects.all()
    return event


@pytest.fixture
def event(advisor_user: User) -> AuditEvent:
    record_audit(AuditAction.AUTH_LOGIN, advisor_user, actor=advisor_user)
    return only()


# --- Inmutable --------------------------------------------------------------------------


def test_an_existing_event_cannot_be_saved_or_deleted(event: AuditEvent) -> None:
    event.metadata = {"cambio": True}

    with pytest.raises(AuditImmutable):
        event.save()
    with pytest.raises(AuditImmutable):
        event.delete()
    with pytest.raises(AuditImmutable):
        AuditEvent.objects.filter(pk=event.pk).update(result=AuditResult.FAILED)
    with pytest.raises(AuditImmutable):
        AuditEvent.objects.filter(pk=event.pk).delete()
    assert only().metadata == {}
    assert str(event) == "AUTH_LOGIN SUCCESS"


def test_the_database_blocks_updates(event: AuditEvent) -> None:
    with pytest.raises(DatabaseError, match="inmutable"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("UPDATE audit_events SET result = 'FAILED' WHERE id = %s", [event.pk])
    assert only().result == AuditResult.SUCCESS


def test_only_the_retention_can_delete(event: AuditEvent) -> None:
    with allow_purge():
        AuditEvent.objects.filter(pk=event.pk).delete()

    assert not AuditEvent.objects.exists()
    # Fuera de `allow_purge` vuelve a estar protegido.
    record_audit(AuditAction.AUTH_LOGIN, "auth")
    with pytest.raises(AuditImmutable):
        AuditEvent.objects.all().delete()


# --- Saneamiento ------------------------------------------------------------------------


def test_sanitize_drops_secrets_masks_documents_and_clips_texts() -> None:
    clean = sanitize_metadata(
        {
            "password": "x",
            "new_password": "x",
            "access_token": "x",
            "Authorization": "Bearer x",
            "cookie": "x",
            "client_secret": "x",
            "signature": "x",
            "download_url": "https://s3/x?X-Amz-Signature=1",
            "document_number": "1032445908",
            "note": "Ver https://bucket.example/file.pdf?X-Amz-Signature=abc",
            "comment": "x" * 900,
            "nested": {"token_hash": "x", "status": "OK", "items": [{"secret": 1}, 2]},
            "flags": (True, None, 1.5),
            "when": uuid.UUID(int=1),
        }
    )

    assert clean == {
        "document_number": "••••5908",
        "note": OMITTED_URL,
        "comment": "x" * (MAX_TEXT_LENGTH - 1) + "…",
        "nested": {"status": "OK", "items": [{}, 2]},
        "flags": [True, None, 1.5],
        "when": str(uuid.UUID(int=1)),
    }
    assert sanitize_metadata(None) == {}


def test_masks() -> None:
    assert mask_document("12 34") == "••••"
    assert mask_document(80123456) == "••••3456"
    assert mask_email("laura.gomez@example.com") == "l•••@example.com"
    assert mask_email("sin-arroba") == "•••"


def test_the_forbidden_data_scanner_finds_problems() -> None:
    found = problems(
        {
            "token": "x",
            "a": ["https://x/y?z=1", "y" * 600],
            "b": "CC 1032445908",
            "id": str(uuid.uuid4()),
        }
    )

    assert len(found) == 4


# --- record_audit -----------------------------------------------------------------------


def test_record_takes_the_request_id_the_ip_and_the_actor_from_the_request(
    advisor_user: User,
) -> None:
    request = RequestFactory().get("/api/v1/x", REMOTE_ADDR="10.0.0.7")
    request.user = advisor_user
    set_request_id("req-abc-12345")

    record_audit(
        AuditAction.DOCUMENT_DOWNLOADED,
        ("document_files", "1e6b4f3e-0000-4000-8000-000000000001"),
        request=request,
        metadata={"slot_id": "s-1"},
    )

    event = only()
    assert (event.actor_user, event.actor_buyer_session) == (advisor_user, None)
    assert (event.request_id, event.ip_address) == ("req-abc-12345", "10.0.0.7")
    assert (event.resource_type, str(event.resource_id)) == (
        "document_files",
        "1e6b4f3e-0000-4000-8000-000000000001",
    )
    assert event.metadata == {"slot_id": "s-1"}
    assert (event.action, event.result) == (AuditAction.DOCUMENT_DOWNLOADED, AuditResult.SUCCESS)


def test_a_buyer_session_is_the_actor_of_its_requests(buyer_session: BuyerSession) -> None:
    request = RequestFactory().get("/api/v1/buyer/x", REMOTE_ADDR="no-es-una-ip")
    request.auth = buyer_session  # type: ignore[attr-defined]

    record_audit(AuditAction.BUYER_SESSION_CLOSED, buyer_session, request=request)

    event = only()
    assert (event.actor_user, event.actor_buyer_session) == (None, buyer_session)
    assert event.ip_address is None
    assert event.resource_type == "buyer_sessions"


def test_without_a_request_it_uses_the_middleware_ip_and_a_new_request_id() -> None:
    set_request_id(None)
    seen: list[str | None] = []

    def view(request: Any) -> HttpResponse:
        # Un evento que llega por una señal, sin la petición a mano.
        seen.append(get_client_ip())
        record_audit(AuditAction.AUTH_LOGIN_FAILED, "auth", AuditResult.FAILED)
        return HttpResponse()

    AuditContextMiddleware(view)(RequestFactory().get("/", REMOTE_ADDR="192.168.1.20"))

    event = only()
    assert seen == [event.ip_address] == ["192.168.1.20"]
    # Al terminar la petición, la IP ya no queda en el contexto.
    assert get_client_ip() is None
    assert uuid.UUID(event.request_id)
    assert (event.resource_type, event.resource_id, event.actor_user) == ("auth", None, None)


def test_resource_ids_that_are_not_uuids_go_to_the_metadata() -> None:
    assert resource_ref(("roles", 7)) == ("roles", None, {"resource_pk": "7"})
    assert resource_ref(("users", None)) == ("users", None, {})
    identifier = uuid.uuid4()
    assert resource_ref(("users", str(identifier))) == ("users", identifier, {})


def test_success_inside_a_transaction_waits_for_the_commit(
    advisor_user: User, django_capture_on_commit_callbacks: Capture
) -> None:
    with django_capture_on_commit_callbacks() as callbacks, transaction.atomic():
        record_audit(AuditAction.USER_CHANGED, advisor_user)
        assert not AuditEvent.objects.exists()

    assert len(callbacks) == 1
    callbacks[0]()
    assert only().action == AuditAction.USER_CHANGED


def test_success_that_rolls_back_is_not_recorded(advisor_user: User) -> None:
    with pytest.raises(RuntimeError), transaction.atomic():
        record_audit(AuditAction.USER_CHANGED, advisor_user)
        raise RuntimeError("se deshace")

    assert not AuditEvent.objects.exists()


@pytest.mark.django_db(databases=["default", "audit"])
def test_a_failure_survives_the_rollback_of_the_operation(advisor_user: User) -> None:
    with pytest.raises(RuntimeError), transaction.atomic():
        record_audit(
            AuditAction.AUTH_LOGIN_FAILED,
            "auth",
            AuditResult.FAILED,
            metadata={"email": mask_email(advisor_user.email)},
        )
        raise RuntimeError("se deshace")

    (event,) = AuditEvent.objects.using("audit").all()
    assert (event.action, event.result) == (AuditAction.AUTH_LOGIN_FAILED, AuditResult.FAILED)
    assert event.metadata == {"email": "a•••@example.com"}
    # La conexión normal no lo tiene: se escribió por la de auditoría.
    assert not AuditEvent.objects.exists()


def test_an_error_while_auditing_never_breaks_the_operation(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("base caída")

    monkeypatch.setattr(AuditEvent, "save", broken)
    with caplog.at_level(logging.ERROR, logger="apps.audit.services"):
        record_audit(AuditAction.AUTH_LOGIN, "auth")
    assert "No se pudo registrar la auditoría AUTH_LOGIN" in caplog.text

    monkeypatch.setattr(services, "build_event", broken)
    with caplog.at_level(logging.ERROR, logger="apps.audit.services"):
        record_audit(AuditAction.AUTH_LOGOUT, "auth")
    assert "No se pudo preparar la auditoría AUTH_LOGOUT" in caplog.text


def test_every_action_has_a_label() -> None:
    assert all(label for _, label in AuditAction.choices)
    assert len(AuditAction.values) == len(set(AuditAction.values))
