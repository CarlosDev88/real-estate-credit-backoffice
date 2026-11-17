"""Endpoints de las notificaciones (Parte 1 del paso 13, API §21.2): el comprador lee y
marca las suyas, y el backoffice ve cada notificación con sus entregas."""

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, Opportunity
from apps.notifications import services
from apps.notifications.models import (
    DeliveryChannel,
    DeliveryStatus,
    Notification,
    NotificationDelivery,
    NotificationType,
)
from tests.applications.buyer_access.conftest import set_status
from tests.applications.conftest import application_url
from tests.applications.notifications.conftest import NotificationFactory
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/buyer/notifications"
UNREAD_COUNT_URL = "/api/v1/buyer/notifications/unread-count"
READ_ALL_URL = "/api/v1/buyer/notifications/read-all"


def read_url(notification: Notification | str) -> str:
    notification_id = notification if isinstance(notification, str) else notification.pk
    return f"/api/v1/buyer/notifications/{notification_id}/read"


def ids(response: Any) -> list[str]:
    return [item["id"] for item in response.json()["items"]]


@pytest.fixture
def welcome() -> Notification:
    """La bienvenida que dejó el consumo del enlace de ``portal`` o ``buyer_client``."""
    return Notification.objects.get(notification_type=NotificationType.ACCESS_GRANTED)


@pytest.fixture
def foreign(
    make_client: Any,
    make_opportunity: Any,
    make_application: Any,
    make_notification: NotificationFactory,
) -> Notification:
    """Notificación de otro comprador en otra solicitud."""
    other: Client = make_client(document_number="52987654", first_names="Marta")
    opportunity: Opportunity = make_opportunity(other)
    return make_notification(application=make_application(opportunity))


# --- Comprador --------------------------------------------------------------------------


def test_the_buyer_lists_their_notifications_newest_first(
    portal: APIClient,
    welcome: Notification,
    make_notification: NotificationFactory,
    foreign: Notification,
) -> None:
    Notification.objects.filter(pk=welcome.pk).update(
        created_at=timezone.now() - timedelta(hours=1)
    )
    newer = make_notification(NotificationType.READY_TO_FILE)

    response = portal.get(LIST_URL)

    assert response.status_code == 200, response.content
    assert response["Cache-Control"] == "no-store"
    assert ids(response) == [str(newer.pk), str(welcome.pk)]
    item = response.json()["items"][0]
    assert item == {
        "id": str(newer.pk),
        "notification_type": "READY_TO_FILE",
        "notification_type_label": "Expediente completo",
        "title": "Tu expediente está completo",
        "message": newer.message,
        "created_at": item["created_at"],
        "read_at": None,
    }


def test_only_the_session_application_is_listed(
    portal: APIClient,
    welcome: Notification,
    application: CreditApplication,
    make_opportunity: Any,
    make_application: Any,
    make_notification: NotificationFactory,
) -> None:
    # Otra solicitud del mismo comprador: no es la de la sesión.
    other_application = make_application(make_opportunity(application.opportunity.client))
    make_notification(application=other_application)

    assert ids(portal.get(LIST_URL)) == [str(welcome.pk)]


def test_unread_filter(
    portal: APIClient, welcome: Notification, make_notification: NotificationFactory
) -> None:
    unread = make_notification()
    Notification.objects.filter(pk=welcome.pk).update(read_at=timezone.now())

    assert ids(portal.get(LIST_URL, {"unread": "true"})) == [str(unread.pk)]
    assert len(ids(portal.get(LIST_URL, {"unread": "false"}))) == 2
    assert_error(portal.get(LIST_URL, {"unread": "tal vez"}), 400, "VALIDATION_ERROR")


def test_unread_count(
    portal: APIClient,
    welcome: Notification,
    make_notification: NotificationFactory,
    foreign: Notification,
) -> None:
    make_notification()
    assert portal.get(UNREAD_COUNT_URL).json() == {"count": 2}

    Notification.objects.filter(pk=welcome.pk).update(read_at=timezone.now())

    assert portal.get(UNREAD_COUNT_URL).json() == {"count": 1}


def test_marking_one_as_read_is_idempotent(portal: APIClient, welcome: Notification) -> None:
    first = portal.patch(read_url(welcome))

    assert first.status_code == 200, first.content
    read_at = first.json()["read_at"]
    assert read_at is not None
    second = portal.patch(read_url(welcome))
    assert second.status_code == 200
    assert second.json()["read_at"] == read_at
    assert portal.get(UNREAD_COUNT_URL).json() == {"count": 0}


def test_a_concurrent_read_keeps_the_first_date(make_notification: NotificationFactory) -> None:
    notification = make_notification()
    earlier = timezone.now() - timedelta(minutes=5)
    stale = Notification.objects.get(pk=notification.pk)
    Notification.objects.filter(pk=notification.pk).update(read_at=earlier)

    assert services.mark_read(stale).read_at == earlier


