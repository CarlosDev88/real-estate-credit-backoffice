"""Acceso passwordless del comprador (DER §4.9 y §4.10).

El comprador no es un ``User``: es un ``Client`` que entra con un enlace mágico de un
solo uso, ligado a una solicitud. Consumir el enlace crea una ``BuyerSession`` opaca,
temporal y revocable. Solo se guardan los hashes SHA-256 del enlace y de la sesión.
"""

import uuid
from datetime import datetime

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class BuyerAccessLinkStatus(models.TextChoices):
    """Estado derivado de las fechas; no se guarda en una columna."""

    PENDING = "PENDING", "Pendiente"
    CONSUMED = "CONSUMED", "Utilizado"
    REVOKED = "REVOKED", "Revocado"
    EXPIRED = "EXPIRED", "Vencido"


class BuyerAccessLink(models.Model):
    """Enlace mágico de un solo uso para que el comprador entre a una solicitud."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    client = models.ForeignKey(
        "crm.Client", on_delete=models.RESTRICT, related_name="buyer_access_links"
    )
    application = models.ForeignKey(
        "applications.CreditApplication",
        on_delete=models.RESTRICT,
        related_name="buyer_access_links",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="buyer_access_links_created",
    )
    # Ítem del catálogo `buyer_access_channel`.
    delivery_channel_item = models.ForeignKey(
        "catalogs.CatalogItem",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
    )

    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "buyer_access_links"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="ck_buyer_access_links_expiry",
            ),
            models.CheckConstraint(
                condition=Q(consumed_at__isnull=True) | Q(revoked_at__isnull=True),
                name="ck_buyer_access_links_terminal",
            ),
        ]
        indexes = [
            models.Index(
                fields=["application", "expires_at"],
                name="ix_buyer_access_links_pending",
                condition=Q(consumed_at__isnull=True, revoked_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f"Enlace {self.id} de {self.application_id}"

    def status_at(self, moment: datetime | None = None) -> str:
        if self.consumed_at is not None:
            return BuyerAccessLinkStatus.CONSUMED
        if self.revoked_at is not None:
            return BuyerAccessLinkStatus.REVOKED
        if self.expires_at <= (moment or timezone.now()):
            return BuyerAccessLinkStatus.EXPIRED
        return BuyerAccessLinkStatus.PENDING

    @property
    def status(self) -> str:
        return self.status_at()


def buyer_access_link_status_filter(status: str, moment: datetime | None = None) -> Q:
    """Filtro de base de datos equivalente a ``BuyerAccessLink.status``."""
    now = moment or timezone.now()
    open_link = Q(consumed_at__isnull=True, revoked_at__isnull=True)
    return {
        BuyerAccessLinkStatus.CONSUMED: Q(consumed_at__isnull=False),
        BuyerAccessLinkStatus.REVOKED: Q(revoked_at__isnull=False),
        BuyerAccessLinkStatus.EXPIRED: open_link & Q(expires_at__lte=now),
        BuyerAccessLinkStatus.PENDING: open_link & Q(expires_at__gt=now),
    }[BuyerAccessLinkStatus(status)]


class BuyerSession(models.Model):
    """Sesión temporal del comprador, creada al consumir un enlace.

    Repite ``client`` y ``application`` del enlace (DER §4.10) para validar el
    alcance en cada petición sin otra consulta.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Un enlace se consume una sola vez, así que crea como máximo una sesión.
    access_link = models.OneToOneField(
        BuyerAccessLink, on_delete=models.RESTRICT, related_name="session"
    )
    client = models.ForeignKey(
        "crm.Client", on_delete=models.RESTRICT, related_name="buyer_sessions"
    )
    application = models.ForeignKey(
        "applications.CreditApplication",
        on_delete=models.RESTRICT,
        related_name="buyer_sessions",
    )
    session_token_hash = models.CharField(max_length=64, unique=True)

    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(
        protocol="both", unpack_ipv4=True, null=True, blank=True
    )
    user_agent_summary = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "buyer_sessions"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="ck_buyer_sessions_expiry",
            ),
        ]
        indexes = [
            # Revocar las otras sesiones vivas del mismo comprador y solicitud.
            models.Index(
                fields=["application", "client"],
                name="ix_buyer_sessions_open",
                condition=Q(revoked_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f"Sesión de comprador {self.id} en {self.application_id}"

    def is_active_at(self, moment: datetime | None = None) -> bool:
        moment = moment or timezone.now()
        return self.revoked_at is None and self.expires_at > moment
