"""Avisos del comprador y entregas de correo de demo (``seed_demo_data``,
TAREA-brechas-3-demo).

Los avisos los crean las señales de la propia demo (documentos rechazados, radicaciones,
respuestas del banco, desembolsos). Este bloque solo los lleva a estados que la siembra no
alcanza por sí sola:

- leídos: la mitad de los avisos de la historia de seis meses (``mark_read``, con la
  fecha de lectura poco después del aviso); los demás quedan sin leer;
- una entrega de correo fallida con reintento programado (``PENDING``, un intento,
  ``SMTP_TIMEOUT``) y otra fallida del todo (``FAILED`` tras agotar los intentos). En
  local el correo nunca falla, así que estas dos se escriben con ``update()``.

Marca del bloque: la entrega con ``last_error_code`` ``DEMO_ERROR_CODE``.
"""

from datetime import timedelta

from django.utils import timezone

from apps.notifications.emails import MAX_ATTEMPTS
from apps.notifications.models import (
    DeliveryChannel,
    DeliveryStatus,
    Notification,
    NotificationDelivery,
)
from apps.notifications.services import mark_read

DEMO_ERROR_CODE = "SMTP_TIMEOUT"
FINAL_ERROR_CODE = "SMTP_MAILBOX_UNAVAILABLE"


def notification_states_exist() -> bool:
    return NotificationDelivery.objects.filter(
        last_error_code__in=(DEMO_ERROR_CODE, FINAL_ERROR_CODE)
    ).exists()


def seed_notification_states(document_prefix: str) -> int:
    """``document_prefix``: el de los clientes de la historia. Devuelve cuántos avisos
    tocó."""
    notifications = list(
        Notification.objects.filter(client__document_number__startswith=document_prefix).order_by(
            "created_at", "id"
        )
    )
    touched = 0
    for notification in notifications[::2]:
        mark_read(notification)
        Notification.objects.filter(pk=notification.pk).update(
            read_at=min(notification.created_at + timedelta(hours=5), timezone.now())
        )
        touched += 1
    emails = NotificationDelivery.objects.filter(
        notification__in=[n.pk for n in notifications[1::2]],
        channel=DeliveryChannel.EMAIL,
        status=DeliveryStatus.SENT,
    ).order_by("-created_at")
    retrying, failed = emails[:1], emails[1:2]
    for delivery in retrying:
        NotificationDelivery.objects.filter(pk=delivery.pk).update(
            status=DeliveryStatus.PENDING,
            sent_at=None,
            provider_message_id=None,
            attempt_count=1,
            last_error_code=DEMO_ERROR_CODE,
            next_attempt_at=timezone.now() + timedelta(minutes=30),
        )
        touched += 1
    for delivery in failed:
        NotificationDelivery.objects.filter(pk=delivery.pk).update(
            status=DeliveryStatus.FAILED,
            sent_at=None,
            provider_message_id=None,
            attempt_count=MAX_ATTEMPTS,
            last_error_code=FINAL_ERROR_CODE,
            next_attempt_at=None,
        )
        touched += 1
    return touched
