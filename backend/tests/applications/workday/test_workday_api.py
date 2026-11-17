""" "Mi día" (API §15.1): alcance, segmentos, filtros, orden, días en la etapa y resumen."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.applications.models import TERMINAL_APPLICATION_STATUSES, CreditApplication
from apps.banking.models import BankProduct
from apps.catalogs.workflow import ApplicationStatus as S
from apps.documents.models import SlotStatus
from apps.identity.models import BuyerAccessLink, BuyerSession, User
from apps.tasks.models import Task, TaskStatus
from apps.workday import services
from apps.workday.rules import (
    NEXT_ACTIONS,
    WORKDAY_STATUSES,
    AttentionSegment,
    NextAction,
    end_of_today,
    segment_conditions,
)
from tests.applications.conftest import catalog_item, seeded_product
from tests.applications.workday.conftest import SUMMARY_URL, WORKDAY_URL, add_slot
from tests.helpers import assert_error
from tests.partners.conftest import client_for

pytestmark = pytest.mark.django_db

AppFactory = Callable[..., CreditApplication]
TaskFactory = Callable[..., Task]


def items(client: APIClient, **params: Any) -> list[dict[str, Any]]:
    response = client.get(WORKDAY_URL, {**params, "page_size": "100"})
    assert response.status_code == 200, response.content
    return list(response.json()["items"])


def codes(client: APIClient, **params: Any) -> list[str]:
    return [row["code"] for row in items(client, **params)]


def segment_counts(client: APIClient, **params: Any) -> dict[str, int]:
    response = client.get(SUMMARY_URL, params)
    assert response.status_code == 200, response.content
    body = response.json()
    return {"total": body["total"], **{row["code"]: row["count"] for row in body["segments"]}}


# --- Reglas fijas ------------------------------------------------------------------------


def test_every_active_status_has_a_next_action_with_its_label() -> None:
    assert set(NEXT_ACTIONS) == set(WORKDAY_STATUSES)
    assert not set(WORKDAY_STATUSES) & set(TERMINAL_APPLICATION_STATUSES)
    assert set(NEXT_ACTIONS.values()) == set(NextAction)
    assert NEXT_ACTIONS[S.FILING_VALIDATION].label == "Esperar respuesta del banco"


def test_every_segment_has_a_rule_in_the_table_order() -> None:
    assert list(segment_conditions(timezone.now())) == list(AttentionSegment.values)
    assert [segment.label for segment in AttentionSegment][0] == "Documentos por revisar"


# --- Alcance --------------------------------------------------------------------------------


def test_the_advisor_sees_only_their_active_applications_and_advisor_id_is_ignored(
    advisor_client: APIClient, other_advisor: User, make_workday_application: AppFactory
) -> None:
    mine = make_workday_application(S.DOCUMENTS_REVIEW)
    make_workday_application(S.DISBURSED)
    make_workday_application(
        S.WITHDRAWN,
        withdrawn_at=timezone.now(),
        withdrawal_reason_item=(catalog_item("application_withdrawal_reason", "OTHER")),
    )
    make_workday_application(S.DRAFT, advisor=other_advisor)

    assert codes(advisor_client) == [mine.code]
    assert codes(advisor_client, advisor_id=str(other_advisor.pk)) == [mine.code]
    assert codes(advisor_client, advisor_id="no-es-un-uuid") == [mine.code]


def test_the_admin_sees_every_active_application_or_one_advisor(
    admin_client: APIClient, other_advisor: User, make_workday_application: AppFactory
) -> None:
    first = make_workday_application(S.DRAFT)
    second = make_workday_application(S.FILED, advisor=other_advisor)
    make_workday_application(S.REJECTED)

    assert set(codes(admin_client)) == {first.code, second.code}
    assert codes(admin_client, advisor_id=str(other_advisor.pk)) == [second.code]
    assert_error(admin_client.get(WORKDAY_URL, {"advisor_id": "x"}), 400, "VALIDATION_ERROR")


@pytest.mark.parametrize("url", [WORKDAY_URL, SUMMARY_URL])
def test_broker_and_partner_have_no_workday(
    broker_client: APIClient, partner_client: APIClient, url: str
) -> None:
    assert_error(broker_client.get(url), 403, "PERMISSION_DENIED")
    assert_error(partner_client.get(url), 403, "PERMISSION_DENIED")


# --- Fila ------------------------------------------------------------------------------------


def test_the_row_has_the_workday_fields(
    advisor_client: APIClient, make_workday_application: AppFactory
) -> None:
    product = seeded_product()
    application = make_workday_application(
        S.WAITING_DOCUMENTS, bank_product=product, first_names="Sofía"
    )

    (row,) = items(advisor_client)

    assert row == {
        "id": str(application.pk),
        "code": application.code,
        "client_display_name": "Sofía Gómez Vélez",
        "bank": {"id": str(product.bank_id), "name": "Bancolombia", "short_name": ""},
        "bank_product": {"id": str(product.pk), "name": product.name},
        "status": "WAITING_DOCUMENTS",
        "status_label": "Esperando documentos",
        "next_action": "FOLLOW_UP_DOCUMENTS",
        "next_action_label": "Hacer seguimiento a los documentos",
        "days_in_stage": 0,
        "attention": [],
        "pending_tasks_count": 0,
        "updated_at": row["updated_at"],
    }


def test_without_product_bank_and_product_are_null(
    advisor_client: APIClient, make_workday_application: AppFactory
) -> None:
    make_workday_application(S.DRAFT)

    (row,) = items(advisor_client)

    assert (row["bank"], row["bank_product"]) == (None, None)


# --- Segmentos ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "segment"),
    [
        (S.READY_TO_FILE, AttentionSegment.READY_TO_FILE),
        (S.FILED, AttentionSegment.FILED),
        (S.FILING_VALIDATION, AttentionSegment.FILED),
        (S.CREDIT_ANALYSIS, AttentionSegment.IN_ANALYSIS),
        (S.BANK_OBSERVATION, AttentionSegment.OBSERVED),
    ],
)
def test_status_segments(
    advisor_client: APIClient, make_workday_application: AppFactory, status: str, segment: str
) -> None:
    application = make_workday_application(status)
    make_workday_application(S.DRAFT)

    assert codes(advisor_client, attention=segment) == [application.code]
    (row,) = items(advisor_client, attention=segment)
    assert [item["code"] for item in row["attention"]] == [segment]


def test_review_documents_needs_a_current_uploaded_slot(
    advisor_client: APIClient, make_workday_application: AppFactory
) -> None:
    uploaded = make_workday_application(S.DOCUMENTS_REVIEW)
    add_slot(uploaded, SlotStatus.UPLOADED)
    retired = make_workday_application(S.DOCUMENTS_REVIEW)
    add_slot(retired, SlotStatus.UPLOADED, retired_at=timezone.now())
    approved = make_workday_application(S.DOCUMENTS_REVIEW)
    add_slot(approved, SlotStatus.APPROVED)

    assert codes(advisor_client, attention=AttentionSegment.REVIEW_DOCUMENTS) == [uploaded.code]


NOW = datetime(2026, 11, 10, 17, 0, tzinfo=UTC)  # 12:00 en Bogotá.


@pytest.mark.parametrize(
    ("status", "stage_days", "seen_days", "inactive"),
    [
        (S.WAITING_DOCUMENTS, 10, 5, True),  # Actividad vieja.
        (S.WAITING_BUYER_DATA, 4, None, True),  # Nunca entró y la etapa es vieja.
        (S.WAITING_DOCUMENTS, 10, 1, False),  # Actividad reciente.
        (S.WAITING_DOCUMENTS, 1, None, False),  # Nunca entró, etapa reciente.
        (S.WAITING_DOCUMENTS, 10, 3, False),  # Exactamente 3 días: hace falta más.
        (S.DOCUMENTS_REVIEW, 10, None, False),  # Fuera de la pestaña `waiting`.
    ],
)
def test_buyer_inactive_uses_the_list_rule(
    advisor_user: User,
    make_workday_application: AppFactory,
    make_link: Callable[..., BuyerAccessLink],
    make_session: Callable[..., BuyerSession],
    status: str,
    stage_days: int,
    seen_days: int | None,
    inactive: bool,
) -> None:
    with freeze_time(NOW):
        advisor_client = client_for(advisor_user)
        application = make_workday_application(
            status, current_stage_started_at=NOW - timedelta(days=stage_days)
        )
        if seen_days is not None:
            link = make_link(application=application, consumed_at=NOW)
            make_session(access_link=link, last_seen_at=NOW - timedelta(days=seen_days))

        inactive_codes = codes(advisor_client, attention=AttentionSegment.BUYER_INACTIVE)

    assert (inactive_codes == [application.code]) is inactive


def test_tasks_due_counts_pending_tasks_due_by_the_end_of_today_in_bogota(
    advisor_user: User, make_workday_application: AppFactory, make_task: TaskFactory
) -> None:
    # 23:30 en Bogotá: en UTC ya es el día siguiente.
    with freeze_time(datetime(2026, 11, 11, 4, 30, tzinfo=UTC)):
        advisor_client = client_for(advisor_user)
        today_late = make_workday_application(S.DRAFT)
        make_task(today_late, datetime(2026, 11, 11, 4, 50, tzinfo=UTC))  # 23:50 de hoy.
        overdue = make_workday_application(S.DRAFT)
        make_task(overdue, datetime(2026, 11, 1, 12, 0, tzinfo=UTC))
        tomorrow = make_workday_application(S.DRAFT)
        make_task(tomorrow, datetime(2026, 11, 11, 5, 30, tzinfo=UTC))  # 00:30 de mañana.
        done = make_workday_application(S.DRAFT)
        make_task(
            done,
            datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
            status=TaskStatus.COMPLETED,
            completed_at=timezone.now(),
        )
        undated = make_workday_application(S.DRAFT)
        make_task(undated, None)

        due = codes(advisor_client, attention=AttentionSegment.TASKS_DUE)
        rows = {row["code"]: row for row in items(advisor_client)}

    assert set(due) == {today_late.code, overdue.code}
    assert rows[tomorrow.code]["pending_tasks_count"] == 1
    assert rows[done.code]["pending_tasks_count"] == 0
    assert rows[undated.code]["attention"] == []


def test_segments_are_not_exclusive(
    advisor_client: APIClient, make_workday_application: AppFactory, make_task: TaskFactory
) -> None:
    application = make_workday_application(S.READY_TO_FILE)
    make_task(application, timezone.now() - timedelta(hours=1))

    (row,) = items(advisor_client)

    assert [item["code"] for item in row["attention"]] == ["READY_TO_FILE", "TASKS_DUE"]
    assert row["attention"][1]["label"] == "Con tareas vencidas o de hoy"


def test_end_of_today_is_the_last_instant_of_the_bogota_date() -> None:
    with freeze_time(datetime(2026, 11, 11, 4, 30, tzinfo=UTC)):
        end = end_of_today()
    assert timezone.localtime(end).date().isoformat() == "2026-11-10"
    assert (timezone.localtime(end).hour, timezone.localtime(end).minute) == (23, 59)


# --- Filtros ---------------------------------------------------------------------------------


def test_filters_by_stage_bank_purpose_and_search(
    advisor_client: APIClient, make_workday_application: AppFactory
) -> None:
    bancolombia = make_workday_application(
        S.DOCUMENTS_REVIEW, bank_product=seeded_product(), first_names="Mariana"
    )
    fna = make_workday_application(
        S.DRAFT,
        bank_product=seeded_product("FNA"),
        purpose_item=catalog_item("loan_purpose", "PURCHASE_USED"),
    )

    assert codes(advisor_client, stage="DOCUMENTS_REVIEW") == [bancolombia.code]
    assert codes(advisor_client, bank_id=str(fna.bank_product.bank_id)) == [fna.code]  # type: ignore[union-attr]
    assert codes(advisor_client, purpose="PURCHASE_USED") == [fna.code]
    assert codes(advisor_client, search="Mariana") == [bancolombia.code]
    assert codes(advisor_client, search=fna.code) == [fna.code]


@pytest.mark.parametrize(
    "params",
    [
        {"stage": "NOPE"},
        {"stage": "DISBURSED"},  # Terminal: nunca está en "Mi día".
        {"purpose": "NOPE"},
        {"attention": "NOPE"},
        {"bank_id": "x"},
        {"ordering": "status"},
    ],
)
def test_unknown_codes_answer_400(advisor_client: APIClient, params: dict[str, str]) -> None:
    assert_error(advisor_client.get(WORKDAY_URL, params), 400, "VALIDATION_ERROR")


# --- Orden y días en la etapa --------------------------------------------------------------


@pytest.mark.parametrize(
    ("started_at", "now", "days"),
    [
        # 23:00 del 9 y 00:30 del 10 en Bogotá: 1 día, aunque en UTC sean el mismo día.
        (datetime(2026, 3, 10, 4, 0, tzinfo=UTC), datetime(2026, 3, 10, 5, 30, tzinfo=UTC), 1),
        (datetime(2026, 3, 1, 15, 0, tzinfo=UTC), datetime(2026, 3, 10, 15, 0, tzinfo=UTC), 9),
        (datetime(2026, 3, 10, 6, 0, tzinfo=UTC), datetime(2026, 3, 10, 23, 0, tzinfo=UTC), 0),
    ],
)
def test_days_in_stage_with_frozen_time(
    advisor_user: User,
    make_workday_application: AppFactory,
    started_at: datetime,
    now: datetime,
    days: int,
) -> None:
    with freeze_time(now):
        advisor_client = client_for(advisor_user)
        make_workday_application(S.DRAFT, current_stage_started_at=started_at)
        (row,) = items(advisor_client)
    assert row["days_in_stage"] == days


def test_default_order_puts_due_tasks_first_then_the_oldest_stage(
    advisor_client: APIClient, make_workday_application: AppFactory, make_task: TaskFactory
) -> None:
    now = timezone.now()
    old = make_workday_application(S.DRAFT, current_stage_started_at=now - timedelta(days=9))
    recent = make_workday_application(S.DRAFT, current_stage_started_at=now - timedelta(days=1))
    with_task = make_workday_application(S.DRAFT, current_stage_started_at=now)
    make_task(with_task, now - timedelta(hours=2))

    assert codes(advisor_client) == [with_task.code, old.code, recent.code]
    assert codes(advisor_client, ordering="days_in_stage") == [
        with_task.code,
        recent.code,
        old.code,
    ]
    assert codes(advisor_client, ordering="-code") == sorted(
        [old.code, recent.code, with_task.code], reverse=True
    )


def test_list_queries_do_not_grow_with_the_rows(
    advisor_client: APIClient, make_workday_application: AppFactory, make_task: TaskFactory
) -> None:
    def measure() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert advisor_client.get(WORKDAY_URL).status_code == 200
        return len(queries)

    first = make_workday_application(S.DOCUMENTS_REVIEW, bank_product=seeded_product())
    add_slot(first, SlotStatus.UPLOADED)
    make_task(first, timezone.now())
    one = measure()
    for _ in range(24):
        application = make_workday_application(S.DOCUMENTS_REVIEW, bank_product=seeded_product())
        add_slot(application, SlotStatus.UPLOADED)
        make_task(application, timezone.now())

    assert measure() == one


# --- Resumen ----------------------------------------------------------------------------------


def test_summary_counts_every_segment_with_the_filters_but_not_attention(
    advisor_client: APIClient, make_workday_application: AppFactory, make_task: TaskFactory
) -> None:
    review = make_workday_application(S.DOCUMENTS_REVIEW, bank_product=seeded_product())
    add_slot(review, SlotStatus.UPLOADED)
    ready = make_workday_application(S.READY_TO_FILE, bank_product=seeded_product())
    make_task(ready, timezone.now() - timedelta(hours=1))
    make_workday_application(S.FILED, bank_product=seeded_product("FNA"))

    assert segment_counts(advisor_client) == {
        "total": 3,
        "REVIEW_DOCUMENTS": 1,
        "READY_TO_FILE": 1,
        "FILED": 1,
        "IN_ANALYSIS": 0,
        "OBSERVED": 0,
        "BUYER_INACTIVE": 0,
        "TASKS_DUE": 1,
    }
    bank_id = str(BankProduct.objects.get(pk=seeded_product().pk).bank_id)
    filtered = segment_counts(advisor_client, bank_id=bank_id, attention="FILED")
    assert (filtered["total"], filtered["FILED"], filtered["READY_TO_FILE"]) == (2, 0, 1)
    body = advisor_client.get(SUMMARY_URL).json()
    assert [row["code"] for row in body["segments"]] == AttentionSegment.values
    assert body["segments"][5]["label"] == "Comprador sin actividad"


def test_summary_is_a_single_query(
    advisor_user: User, make_workday_application: AppFactory
) -> None:
    make_workday_application(S.DRAFT)
    applications = services.workday_applications(advisor_user)

    with CaptureQueriesContext(connection) as queries:
        services.summary(applications)

    assert len(queries) == 1


def test_summary_validates_its_filters(advisor_client: APIClient) -> None:
    assert_error(advisor_client.get(SUMMARY_URL, {"stage": "NOPE"}), 400, "VALIDATION_ERROR")
