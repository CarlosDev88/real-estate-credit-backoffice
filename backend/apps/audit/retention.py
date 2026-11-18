"""Retención de la auditoría: ``purge_audit_events`` borra lo más viejo que
``AUDIT_RETENTION_DAYS``. Es la única forma de borrar eventos."""

from datetime import timedelta

from django.utils import timezone

from apps.audit.models import AuditEvent, allow_purge

AUDIT_RETENTION_DAYS = 365


def purge_audit_events(*, days: int = AUDIT_RETENTION_DAYS) -> int:
    """Borra los eventos con ``created_at`` anterior a hace ``days`` días. Devuelve cuántos."""
    cutoff = timezone.now() - timedelta(days=days)
    with allow_purge():
        deleted, _ = AuditEvent.objects.filter(created_at__lt=cutoff).delete()
    return deleted
