"""Eventos que avisan al comprador (Parte 1 del paso 13): cada uno crea su notificación
una sola vez, con sus entregas, sin datos internos, y un error nunca rompe la
operación original."""

import logging
from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.applications.models import ApplicationParticipant, CreditApplication, ParticipantRole
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client
from apps.documents.models import ApplicationDocumentSlot, DocumentReview
from apps.documents.signals import document_reviewed
from apps.filings.models import Filing, FilingResponse
from apps.filings.signals import filing_response_recorded
from apps.identity.models import User
from apps.notifications import receivers, services
from apps.notifications.messages import long_date, pesos, render
from apps.notifications.models import (
    DeliveryChannel,
    DeliveryStatus,
    Notification,
    NotificationDelivery,
    NotificationType,
)
from tests.applications.buyer_access.conftest import LinkFactory, consume, pending_token
from tests.applications.dossier.conftest import SlotFactory
from tests.applications.dossier.test_reviews_api import (
    VersionFactory,
    approve,
    doc_type,
    reject,
    waive,
    with_version,
)
from tests.applications.filings.test_filings_api import file, package, ready
from tests.applications.filings.test_responses_api import (
    APPROVED_BODY,
    DISBURSED_BODY,
    REJECTED_BODY,
    RETURNED_BODY,
    filed,
    observation,
    recorded,
    required_slots,
)
from tests.applications.test_status_api import transition

__all__ = ["filed", "package", "ready", "with_version"]

pytestmark = pytest.mark.django_db

Capture = Callable[..., Any]

INTERNAL = "Respuesta recibida por correo."


def of_type(notification_type: str) -> list[Notification]:
    return list(Notification.objects.filter(notification_type=notification_type))


def only(notification_type: str) -> Notification:
    (notification,) = of_type(notification_type)
    return notification


def deliveries(notification: Notification) -> dict[str, NotificationDelivery]:
    return {delivery.channel: delivery for delivery in notification.deliveries.all()}


# --- Acceso al portal -------------------------------------------------------------------


def test_first_access_welcomes_the_buyer(
    api_client: APIClient, make_link: LinkFactory, application: CreditApplication, buyer: Client
) -> None:
    Client.objects.filter(pk=buyer.pk).update(email="laura@example.com")

    assert consume(api_client, pending_token(make_link)).status_code == 200

    notification = only(NotificationType.ACCESS_GRANTED)
    assert (notification.client_id, notification.user_id) == (buyer.pk, None)
    assert notification.application_id == application.pk
    assert notification.title == "Bienvenido a tu portal"
    assert notification.message.endswith("Tu asesor está preparando la solicitud.")
    assert notification.deduplication_key == f"ACCESS_GRANTED:{application.pk}:{buyer.pk}"
    by_channel = deliveries(notification)
    portal_delivery = by_channel[DeliveryChannel.PORTAL]
    assert (portal_delivery.status, portal_delivery.attempt_count) == (DeliveryStatus.SENT, 1)
    assert portal_delivery.sent_at is not None
    email = by_channel[DeliveryChannel.EMAIL]
    assert (email.status, email.destination, email.attempt_count) == (
        DeliveryStatus.PENDING,
        "laura@example.com",
        0,
    )


def test_a_later_access_does_not_welcome_again(
    api_client: APIClient, make_link: LinkFactory
) -> None:
    assert consume(api_client, pending_token(make_link)).status_code == 200
    assert consume(APIClient(), pending_token(make_link)).status_code == 200

    assert len(of_type(NotificationType.ACCESS_GRANTED)) == 1
    assert NotificationDelivery.objects.count() == 2


def test_a_buyer_without_email_has_no_email_destination(
    api_client: APIClient, make_link: LinkFactory
) -> None:
    assert consume(api_client, pending_token(make_link)).status_code == 200

    email = deliveries(only(NotificationType.ACCESS_GRANTED))[DeliveryChannel.EMAIL]
    assert email.destination is None


# --- Documentos rechazados --------------------------------------------------------------


