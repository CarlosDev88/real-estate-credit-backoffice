import uuid
from datetime import datetime
from typing import Any

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class InvitationStatus(models.TextChoices):
    """Estado derivado de las fechas; no se guarda en una columna."""

    PENDING = "PENDING", "Pendiente"
    ACCEPTED = "ACCEPTED", "Aceptada"
    REVOKED = "REVOKED", "Revocada"
    EXPIRED = "EXPIRED", "Vencida"


class InternalInvitation(models.Model):
    """Invitación para que un usuario interno cree su contraseña.

    Existe antes que la cuenta: al aceptarla se crea el usuario (o se vincula uno
    existente sin contraseña), se le asigna el rol y, si la invitación es para una
    constructora, se crea su membresía. Solo se guarda el hash del token.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    role = models.ForeignKey("identity.Role", on_delete=models.RESTRICT, related_name="invitations")
    # Solo para el rol CONSTRUCTION_PARTNER: la constructora a la que se une.
    partner = models.ForeignKey(
        "partners.Partner",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="invitations",
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations_sent",
    )

    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "internal_invitations"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_at__gt=models.F("created_at")),
                name="ck_internal_invitations_expiry",
            ),
            models.CheckConstraint(
                condition=Q(consumed_at__isnull=True) | Q(revoked_at__isnull=True),
                name="ck_internal_invitations_terminal",
            ),
        ]
        indexes = [models.Index(fields=["email"], name="ix_internal_invitations_email")]

    def __str__(self) -> str:
        return f"Invitación a {self.email}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    def status_at(self, moment: datetime | None = None) -> str:
        if self.consumed_at is not None:
            return InvitationStatus.ACCEPTED
        if self.revoked_at is not None:
            return InvitationStatus.REVOKED
        if self.expires_at <= (moment or timezone.now()):
            return InvitationStatus.EXPIRED
        return InvitationStatus.PENDING

    @property
    def status(self) -> str:
        return self.status_at()


def invitation_status_filter(status: str, moment: datetime | None = None) -> Q:
    """Filtro de base de datos equivalente a ``InternalInvitation.status``."""
    now = moment or timezone.now()
    open_invitation = Q(consumed_at__isnull=True, revoked_at__isnull=True)
    return {
        InvitationStatus.ACCEPTED: Q(consumed_at__isnull=False),
        InvitationStatus.REVOKED: Q(revoked_at__isnull=False),
        InvitationStatus.EXPIRED: open_invitation & Q(expires_at__lte=now),
        InvitationStatus.PENDING: open_invitation & Q(expires_at__gt=now),
    }[InvitationStatus(status)]
