"""Aviso "sin actividad del comprador" del listado (TAREA-applications-listado, Parte 4,
precisión C), con el tiempo congelado."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.applications.serializers import ApplicationSerializer
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Opportunity
from apps.identity.models import BuyerAccessLink, BuyerSession, User
from tests.applications.conftest import APPLICATIONS_URL
from tests.applications.test_applications_api import SUMMARY_KEYS

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen() -> Any:
    with freeze_time(NOW):
        yield


def waiting(
    application: CreditApplication, *, stage_days: float, status: str | None = None
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(
        status=status or ApplicationStatus.WAITING_DOCUMENTS,
        current_stage_started_at=NOW - timedelta(days=stage_days),
    )


def seen(session: BuyerSession, days: float) -> None:
    BuyerSession.objects.filter(pk=session.pk).update(last_seen_at=NOW - timedelta(days=days))


def row(client: APIClient) -> dict[str, Any]:
    response = client.get(APPLICATIONS_URL)
    assert response.status_code == 200, response.content
    [item] = response.json()["items"]
    return dict(item)


@pytest.mark.parametrize(
    ("stage_days", "activity_days", "inactive"),
    [
        (10, 5, True),  # Actividad vieja.
        (4, None, True),  # Nunca entró y la etapa es vieja.
        (10, 1, False),  # Actividad reciente.
        (1, None, False),  # Nunca entró, pero la etapa es reciente.
        (10, 3, False),  # Exactamente 3 días: hace falta *más* de 3.
    ],
)
def test_buyer_inactive_in_the_waiting_tab(
    advisor_client: APIClient,
    application: CreditApplication,
    make_session: Callable[..., BuyerSession],
    stage_days: float,
    activity_days: float | None,
    inactive: bool,
) -> None:
    waiting(application, stage_days=stage_days)
    if activity_days is not None:
        seen(make_session(), activity_days)

    item = row(advisor_client)

    assert item["buyer_inactive"] is inactive
    if activity_days is None:
        assert item["last_buyer_activity_at"] is None
    else:
        reported = datetime.fromisoformat(item["last_buyer_activity_at"])
        assert reported == NOW - timedelta(days=activity_days)


def test_waiting_for_buyer_data_counts_too(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    waiting(application, stage_days=5, status=ApplicationStatus.WAITING_BUYER_DATA)

    assert row(advisor_client)["buyer_inactive"] is True


@pytest.mark.parametrize(
    "status",
    [ApplicationStatus.DRAFT, ApplicationStatus.DOCUMENTS_REVIEW, ApplicationStatus.FILED],
)
def test_outside_the_waiting_tab_it_is_null(
    advisor_client: APIClient,
    application: CreditApplication,
    make_session: Callable[..., BuyerSession],
    status: str,
) -> None:
    waiting(application, stage_days=30, status=status)
    seen(make_session(), 20)

    item = row(advisor_client)

    assert item["buyer_inactive"] is None
    assert item["last_buyer_activity_at"] is not None  # La fecha sí sale.


def test_the_latest_session_of_this_application_counts(
    advisor_client: APIClient,
    application: CreditApplication,
    make_link: Callable[..., BuyerAccessLink],
    make_session: Callable[..., BuyerSession],
    make_application: Callable[..., CreditApplication],
    make_opportunity: Callable[..., Opportunity],
    make_client: Callable[..., Any],
    other_advisor: User,
) -> None:
    waiting(application, stage_days=10)
    seen(make_session(), 6)
    seen(make_session(), 2)  # La más reciente gana.
    never_seen = make_session()
    assert never_seen.last_seen_at is None
    # Una sesión más reciente de otra solicitud (de otro asesor) no cuenta.
    other = make_application(
        make_opportunity(make_client(document_number="9001")), assigned_advisor=other_advisor
    )
    other_link = make_link(application=other, consumed_at=timezone.now())
    seen(make_session(access_link=other_link), 0)

    item = row(advisor_client)

    assert datetime.fromisoformat(item["last_buyer_activity_at"]) == NOW - timedelta(days=2)
    assert item["buyer_inactive"] is False


def test_without_the_annotation_it_queries(
    application: CreditApplication, make_session: Callable[..., BuyerSession]
) -> None:
    waiting(application, stage_days=10)
    seen(make_session(), 5)
    plain = CreditApplication.objects.get(pk=application.pk)

    data = ApplicationSerializer(plain).data

    assert data["buyer_inactive"] is True
    assert datetime.fromisoformat(data["last_buyer_activity_at"]) == NOW - timedelta(days=5)


def test_broker_does_not_see_the_activity(
    broker_client: APIClient,
    broker_user: User,
    application: CreditApplication,
    make_session: Callable[..., BuyerSession],
) -> None:
    Opportunity.objects.filter(pk=application.opportunity_id).update(origin_user=broker_user)
    waiting(application, stage_days=10)
    seen(make_session(), 5)

    item = row(broker_client)

    assert set(item) == SUMMARY_KEYS
