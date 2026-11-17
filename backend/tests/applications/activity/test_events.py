"""Cada evento deja su fila de actividad con la visibilidad correcta, sin datos internos
en las del comprador, y un error en un suscriptor no rompe la operación original."""

import logging
from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.activity import receivers
from apps.activity.models import ActivityEventType as E
from apps.activity.models import ActivityLog
from apps.activity.models import ActivityVisibility as V
from apps.applications.models import (
    ApplicationParticipant,
    ApplicationStatusHistory,
    CreditApplication,
    ParticipantRole,
)
from apps.applications.signals import participant_added, participant_removed
from apps.crm.models import Client, Opportunity
from apps.documents.models import ApplicationDocumentSlot, DocumentType
from apps.filings.models import Filing
from apps.identity.buyer_portal import public_status_label
from apps.identity.models import BuyerSession, User
from tests.applications.activity.conftest import by_visibility, rows
from tests.applications.buyer_access.conftest import LinkFactory, consume, pending_token
from tests.applications.buyer_access.test_consents_api import definition, post_consent
from tests.applications.buyer_access.test_links_api import issue
from tests.applications.dossier.conftest import SlotFactory
from tests.applications.dossier.test_buyer_dossier_api import upload
from tests.applications.dossier.test_reviews_api import (
    VersionFactory,
    approve,
    reject,
    with_version,
)
from tests.applications.filings.test_filings_api import file, package, ready
from tests.applications.filings.test_responses_api import (
    APPROVED_BODY,
    OTHER_BODY,
    filed,
    recorded,
)
from tests.applications.tasks.conftest import TASKS_URL, task_url
from tests.applications.test_assignments_and_clients_api import assign
from tests.applications.test_status_api import transition

__all__ = ["file", "filed", "package", "ready", "with_version"]

pytestmark = pytest.mark.django_db

Capture = Callable[..., Any]

INTERNAL_COMMENT = "Comentario interno que el comprador no debe ver."


def buyer_rows_text() -> str:
    """Todo el texto de las filas del comprador, para buscar fugas."""
    return " ".join(
        f"{row.title} {row.message}" for row in ActivityLog.objects.filter(visibility=V.BUYER)
    )


# --- Solicitud --------------------------------------------------------------------------


def test_creating_an_application_is_recorded(
    advisor_client: APIClient, advisor_user: User, opportunity: Opportunity
) -> None:
    response = advisor_client.post(
        "/api/v1/applications",
        {"opportunity_id": str(opportunity.id), "purpose_code": "PURCHASE_NEW"},
        format="json",
    )

    assert response.status_code == 201, response.content
    (row,) = rows(E.APPLICATION_CREATED)
    application = CreditApplication.objects.get(pk=response.json()["id"])
    history = ApplicationStatusHistory.objects.get(application=application)
    assert (row.visibility, row.title) == (V.INTERNAL, f"Solicitud {application.code} creada")
    assert (row.application, row.opportunity, row.client) == (
        application,
        opportunity,
        opportunity.client,
    )
    assert row.actor_user == advisor_user
    assert row.metadata == {"status_history_id": str(history.pk)}


def test_a_status_change_has_an_internal_and_a_buyer_row(
    advisor_client: APIClient, advisor_user: User, application: CreditApplication
) -> None:
    response = transition(
        advisor_client, application, "WAITING_BUYER_DATA", comment=INTERNAL_COMMENT
    )

    assert response.status_code == 200, response.content
    grouped = by_visibility(E.STATUS_CHANGED)
    (internal,) = grouped[V.INTERNAL]
    (buyer,) = grouped[V.BUYER]
    assert internal.title == "Pasó de Borrador a Esperando datos del comprador"
    assert internal.message == INTERNAL_COMMENT
    assert buyer.title == (
        f"Pasó de {public_status_label('DRAFT')} a {public_status_label('WAITING_BUYER_DATA')}"
    )
    assert buyer.message == ""
    assert internal.actor_user == buyer.actor_user == advisor_user
    history = ApplicationStatusHistory.objects.get(application=application)
    assert internal.metadata == {
        "from_status": "DRAFT",
        "to_status": "WAITING_BUYER_DATA",
        "transition_code": "REQUEST_BUYER_DATA",
        "reason_code": None,
        "status_history_id": str(history.pk),
    }
    assert buyer.metadata == {
        "from_status": "DRAFT",
        "to_status": "WAITING_BUYER_DATA",
        "status_history_id": str(history.pk),
    }
    assert INTERNAL_COMMENT not in buyer_rows_text()


def test_reassignment_is_recorded(
    admin_client: APIClient, application: CreditApplication, other_advisor: User
) -> None:
    response = assign(admin_client, application, other_advisor, reason="Vacaciones")

    assert response.status_code == 200, response.content
    (row,) = rows(E.ADVISOR_ASSIGNED)
    assert (row.visibility, row.title, row.message) == (
        V.INTERNAL,
        "Marta García quedó como responsable",
        "Vacaciones",
    )
    assert row.metadata == {"advisor_id": str(other_advisor.pk)}


