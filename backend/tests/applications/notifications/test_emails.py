"""Correo transaccional de las notificaciones (Parte 2 del paso 13): envío, sin destino,
reintentos con espera, fallo definitivo, comando de reintento y contenido."""

import logging
import smtplib
from collections.abc import Callable
from datetime import timedelta
from io import StringIO
from typing import Any

import pytest
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.core.management import call_command
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.applications.models import CreditApplication
from apps.crm.models import Client
from apps.notifications import emails, services, tasks
from apps.notifications.emails import PORTAL_LINE, deliver_email, retry_delay
from apps.notifications.models import (
    DeliveryChannel,
    DeliveryStatus,
    Notification,
    NotificationDelivery,
    NotificationType,
)
from tests.applications.notifications.conftest import NotificationFactory

pytestmark = pytest.mark.django_db

Capture = Callable[..., Any]

EMAIL = "laura@example.com"


@pytest.fixture
def buyer_email(buyer: Client) -> Client:
    Client.objects.filter(pk=buyer.pk).update(email=EMAIL)
    buyer.refresh_from_db()
    return buyer


def email_of(notification: Notification) -> NotificationDelivery:
    return notification.deliveries.get(channel=DeliveryChannel.EMAIL)


def fail_with(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> list[int]:
    """Cada envío lanza ``exc``; devuelve la lista de intentos."""
    calls: list[int] = []

    def broken(self: EmailMultiAlternatives, fail_silently: bool = False) -> int:
        calls.append(1)
        raise exc

    monkeypatch.setattr(EmailMultiAlternatives, "send", broken)
    return calls


def sent_message() -> EmailMultiAlternatives:
    (message,) = mail.outbox
    assert isinstance(message, EmailMultiAlternatives)
    return message


def make_due(delivery: NotificationDelivery) -> None:
    NotificationDelivery.objects.filter(pk=delivery.pk).update(
        next_attempt_at=timezone.now() - timedelta(seconds=1)
    )


# --- Envío ------------------------------------------------------------------------------


def test_the_email_goes_out_after_the_commit(
    buyer_email: Client,
    application: CreditApplication,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        created = services.notify_client(
            buyer_email,
            application,
            NotificationType.BANK_REJECTED,
            source_id="r-1",
            public_message="El banco no aprobó por políticas de riesgo.",
        )

    message = sent_message()
    assert message.to == [EMAIL]
    assert message.subject == "El banco rechazó tu solicitud"
    assert message.body.startswith("Hola Laura,")
    assert "El banco no aprobó por políticas de riesgo." in message.body
    assert PORTAL_LINE in message.body
    ((html, mime),) = message.alternatives
    assert mime == "text/html"
    assert "El banco no aprobó por políticas de riesgo." in str(html)
    assert message.attachments == []
    delivery = email_of(created.notification)
    assert (delivery.status, delivery.attempt_count) == (DeliveryStatus.SENT, 1)
    assert delivery.sent_at is not None and delivery.next_attempt_at is None
    assert delivery.provider_message_id == message.extra_headers["Message-ID"]
    assert delivery.last_error_code is None


def test_a_repeated_event_sends_a_single_email(
    buyer_email: Client,
    application: CreditApplication,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        for _ in range(2):
            services.notify_client(
                buyer_email, application, NotificationType.READY_TO_FILE, source_id="x"
            )

    assert len(mail.outbox) == 1


def test_a_delivery_is_sent_only_once(
    buyer_email: Client, make_notification: NotificationFactory
) -> None:
    notification = make_notification()
    portal_delivery = notification.deliveries.get(channel=DeliveryChannel.PORTAL)

    assert deliver_email(email_of(notification).pk) is not None
    assert deliver_email(email_of(notification).pk) is None
    assert deliver_email(portal_delivery.pk) is None
    assert len(mail.outbox) == 1


def test_without_email_the_delivery_fails_without_retries(
    make_notification: NotificationFactory, caplog: pytest.LogCaptureFixture
) -> None:
    delivery = email_of(make_notification())
    assert delivery.destination is None

    with caplog.at_level(logging.WARNING, logger="apps.notifications.emails"):
        outcome = deliver_email(delivery.pk)

    assert outcome == emails.Outcome(DeliveryStatus.FAILED)
    delivery.refresh_from_db()
    assert (delivery.status, delivery.last_error_code) == (DeliveryStatus.FAILED, "NO_DESTINATION")
    assert (delivery.attempt_count, delivery.next_attempt_at) == (0, None)
    assert mail.outbox == []
    assert "sin correo de destino" in caplog.text


# --- Reintentos -------------------------------------------------------------------------


def test_a_failure_waits_for_the_next_attempt(
    buyer_email: Client, make_notification: NotificationFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    fail_with(monkeypatch, smtplib.SMTPServerDisconnected("se cayó"))
    delivery = email_of(make_notification())
    before = timezone.now()

    assert tasks.deliver_notification_email(str(delivery.pk)) == DeliveryStatus.PENDING

    delivery.refresh_from_db()
    assert delivery.status == DeliveryStatus.PENDING
    assert (delivery.attempt_count, delivery.last_error_code) == (1, "SMTP_ERROR")
    assert delivery.next_attempt_at is not None
    assert before + timedelta(minutes=1) <= delivery.next_attempt_at
    assert delivery.next_attempt_at <= timezone.now() + timedelta(minutes=1)
    # Antes de que venza, otro intento no hace nada.
    assert deliver_email(delivery.pk) is None


def test_the_retries_wait_longer_until_the_delivery_fails(
    buyer_email: Client, make_notification: NotificationFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fail_with(monkeypatch, ConnectionRefusedError())
    delivery = email_of(make_notification())
    waits = []

    for _ in range(6):
        make_due(delivery)
        outcome = deliver_email(delivery.pk)
        assert outcome is not None
        waits.append(outcome.retry_in)

    assert waits == [timedelta(minutes=minutes) for minutes in (1, 5, 15, 60, 240)] + [None]
    delivery.refresh_from_db()
    assert delivery.status == DeliveryStatus.FAILED
    assert (delivery.attempt_count, delivery.next_attempt_at) == (6, None)
    assert delivery.last_error_code == "CONNECTION_ERROR"
    make_due(delivery)
    assert deliver_email(delivery.pk) is None
    assert len(calls) == 6


def test_an_unexpected_error_is_recorded(
    buyer_email: Client, make_notification: NotificationFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    fail_with(monkeypatch, ValueError("plantilla rota"))
    delivery = email_of(make_notification())

    deliver_email(delivery.pk)

    delivery.refresh_from_db()
    assert delivery.last_error_code == "SEND_FAILED"


def test_retry_delays() -> None:
    assert [retry_delay(attempt) for attempt in range(1, 7)] == [
        timedelta(minutes=1),
        timedelta(minutes=5),
        timedelta(minutes=15),
        timedelta(minutes=60),
        timedelta(minutes=240),
        None,
    ]


def test_with_a_worker_the_task_schedules_its_retry(
    buyer_email: Client,
    make_notification: NotificationFactory,
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
) -> None:
    fail_with(monkeypatch, smtplib.SMTPException())
    scheduled: list[dict[str, Any]] = []
    monkeypatch.setattr(
        tasks.deliver_notification_email,
        "apply_async",
        lambda args, countdown: scheduled.append({"args": args, "countdown": countdown}),
    )
    settings.CELERY_TASK_ALWAYS_EAGER = False
    delivery = email_of(make_notification())

    tasks.deliver_notification_email(str(delivery.pk))

    assert scheduled == [{"args": (str(delivery.pk),), "countdown": 60}]


def test_in_local_mode_the_task_does_not_reschedule(
    buyer_email: Client, make_notification: NotificationFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    fail_with(monkeypatch, smtplib.SMTPException())
    scheduled: list[Any] = []
    monkeypatch.setattr(
        tasks.deliver_notification_email, "apply_async", lambda *a, **k: scheduled.append(a)
    )
    delivery = email_of(make_notification())

    tasks.deliver_notification_email(str(delivery.pk))
    assert tasks.deliver_notification_email(str(delivery.pk)) is None

    assert scheduled == []


def test_a_broker_outage_does_not_break_the_operation(
    make_notification: NotificationFactory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def down(*args: Any) -> None:
        raise OperationalError("sin broker")

    monkeypatch.setattr(tasks.deliver_notification_email, "delay", down)
    delivery = email_of(make_notification())

    with caplog.at_level(logging.WARNING, logger="apps.notifications.tasks"):
        tasks.enqueue_email(delivery.pk)

    delivery.refresh_from_db()
    assert delivery.status == DeliveryStatus.PENDING
    assert "No se pudo encolar el correo" in caplog.text


# --- Comando de reintento ---------------------------------------------------------------


def test_the_command_requeues_the_due_deliveries(
    buyer_email: Client, make_notification: NotificationFactory
) -> None:
    due = email_of(make_notification())
    later = email_of(make_notification())
    NotificationDelivery.objects.filter(pk=later.pk).update(
        next_attempt_at=timezone.now() + timedelta(minutes=5)
    )
    sent = email_of(make_notification())
    deliver_email(sent.pk)
    mail.outbox.clear()
    out = StringIO()

    call_command("retry_notification_deliveries", stdout=out)

    assert "Correos reencolados: 1." in out.getvalue()
    (message,) = mail.outbox
    assert message.to == [EMAIL]
    due.refresh_from_db()
    later.refresh_from_db()
    assert (due.status, later.status) == (DeliveryStatus.SENT, DeliveryStatus.PENDING)


# --- Contenido --------------------------------------------------------------------------


def test_the_email_carries_no_link_and_escapes_the_html(
    buyer_email: Client, application: CreditApplication
) -> None:
    created = services.notify_client(
        buyer_email,
        application,
        NotificationType.DOCUMENT_REJECTED,
        source_id="r-2",
        document="Cédula",
        buyer_comment="Súbela <b>legible</b>.",
    )

    deliver_email(email_of(created.notification).pk)

    message = sent_message()
    html = str(message.alternatives[0][0])
    assert "Súbela <b>legible</b>." in message.body
    assert "&lt;b&gt;legible&lt;/b&gt;" in html
    for text in (message.body, html):
        assert "http" not in text
        assert "token" not in text
