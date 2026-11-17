"""Backfill de la actividad desde el historial de estados (migración ``activity.0003``)."""

import importlib
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.activity.models import ActivityEventType as E
from apps.activity.models import ActivityLog
from apps.activity.models import ActivityVisibility as V
from apps.applications.models import ApplicationStatusHistory, CreditApplication
from apps.identity.buyer_portal import public_status_label
from apps.identity.models import BuyerSession, User

pytestmark = pytest.mark.django_db

backfill = importlib.import_module("apps.activity.migrations.0003_backfill_status_history").backfill


def run() -> None:
    backfill(django_apps, None)


@pytest.fixture
def history(
    application: CreditApplication, advisor_user: User, buyer_session: BuyerSession
) -> list[ApplicationStatusHistory]:
    start = timezone.now() - timedelta(days=3)
    created = [
        ApplicationStatusHistory.objects.create(
            application=application,
            application_version=1,
            from_status=None,
            to_status="DRAFT",
            actor_user=advisor_user,
        ),
        ApplicationStatusHistory.objects.create(
            application=application,
            application_version=2,
            from_status="DRAFT",
            to_status="WAITING_BUYER_DATA",
            comment="Pedí los datos por teléfono.",
            actor_user=advisor_user,
        ),
        ApplicationStatusHistory.objects.create(
            application=application,
            application_version=3,
            from_status="WAITING_BUYER_DATA",
            to_status="WAITING_DOCUMENTS",
            actor_buyer_session=buyer_session,
        ),
    ]
    for index, item in enumerate(created):
        ApplicationStatusHistory.objects.filter(pk=item.pk).update(
            created_at=start + timedelta(hours=index)
        )
        item.refresh_from_db()
    return created


def test_backfill_builds_the_timeline_from_the_history(
    application: CreditApplication,
    history: list[ApplicationStatusHistory],
    advisor_user: User,
    buyer_session: BuyerSession,
) -> None:
    run()

    rows = list(ActivityLog.objects.order_by("created_at", "visibility"))
    assert [(row.event_type, row.visibility, row.title) for row in rows] == [
        (E.APPLICATION_CREATED, V.INTERNAL, f"Solicitud {application.code} creada"),
        (
            E.STATUS_CHANGED,
            V.BUYER,
            f"Pasó de {public_status_label('DRAFT')} a {public_status_label('WAITING_BUYER_DATA')}",
        ),
        (E.STATUS_CHANGED, V.INTERNAL, "Pasó de Borrador a Esperando datos del comprador"),
        (
            E.STATUS_CHANGED,
            V.BUYER,
            f"Pasó de {public_status_label('WAITING_BUYER_DATA')} a "
            f"{public_status_label('WAITING_DOCUMENTS')}",
        ),
        (
            E.STATUS_CHANGED,
            V.INTERNAL,
            "Pasó de Esperando datos del comprador a Esperando documentos",
        ),
    ]
    # Conserva la fecha y el actor; el comentario solo va en la fila interna.
    assert rows[0].created_at == history[0].created_at
    assert [row.message for row in rows[1:3]] == ["", "Pedí los datos por teléfono."]
    assert rows[2].actor_user == advisor_user
    assert rows[4].actor_buyer_session == buyer_session
    assert {row.client_id for row in rows} == {application.opportunity.client_id}
    assert rows[2].metadata == {
        "from_status": "DRAFT",
        "to_status": "WAITING_BUYER_DATA",
        "status_history_id": str(history[1].pk),
    }


def test_backfill_is_idempotent_and_skips_rows_already_recorded(
    history: list[ApplicationStatusHistory], application: CreditApplication
) -> None:
    # Un suscriptor ya registró la creación en vivo.
    ActivityLog.objects.create(
        event_type=E.APPLICATION_CREATED,
        title="En vivo",
        application=application,
        metadata={"status_history_id": str(history[0].pk)},
    )

    run()
    run()

    assert ActivityLog.objects.count() == 5
    assert ActivityLog.objects.filter(event_type=E.APPLICATION_CREATED).get().title == "En vivo"
