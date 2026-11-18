"""Reportes operativos: embudo con desglose, listado de solicitudes, CSV, señal y cupo."""

import csv
import io
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

import pytest
from django.conf import settings
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.catalogs.workflow import ApplicationStatus as S
from apps.crm.models import Client
from apps.filings.models import Filing
from apps.identity.models import User
from apps.partners.models import Partner, Project
from apps.reporting.exports import COLUMNS, mask_document, neutralize_formula
from apps.reporting.serializers import ReportApplicationSerializer
from apps.reporting.signals import report_exported
from tests.applications.conftest import catalog_item, seeded_product
from tests.reporting.conftest import (
    FUNNEL_URL,
    SUMMARY_URL,
    add_financing,
    add_history,
    add_property,
    at,
)

pytestmark = pytest.mark.django_db

REPORT_FUNNEL_URL = "/api/v1/reports/funnel"
APPLICATIONS_URL = "/api/v1/reports/applications"
CSV_URL = "/api/v1/reports/applications.csv"
REPORT_URLS = [REPORT_FUNNEL_URL, APPLICATIONS_URL, CSV_URL]

AppFactory = Callable[..., CreditApplication]
FilingFactory = Callable[..., Filing]


def _csv_text(response: Any) -> str:
    return b"".join(response.streaming_content).decode("utf-8")


def _csv_rows(response: Any) -> list[list[str]]:
    text = _csv_text(response)
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text[1:])))