@pytest.fixture
def uploaded(make_slot: SlotFactory, with_version: VersionFactory) -> ApplicationDocumentSlot:
    """Cédula del titular con una versión limpia en revisión."""
    slot = make_slot()
    with_version(slot)
    return slot


def test_each_rejection_asks_the_buyer_to_correct(
    advisor_client: APIClient,
    uploaded: ApplicationDocumentSlot,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        response = reject(
            advisor_client,
            uploaded,
            buyer_comment="La foto está borrosa: tómala con buena luz.",
            internal_comment="Parece alterada, revisar con cumplimiento.",
        )
    assert response.status_code == 200, response.content

    notification = only(NotificationType.DOCUMENT_REJECTED)
    review = DocumentReview.objects.get(slot=uploaded)
    assert notification.deduplication_key == f"DOCUMENT_REJECTED:{review.pk}"
    assert notification.title == f"Debes corregir: {uploaded.document_type.name}"
    assert notification.message == "La foto está borrosa: tómala con buena luz."
    assert "cumplimiento" not in notification.title + notification.message


def test_a_new_rejection_is_a_new_notification(
    advisor_client: APIClient,
    uploaded: ApplicationDocumentSlot,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        assert reject(advisor_client, uploaded).status_code == 200
        assert reject(advisor_client, uploaded, buyer_comment="Sigue borrosa.").status_code == 200

    assert [n.message for n in of_type(NotificationType.DOCUMENT_REJECTED)] == [
        "Sigue borrosa.",
        "La foto está borrosa.",
    ]


def test_approving_or_waiving_does_not_notify(
    advisor_client: APIClient,
    uploaded: ApplicationDocumentSlot,
    make_slot: SlotFactory,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    waivable = make_slot(document_type=doc_type("EMPLOYMENT_CERTIFICATE"), is_waivable=True)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        assert approve(advisor_client, uploaded).status_code == 200
        assert waive(advisor_client, waivable).status_code == 200

    assert len(callbacks) >= 2
    assert not Notification.objects.exists()


def test_the_signal_carries_each_review(
    advisor_client: APIClient,
    advisor_user: User,
    uploaded: ApplicationDocumentSlot,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    received: list[dict[str, Any]] = []

    def listener(**kwargs: Any) -> None:
        received.append(kwargs)

    document_reviewed.connect(listener)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            assert reject(advisor_client, uploaded).status_code == 200
    finally:
        document_reviewed.disconnect(listener)

    (event,) = received
    review = DocumentReview.objects.get(slot=uploaded)
    assert event["review"] == review
    assert (event["slot"], event["document_file"], event["actor"]) == (
        uploaded,
        uploaded.current_file,
        advisor_user,
    )


def test_a_co_applicant_document_names_its_holder(
    advisor_client: APIClient,
    application: CreditApplication,
    make_client: Callable[..., Client],
    make_slot: SlotFactory,
    with_version: VersionFactory,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    co_client = make_client(document_number="80123456", first_names="Pedro", last_names="Ruiz")
    co_applicant = ApplicationParticipant.objects.create(
        application=application, client=co_client, role=ParticipantRole.CO_APPLICANT
    )
    slot = make_slot(participant=co_applicant)
    with_version(slot)

    with django_capture_on_commit_callbacks(execute=True):
        assert reject(advisor_client, slot).status_code == 200

    notification = only(NotificationType.DOCUMENT_REJECTED)
    assert notification.client_id == application.opportunity.client_id
    assert notification.title == f"Debes corregir: {slot.document_type.name} de Pedro Ruiz"


# --- Expediente listo y radicación ------------------------------------------------------


def test_ready_to_file_and_filing_notify_the_buyer(
    advisor_client: APIClient, ready: CreditApplication, package: Any
) -> None:
    ready_notice = only(NotificationType.READY_TO_FILE)
    assert ready_notice.title == "Tu expediente está completo"
    assert ready_notice.deduplication_key == f"READY_TO_FILE:{ready.pk}:{ready.version}"

    response = file(advisor_client, ready, package, comment="Nota interna de radicación.")

    assert response.status_code == 201, response.content
    filing = Filing.objects.select_related("bank_product__bank").get(pk=response.json()["id"])
    filed_notice = only(NotificationType.FILED)
    bank = filing.bank_product.bank.name
    assert filed_notice.deduplication_key == f"FILED:{filing.pk}"
    assert filed_notice.title == f"Radicamos tu solicitud en {bank}"
    assert long_date(filing.filed_at) in filed_notice.message
    assert "Nota interna" not in filed_notice.message


def test_ready_again_later_is_a_new_notification(application: CreditApplication) -> None:
    for version in (4, 7, 7):
        CreditApplication.objects.filter(pk=application.pk).update(version=version)
        application.refresh_from_db()
        receivers.on_application_status_changed(
            sender=CreditApplication,
            application=application,
            to_status=ApplicationStatus.READY_TO_FILE,
        )

    assert sorted(n.deduplication_key for n in of_type(NotificationType.READY_TO_FILE)) == [
        f"READY_TO_FILE:{application.pk}:4",
        f"READY_TO_FILE:{application.pk}:7",
    ]


def test_other_status_changes_do_not_notify(application: CreditApplication) -> None:
    receivers.on_application_status_changed(
        sender=CreditApplication,
        application=application,
        to_status=ApplicationStatus.DOCUMENTS_REVIEW,
    )

    assert not Notification.objects.exists()


# --- Respuestas del banco ---------------------------------------------------------------


def test_a_return_notifies_with_the_public_message(
    advisor_client: APIClient, filed: Filing, django_capture_on_commit_callbacks: Capture
) -> None:
    slot = required_slots(filed.application)[0]
    body = {**RETURNED_BODY, "observations": [observation(slot)]}
    with django_capture_on_commit_callbacks(execute=True):
        response = recorded(advisor_client, filed, "RETURNED", **body)

    notice = only(NotificationType.BANK_RETURNED)
    assert notice.deduplication_key == f"BANK_RETURNED:{response.pk}"
    assert notice.title == "El banco pidió correcciones"
    assert notice.message == RETURNED_BODY["public_message"]
    # Cada observación rechaza el documento: el comprador sabe cuál corregir.
    rejected = only(NotificationType.DOCUMENT_REJECTED)
    assert rejected.message == observation(slot)["message"]
    assert INTERNAL not in notice.message + rejected.message
    assert "Observación del banco" not in rejected.message


def test_an_approval_includes_the_amount(advisor_client: APIClient, filed: Filing) -> None:
    recorded(advisor_client, filed, "APPROVED", **APPROVED_BODY, internal_comment=INTERNAL)

    notice = only(NotificationType.BANK_APPROVED)
    assert notice.title == "¡Tu crédito fue aprobado!"
    assert notice.message == (
        "¡Tu crédito fue aprobado!\n\nMonto aprobado: $294.000.000 a 240 meses."
    )
    assert INTERNAL not in notice.message


def test_a_bank_rejection_notifies(advisor_client: APIClient, filed: Filing) -> None:
    recorded(advisor_client, filed, "REJECTED", **REJECTED_BODY)

    assert only(NotificationType.BANK_REJECTED).message == REJECTED_BODY["public_message"]


def test_a_disbursement_notifies_with_the_date(advisor_client: APIClient, filed: Filing) -> None:
    recorded(advisor_client, filed, "APPROVED", **APPROVED_BODY)
    application = CreditApplication.objects.get(pk=filed.application_id)
    assert (
        transition(
            advisor_client, application, "LEGALIZATION", version=application.version
        ).status_code
        == 200
    )

    disbursed = recorded(advisor_client, filed, "DISBURSED", **DISBURSED_BODY)

    notice = only(NotificationType.DISBURSED)
    assert notice.title == "Se desembolsó tu crédito"
    assert long_date(disbursed.received_at) in notice.message
    assert pesos(294_000_000) not in notice.message


def test_intermediate_responses_do_not_notify(advisor_client: APIClient, filed: Filing) -> None:
    recorded(advisor_client, filed, "RECEIVED")
    recorded(advisor_client, filed, "IN_ANALYSIS")
    recorded(advisor_client, filed, "OTHER", internal_comment=INTERNAL)

    assert set(Notification.objects.values_list("notification_type", flat=True)) == {
        NotificationType.READY_TO_FILE,
        NotificationType.FILED,
    }


def test_a_repeated_event_does_not_duplicate(advisor_client: APIClient, filed: Filing) -> None:
    response = recorded(advisor_client, filed, "REJECTED", **REJECTED_BODY)
    application = CreditApplication.objects.get(pk=filed.application_id)

    for _ in range(2):
        filing_response_recorded.send(
            sender=FilingResponse,
            response=response,
            filing=filed,
            application=application,
            status_changed=False,
            actor=None,
        )

    assert len(of_type(NotificationType.BANK_REJECTED)) == 1
    assert (
        NotificationDelivery.objects.filter(
            notification__notification_type=NotificationType.BANK_REJECTED
        ).count()
        == 2
    )


# --- Errores y casos borde --------------------------------------------------------------


def test_an_error_in_the_subscriber_does_not_break_the_operation(
    advisor_client: APIClient,
    filed: Filing,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("base caída")

    monkeypatch.setattr(services, "notify_client", broken)

    with caplog.at_level(logging.ERROR, logger="apps.notifications.receivers"):
        response = recorded(advisor_client, filed, "REJECTED", **REJECTED_BODY)

    assert response.filing.application.status == ApplicationStatus.REJECTED
    assert not of_type(NotificationType.BANK_REJECTED)
    assert "No se pudo crear la notificación (on_filing_response_recorded)" in caplog.text


def test_an_application_without_an_active_holder_is_not_notified(
    application: CreditApplication,
    primary: ApplicationParticipant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ApplicationParticipant.objects.filter(pk=primary.pk).update(is_active=False)

    with caplog.at_level(logging.WARNING, logger="apps.notifications.receivers"):
        receivers.on_application_status_changed(
            sender=CreditApplication,
            application=application,
            to_status=ApplicationStatus.READY_TO_FILE,
        )

    assert not Notification.objects.exists()
    assert "sin titular activo" in caplog.text


def test_a_rejection_without_an_active_holder_is_not_notified(
    advisor_client: APIClient,
    uploaded: ApplicationDocumentSlot,
    primary: ApplicationParticipant,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        assert reject(advisor_client, uploaded).status_code == 200
    Notification.objects.all().delete()
    ApplicationParticipant.objects.filter(pk=primary.pk).update(is_active=False)

    receivers.on_document_reviewed(sender=DocumentReview, review=DocumentReview.objects.get())

    assert not Notification.objects.exists()


# --- Textos -----------------------------------------------------------------------------


def test_every_type_has_its_texts() -> None:
    values = {
        "next_action": "x",
        "document": "x",
        "buyer_comment": "x",
        "bank": "x",
        "date": "x",
        "public_message": "x",
        "approval": "",
    }
    for notification_type in NotificationType.values:
        rendered = render(notification_type, **values)
        assert rendered.title and rendered.message


def test_a_long_title_is_cut_to_the_column() -> None:
    rendered = render(NotificationType.DOCUMENT_REJECTED, document="x" * 300, buyer_comment="y")

    assert len(rendered.title) == 180
    assert rendered.title.endswith("…")


def test_dates_and_amounts_are_written_for_the_buyer() -> None:
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    # 2026-11-18 03:00 UTC es aún el 17 en Bogotá.
    assert long_date(datetime(2026, 11, 18, 3, tzinfo=ZoneInfo("UTC"))) == "17 de noviembre de 2026"
    assert long_date(date(2026, 1, 5)) == "5 de enero de 2026"
    assert pesos(1_500) == "$1.500"
