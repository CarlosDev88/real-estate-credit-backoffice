"""Consentimientos (DER §4.11 y §4.12).

Una ``ConsentDefinition`` es una versión publicada de un texto. No se edita: un texto
nuevo es una versión nueva, que se publica por migración. Un ``ConsentRecord`` es la
evidencia inmutable de que alguien aceptó o retiró una versión concreta.
"""

import hashlib
import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.db.models import F, Q


def consent_content_hash(body: str) -> str:
    """Huella SHA-256 del texto, para demostrar qué versión exacta se aceptó."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class ConsentDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    code = models.CharField(max_length=50)
    version = models.IntegerField()
    title = models.CharField(max_length=180)
    body = models.TextField()
    # La calcula `save()` a partir de `body`; nunca viene de la entrada.
    content_hash = models.CharField(max_length=64, editable=False)
    effective_from = models.DateTimeField()
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "consent_definitions"
        ordering = ["code", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["code", "version"], name="uq_consent_definitions_version"
            ),
            models.CheckConstraint(
                condition=Q(version__gt=0), name="ck_consent_definitions_version"
            ),
            models.CheckConstraint(
                condition=Q(retired_at__isnull=True) | Q(retired_at__gte=F("effective_from")),
                name="ck_consent_definitions_dates",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} v{self.version}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.content_hash = consent_content_hash(self.body)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "body" in update_fields:
            kwargs["update_fields"] = {*update_fields, "content_hash"}
        super().save(*args, **kwargs)


class ConsentAction(models.TextChoices):
    ACCEPTED = "ACCEPTED", "Aceptado"
    WITHDRAWN = "WITHDRAWN", "Retirado"


class ConsentRecord(models.Model):
    """Aceptación o retiro de una versión. Exactamente uno de ``client`` o ``user``."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    consent_definition = models.ForeignKey(
        ConsentDefinition, on_delete=models.RESTRICT, related_name="records"
    )
    client = models.ForeignKey(
        "crm.Client",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="consent_records",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="consent_records",
    )
    application = models.ForeignKey(
        "applications.CreditApplication",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="consent_records",
    )
    action = models.CharField(max_length=20, choices=ConsentAction.choices)

    ip_address = models.GenericIPAddressField(
        protocol="both", unpack_ipv4=True, null=True, blank=True
    )
    user_agent_summary = models.CharField(max_length=255, blank=True)
    buyer_session = models.ForeignKey(
        "identity.BuyerSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consent_records",
    )

    class Meta:
        db_table = "consent_records"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(client__isnull=False) & Q(user__isnull=True))
                | (Q(client__isnull=True) & Q(user__isnull=False)),
                name="ck_consent_records_actor",
            ),
            models.CheckConstraint(
                condition=Q(action__in=ConsentAction.values),
                name="ck_consent_records_action",
            ),
            models.CheckConstraint(
                condition=Q(buyer_session__isnull=True) | Q(client__isnull=False),
                name="ck_consent_records_buyer_session",
            ),
        ]
        indexes = [
            # Última acción de un cliente sobre cada definición, dentro de una solicitud.
            models.Index(
                F("application"),
                F("client"),
                F("consent_definition"),
                F("created_at").desc(),
                name="ix_consent_records_subject",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.consent_definition_id}"
