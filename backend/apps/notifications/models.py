"""Notificaciones y sus entregas por canal (REQ §4.5, API §21.2, paso 13).

La notificación en el portal es la fuente de verdad. El correo es una entrega más: si
falla, la notificación sigue ahí y la operación que la originó no se revierte.
"""

import uuid

from django.db import models
from django.db.models import F, Q


class NotificationType(models.TextChoices):
    """Eventos que avisan al comprador. Su título y mensaje están en
    ``apps.notifications.messages.MESSAGES``."""

    ACCESS_GRANTED = "ACCESS_GRANTED", "Acceso al portal"
    DOCUMENT_REJECTED = "DOCUMENT_REJECTED", "Documento por corregir"
    READY_TO_FILE = "READY_TO_FILE", "Expediente completo"
    FILED = "FILED", "Solicitud radicada"
    BANK_RETURNED = "BANK_RETURNED", "Devolución del banco"
    BANK_APPROVED = "BANK_APPROVED", "Crédito aprobado"
    BANK_REJECTED = "BANK_REJECTED", "Crédito rechazado"
    DISBURSED = "DISBURSED", "Crédito desembolsado"


class DeliveryChannel(models.TextChoices):
    EMAIL = "EMAIL", "Correo electrónico"
    PORTAL = "PORTAL", "Portal"


class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "Pendiente"
    SENT = "SENT", "Enviada"
    FAILED = "FAILED", "Fallida"


class Notification(models.Model):
    """Aviso para un comprador (``client``) o un usuario interno (``user``), nunca
    ambos. En este paso solo se crean para el comprador.

    ``deduplication_key`` es el tipo más el id del objeto que la origina: un evento
    repetido no crea otra.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    client = models.ForeignKey(
        "crm.Client",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="notifications",
    )
    user = models.ForeignKey(
        "identity.User",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="notifications",
    )
    application = models.ForeignKey(
        "applications.CreditApplication",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="notifications",
    )
    # Sin `CHECK`, como en el SQL: los tipos internos llegarán después.
    notification_type = models.CharField(max_length=80, choices=NotificationType.choices)
    title = models.CharField(max_length=180)
    # Texto público: nunca lleva notas internas.
    message = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True)
    deduplication_key = models.CharField(max_length=180, unique=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(client__isnull=False) & Q(user__isnull=True))
                | (Q(client__isnull=True) & Q(user__isnull=False)),
                name="ck_notifications_recipient",
            ),
        ]
        indexes = [
            models.Index(
                F("client"),
                F("created_at").desc(),
                condition=Q(read_at__isnull=True),
                name="ix_notifications_client_unread",
            ),
            models.Index(
                F("user"),
                F("created_at").desc(),
                condition=Q(read_at__isnull=True),
                name="ix_notifications_user_unread",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.notification_type}: {self.title}"


class NotificationDelivery(models.Model):
    """Entrega de una notificación por un canal. ``PORTAL`` queda ``SENT`` al crearse;
    ``EMAIL`` empieza ``PENDING`` y la envía la tarea de correo."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="deliveries"
    )
    channel = models.CharField(max_length=20, choices=DeliveryChannel.choices)
    # El correo del destinatario; nulo en el portal o si no tiene correo.
    destination = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    # `PositiveSmallIntegerField` ya crea el `CHECK (attempt_count >= 0)` del SQL.
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=180, null=True, blank=True)
    last_error_code = models.CharField(max_length=80, null=True, blank=True)

    class Meta:
        db_table = "notification_deliveries"
        ordering = ["channel"]
        constraints = [
            models.CheckConstraint(
                condition=Q(channel__in=DeliveryChannel.values),
                name="ck_notification_deliveries_channel",
            ),
            models.CheckConstraint(
                condition=Q(status__in=DeliveryStatus.values),
                name="ck_notification_deliveries_status",
            ),
            models.CheckConstraint(
                condition=~Q(status=DeliveryStatus.SENT) | Q(sent_at__isnull=False),
                name="ck_notification_deliveries_sent",
            ),
            # Desvío del SQL: una entrega por canal, para que reintentar no duplique.
            models.UniqueConstraint(
                fields=["notification", "channel"], name="uq_notification_deliveries_channel"
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "next_attempt_at"],
                condition=Q(status__in=[DeliveryStatus.PENDING, DeliveryStatus.FAILED]),
                # `ix_notification_deliveries_queue` en el SQL: Django admite 30 caracteres.
                name="ix_notification_delivery_queue",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.notification_id} {self.channel}: {self.status}"