def test_another_buyers_notification_is_not_found(portal: APIClient, foreign: Notification) -> None:
    assert_error(portal.patch(read_url(foreign)), 404, "RESOURCE_NOT_FOUND")
    assert_error(
        portal.patch(read_url("00000000-0000-0000-0000-000000000000")), 404, "RESOURCE_NOT_FOUND"
    )
    foreign.refresh_from_db()
    assert foreign.read_at is None


def test_read_all_marks_only_the_unread_ones(
    portal: APIClient,
    welcome: Notification,
    make_notification: NotificationFactory,
    foreign: Notification,
) -> None:
    make_notification()
    make_notification()
    Notification.objects.filter(pk=welcome.pk).update(read_at=timezone.now())

    response = portal.post(READ_ALL_URL)

    assert response.status_code == 200, response.content
    assert response.json() == {"count": 2}
    assert portal.post(READ_ALL_URL).json() == {"count": 0}
    foreign.refresh_from_db()
    assert foreign.read_at is None


def test_pending_consents_do_not_block_reading(
    buyer_client: APIClient, welcome: Notification
) -> None:
    """``buyer_client`` no aceptó los consentimientos: las escrituras del portal
    responden ``CONSENT_REQUIRED``, pero las notificaciones no."""
    assert buyer_client.get(LIST_URL).status_code == 200
    assert buyer_client.patch(read_url(welcome)).status_code == 200
    assert buyer_client.post(READ_ALL_URL).status_code == 200


def test_a_closed_application_still_marks_as_read(
    portal: APIClient, welcome: Notification, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.DISBURSED)

    assert portal.patch(read_url(welcome)).status_code == 200


def test_writes_require_csrf(buyer_csrf_client: APIClient, welcome: Notification) -> None:
    assert_error(buyer_csrf_client.patch(read_url(welcome)), 403, "CSRF_FAILED")
    assert_error(buyer_csrf_client.post(READ_ALL_URL), 403, "CSRF_FAILED")


def test_the_buyer_endpoints_require_the_buyer_session(
    api_client: APIClient, advisor_client: APIClient
) -> None:
    for client in (api_client, advisor_client):
        assert_error(client.get(LIST_URL), 401, "NOT_AUTHENTICATED")
        assert_error(client.get(UNREAD_COUNT_URL), 401, "NOT_AUTHENTICATED")
        assert_error(client.post(READ_ALL_URL), 401, "NOT_AUTHENTICATED")


# --- Backoffice -------------------------------------------------------------------------


def notifications_url(application: CreditApplication) -> str:
    return application_url(application, "/notifications")


def test_the_advisor_sees_each_delivery(
    advisor_client: APIClient,
    application: CreditApplication,
    make_notification: NotificationFactory,
    foreign: Notification,
) -> None:
    notification = make_notification()
    NotificationDelivery.objects.filter(
        notification=notification, channel=DeliveryChannel.EMAIL
    ).update(status=DeliveryStatus.FAILED, attempt_count=5, last_error_code="SMTP_ERROR")

    response = advisor_client.get(notifications_url(application))

    assert response.status_code == 200, response.content
    (item,) = response.json()["items"]
    assert item["id"] == str(notification.pk)
    assert item["notification_type_label"] == "Expediente completo"
    email, portal_delivery = item["deliveries"]
    assert email["channel"] == "EMAIL"
    assert email["channel_label"] == "Correo electrónico"
    assert (email["status"], email["status_label"]) == ("FAILED", "Fallida")
    assert (email["attempt_count"], email["last_error_code"]) == (5, "SMTP_ERROR")
    assert (portal_delivery["channel"], portal_delivery["status"]) == ("PORTAL", "SENT")
    assert set(portal_delivery) == {
        "id",
        "channel",
        "channel_label",
        "destination",
        "status",
        "status_label",
        "attempt_count",
        "next_attempt_at",
        "sent_at",
        "last_error_code",
    }


def test_the_admin_sees_any_application(
    admin_client: APIClient, application: CreditApplication, make_notification: NotificationFactory
) -> None:
    make_notification()

    response = admin_client.get(notifications_url(application))

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_others_do_not_see_the_notifications(
    other_advisor_client: APIClient,
    broker_client: APIClient,
    api_client: APIClient,
    application: CreditApplication,
) -> None:
    assert_error(
        other_advisor_client.get(notifications_url(application)), 404, "RESOURCE_NOT_FOUND"
    )
    assert_error(broker_client.get(notifications_url(application)), 403, "PERMISSION_DENIED")
    assert_error(api_client.get(notifications_url(application)), 401, "NOT_AUTHENTICATED")
