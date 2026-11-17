"""Endpoints de la actividad y las notas (API §21.1)."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.activity.models import ActivityEventType as E
from apps.activity.models import ActivityLog
from apps.activity.models import ActivityVisibility as V
from apps.activity.services import record_activity
from apps.applications.models import CreditApplication
from apps.crm.models import Client, Opportunity
from apps.identity.models import BuyerSession, User
from tests.applications.activity.conftest import activity_url, buyer_activity_url, notes_url
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

AppFactory = Callable[..., CreditApplication]


def items(response: Any) -> list[dict[str, Any]]:
    assert response.status_code == 200, response.content
    return list(response.json()["items"])


def titles(response: Any) -> list[str]:
    return [item["title"] for item in items(response)]


def log(application: CreditApplication, title: str, minutes_ago: int, **extra: Any) -> ActivityLog:
    extra.setdefault("event_type", E.STATUS_CHANGED)
    row = record_activity(application=application, title=title, **extra)
    ActivityLog.objects.filter(pk=row.pk).update(
        created_at=timezone.now() - timedelta(minutes=minutes_ago)
    )
    return row


@pytest.fixture
def timeline(
    application: CreditApplication, advisor_user: User, buyer_session: BuyerSession
) -> CreditApplication:
    """Dos filas internas, una nota y dos filas para el comprador."""
    log(application, "Interna antigua", 30, actor=advisor_user)
    log(application, "Interna reciente", 10, actor=buyer_session, event_type=E.DOCUMENT_UPLOADED)
    log(application, "Nota de Andrea García", 5, actor=advisor_user, event_type=E.NOTE_ADDED)
    log(application, "Del comprador, antigua", 20, visibility=V.BUYER, actor=advisor_user)
    log(
        application,
        "Del comprador, reciente",
        8,
        visibility=V.BUYER,
        actor=buyer_session,
        event_type=E.DOCUMENT_UPLOADED,
    )
    log(application, "Del sistema", 1, visibility=V.BUYER)
    return application


# --- Actividad interna ------------------------------------------------------------------


def test_internal_activity_is_newest_first_with_the_internal_rows(
    advisor_client: APIClient, timeline: CreditApplication
) -> None:
    body = items(advisor_client.get(activity_url(timeline)))

    assert [item["title"] for item in body] == [
        "Nota de Andrea García",
        "Interna reciente",
        "Interna antigua",
    ]
    reciente = body[1]
    assert reciente == {
        "id": reciente["id"],
        "event_type": "DOCUMENT_UPLOADED",
        "event_type_label": "Documento cargado",
        "title": "Interna reciente",
        "message": "",
        "actor": {"name": "Portal del comprador"},
        "created_at": reciente["created_at"],
    }
    assert body[2]["actor"] == {"name": "Andrea García"}


def test_activity_filters_by_event_type(
    advisor_client: APIClient, timeline: CreditApplication
) -> None:
    url = activity_url(timeline)

    assert titles(advisor_client.get(url, {"event_type": "NOTE_ADDED"})) == [
        "Nota de Andrea García"
    ]
    both = advisor_client.get(f"{url}?event_type=NOTE_ADDED&event_type=STATUS_CHANGED")
    assert titles(both) == ["Nota de Andrea García", "Interna antigua"]
    error = assert_error(
        advisor_client.get(url, {"event_type": "INVENTED"}), 400, "VALIDATION_ERROR"
    )
    assert error["details"][0]["field"] == "event_type"


def test_broker_sees_only_the_buyer_rows(
    make_user: Callable[..., User],
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    make_application: AppFactory,
    application: CreditApplication,
) -> None:
    from tests.partners.conftest import client_for

    broker = make_user(email="broker@example.com", role_code="INDEPENDENT_BROKER")
    client = make_client(document_number="70111222")
    originated = make_application(make_opportunity(client, origin_user=broker))
    log(originated, "Interna", 5)
    log(originated, "Para el comprador", 3, visibility=V.BUYER)
    broker_client = client_for(broker)

    assert titles(broker_client.get(activity_url(originated))) == ["Para el comprador"]
    assert_error(broker_client.get(activity_url(application)), 404, "RESOURCE_NOT_FOUND")


def test_partner_and_other_advisors_do_not_see_the_activity(
    partner_client: APIClient, other_advisor_client: APIClient, application: CreditApplication
) -> None:
    assert_error(partner_client.get(activity_url(application)), 403, "PERMISSION_DENIED")
    assert_error(other_advisor_client.get(activity_url(application)), 404, "RESOURCE_NOT_FOUND")


def test_activity_queries_do_not_grow_with_the_rows(
    advisor_client: APIClient, application: CreditApplication, advisor_user: User
) -> None:
    def measure() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert advisor_client.get(activity_url(application)).status_code == 200
        return len(queries)

    log(application, "Primera", 50, actor=advisor_user)
    one = measure()
    for minute in range(24):
        log(application, f"Fila {minute}", minute, actor=advisor_user)

    assert measure() == one


# --- Actividad del comprador ------------------------------------------------------------


def test_buyer_sees_only_buyer_rows_with_friendly_actors(
    portal: APIClient, timeline: CreditApplication
) -> None:
    body = items(portal.get(buyer_activity_url(timeline)))

    assert [(item["title"], item["actor"]) for item in body] == [
        ("Del sistema", None),
        ("Del comprador, reciente", {"name": "Tú"}),
        ("Del comprador, antigua", {"name": "Tu asesor"}),
    ]
    assert portal.get(buyer_activity_url(timeline), {"event_type": "DOCUMENT_UPLOADED"}).json()[
        "items"
    ][0]["title"] == ("Del comprador, reciente")


def test_buyer_cannot_read_another_application(
    portal: APIClient,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    make_application: AppFactory,
) -> None:
    other = make_application(make_opportunity(make_client(document_number="70333444")))

    assert_error(portal.get(buyer_activity_url(other)), 404, "RESOURCE_NOT_FOUND")


def test_internal_users_cannot_use_the_buyer_endpoint(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    response = advisor_client.get(buyer_activity_url(application))

    assert response.status_code == 401


# --- Notas ------------------------------------------------------------------------------


def test_advisor_adds_and_lists_notes(
    advisor_client: APIClient, advisor_user: User, application: CreditApplication, portal: APIClient
) -> None:
    response = advisor_client.post(
        notes_url(application), {"body": "El comprador viaja en diciembre."}, format="json"
    )

    assert response.status_code == 201, response.content
    note = response.json()
    assert note == {
        "id": note["id"],
        "body": "El comprador viaja en diciembre.",
        "author": {"id": str(advisor_user.pk), "name": "Andrea García"},
        "created_at": note["created_at"],
    }
    row = ActivityLog.objects.get(pk=note["id"])
    assert (row.event_type, row.visibility, row.title) == (
        E.NOTE_ADDED,
        V.INTERNAL,
        "Nota de Andrea García",
    )
    assert items(advisor_client.get(notes_url(application))) == [note]
    notes_only = advisor_client.get(activity_url(application), {"event_type": "NOTE_ADDED"})
    assert titles(notes_only) == ["Nota de Andrea García"]
    # El comprador nunca ve las notas.
    assert items(portal.get(buyer_activity_url(application))) == []


@pytest.mark.parametrize("body", [{}, {"body": ""}, {"body": "x" * 2001}, {"body": "ok", "x": 1}])
def test_note_body_is_validated(
    advisor_client: APIClient, application: CreditApplication, body: dict[str, Any]
) -> None:
    response = advisor_client.post(notes_url(application), body, format="json")

    assert_error(response, 400, "VALIDATION_ERROR")
    assert not ActivityLog.objects.exists()


def test_notes_are_allowed_on_a_closed_application(
    admin_client: APIClient, application: CreditApplication
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(status="CANCELLED")

    response = admin_client.post(notes_url(application), {"body": "Cierre"}, format="json")

    assert response.status_code == 201, response.content


def test_only_admin_and_the_assigned_advisor_handle_notes(
    broker_client: APIClient,
    other_advisor_client: APIClient,
    admin_client: APIClient,
    application: CreditApplication,
) -> None:
    assert_error(broker_client.get(notes_url(application)), 403, "PERMISSION_DENIED")
    assert_error(
        broker_client.post(notes_url(application), {"body": "x"}, format="json"),
        403,
        "PERMISSION_DENIED",
    )
    assert_error(other_advisor_client.get(notes_url(application)), 404, "RESOURCE_NOT_FOUND")
    assert items(admin_client.get(notes_url(application))) == []
