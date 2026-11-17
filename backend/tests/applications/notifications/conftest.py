"""Fixtures de las notificaciones (paso 13).

Viven bajo ``tests/applications`` para heredar la solicitud, el titular y los usuarios;
las del comprador, el expediente y la radicación se importan de ``filings``.
"""

from collections.abc import Callable
from typing import Any

import pytest

from apps.applications.models import CreditApplication
from apps.crm.models import Client
from apps.notifications import services
from apps.notifications.models import Notification, NotificationType
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
    make_observation,
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
    "make_observation",
    "make_session",
    "make_slot",
    "package_dossier",
    "portal",
    "waive_slot",
]

NotificationFactory = Callable[..., Notification]


@pytest.fixture
def make_notification(application: CreditApplication) -> NotificationFactory:
    """Notificación creada por el servicio, con sus entregas, para el titular de
    ``application`` (o el cliente y la solicitud que se indiquen)."""
    counter = iter(range(1, 1_000))

    def _make_notification(
        notification_type: str = NotificationType.READY_TO_FILE, **extra: Any
    ) -> Notification:
        target: CreditApplication = extra.pop("application", application)
        client: Client = extra.pop("client", target.opportunity.client)
        source_id = extra.pop("source_id", f"prueba-{next(counter)}")
        created = services.notify_client(client, target, notification_type, source_id=source_id)
        if extra:
            Notification.objects.filter(pk=created.notification.pk).update(**extra)
            created.notification.refresh_from_db()
        return created.notification

    return _make_notification
