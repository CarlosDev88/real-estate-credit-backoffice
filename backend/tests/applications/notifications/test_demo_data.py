"""Avisos de ``seed_demo_data`` (Cierre del paso 13): las señales de la demo crean las
notificaciones, y la segunda corrida no duplica nada."""

from collections.abc import Callable
from typing import Any

import pytest

from apps.documents.models import DocumentReview, ReviewDecision
from apps.filings.models import Filing
from apps.notifications.models import Notification, NotificationDelivery, NotificationType
from tests.applications.test_demo_data import seed

pytestmark = pytest.mark.django_db


def by_type() -> dict[str, int]:
    return {
        notification_type: Notification.objects.filter(notification_type=notification_type).count()
        for notification_type in NotificationType.values
    }


def test_the_demo_notifies_its_buyers_once(
    django_capture_on_commit_callbacks: Callable[..., Any],
) -> None:
    # En las pruebas la transacción nunca confirma: se ejecutan los `on_commit` (las
    # revisiones emiten `document_reviewed` al confirmar).
    with django_capture_on_commit_callbacks(execute=True):
        seed()

    created = by_type()
    filed = Filing.objects.count()
    rejected = DocumentReview.objects.filter(decision=ReviewDecision.REJECTED).count()
    assert created[NotificationType.FILED] == filed == 4
    assert created[NotificationType.DOCUMENT_REJECTED] == rejected > 0
    assert created[NotificationType.BANK_RETURNED] == 1
    assert created[NotificationType.BANK_APPROVED] == 2
    assert created[NotificationType.DISBURSED] == 1
    assert created[NotificationType.ACCESS_GRANTED] > 0
    assert NotificationDelivery.objects.count() == 2 * sum(created.values())

    with django_capture_on_commit_callbacks(execute=True):
        seed()

    assert by_type() == created
