import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class PartnerStatus(models.TextChoices):
    """Estados de partner y de membresía (mismos valores en el esquema)."""

    ACTIVE = "ACTIVE", "Activo"
    INACTIVE = "INACTIVE", "Inactivo"


class Partner(models.Model):
    """Constructora aliada. No es un tenant: solo delimita el acceso a sus proyectos."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    legal_name = models.CharField(max_length=180)
    trade_name = models.CharField(max_length=180, blank=True)
    # NIT normalizado con dígito de verificación, por ejemplo `900123456-8`.
    tax_id = models.CharField(max_length=30, unique=True)
    status = models.CharField(
        max_length=20, choices=PartnerStatus.choices, default=PartnerStatus.ACTIVE
    )

    contact_name = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)

    # Archivo lógico: el partner conserva su historial, pero deja de listarse.
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "partners"
        ordering = ["legal_name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=PartnerStatus.values), name="ck_partners_status"
            ),
        ]

    def __str__(self) -> str:
        return self.trade_name or self.legal_name

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.contact_email = (self.contact_email or "").strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_active(self) -> bool:
        return self.status == PartnerStatus.ACTIVE and self.deleted_at is None


class PartnerMembership(models.Model):
    """Vínculo entre un usuario interno y una constructora.

    En el MVP un usuario tiene como máximo una membresía activa. Finalizar una
    membresía no la borra: se marca inactiva con fecha de fin para conservar el
    historial.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    partner = models.ForeignKey(Partner, on_delete=models.RESTRICT, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="partner_memberships",
    )
    job_title = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=20, choices=PartnerStatus.choices, default=PartnerStatus.ACTIVE
    )
    started_at = models.DateField()
    ended_at = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "partner_memberships"
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["partner", "user", "started_at"],
                name="uq_partner_memberships_partner_user_start",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status=PartnerStatus.ACTIVE, ended_at__isnull=True),
                name="uq_partner_memberships_active_user",
            ),
            models.CheckConstraint(
                condition=Q(status__in=PartnerStatus.values),
                name="ck_partner_memberships_status",
            ),
            models.CheckConstraint(
                condition=Q(ended_at__isnull=True) | Q(ended_at__gte=F("started_at")),
                name="ck_partner_memberships_dates",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} en {self.partner_id}"

    @property
    def is_current(self) -> bool:
        return self.status == PartnerStatus.ACTIVE and self.ended_at is None
