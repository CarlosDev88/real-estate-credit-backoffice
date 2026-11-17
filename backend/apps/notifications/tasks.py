"""Tareas de Celery de las notificaciones. Reciben ids y son idempotentes."""

import logging
import uuid

from celery import shared_task
from django.conf import settings
from kombu.exceptions import OperationalError

from apps.documents.tasks import log_eager_failure
from apps.notifications.emails import deliver_email

logger = logging.getLogger(__name__)


@shared_task(acks_late=True)
def deliver_notification_email(delivery_id: str) -> str | None:
    """Un intento de envío del correo de la entrega.

    Si falla y quedan reintentos, se vuelve a encolar con la espera que toca. En el modo
    inmediato (``CELERY_TASK_ALWAYS_EAGER``) no: correría en el acto, sin esperar, así
    que la retoma ``retry_notification_deliveries`` cuando venza ``next_attempt_at``.
    """
    outcome = deliver_email(uuid.UUID(delivery_id))
    if outcome is None:
        return None
    if outcome.retry_in is not None and not settings.CELERY_TASK_ALWAYS_EAGER:
        deliver_notification_email.apply_async(
            (delivery_id,), countdown=int(outcome.retry_in.total_seconds())
        )
    return outcome.status


def enqueue_email(delivery_id: uuid.UUID) -> None:
    """Encola el envío. Si el broker no responde, la entrega sigue ``PENDING`` y la
    retoma ``retry_notification_deliveries``; la operación que avisó no se entera."""
    try:
        result = deliver_notification_email.delay(str(delivery_id))
    except OperationalError:
        logger.warning("No se pudo encolar el correo de la entrega %s", delivery_id)
        return
    log_eager_failure(result, f"Correo de la entrega {delivery_id}")