@pytest.fixture
def exported() -> Iterator[list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def receiver(sender: Any, **kwargs: Any) -> None:
        calls.append(kwargs)

    report_exported.connect(receiver, weak=False)
    yield calls
    report_exported.disconnect(receiver)


# --- Permisos -----------------------------------------------------------------------------


@pytest.mark.parametrize("url", REPORT_URLS)
def test_the_broker_has_no_reports(broker_client: APIClient, url: str) -> None:
    response = broker_client.get(url)

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize("url", REPORT_URLS)
def test_the_construction_partner_has_no_reports(partner_client: APIClient, url: str) -> None:
    assert partner_client.get(url).status_code == 403


@pytest.mark.parametrize("url", REPORT_URLS)
def test_reports_apply_the_filter_scope(
    advisor_client: APIClient, other_advisor: User, url: str
) -> None:
    response = advisor_client.get(url, {"advisor_id": str(other_advisor.pk)})

    assert response.status_code == 403
    assert response.json()["code"] == "FILTER_OUT_OF_SCOPE"


# --- Embudo -------------------------------------------------------------------------------


def test_the_report_funnel_matches_the_dashboard_and_filters_by_status(
    admin_client: APIClient, make_report_application: AppFactory
) -> None:
    filed = make_report_application(status=S.FILED)
    add_history(filed, S.DRAFT, S.DOCUMENTS_REVIEW, S.READY_TO_FILE, S.FILED)
    approved = make_report_application(status=S.APPROVED)
    add_history(approved, S.DRAFT, S.APPROVED)
    make_report_application()

    report = admin_client.get(REPORT_FUNNEL_URL).json()
    dashboard = admin_client.get(FUNNEL_URL).json()
    by_status = admin_client.get(
        REPORT_FUNNEL_URL, [("status", S.FILED), ("status", S.APPROVED)]
    ).json()

    assert report["stages"] == dashboard["stages"]
    assert report["group_by"] is None
    assert report["groups"] == []
    assert by_status["stages"][0]["count"] == 2


def test_an_unknown_status_or_group_by_is_rejected(admin_client: APIClient) -> None:
    assert admin_client.get(REPORT_FUNNEL_URL, {"status": "LOST"}).status_code == 400
    assert admin_client.get(REPORT_FUNNEL_URL, {"group_by": "city"}).status_code == 400


def test_the_report_funnel_breaks_down_by_bank(
    admin_client: APIClient, make_report_application: AppFactory
) -> None:
    product = seeded_product()
    make_report_application(bank_product=product)
    with_bank = make_report_application(bank_product=product, status=S.FILED)
    add_history(with_bank, S.DRAFT, S.FILED)
    make_report_application()

    body = admin_client.get(REPORT_FUNNEL_URL, {"group_by": "bank"}).json()

    groups = {group["label"]: group for group in body["groups"]}
    assert body["group_by"] == "bank"
    assert [group["label"] for group in body["groups"]] == [product.bank.name, "Sin banco"]
    assert groups[product.bank.name]["key"] == str(product.bank_id)
    assert groups[product.bank.name]["stages"][0]["count"] == 2
    assert groups[product.bank.name]["stages"][3]["count"] == 1  # FILED
    assert groups["Sin banco"]["key"] is None
    assert groups["Sin banco"]["stages"][0]["count"] == 1


def test_the_report_funnel_breaks_down_by_advisor_and_purpose(
    admin_client: APIClient,
    other_advisor: User,
    make_report_application: AppFactory,
) -> None:
    make_report_application()
    make_report_application(advisor=other_advisor)
    make_report_application(
        advisor=other_advisor, purpose_item=catalog_item("loan_purpose", "PURCHASE_USED")
    )

    advisors = admin_client.get(REPORT_FUNNEL_URL, {"group_by": "advisor"}).json()["groups"]
    purposes = admin_client.get(REPORT_FUNNEL_URL, {"group_by": "purpose"}).json()["groups"]

    assert [(group["label"], group["stages"][0]["count"]) for group in advisors] == [
        ("Andrea García", 1),
        ("Marta García", 2),
    ]
    assert {group["key"]: group["stages"][0]["count"] for group in purposes} == {
        "PURCHASE_NEW": 2,
        "PURCHASE_USED": 1,
    }


# --- Listado ------------------------------------------------------------------------------


def test_the_applications_report_has_the_operational_columns_and_masks_the_document(
    advisor_client: APIClient,
    advisor_user: User,
    make_report_application: AppFactory,
    make_filing: FilingFactory,
    make_project: Callable[..., Project],
) -> None:
    application = make_report_application(status=S.FILED, bank_product=seeded_product())
    add_financing(application, 294_000_000)
    add_property(application, make_project(name="Verona 118"))
    add_history(application, S.DRAFT, S.FILED)
    make_filing(application)

    body = advisor_client.get(APPLICATIONS_URL).json()

    assert body["total"] == 1
    row = body["items"][0]
    assert list(row) == [name for name, _ in COLUMNS]
    client = application.opportunity.client
    assert row["code"] == application.code
    assert row["status"] == "FILED"
    assert row["status_label"] == "Radicada"
    assert row["purpose"] == application.purpose_item.label
    assert row["advisor_name"] == advisor_user.get_full_name()
    assert row["client_name"] == client.full_name
    assert row["client_document_masked"] == f"******{client.document_number[-4:]}"
    assert client.document_number not in str(row)
    assert row["bank_name"] == application.bank_product.bank.name  # type: ignore[union-attr]
    assert row["project_name"] == "Verona 118"
    assert row["requested_amount"] == "294000000.00"
    assert row["filings_count"] == 1
    assert row["last_status_change_at"] is not None
    assert not {"email", "phone", "address", "document_number"} & set(row)


def test_the_applications_report_is_paginated_newest_first_by_creation_date(
    admin_client: APIClient, make_report_application: AppFactory
) -> None:
    today = timezone.localdate()
    older = make_report_application(created_at=at(today.replace(day=1), hour=0))
    newer = make_report_application()
    make_report_application(created_at=at(date(2025, 1, 5)))  # Fuera del periodo.

    body = admin_client.get(APPLICATIONS_URL, {"page_size": 1}).json()

    assert body["total"] == 2
    assert [item["code"] for item in body["items"]] == [newer.code]
    assert body["next"] is not None
    second = admin_client.get(APPLICATIONS_URL, {"page_size": 1, "page": 2}).json()
    assert [item["code"] for item in second["items"]] == [older.code]


def test_the_applications_report_has_nullable_columns_without_data(
    admin_client: APIClient, make_report_application: AppFactory
) -> None:
    make_report_application()

    row = admin_client.get(APPLICATIONS_URL).json()["items"][0]

    assert row["bank_name"] is None
    assert row["project_name"] is None
    assert row["requested_amount"] is None
    assert row["filings_count"] == 0


def test_the_applications_report_query_count_does_not_grow(
    admin_client: APIClient,
    make_report_application: AppFactory,
    make_filing: FilingFactory,
) -> None:
    def add_row() -> None:
        application = make_report_application(bank_product=seeded_product())
        add_financing(application, 100_000_000)
        make_filing(application)

    def queries(url: str) -> int:
        with CaptureQueriesContext(connection) as context:
            response = admin_client.get(url)
            if url == CSV_URL:
                _csv_text(response)
        return len(context.captured_queries)

    add_row()
    few = {url: queries(url) for url in (APPLICATIONS_URL, CSV_URL)}
    for _ in range(4):
        add_row()

    assert {url: queries(url) for url in (APPLICATIONS_URL, CSV_URL)} == few


# --- CSV ----------------------------------------------------------------------------------


def test_the_csv_has_bom_spanish_headers_and_the_same_columns(
    advisor_client: APIClient, make_report_application: AppFactory, exported: list[Any]
) -> None:
    application = make_report_application(status=S.FILED)
    add_financing(application, 294_000_000)
    Client.objects.filter(pk=application.opportunity.client_id).update(
        first_names="José Ñoño", last_names="Pérez"
    )

    today = timezone.localdate()
    first = today.replace(day=1)
    response = advisor_client.get(
        CSV_URL,
        {"date_from": first.isoformat(), "date_to": today.isoformat()},
        HTTP_ACCEPT="text/csv",
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Content-Disposition"] == (
        f'attachment; filename="solicitudes_{first.isoformat()}_{today.isoformat()}.csv"'
    )
    rows = _csv_rows(response)
    assert rows[0] == [header for _, header in COLUMNS]
    assert rows[0][1] == "Fecha de creación"
    assert len(rows) == 2
    row = dict(zip([name for name, _ in COLUMNS], rows[1], strict=True))
    assert row["code"] == application.code
    assert row["status_label"] == "Radicada"
    assert row["client_name"] == "José Ñoño Pérez"
    assert row["client_document_masked"].startswith("******")
    assert row["requested_amount"] == "294000000"
    assert row["bank_name"] == ""
    assert len(row["created_at"]) == len("2026-11-17 10:30")
    assert set(ReportApplicationSerializer().fields) == {name for name, _ in COLUMNS}


def test_the_csv_neutralizes_formulas(
    admin_client: APIClient, make_report_application: AppFactory, exported: list[Any]
) -> None:
    application = make_report_application()
    Client.objects.filter(pk=application.opportunity.client_id).update(
        first_names='=HYPERLINK("http://malo")', last_names="+1"
    )
    project = Project.objects.create(
        partner=Partner.objects.create(legal_name="Constructora", tax_id="900111222-3"),
        name="@SUM(A1:A9)",
        address="Calle 1",
        city_item=catalog_item("municipality", "11001"),
        created_by=application.assigned_advisor,
    )
    add_property(application, project)

    rows = _csv_rows(admin_client.get(CSV_URL))

    row = dict(zip([name for name, _ in COLUMNS], rows[1], strict=True))
    assert row["client_name"] == '\'=HYPERLINK("http://malo") +1'
    assert row["project_name"] == "'@SUM(A1:A9)"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("=1+1", "'=1+1"),
        ("+57 300", "'+57 300"),
        ("-2", "'-2"),
        ("@cmd", "'@cmd"),
        ("\tx", "'\tx"),
        ("\rx", "'\rx"),
        ("Laura", "Laura"),
        ("", ""),
    ],
)
def test_formula_prefixes_are_neutralized(value: str, expected: str) -> None:
    assert neutralize_formula(value) == expected


