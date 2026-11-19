"""Exportaciones de reportes de demo (``seed_demo_data``, TAREA-brechas-3-demo): una
terminada (vigente 24 horas) y una vencida, las dos del administrador y de los últimos seis
meses.

Pasan por el servicio (``request_export`` y ``build_export``). Para la vencida, después de
armarla se mueven sus fechas cinco días atrás y ``purge_exports`` la deja ``EXPIRED`` (y
borra su CSV), como lo haría la tarea programada. Marca del bloque: alguna exportación del
administrador de demo.
"""

from datetime import timedelta

from django.utils import timezone

from apps.identity.models import User
from apps.reporting.export_jobs import build_export, purge_exports, request_export
from apps.reporting.filters import ReportFilters
from apps.reporting.models import ReportExportJob

PERIOD_DAYS = 180
EXPIRED_DAYS_AGO = 5


def exports_exist(admin: User) -> bool:
    return ReportExportJob.objects.filter(requested_by=admin).exists()


def _export(admin: User) -> ReportExportJob:
    today = timezone.localdate()
    job = request_export(
        admin, ReportFilters(date_from=today - timedelta(days=PERIOD_DAYS), date_to=today)
    )
    # Con tareas inmediatas ya se armó al confirmar; si no, se arma aquí (es idempotente).
    build_export(job.pk)
    job.refresh_from_db()
    return job


def seed_exports(admin: User) -> list[ReportExportJob]:
    """Quien llama comprueba ``exports_exist``."""
    expired = _export(admin)
    shift = timedelta(days=EXPIRED_DAYS_AGO)
    ReportExportJob.objects.filter(pk=expired.pk).update(
        created_at=expired.created_at - shift,
        started_at=expired.started_at - shift if expired.started_at else None,
        completed_at=expired.completed_at - shift if expired.completed_at else None,
        expires_at=expired.expires_at - shift if expired.expires_at else None,
    )
    purge_exports()
    completed = _export(admin)
    return [expired, completed]
