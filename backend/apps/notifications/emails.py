"""Correo transaccional de las notificaciones (Parte 2 del paso 13, REQ §9.2).

- Destino: el correo del cliente que quedó en la entrega. Sin correo, la entrega queda
  ``FAILED`` con ``NO_DESTINATION`` y no se reintenta.
- Un intento por ejecución de la tarea. Si falla, la entrega sigue ``PENDING`` con su
  ``next_attempt_at``: hasta 5 reintentos (1, 5, 15, 60 y 240 minutos después de cada
  fallo). Si falla el último, queda ``FAILED``.
- Contenido: el título como asunto, el mensaje público y la línea del portal. Sin
  enlace mágico (los emite el asesor), sin adjuntos y sin notas internas.
- Es idempotente: la fila se bloquea, y una entrega que no está ``PENDING`` o cuyo
  próximo intento aún no llega no se toca.
"""

import logging
import smtplib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.mail.message import make_msgid
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.notifications.models import DeliveryChannel, DeliveryStatus, NotificationDelivery

logger = logging.getLogger(__name__)

PORTAL_LINE = (
    "Entra a tu portal con el enlace que te envió tu asesor; si se venció, pídele uno nuevo."
)

# Espera antes de cada reintento, después del fallo número 1, 2... (en minutos).
RETRY_DELAYS_MINUTES = (1, 5, 15, 60, 240)
MAX_ATTEMPTS = len(RETRY_DELAYS_MINUTES) + 1

NO_DESTINATION = "NO_DESTINATION"
SMTP_ERROR = "SMTP_ERROR"
CONNECTION_ERROR = "CONNECTION_ERROR"
SEND_FAILED = "SEND_FAILED"


@dataclass(frozen=True)
class Outcome:
    """Resultado de un intento. ``retry_in`` es la espera hasta el siguiente, si queda."""

    status: str
    retry_in: timedelta | None = None


def retry_delay(attempt_count: int) -> timedelta | None:
    """Espera después de ``attempt_count`` intentos fallidos, o ``None`` si se agotaron."""
    if attempt_count >= MAX_ATTEMPTS:
        return None
    return timedelta(minutes=RETRY_DELAYS_MINUTES[attempt_count - 1])


def _error_code(exc: Exception) -> str:
    if isinstance(exc, smtplib.SMTPException):
        return SMTP_ERROR
    if isinstance(exc, OSError):
        return CONNECTION_ERROR
    return SEND_FAILED


def build_message(delivery: NotificationDelivery) -> EmailMultiAlternatives:
    notification = delivery.notification
    assert notification.client is not None and delivery.destination
    context = {
        "first_names": notification.client.first_names,
        "title": notification.title,
        "message": notification.message,
        "portal_line": PORTAL_LINE,
    }
    message = EmailMultiAlternatives(
        subject=notification.title,
        body=render_to_string("notifications/email.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[delivery.destination],
        headers={"Message-ID": make_msgid()},
    )
    message.attach_alternative(render_to_string("notifications/email.html", context), "text/html")
    return message


def _is_due(delivery: NotificationDelivery, now: datetime) -> bool:
    return delivery.next_attempt_at is None or delivery.next_attempt_at <= now


def deliver_email(delivery_id: uuid.UUID) -> Outcome | None:
    """Un intento de envío. ``None`` si no había nada que hacer."""
    with transaction.atomic():
        delivery = (
            NotificationDelivery.objects.select_for_update(of=("self",))
            .select_related("notification__client")
            .filter(pk=delivery_id, channel=DeliveryChannel.EMAIL)
            .first()
        )
        now = timezone.now()
        if delivery is None or delivery.status != DeliveryStatus.PENDING:
            return None
        if not _is_due(delivery, now):
            return None
        fields = ["status", "attempt_count", "next_attempt_at", "last_error_code", "updated_at"]
        if not delivery.destination:
            delivery.status = DeliveryStatus.FAILED
            delivery.next_attempt_at = None
            delivery.last_error_code = NO_DESTINATION
            delivery.save(update_fields=fields)
            logger.warning("Entrega %s sin correo de destino: no se envía", delivery.pk)
            return Outcome(DeliveryStatus.FAILED)

        delivery.attempt_count += 1
        message = build_message(delivery)
        try:
            message.send()
        except Exception as exc:
            retry_in = retry_delay(delivery.attempt_count)
            delivery.last_error_code = _error_code(exc)
            if retry_in is None:
                delivery.status = DeliveryStatus.FAILED
                delivery.next_attempt_at = None
            else:
                delivery.next_attempt_at = now + retry_in
            delivery.save(update_fields=fields)
            logger.warning(
                "Correo de la entrega %s fallido (intento %s, %s): %s",
                delivery.pk,
                delivery.attempt_count,
                delivery.last_error_code,
                type(exc).__name__,
            )
            return Outcome(delivery.status, retry_in)

        delivery.status = DeliveryStatus.SENT
        delivery.sent_at = now
        delivery.next_attempt_at = None
        delivery.last_error_code = None
        delivery.provider_message_id = message.extra_headers["Message-ID"]
        delivery.save(update_fields=[*fields, "sent_at", "provider_message_id"])
    logger.info("Correo de la entrega %s enviado (intento %s)", delivery.pk, delivery.attempt_count)
    return Outcome(DeliveryStatus.SENT)
