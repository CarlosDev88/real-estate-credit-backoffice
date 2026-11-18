"""Parte 2 del módulo 14: cada grupo genera su evento con el actor, el resultado y la
metadata correctos. El escáner de ``conftest`` revisa que ninguno guarde datos prohibidos."""

from collections.abc import Callable
from typing import Any

import pytest
from django.core import mail
from django.test import TestCase
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.audit.actions import AuditAction as A
from apps.audit.actions import AuditResult as R
from apps.audit.models import AuditEvent
from apps.banking.models import Bank, BankProduct
from apps.catalogs.models import Catalog
from apps.documents.models import ApplicationDocumentSlot, DocumentFile
from apps.filings.models import Filing
from apps.identity.models import BuyerSession, User
from tests.applications.buyer_access.conftest import LinkFactory, consume, pending_token
from tests.applications.buyer_access.test_consents_api import definition, post_consent
from tests.applications.buyer_access.test_links_api import issue
from tests.applications.dossier.conftest import SlotFactory
from tests.applications.dossier.test_buyer_dossier_api import upload
from tests.applications.dossier.test_downloads_api import file_url, make_version
from tests.applications.dossier.test_reviews_api import (
    VersionFactory,
    approve,
    doc_type,
    reopen,
    waive,
    with_version,
)
from tests.applications.filings.test_filings_api import file, package, ready
from tests.applications.filings.test_responses_api import APPROVED_BODY, filed, recorded
from tests.applications.test_assignments_and_clients_api import assign
from tests.applications.test_status_api import transition, withdraw
from tests.helpers import (
    LOGIN_URL,
    LOGOUT_URL,
    PASSWORD_RESET_REQUEST_URL,
    REFRESH_URL,
    login,
)

__all__ = ["file", "filed", "make_version", "package", "ready", "with_version"]

pytestmark = pytest.mark.django_db

Capture = Callable[..., Any]


def events(action: str, **filters: Any) -> list[AuditEvent]:
    return list(AuditEvent.objects.filter(action=action, **filters).order_by("created_at"))


def one(action: str, **filters: Any) -> AuditEvent:
    (event,) = events(action, **filters)
    return event


# --- Autenticación ----------------------------------------------------------------------


def test_login_logout_and_failures(api_client: APIClient, advisor_user: User) -> None:
    assert login(api_client).status_code == 200
    assert api_client.post(LOGOUT_URL).status_code == 204
    assert login(api_client, password="no-es-la-clave").status_code == 401
    assert APIClient().post(REFRESH_URL).status_code == 401

    ok = one(A.AUTH_LOGIN)
    assert (ok.result, ok.actor_user, ok.resource_type, ok.resource_id) == (
        R.SUCCESS,
        advisor_user,
        "users",
        advisor_user.pk,
    )
    assert ok.ip_address == "127.0.0.1"
    assert one(A.AUTH_LOGOUT).actor_user == advisor_user
    failed = one(A.AUTH_LOGIN_FAILED)
    assert (failed.result, failed.actor_user) == (R.FAILED, None)
    assert failed.metadata["email"] == "a•••@example.com"
    assert failed.metadata["code"] == "INVALID_CREDENTIALS"
    assert "no-es-la-clave" not in str(failed.metadata)
    refresh = one(A.AUTH_REFRESH_REJECTED)
    assert (refresh.result, refresh.metadata["status"]) == (R.FAILED, 401)


def test_rate_limited_login_is_denied(api_client: APIClient, advisor_user: User) -> None:
    for _ in range(6):
        login(api_client, password="otra-clave")

    limited = one(A.AUTH_RATE_LIMITED)
    assert (limited.result, limited.metadata["code"]) == (R.DENIED, "RATE_LIMITED")
    assert limited.metadata["path"] == LOGIN_URL
    assert len(events(A.AUTH_LOGIN_FAILED)) == 5


def test_password_reset_request_is_recorded_without_the_token(
    api_client: APIClient, advisor_user: User
) -> None:
    with TestCase.captureOnCommitCallbacks(execute=True):
        response = api_client.post(PASSWORD_RESET_REQUEST_URL, {"email": advisor_user.email})

    assert response.status_code == 202, response.content
    event = one(A.AUTH_PASSWORD_RESET_REQUESTED)
    assert (event.result, event.resource_type, event.metadata["email"]) == (
        R.SUCCESS,
        "auth",
        "a•••@example.com",
    )
    assert event.metadata["fields"] == ["email"]
    token_part = str(mail.outbox[-1].body).split("token=")[-1][:20]
    assert token_part not in str(event.metadata)


# --- Comprador --------------------------------------------------------------------------


