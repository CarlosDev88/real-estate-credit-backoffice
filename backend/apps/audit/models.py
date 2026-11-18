import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from django.db import models
from django.db.models import Q

from apps.audit.actions import AuditAction, AuditResult

# Solo `purge_audit_events` la activa, de forma explícita (``allow_purge``).
_purge_allowed: ContextVar[bool] = ContextVar("audit_purge_allowed", default=False)


class AuditImmutable(Exception):
    """Un evento de auditoría no se modifica ni se borra (salvo la retención)."""


@contextmanager
def allow_purge() -> Iterator[None]:
    token = _purge_allowed.set(True)
    try:
        yield
    finally:
        _purge_allowed.reset(token)


class AuditEventQuerySet(models.QuerySet["AuditEvent"]):
    def update(self, **kwargs: Any) -> int:
        raise AuditImmutable("Los eventos de auditoría no se modifican.")

    def delete(self) -> tuple[int, dict[str, int]]:
        if not _purge_allowed.get():
            raise AuditImmutable("Los eventos de auditoría solo se borran con la retención.")
        return super().delete()


class AuditEvent(models.Model):
    """Bitácora técnica inmutable (API §24.1, REQ §9). Solo se crea con
    ``apps.audit.services.record_audit``.

    Desvío del SQL: ``request_id`` es texto (hasta 64), porque ``RequestIDMiddleware``
    acepta el identificador que manda el cliente aunque no sea un UUID.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    actor_user = models.ForeignKey(
        "identity.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    actor_buyer_session = models.ForeignKey(
        "identity.BuyerSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    action = models.CharField(max_length=100, choices=AuditAction.choices)
    resource_type = models.CharField(max_length=80)
    resource_id = models.UUIDField(null=True, blank=True)
    result = models.CharField(max_length=20, choices=AuditResult.choices)
    request_id = models.CharField(max_length=64)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        db_table = "audit_events"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(actor_user__isnull=True) | Q(actor_buyer_session__isnull=True),
                name="ck_audit_events_actor",
            ),
            models.CheckConstraint(
                condition=Q(result__in=AuditResult.values), name="ck_audit_events_result"
            ),
        ]
        indexes = [
            models.Index(fields=["-created_at"], name="ix_audit_created"),
            models.Index(
                fields=["resource_type", "resource_id", "-created_at"], name="ix_audit_resource"
            ),
            models.Index(fields=["actor_user", "-created_at"], name="ix_audit_user"),
            models.Index(fields=["request_id"], name="ix_audit_request"),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.result}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AuditImmutable("Los eventos de auditoría no se modifican.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise AuditImmutable("Los eventos de auditoría no se borran.")
