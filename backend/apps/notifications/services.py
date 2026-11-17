"""Crear, listar y marcar notificaciones (paso 13).

- Una notificación por ``deduplication_key``: si el evento llega dos veces, la segunda
  no crea nada (``get_or_create``).
- Al crearla se crean sus dos entregas: ``PORTAL`` (``SENT`` de inmediato) y ``EMAIL``
  (``PENDING``, con el correo del comprador como destino).
- El comprador solo ve las de su cliente en la solicitud de su sesión.
"""

import logging
import uuid
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Prefetch, QuerySet
from django.utils import timezone

from apps.applications.models import ApplicationParticipant, CreditApplication, ParticipantRole
from apps.crm.models import Client
from apps.identity.models import BuyerSession
from apps.notifications.messages import render
from apps.notifications.models import (
    DeliveryChannel,
    DeliveryStatus,
    Notification,
    NotificationDelivery,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Created:
    notification: Notification
    created: bool


def primary_client(application_id: uuid.UUID) -> Client | None:
    """El titular activo de la solicitud: el destinatario de sus avisos."""
    participant = (
        ApplicationParticipant.objects.select_related("client")
        .filter(application_id=application_id, role=ParticipantRole.PRIMARY, is_active=True)
        .first()
    )
    return participant.client if participant is not None else None


def notify_client(
    client: Client,
    application: CreditApplication,
    notification_type: str,
    *,
    source_id: object,
    **values: object,
) -> Created:
    """Crea la notificación ``notification_type`` para ``client``, una sola vez por
    ``<tipo>:<source_id>``, con sus entregas."""
    key = f"{notification_type}:{source_id}"
    rendered = render(notification_type, **values)
    with transaction.atomic():
        notification, created = Notification.objects.get_or_create(
            deduplication_key=key,
            defaults={
                "client": client,
                "application": application,
                "notification_type": notification_type,
                "title": rendered.title,
                "message": rendered.message,
            },
        )
        if created:
            now = timezone.now()
            NotificationDelivery.objects.bulk_create(
                [
                    NotificationDelivery(
                        notification=notification,
                        channel=DeliveryChannel.PORTAL,
                        status=DeliveryStatus.SENT,
                        attempt_count=1,
                        sent_at=now,
                    ),
                    NotificationDelivery(
                        notification=notification,
                        channel=DeliveryChannel.EMAIL,
                        destination=client.email or None,
                        status=DeliveryStatus.PENDING,
                        next_attempt_at=now,
                    ),
                ]
            )
    if created:
        logger.info(
            "Notificación %s (%s) creada para la solicitud %s",
            notification.pk,
            notification_type,
            application.code,
        )
    return Created(notification=notification, created=created)


# --- Comprador --------------------------------------------------------------------------


def buyer_notifications(session: BuyerSession) -> QuerySet[Notification]:
    """Las de su cliente en la solicitud de la sesión, de la más nueva a la más vieja."""
    return Notification.objects.filter(
        client_id=session.client_id, application_id=session.application_id
    ).order_by("-created_at", "-id")


def unread_count(session: BuyerSession) -> int:
    return buyer_notifications(session).filter(read_at__isnull=True).count()


def mark_read(notification: Notification) -> Notification:
    """Idempotente: una notificación ya leída conserva su ``read_at``."""
    if notification.read_at is None:
        now = timezone.now()
        updated = Notification.objects.filter(pk=notification.pk, read_at__isnull=True).update(
            read_at=now
        )
        if updated:
            notification.read_at = now
        else:
            notification.refresh_from_db(fields=["read_at"])
    return notification


def mark_all_read(session: BuyerSession) -> int:
    """Marca las no leídas y devuelve cuántas marcó."""
    return buyer_notifications(session).filter(read_at__isnull=True).update(read_at=timezone.now())


# --- Backoffice -------------------------------------------------------------------------


def application_notifications(application: CreditApplication) -> QuerySet[Notification]:
    """Todas las de la solicitud, con sus entregas, para que el asesor vea si el correo
    salió."""
    return (
        Notification.objects.filter(application=application)
        .prefetch_related(
            Prefetch("deliveries", queryset=NotificationDelivery.objects.order_by("channel"))
        )
        .order_by("-created_at", "-id")
    )
