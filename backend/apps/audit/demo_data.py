"""Auditoría de demo (``seed_demo_data``, TAREA-brechas-3-demo): inicios de sesión
correctos y fallidos, un ``403``, descargas de documentos y una exportación, repartidos en
las últimas semanas.

La bitácora es inmutable: un trigger rechaza ``UPDATE`` y ``created_at`` lo pone la base
al insertar. Por eso estos eventos no se mueven después: se **insertan** ya con su fecha,
fijando el reloj de Django (``timezone.now``) mientras se guarda cada uno. Se arman con
``build_event``, igual que los del sistema, con la misma metadata que dejaría el gancho
de las vistas (``apps.audit.hooks``).

Marca del bloque: el ``request_id`` de los eventos empieza por ``REQUEST_ID_PREFIX``.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any
from unittest import mock

from django.utils import timezone

from apps.audit.actions import AuditAction, AuditResult
from apps.audit.models import AuditEvent
from apps.audit.sanitize import mask_email
from apps.audit.services import build_event
from apps.documents.models import DocumentFile
from apps.identity.models import User
from apps.reporting.models import ReportExportJob

REQUEST_ID_PREFIX = "demo-audit-"
DEMO_IP = "190.24.10.15"


def audit_exists() -> bool:
    return AuditEvent.objects.filter(request_id__startswith=REQUEST_ID_PREFIX).exists()


@contextmanager
def _clock(moment: datetime) -> Iterator[None]:
    with mock.patch("django.utils.timezone.now", return_value=moment):
        yield


def _save(
    number: int,
    moment: datetime,
    action: str,
    resource: Any,
    result: str,
    *,
    actor: User | None,
    metadata: dict[str, Any],
) -> None:
    event = build_event(action, resource, result, actor=actor, metadata=metadata)
    event.request_id = f"{REQUEST_ID_PREFIX}{number:03d}"
    event.ip_address = DEMO_IP
    with _clock(moment):
        event.save()


def _login_metadata(email: str, view: str = "LoginView") -> dict[str, Any]:
    return {
        "method": "POST",
        "path": "/api/v1/auth/login",
        "view": view,
        "email": mask_email(email),
    }


def seed_audit(
    *,
    admin: User,
    advisors: list[User],
    broker: User,
    partner_user: User | None,
) -> int:
    """Quien llama comprueba ``audit_exists``. Devuelve cuántos eventos insertó."""
    now = timezone.now()
    events: list[tuple[datetime, str, Any, str, User | None, dict[str, Any]]] = []
    people = [admin, *advisors, broker, *([partner_user] if partner_user else [])]
    for day, user in enumerate(people, start=1):
        events.append(
            (
                now - timedelta(days=day * 3, hours=2),
                AuditAction.AUTH_LOGIN,
                user,
                AuditResult.SUCCESS,
                user,
                {},
            )
        )
    for day, email in ((4, advisors[0].email), (9, "desconocido@demo.local")):
        events.append(
            (
                now - timedelta(days=day, minutes=7),
                AuditAction.AUTH_LOGIN_FAILED,
                "auth",
                AuditResult.FAILED,
                None,
                {**_login_metadata(email), "status": 401, "code": "INVALID_CREDENTIALS"},
            )
        )
    events.append(
        (
            now - timedelta(days=6, hours=3),
            AuditAction.ACCESS_DENIED,
            "api",
            AuditResult.DENIED,
            broker,
            {
                "method": "GET",
                "path": "/api/v1/users",
                "view": "UserListView",
                "status": 403,
                "code": "PERMISSION_DENIED",
            },
        )
    )
    files = DocumentFile.objects.select_related("slot").order_by("created_at")[:3]
    for position, document in enumerate(files, start=1):
        events.append(
            (
                now - timedelta(days=position * 2, hours=1),
                AuditAction.DOCUMENT_DOWNLOADED,
                ("document_files", document.pk),
                AuditResult.SUCCESS,
                advisors[position % len(advisors)],
                {
                    "method": "GET",
                    "path": f"/api/v1/document-files/{document.pk}/download",
                    "view": "DocumentFileDownloadView",
                    "file_id": str(document.pk),
                    "fields": [],
                },
            )
        )
    job = ReportExportJob.objects.filter(requested_by=admin).order_by("-created_at").first()
    events.append(
        (
            now - timedelta(days=1, hours=4),
            AuditAction.REPORT_EXPORTED,
            ("report_export_jobs", job.pk if job else None),
            AuditResult.SUCCESS,
            admin,
            {
                "method": "POST",
                "path": "/api/v1/reports/applications/exports",
                "view": "ReportExportListView",
                "fields": ["date_from", "date_to"],
            },
        )
    )
    for number, (moment, action, resource, result, actor, metadata) in enumerate(
        sorted(events, key=lambda event: event[0]), start=1
    ):
        _save(number, moment, action, resource, result, actor=actor, metadata=metadata)
    return len(events)