def test_buyer_link_lifecycle(
    advisor_client: APIClient,
    advisor_user: User,
    application: CreditApplication,
    api_client: APIClient,
    make_link: LinkFactory,
) -> None:
    assert issue(advisor_client, application).status_code == 201
    assert consume(api_client, pending_token(make_link)).status_code == 200
    assert consume(APIClient(), "token-que-no-existe-123456").status_code == 401
    assert api_client.post("/api/v1/buyer/session/logout").status_code == 204

    created = one(A.BUYER_LINK_CREATED)
    assert (created.actor_user, created.resource_type) == (advisor_user, "buyer_access_links")
    assert created.metadata["application_id"] == str(application.pk)
    session = BuyerSession.objects.get()
    consumed = one(A.BUYER_LINK_CONSUMED)
    assert consumed.actor_buyer_session == session
    failed = one(A.BUYER_LINK_FAILED)
    assert (failed.result, failed.metadata["code"]) == (R.FAILED, "MAGIC_LINK_INVALID")
    closed = one(A.BUYER_SESSION_CLOSED)
    assert (closed.actor_buyer_session, closed.resource_id) == (session, session.pk)


def test_consents_are_recorded(
    buyer_client: APIClient,
    application: CreditApplication,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    consent = definition("DATA_PROCESSING")
    with django_capture_on_commit_callbacks(execute=True):
        post_consent(buyer_client, application, consent)
        post_consent(buyer_client, application, consent, action="WITHDRAWN")

    accepted = one(A.CONSENT_ACCEPTED)
    withdrawn = one(A.CONSENT_WITHDRAWN)
    assert (
        accepted.metadata["consent_code"] == withdrawn.metadata["consent_code"] == "DATA_PROCESSING"
    )
    assert accepted.actor_buyer_session is not None


# --- Archivos ---------------------------------------------------------------------------


def test_upload_and_download_without_the_signed_url(
    portal: APIClient,
    advisor_client: APIClient,
    advisor_user: User,
    make_slot: SlotFactory,
    make_version: Callable[..., DocumentFile],
    django_capture_on_commit_callbacks: Capture,
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        assert upload(portal, make_slot(document_type=doc_type("PAYROLL_SLIP"))).status_code == 201
    version = make_version()
    body = advisor_client.get(file_url(version, "/download")).json()

    uploaded = one(A.DOCUMENT_UPLOADED)
    assert uploaded.actor_buyer_session is not None
    assert uploaded.metadata["document_type"] == "PAYROLL_SLIP"
    downloaded = one(A.DOCUMENT_DOWNLOADED)
    assert (downloaded.actor_user, downloaded.resource_type, downloaded.resource_id) == (
        advisor_user,
        "document_files",
        version.pk,
    )
    assert body["url"] not in str(downloaded.metadata)
    assert downloaded.metadata["fields"] == []


# --- Expediente -------------------------------------------------------------------------


def test_dossier_events(
    advisor_client: APIClient,
    admin_client: APIClient,
    application: CreditApplication,
    other_advisor: User,
    make_slot: SlotFactory,
    with_version: VersionFactory,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    reviewed = make_slot()
    with_version(reviewed)
    waivable = make_slot(
        document_type=doc_type("BANK_STATEMENT"), is_waivable=True, is_required=False
    )
    with django_capture_on_commit_callbacks(execute=True):
        assert approve(advisor_client, reviewed).status_code == 200
        assert waive(advisor_client, waivable).status_code == 200
        assert reopen(advisor_client, waivable).status_code == 200
    assert transition(advisor_client, application, "WAITING_BUYER_DATA").status_code == 200
    assert assign(admin_client, application, other_advisor).status_code == 200
    assert withdraw(admin_client, application, version=2).status_code == 200

    assert one(A.DOCUMENT_REVIEWED).metadata["decision"] == "APPROVED"
    assert one(A.DOCUMENT_WAIVED).resource_id == waivable.pk
    assert one(A.DOCUMENT_WAIVER_REOPENED).metadata["decision"] == "REOPENED"
    changed = one(A.APPLICATION_STATUS_CHANGED)
    assert (changed.metadata["from_status"], changed.metadata["to_status"]) == (
        "DRAFT",
        "WAITING_BUYER_DATA",
    )
    assert one(A.APPLICATION_ASSIGNED).metadata["advisor_id"] == str(other_advisor.pk)
    withdrawn = one(A.APPLICATION_WITHDRAWN)
    assert (withdrawn.resource_type, withdrawn.resource_id) == (
        "credit_applications",
        application.pk,
    )


# --- Radicación -------------------------------------------------------------------------


def test_filing_events(advisor_client: APIClient, filed: Filing) -> None:
    response = recorded(advisor_client, filed, "RECEIVED")
    recorded(advisor_client, filed, "APPROVED", **APPROVED_BODY)
    patched = advisor_client.patch(
        f"/api/v1/filings/{filed.pk}", {"external_reference": "RAD-2026-0099"}, format="json"
    )

    assert patched.status_code == 200, patched.content
    assert one(A.FILING_CREATED).metadata["sequence_number"] == 1
    responses = events(A.BANK_RESPONSE_RECORDED)
    assert [event.metadata["response_type"] for event in responses] == ["RECEIVED", "APPROVED"]
    assert responses[0].resource_id == response.pk
    updated = one(A.FILING_UPDATED)
    assert (updated.resource_id, updated.metadata["fields"]) == (filed.pk, ["external_reference"])
    assert "¡Tu crédito fue aprobado!" not in str([event.metadata for event in responses])


# --- Configuración ----------------------------------------------------------------------


def test_configuration_changes(
    admin_client: APIClient, admin_user: User, advisor_user: User
) -> None:
    created = admin_client.post(
        f"/api/v1/catalogs/{Catalog.objects.get(code='lead_origin').pk}/items",
        {"code": "EVENT", "label": "Feria de vivienda"},
        format="json",
    )
    bank = Bank.objects.first()
    assert bank is not None
    deactivated = admin_client.post(
        f"/api/v1/banks/{bank.pk}/deactivate", {"reason": "Pausa comercial"}, format="json"
    )
    user_off = admin_client.post(
        f"/api/v1/users/{advisor_user.pk}/deactivate", {"reason": "Licencia"}, format="json"
    )

    assert created.status_code == 201, created.content
    item = one(A.CATALOG_CHANGED)
    assert (item.resource_type, str(item.resource_id)) == ("catalog_items", created.json()["id"])
    assert item.metadata["fields"] == ["code", "label"]
    assert "Feria de vivienda" not in str(item.metadata)
    assert deactivated.status_code == 200, deactivated.content
    bank_event = one(A.BANK_CHANGED)
    assert (bank_event.metadata["to_status"], bank_event.actor_user) == ("INACTIVE", admin_user)
    assert user_off.status_code == 200, user_off.content
    assert one(A.USER_STATUS_CHANGED).resource_id == advisor_user.pk


# --- Acceso denegado --------------------------------------------------------------------


def test_every_403_is_denied_without_the_body(
    advisor_client: APIClient, advisor_user: User
) -> None:
    response = advisor_client.post("/api/v1/users", {"email": "x@example.com"}, format="json")

    assert response.status_code == 403
    denied = one(A.ACCESS_DENIED)
    assert (denied.result, denied.actor_user) == (R.DENIED, advisor_user)
    assert denied.metadata == {
        "method": "POST",
        "path": "/api/v1/users",
        "view": "UserListView",
        "email": "x•••@example.com",
        "status": 403,
        "code": "PERMISSION_DENIED",
    }


def test_successful_reads_without_audit_actions_are_not_recorded(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    assert advisor_client.get(f"/api/v1/applications/{application.pk}").status_code == 200

    # Solo el inicio de sesión del cliente de prueba.
    assert set(AuditEvent.objects.values_list("action", flat=True)) == {A.AUTH_LOGIN}


def test_slot_types_are_resources(make_slot: SlotFactory) -> None:
    slot: ApplicationDocumentSlot = make_slot()

    assert slot._meta.db_table == "application_document_slots"


# --- Señales de configuración y caminos de error ----------------------------------------


def test_configuration_status_signals(admin_user: User) -> None:
    from apps.audit import receivers

    product = BankProduct.objects.first()
    rule = ("bank_policy_rules", "5d0c1a8e-0000-4000-8000-000000000001")
    receivers.on_product_status(
        None, product=product, from_status="ACTIVE", to_status="INACTIVE", actor=admin_user
    )
    receivers.on_requirement_status(
        None, requirement=rule, from_status="DRAFT", to_status="ACTIVE", actor=admin_user
    )
    receivers.on_rule_status(
        None, rule=rule, from_status="DRAFT", to_status="ACTIVE", actor=admin_user
    )
    receivers.on_document_type_status(
        None, document_type=doc_type("PAYROLL_SLIP"), is_active=False, actor=admin_user
    )

    assert one(A.BANK_PRODUCT_CHANGED).metadata["to_status"] == "INACTIVE"
    assert one(A.DOCUMENT_REQUIREMENT_CHANGED).resource_type == "bank_policy_rules"
    assert one(A.BANK_RULE_CHANGED).metadata["from_status"] == "DRAFT"
    assert one(A.DOCUMENT_TYPE_CHANGED).metadata == {"is_active": False, "reason": ""}


def test_hooks_never_break_the_response(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    from apps.audit import hooks

    class BrokenRequest:
        @property
        def data(self) -> Any:
            raise ValueError("cuerpo ilegible")

    assert hooks._data(BrokenRequest()) == {}

    class Exploding:
        @property
        def renderer_context(self) -> Any:
            raise RuntimeError("falla")

    with caplog.at_level(logging.ERROR, logger="apps.audit.hooks"):
        hooks.safe_audit_response(Exploding())  # type: ignore[arg-type]
    assert "No se pudo auditar la respuesta" in caplog.text