def test_the_document_mask_keeps_only_the_last_four() -> None:
    assert mask_document("1032445908") == "******5908"
    assert mask_document("123") == "******123"
    assert mask_document("") == ""


def test_the_csv_over_the_limit_is_rejected(
    admin_client: APIClient, make_report_application: AppFactory, exported: list[Any]
) -> None:
    make_report_application()
    make_report_application()

    with override_settings(REPORTS_CSV_MAX_ROWS=1):
        response = admin_client.get(CSV_URL, HTTP_ACCEPT="text/csv")

    assert response.status_code == 422
    assert response["Content-Type"] == "application/json"
    assert response.json()["code"] == "EXPORT_TOO_LARGE"
    assert "asíncrona" in response.json()["message"]
    assert exported == []


def test_the_csv_at_the_limit_is_allowed(
    admin_client: APIClient, make_report_application: AppFactory, exported: list[Any]
) -> None:
    make_report_application()

    with override_settings(REPORTS_CSV_MAX_ROWS=1):
        response = admin_client.get(CSV_URL)

    assert response.status_code == 200
    assert len(_csv_rows(response)) == 2


def test_the_csv_emits_report_exported_once_with_the_validated_filters(
    admin_client: APIClient,
    admin_user: User,
    make_report_application: AppFactory,
    exported: list[Any],
) -> None:
    make_report_application(status=S.FILED)
    make_report_application()

    today = timezone.localdate()
    response = admin_client.get(
        CSV_URL, {"date_to": today.isoformat(), "status": S.FILED, "unknown": "x"}
    )
    _csv_text(response)

    assert len(exported) == 1
    assert exported[0] == {
        "signal": report_exported,
        "user": admin_user,
        "report_type": "applications",
        "filters": {
            "date_from": today.replace(day=1).isoformat(),
            "date_to": today.isoformat(),
            "advisor_id": None,
            "partner_id": None,
            "project_id": None,
            "bank_id": None,
            "purpose_code": None,
            "status": [S.FILED],
        },
        "row_count": 1,
        "format": "csv",
        "job": None,
    }


def test_the_paginated_report_does_not_emit_report_exported(
    admin_client: APIClient, make_report_application: AppFactory, exported: list[Any]
) -> None:
    make_report_application()

    admin_client.get(APPLICATIONS_URL)

    assert exported == []


# --- Cupo de consumo ----------------------------------------------------------------------


def test_the_default_reports_rate_is_20_per_minute() -> None:
    assert settings.AUTH_RATE_LIMITS["reports"] == "20/1m"


def test_dashboard_and_reports_share_a_per_user_rate_limit(
    admin_client: APIClient, advisor_client: APIClient
) -> None:
    limits = {**settings.AUTH_RATE_LIMITS, "reports": "2/1m"}
    with override_settings(AUTH_RATE_LIMITS=limits):
        assert admin_client.get(SUMMARY_URL).status_code == 200
        assert admin_client.get(REPORT_FUNNEL_URL).status_code == 200
        limited = admin_client.get(APPLICATIONS_URL)
        # Otro usuario tiene su propio cupo.
        assert advisor_client.get(SUMMARY_URL).status_code == 200

    assert limited.status_code == 429
    assert limited.json()["code"] == "RATE_LIMITED"
    assert "Retry-After" in limited
