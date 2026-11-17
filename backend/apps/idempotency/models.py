"""Claves ``Idempotency-Key`` de los ``POST`` críticos (API §6, paso 13).

Una fila por actor, clave, método y ruta. Mientras la operación corre,
``response_status`` es nulo; al terminar con un ``2xx`` guarda la respuesta. Son datos
técnicos: ``purge_idempotency_keys`` borra las vencidas.
"""

import uuid

from django.db import models
from django.db.models import F, Q


class IdempotencyKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(
        "identity.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="idempotency_keys",
    )
    buyer_session = models.ForeignKey(
        "identity.BuyerSession",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="idempotency_keys",
    )
    key = models.CharField(max_length=100)
    method = models.CharField(max_length=10)
    # La ruta de la petición, con sus ids (`/api/v1/filings/<id>/responses`).
    route_fingerprint = models.CharField(max_length=180)
    # SHA-256 del cuerpo JSON canónico (claves ordenadas).
    request_hash = models.CharField(max_length=64)
    response_status = models.SmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    # Desvío del SQL: las cabeceras que la respuesta repetida debe conservar (`ETag`).
    response_headers = models.JSONField(default=dict, blank=True)
    resource_id = models.UUIDField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "idempotency_keys"
        constraints = [
            models.CheckConstraint(
                condition=(Q(user__isnull=False) & Q(buyer_session__isnull=True))
                | (Q(user__isnull=True) & Q(buyer_session__isnull=False)),
                name="ck_idempotency_keys_actor",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="ck_idempotency_keys_expiry",
            ),
            # Desvío del SQL: únicas parciales. Con `NULLS NOT DISTINCT`, dos usuarios
            # internos (ambos con `buyer_session` nulo) chocarían en la del comprador.
            models.UniqueConstraint(
                fields=["user", "key", "method", "route_fingerprint"],
                condition=Q(user__isnull=False),
                name="uq_idempotency_keys_user",
            ),
            models.UniqueConstraint(
                fields=["buyer_session", "key", "method", "route_fingerprint"],
                condition=Q(buyer_session__isnull=False),
                name="uq_idempotency_keys_buyer",
            ),
        ]
        indexes = [models.Index(fields=["expires_at"], name="ix_idempotency_keys_expires")]

    def __str__(self) -> str:
        return f"{self.method} {self.route_fingerprint} ({self.key})"