def test_participants_added_and_removed_are_recorded(
    application: CreditApplication, make_client: Callable[..., Client], advisor_user: User
) -> None:
    daniel = make_client(document_number="80999111", first_names="Daniel", last_names="Mejía")
    participant = ApplicationParticipant.objects.create(
        application=application, client=daniel, role=ParticipantRole.CO_APPLICANT
    )

    for signal in (participant_added, participant_removed):
        signal.send(
            sender=CreditApplication,
            application=application,
            participant=participant,
            reactivated=False,
            actor=advisor_user,
        )

    (added,) = rows(E.PARTICIPANT_ADDED)
    (removed,) = rows(E.PARTICIPANT_REMOVED)
    assert added.title == "Se agregó a Daniel Mejía como co-solicitante"
    assert removed.title == "Se retiró a Daniel Mejía como co-solicitante"
    assert {added.visibility, removed.visibility} == {V.INTERNAL}


# --- Documentos -------------------------------------------------------------------------


def test_an_upload_is_recorded_for_the_backoffice_and_the_buyer(
    portal: APIClient,
    make_slot: SlotFactory,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    slot = make_slot()

    with django_capture_on_commit_callbacks(execute=True):
        response = upload(portal, slot)

    assert response.status_code == 201, response.content
    grouped = by_visibility(E.DOCUMENT_UPLOADED)
    assert set(grouped) == {V.INTERNAL, V.BUYER}
    name = DocumentType.objects.get(code="IDENTITY_DOCUMENT").name
    session = BuyerSession.objects.get()
    for (row,) in grouped.values():
        assert row.title == f"Laura Gómez Vélez cargó «{name}»"
        assert row.actor_buyer_session == session
        assert row.actor_user is None
        assert row.metadata["slot_id"] == str(slot.pk)


def test_a_rejection_reaches_the_buyer_with_the_buyer_message_only(
    advisor_client: APIClient,
    make_slot: SlotFactory,
    with_version: VersionFactory,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    slot = make_slot(
        minimum_files=3, slot_index=2, document_type=DocumentType.objects.get(code="PAYROLL_SLIP")
    )
    with_version(slot)

    with django_capture_on_commit_callbacks(execute=True):
        response = reject(advisor_client, slot, internal_comment=INTERNAL_COMMENT)

    assert response.status_code == 200, response.content
    grouped = by_visibility(E.DOCUMENT_REVIEWED)
    (internal,) = grouped[V.INTERNAL]
    (buyer,) = grouped[V.BUYER]
    name = slot.document_type.name
    assert internal.title == f"Andrea García rechazó «{name}» 2 de 3"
    assert internal.message == INTERNAL_COMMENT
    assert buyer.title == f"Tu asesor rechazó «{name}» 2 de 3"
    assert buyer.message == "La foto está borrosa."
    assert INTERNAL_COMMENT not in buyer_rows_text()


def test_an_approval_is_internal_and_names_a_co_applicant(
    advisor_client: APIClient,
    application: CreditApplication,
    make_client: Callable[..., Client],
    make_slot: SlotFactory,
    with_version: VersionFactory,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    daniel = make_client(document_number="80999111", first_names="Daniel", last_names="Mejía")
    co_applicant = ApplicationParticipant.objects.create(
        application=application, client=daniel, role=ParticipantRole.CO_APPLICANT
    )
    slot = make_slot(participant=co_applicant)
    with_version(slot)

    with django_capture_on_commit_callbacks(execute=True):
        response = approve(advisor_client, slot)

    assert response.status_code == 200, response.content
    (row,) = rows(E.DOCUMENT_REVIEWED)
    assert row.visibility == V.INTERNAL
    assert row.title == f"Andrea García aprobó «{slot.document_type.name}» de Daniel Mejía"


# --- Acceso del comprador y consentimientos ---------------------------------------------


def test_issuing_and_consuming_a_link_are_recorded(
    advisor_client: APIClient,
    advisor_user: User,
    application: CreditApplication,
    api_client: APIClient,
    make_link: LinkFactory,
) -> None:
    assert issue(advisor_client, application).status_code == 201
    assert consume(api_client, pending_token(make_link)).status_code == 200

    (sent,) = rows(E.BUYER_LINK_SENT)
    assert (sent.visibility, sent.title, sent.actor_user) == (
        V.INTERNAL,
        "Andrea García envió el enlace de acceso al comprador",
        advisor_user,
    )
    assert set(sent.metadata) == {"link_id", "channel"}
    (started,) = rows(E.BUYER_SESSION_STARTED)
    assert (started.visibility, started.title) == (V.INTERNAL, "El comprador entró al portal")
    assert started.actor_buyer_session == BuyerSession.objects.get()


def test_a_consent_is_recorded_without_ip_or_user_agent(
    buyer_client: APIClient,
    application: CreditApplication,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    consent = definition("DATA_PROCESSING")

    with django_capture_on_commit_callbacks(execute=True):
        response = post_consent(buyer_client, application, consent, HTTP_USER_AGENT="Firefox")

    assert response.status_code == 201, response.content
    (row,) = rows(E.CONSENT_RECORDED)
    assert row.visibility == V.INTERNAL
    assert row.title == f"Laura Gómez Vélez aceptó «{consent.title}»"
    assert row.metadata == {
        "consent_code": "DATA_PROCESSING",
        "consent_version": 1,
        "action": "ACCEPTED",
    }
    assert "Firefox" not in str(row.metadata)


# --- Tareas -----------------------------------------------------------------------------


def test_task_events_are_recorded(
    advisor_client: APIClient,
    application: CreditApplication,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        created = advisor_client.post(
            TASKS_URL,
            {"title": "Revisar extractos", "application_id": str(application.pk)},
            format="json",
        )
        task_id = created.json()["id"]
        advisor_client.post(task_url(task_id, "/complete"))
        second = advisor_client.post(
            TASKS_URL,
            {"title": "Llamar al banco", "application_id": str(application.pk)},
            format="json",
        ).json()["id"]
        advisor_client.post(task_url(second, "/cancel"), {"reason": "Ya respondió"}, format="json")

    titles = [
        (row.event_type, row.title, row.message)
        for row in ActivityLog.objects.order_by("created_at")
    ]
    assert titles == [
        (E.TASK_CREATED, "Tarea creada: Revisar extractos", ""),
        (E.TASK_COMPLETED, "Tarea completada: Revisar extractos", ""),
        (E.TASK_CREATED, "Tarea creada: Llamar al banco", ""),
        (E.TASK_CANCELLED, "Tarea cancelada: Llamar al banco", "Ya respondió"),
    ]
    assert {row.application_id for row in ActivityLog.objects.all()} == {application.pk}


def test_a_task_on_an_opportunity_is_recorded_on_the_opportunity(
    advisor_client: APIClient,
    opportunity: Opportunity,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        response = advisor_client.post(
            TASKS_URL, {"title": "Llamar", "opportunity_id": str(opportunity.pk)}, format="json"
        )

    assert response.status_code == 201, response.content
    (row,) = rows(E.TASK_CREATED)
    assert (row.application, row.opportunity, row.client) == (None, opportunity, opportunity.client)


# --- Radicación -------------------------------------------------------------------------


def test_filing_and_bank_responses_are_recorded(advisor_client: APIClient, filed: Filing) -> None:
    bank = filed.bank_product.bank.name
    recorded(advisor_client, filed, "RECEIVED")
    recorded(advisor_client, filed, "OTHER", **OTHER_BODY)
    recorded(advisor_client, filed, "APPROVED", **APPROVED_BODY)

    (created,) = rows(E.FILING_CREATED)
    assert (created.visibility, created.title) == (V.INTERNAL, f"Radicada en {bank} (#1)")
    grouped = by_visibility(E.BANK_RESPONSE_RECORDED)
    assert len(grouped[V.INTERNAL]) == 3
    other = grouped[V.INTERNAL][1]
    assert other.message == OTHER_BODY["internal_comment"]
    # Solo las respuestas con mensaje para el comprador llegan a él.
    buyer_messages = [row.message for row in grouped[V.BUYER]]
    assert APPROVED_BODY["public_message"] in buyer_messages
    assert OTHER_BODY["internal_comment"] not in buyer_rows_text()


# --- Errores ----------------------------------------------------------------------------


def test_a_failing_subscriber_does_not_break_the_operation(
    advisor_client: APIClient,
    application: CreditApplication,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(**kwargs: Any) -> None:
        raise RuntimeError("falla de prueba")

    monkeypatch.setattr(receivers, "record_activity", broken)

    with caplog.at_level(logging.ERROR, logger="apps.activity.receivers"):
        response = transition(advisor_client, application, "WAITING_BUYER_DATA")

    assert response.status_code == 200, response.content
    application.refresh_from_db()
    assert application.status == "WAITING_BUYER_DATA"
    assert not ActivityLog.objects.exists()
    assert "No se pudo registrar la actividad de on_status_changed" in caplog.text


def test_a_database_error_in_a_subscriber_keeps_the_outer_transaction(
    advisor_client: APIClient,
    application: CreditApplication,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def violates_the_check(**kwargs: Any) -> None:
        # Sin solicitud, oportunidad ni cliente: `ck_activity_logs_resource` falla.
        ActivityLog.objects.create(event_type=kwargs["event_type"], title=kwargs["title"])

    monkeypatch.setattr(receivers, "record_activity", violates_the_check)

    with caplog.at_level(logging.ERROR, logger="apps.activity.receivers"):
        response = transition(advisor_client, application, "WAITING_BUYER_DATA")

    assert response.status_code == 200, response.content
    # El punto de guardado deshizo solo la fila: la transacción de afuera sigue sana.
    assert CreditApplication.objects.get(pk=application.pk).status == "WAITING_BUYER_DATA"
    assert "IntegrityError" in caplog.text


def test_slot_without_participant_is_labelled_by_type(make_slot: SlotFactory) -> None:
    slot: ApplicationDocumentSlot = make_slot()
    slot.participant = None

    assert receivers.document_label(slot) == f"«{slot.document_type.name}»"
