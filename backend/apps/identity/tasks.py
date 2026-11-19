"""Tareas de Celery de identidad: los correos de recuperación y de invitación (SEC-14).

La petición solo encola, después del commit; el token en claro se genera en el worker,
así que nunca pasa por el broker. Un fallo del envío queda en el log y nunca llega a la
respuesta. Sin reintentos: quien no reciba el correo lo vuelve a pedir (o el
administrador reenvía la invitación). En el modo local simple
(``CELERY_TASK_ALWAYS_EAGER``) la tarea corre en el mismo proceso, igual sin propagar el
error.
"""

import logging
import uuid
from typing import Any

from celery import shared_task
from kombu.exceptions import OperationalError

logger = logging.getLogger(__name__)


@shared_task
def send_password_reset(email: str, requested_ip: str | None) -> None:
    """Crea el token de recuperación y envía el correo, si el usuario existe."""
    from apps.identity.services import issue_password_reset

    try:
        issue_password_reset(email=email, requested_ip=requested_ip)
    except Exception:
        # Sin el correo en el mensaje: el log no confirma qué cuentas existen.
        logger.exception("No se pudo enviar el correo de recuperación de contraseña")


@shared_task
def send_invitation(invitation_id: str) -> None:
    """Genera el token de la invitación pendiente y envía el correo."""
    from apps.identity.invitations import issue_invitation_token

    try:
        issue_invitation_token(uuid.UUID(invitation_id))
    except Exception:
        logger.exception("No se pudo enviar el correo de la invitación %s", invitation_id)


def enqueue(task: Any, *args: Any) -> None:
    """Encola la tarea. Si el broker no responde, se registra y la petición sigue."""
    try:
        task.delay(*args)
    except OperationalError:
        logger.warning("No se pudo encolar la tarea %s", task.name)
