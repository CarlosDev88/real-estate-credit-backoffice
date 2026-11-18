"""Endpoints del dashboard: alcance por rol, embudo, resumen, carga y bancos."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.banking.models import Bank, BankProduct
from apps.catalogs.workflow import ApplicationStatus as S
from apps.crm.models import Client
from apps.filings.models import Filing
from apps.identity.models import User
from apps.tasks.models import Task, TaskStatus
from apps.tasks.services import start_of_today
from tests.applications.conftest import catalog_item, seeded_product
from tests.reporting.conftest import (
    BANK_RESULTS_URL,
    FUNNEL_URL,
    SUMMARY_URL,
    WORKLOAD_URL,
    add_financing,
    add_history,
    add_response,
    at,
)

pytestmark = pytest.mark.django_db

AppFactory = Callable[..., CreditApplication]
TaskFactory = Callable[..., Task]
FilingFactory = Callable[..., Filing]

ALL_URLS = [SUMMARY_URL, FUNNEL_URL, WORKLOAD_URL, BANK_RESULTS_URL]
# Sesión, permisos y alcance son fijos; el resumen consulta además el alcance de CRM.
MAX_QUERIES = {SUMMARY_URL: 11, FUNNEL_URL: 6, WORKLOAD_URL: 8, BANK_RESULTS_URL: 6}


def _stages(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {stage["code"]: stage for stage in body["stages"]}


def _snapshot(body: dict[str, Any]) -> dict[str, int]:
    return {row["status"]: row["count"] for row in body["snapshot"]}


# --- Permisos y alcance por rol -----------------------------------------------------------


@pytest.mark.parametrize("url", ALL_URLS)
def test_the_construction_partner_has_no_dashboard(partner_client: APIClient, url: str) -> None:
    response = partner_client.get(url)

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize("url", ALL_URLS)
def test_the_dashboard_requires_a_session(api_client: APIClient, url: str) -> None:
    assert api_client.get(url).status_code == 401


@pytest.mark.parametrize("url", [WORKLOAD_URL, BANK_RESULTS_URL])
def test_the_broker_cannot_see_workload_or_bank_results(broker_client: APIClient, url: str) -> None:
    response = broker_client.get(url)

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_each_role_counts_only_its_scope(
    admin_client: APIClient,
    advisor_client: APIClient,
    broker_client: APIClient,
    broker_user: User,
    other_advisor: User,
    make_report_application: AppFactory,
) -> None:
    make_report_application()
    make_report_application(origin_user=broker_user)
    make_report_application(advisor=other_advisor)

    def created(client: APIClient) -> int:
        return int(client.get(SUMMARY_URL).json()["applications_created"])

    assert created(admin_client) == 3
    assert created(advisor_client) == 2
    assert created(broker_client) == 1


def test_the_broker_summary_has_counts_but_no_amounts(
    broker_client: APIClient, broker_user: User, make_report_application: AppFactory
) -> None:
    application = make_report_application(origin_user=broker_user)
    add_financing(application, 300_000_000)

    body = broker_client.get(SUMMARY_URL).json()

    assert "amounts" not in body
    assert body["applications_created"] == 1
    assert body["tasks"] == {"overdue": 0, "due_today": 0}


# --- Embudo -------------------------------------------------------------------------------


def test_the_funnel_counts_the_cohort_once_per_stage_even_with_skips(
    admin_client: APIClient, make_report_application: AppFactory
) -> None:
    today = timezone.localdate()
    # Pasa dos veces por revisión documental: cuenta una vez.
    twice = make_report_application(status=S.WAITING_DOCUMENTS)
    add_history(twice, S.DRAFT, S.DOCUMENTS_REVIEW, S.WAITING_DOCUMENTS, S.DOCUMENTS_REVIEW)
    # El historial salta de borrador a desembolsada: cuenta en todas las etapas.
    skipped = make_report_application(status=S.DISBURSED)
    add_history(skipped, S.DRAFT, S.DISBURSED)
    # Radicada sin pasar por "lista para radicar": cuenta hasta FILED.
    filed = make_report_application(status=S.FILED)
    add_history(filed, S.DRAFT, S.DOCUMENTS_REVIEW, S.FILED)
    # Solo borrador.
    make_report_application()
    # Creada antes del periodo: no es de la cohorte aunque haya llegado lejos.
    old = make_report_application(
        status=S.APPROVED, created_at=at(today.replace(day=1) - timedelta(days=1))
    )
    add_history(old, S.DRAFT, S.APPROVED)

    stages = _stages(admin_client.get(FUNNEL_URL).json())

    assert {code: stage["count"] for code, stage in stages.items()} == {
        "CREATED": 4,
        "DOCUMENTS_COMPLETE": 3,
        "READY_TO_FILE": 2,
        "FILED": 2,
        "APPROVED": 1,
        "DISBURSED": 1,
    }
    assert stages["CREATED"]["label"] == "Creadas"
    assert stages["CREATED"]["conversion"] == "1.0000"
    assert stages["CREATED"]["step_conversion"] is None
    assert stages["DOCUMENTS_COMPLETE"]["conversion"] == "0.7500"
    assert stages["READY_TO_FILE"]["step_conversion"] == "0.6667"
    assert stages["APPROVED"]["conversion"] == "0.2500"
    assert stages["APPROVED"]["step_conversion"] == "0.5000"
    assert [stage["code"] for stage in admin_client.get(FUNNEL_URL).json()["stages"]] == [
        "CREATED",
        "DOCUMENTS_COMPLETE",
        "READY_TO_FILE",
        "FILED",
        "APPROVED",
        "DISBURSED",
    ]


def test_conversion_is_null_when_there_is_nothing_to_divide(
    admin_client: APIClient, make_report_application: AppFactory
) -> None:
    empty = _stages(admin_client.get(FUNNEL_URL).json())

    assert all(stage["count"] == 0 for stage in empty.values())
    assert all(stage["conversion"] is None for stage in empty.values())
    assert all(stage["step_conversion"] is None for stage in empty.values())

    make_report_application()
    one = _stages(admin_client.get(FUNNEL_URL).json())

    assert one["DOCUMENTS_COMPLETE"]["conversion"] == "0.0000"
    assert one["DOCUMENTS_COMPLETE"]["step_conversion"] == "0.0000"
    # La etapa anterior está en 0: no hay contra qué dividir.
    assert one["READY_TO_FILE"]["step_conversion"] is None


def test_the_funnel_respects_the_filters(
    admin_client: APIClient, make_report_application: AppFactory
) -> None:
    make_report_application()
    make_report_application(purpose_item=catalog_item("loan_purpose", "PURCHASE_USED"))

    body = admin_client.get(FUNNEL_URL, {"purpose_code": "PURCHASE_USED"}).json()

    assert _stages(body)["CREATED"]["count"] == 1


# --- Resumen ------------------------------------------------------------------------------


def test_the_snapshot_lists_every_status_of_today_without_the_date_filter(
    advisor_client: APIClient, make_report_application: AppFactory, other_advisor: User
) -> None:
    make_report_application(status=S.FILED, created_at=at(date(2025, 6, 1)))
    make_report_application(status=S.FILED)
    make_report_application()
    make_report_application(status=S.APPROVED, advisor=other_advisor)

    body = advisor_client.get(SUMMARY_URL).json()

    assert [row["status"] for row in body["snapshot"]] == list(S.values)
    assert _snapshot(body)[S.FILED] == 2
    assert _snapshot(body)[S.DRAFT] == 1
    assert _snapshot(body)[S.APPROVED] == 0
    assert body["snapshot"][0]["status_label"] == "Borrador"
    assert body["applications_created"] == 2


def test_the_summary_adds_requested_approved_and_disbursed_amounts(
    advisor_client: APIClient,
    make_report_application: AppFactory,
    make_filing: FilingFactory,
) -> None:
    now = timezone.now()
    approved = make_report_application(status=S.APPROVED)
    add_financing(approved, 300_000_000)
    add_response(
        make_filing(approved),
        "APPROVED",
        now,
        approved_amount_cop=280_000_000,
        approved_term_months=240,
    )
    disbursed = make_report_application(status=S.DISBURSED)
    add_financing(disbursed, 200_000_000)
    filing = make_filing(disbursed)
    add_response(filing, "APPROVED", now, approved_amount_cop=200_000_000, approved_term_months=180)
    add_response(filing, "DISBURSED", now, disbursed_amount_cop=195_000_000)
    make_report_application()  # Sin financiación: no suma.

    body = advisor_client.get(SUMMARY_URL).json()

    assert body["amounts"] == {
        "requested_total": "500000000.00",
        "approved_total": "480000000.00",
        "disbursed_total": "195000000.00",
    }


def test_the_summary_counts_clients_created_in_the_period(
    admin_client: APIClient, advisor_client: APIClient, make_report_application: AppFactory
) -> None:
    make_report_application()
    old = make_report_application()
    Client.objects.filter(pk=old.opportunity.client_id).update(created_at=at(date(2025, 1, 10)))
    Client.objects.create(
        document_type_item=old.opportunity.client.document_type_item,
        document_number="5550001",
        first_names="Sin",
        last_names="Oportunidad",
    )

    assert admin_client.get(SUMMARY_URL).json()["clients_created"] == 2
    # El asesor solo ve los clientes de sus oportunidades.
    assert advisor_client.get(SUMMARY_URL).json()["clients_created"] == 1


def test_the_summary_counts_overdue_and_today_tasks_of_the_scope(
    admin_client: APIClient,
    advisor_client: APIClient,
    other_advisor: User,
    make_report_application: AppFactory,
    make_task: TaskFactory,
) -> None:
    now = timezone.now()
    mine = make_report_application()
    make_task(mine, now - timedelta(days=2))
    make_task(mine, start_of_today() + timedelta(hours=12))
    make_task(mine, now + timedelta(days=3))
    make_task(mine, now - timedelta(days=2), status=TaskStatus.CANCELLED, cancelled_at=now)
    theirs = make_report_application(advisor=other_advisor)
    make_task(theirs, now - timedelta(days=1), assigned_to=other_advisor)

    assert advisor_client.get(SUMMARY_URL).json()["tasks"] == {"overdue": 1, "due_today": 1}
    assert admin_client.get(SUMMARY_URL).json()["tasks"] == {"overdue": 2, "due_today": 1}
    by_advisor = admin_client.get(SUMMARY_URL, {"advisor_id": str(other_advisor.pk)}).json()
    assert by_advisor["tasks"] == {"overdue": 1, "due_today": 0}


# --- Carga por asesor ---------------------------------------------------------------------


def test_the_workload_has_one_row_per_advisor(
    admin_client: APIClient,
    advisor_client: APIClient,
    advisor_user: User,
    other_advisor: User,
    make_report_application: AppFactory,
    make_task: TaskFactory,
) -> None:
    waiting = make_report_application(status=S.WAITING_BUYER_DATA)
    make_report_application(status=S.READY_TO_FILE)
    make_report_application(status=S.DISBURSED)  # Terminal: no es carga.
    make_report_application(status=S.WAITING_DOCUMENTS, created_at=at(date(2025, 2, 1)))
    make_task(waiting, timezone.now() - timedelta(days=1))
    make_report_application(status=S.FILED, advisor=other_advisor)

    mine = advisor_client.get(WORKLOAD_URL).json()["advisors"]
    everyone = {row["advisor_id"]: row for row in admin_client.get(WORKLOAD_URL).json()["advisors"]}

    assert mine == [
        {
            "advisor_id": str(advisor_user.pk),
            "advisor_name": "Andrea García",
            "open_applications": 3,
            "overdue_tasks": 1,
            "due_today_tasks": 0,
            "waiting_buyer": 2,
            "ready_to_file": 1,
        }
    ]
    assert set(everyone) == {str(advisor_user.pk), str(other_advisor.pk)}
    assert everyone[str(other_advisor.pk)]["open_applications"] == 1
    assert everyone[str(advisor_user.pk)] == mine[0]


def test_the_admin_can_narrow_the_workload_to_one_advisor(
    admin_client: APIClient, other_advisor: User, make_report_application: AppFactory
) -> None:
    make_report_application()

    rows = admin_client.get(WORKLOAD_URL, {"advisor_id": str(other_advisor.pk)}).json()["advisors"]

    assert [row["advisor_id"] for row in rows] == [str(other_advisor.pk)]
    assert rows[0]["open_applications"] == 0


# --- Resultados por banco -----------------------------------------------------------------


def test_bank_results_group_the_filings_of_the_period_by_bank(
    advisor_client: APIClient,
    make_report_application: AppFactory,
    make_filing: FilingFactory,
) -> None:
    now = timezone.now()
    bancolombia = seeded_product("BANCOLOMBIA")
    other_bank = Bank.objects.exclude(code="BANCOLOMBIA").order_by("name").first()
    assert other_bank is not None
    other_product = BankProduct.objects.filter(bank=other_bank).first()
    assert other_product is not None

    # Devuelta a los 2 días y aprobada después (cuenta en las dos).
    first = make_filing(
        make_report_application(status=S.APPROVED),
        bank_product=bancolombia,
        filed_at=now - timedelta(days=5),
    )
    add_response(first, "RETURNED", now - timedelta(days=3))
    add_response(
        first, "APPROVED", now - timedelta(days=1), approved_amount_cop=1, approved_term_months=12
    )
    # Rechazada al día siguiente.
    second = make_filing(
        make_report_application(status=S.REJECTED),
        bank_product=bancolombia,
        filed_at=now - timedelta(days=4),
    )
    add_response(second, "REJECTED", now - timedelta(days=3))
    # Sin respuesta: no entra en el promedio.
    make_filing(
        make_report_application(status=S.FILED),
        bank_product=bancolombia,
        filed_at=now - timedelta(hours=1),
    )
    # Otro banco.
    make_filing(
        make_report_application(status=S.FILED),
        bank_product=other_product,
        filed_at=now - timedelta(hours=1),
    )
    # Radicada antes del periodo: no cuenta.
    make_filing(
        make_report_application(status=S.FILED),
        bank_product=bancolombia,
        filed_at=at(date(2025, 5, 1)),
    )

    params = {"date_from": (timezone.localdate() - timedelta(days=10)).isoformat()}
    banks = {
        row["bank_name"]: row
        for row in advisor_client.get(BANK_RESULTS_URL, params).json()["banks"]
    }

    assert banks[bancolombia.bank.name] == {
        "bank_id": str(bancolombia.bank_id),
        "bank_name": bancolombia.bank.name,
        "filings": 3,
        "returned": 1,
        "approved": 1,
        "rejected": 1,
        "disbursed": 0,
        "avg_days_to_response": "1.5",
    }
    assert banks[other_bank.name]["filings"] == 1
    assert banks[other_bank.name]["avg_days_to_response"] is None

    only = advisor_client.get(BANK_RESULTS_URL, {**params, "bank_id": str(other_bank.pk)}).json()
    assert [row["bank_name"] for row in only["banks"]] == [other_bank.name]


# --- Consultas ----------------------------------------------------------------------------


def _queries(client: APIClient, url: str) -> int:
    with CaptureQueriesContext(connection) as context:
        assert client.get(url).status_code == 200
    return len(context.captured_queries)


@pytest.mark.parametrize("url", ALL_URLS)
def test_the_number_of_queries_does_not_grow_with_the_rows(
    admin_client: APIClient,
    make_report_application: AppFactory,
    make_filing: FilingFactory,
    make_task: TaskFactory,
    django_assert_max_num_queries: Any,
    url: str,
) -> None:
    def add_rows() -> None:
        application = make_report_application(status=S.FILED)
        add_history(application, S.DRAFT, S.DOCUMENTS_REVIEW, S.FILED)
        add_financing(application, 100_000_000)
        add_response(make_filing(application), "RECEIVED", timezone.now())
        make_task(application, timezone.now() - timedelta(days=1))

    add_rows()
    few = _queries(admin_client, url)
    for _ in range(4):
        add_rows()

    assert _queries(admin_client, url) == few
    with django_assert_max_num_queries(MAX_QUERIES[url]):
        admin_client.get(url)
