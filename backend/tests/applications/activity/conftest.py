"""Fixtures de la actividad (Parte 3 del paso 12).

Viven bajo ``tests/applications`` para heredar la solicitud, el titular y los usuarios;
las del comprador, el expediente y la radicación se importan de ``filings``.
"""

from typing import Any

from apps.activity.models import ActivityLog
from apps.applications.models import CreditApplication
from tests.applications.filings.conftest import (
    accept_consents,
    approve_stored,
    buyer_client,
    buyer_csrf_client,
    buyer_session,
    make_document_file,
    make_file_object,
    make_filing,
    make_link,
    make_session,
    make_slot,
    package_dossier,
    portal,
    waive_slot,
)

__all__ = [
    "accept_consents",
    "approve_stored",
    "buyer_client",
    "buyer_csrf_client",
    "buyer_session",
    "make_document_file",
    "make_file_object",
    "make_filing",
    "make_link",
    "make_session",
    "make_slot",
    "package_dossier",
    "portal",
    "waive_slot",
]


def activity_url(application: CreditApplication) -> str:
    return f"/api/v1/applications/{application.pk}/activity"


def notes_url(application: CreditApplication) -> str:
    return f"/api/v1/applications/{application.pk}/notes"


def buyer_activity_url(application: CreditApplication) -> str:
    return f"/api/v1/buyer/applications/{application.pk}/activity"


def rows(event_type: str, **filters: Any) -> list[ActivityLog]:
    """Filas de ese tipo, en el orden en que se crearon."""
    return list(
        ActivityLog.objects.filter(event_type=event_type, **filters).order_by("created_at", "pk")
    )


def by_visibility(event_type: str, **filters: Any) -> dict[str, list[ActivityLog]]:
    grouped: dict[str, list[ActivityLog]] = {}
    for row in rows(event_type, **filters):
        grouped.setdefault(row.visibility, []).append(row)
    return grouped
