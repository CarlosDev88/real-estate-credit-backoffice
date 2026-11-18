"""Auditoría de los reportes: ``report_exported`` (CSV directo y exportación asíncrona) y
la descarga de una exportación."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.audit.actions import AuditAction as A
from apps.audit.actions import AuditResult as R
from apps.audit.models import AuditEvent
from apps.catalogs.workflow import ApplicationStatus as S
from apps.identity.models import User
from apps.reporting import export_jobs
from apps.reporting.models import ReportExportJob

pytestmark = pytest.mark.django_db

CSV_URL = "/api/v1/reports/applications.csv"
JOBS_URL = "/api/v1/reports/applications/export-jobs"

AppFactory = Callable[..., CreditApplication]
Capture = Callable[..., Any]


def _download(response: Any) -> None:
    b"".join(response.streaming_content)


def test_the_direct_csv_is_audited_with_filter_names_only(
    admin_client: APIClient,
    admin_user: User,
    advisor_user: User,
    make_report_application: AppFactory,
) -> None:
    make_report_application(status=S.FILED)

    _download(admin_client.get(CSV_URL, {"advisor_id": str(advisor_user.pk), "status": S.FILED}))

    event = AuditEvent.objects.get(action=A.REPORT_EXPORTED)
    assert (event.result, event.actor_user, event.resource_type, event.resource_id) == (
        R.SUCCESS,
        admin_user,
        "reports",
        None,
    )
    assert event.metadata == {
        "report_type": "applications",
        "format": "csv",
        "row_count": 1,
        "filters": ["advisor_id", "date_from", "date_to", "status"],
    }
    assert str(advisor_user.pk) not in json.dumps(event.metadata)


def test_a_csv_over_the_limit_is_not_audited_as_exported(
    admin_client: APIClient, make_report_application: AppFactory
) -> None:
    make_report_application()
    make_report_application()

    with override_settings(REPORTS_CSV_MAX_ROWS=1):
        assert admin_client.get(CSV_URL).status_code == 422

    assert not AuditEvent.objects.filter(action=A.REPORT_EXPORTED).exists()


def test_a_completed_export_job_is_audited_on_its_record(
    advisor_client: APIClient,
    advisor_user: User,
    make_report_application: AppFactory,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    make_report_application()

    with django_capture_on_commit_callbacks(execute=True):
        body = advisor_client.post(JOBS_URL, {"purpose_code": "PURCHASE_NEW"}, format="json").json()

    event = AuditEvent.objects.get(action=A.REPORT_EXPORTED)
    assert (event.actor_user, event.resource_type, str(event.resource_id)) == (
        advisor_user,
        "report_export_jobs",
        body["id"],
    )
    assert event.metadata == {
        "report_type": "applications",
        "format": "csv",
        "row_count": 1,
        "filters": ["date_from", "date_to", "purpose_code"],
    }


def test_a_failed_export_job_is_not_audited_as_exported(advisor_user: User) -> None:
    job = ReportExportJob.objects.create(
        requested_by=advisor_user, report_type="applications", filters={"date_from": "x"}
    )
    User.objects.filter(pk=advisor_user.pk).update(is_active=False)

    export_jobs.build_export(job.pk)

    assert not AuditEvent.objects.filter(action=A.REPORT_EXPORTED).exists()


def test_the_export_download_is_audited_without_the_signed_url(
    advisor_client: APIClient, advisor_user: User, make_report_application: AppFactory
) -> None:
    make_report_application()
    body = advisor_client.post(JOBS_URL, {}, format="json").json()
    export_jobs.build_export(body["id"])

    download = advisor_client.get(f"/api/v1/report-export-jobs/{body['id']}/download").json()

    event = AuditEvent.objects.get(action=A.REPORT_EXPORT_DOWNLOADED)
    assert (event.result, event.actor_user, event.resource_type, str(event.resource_id)) == (
        R.SUCCESS,
        advisor_user,
        "report_export_jobs",
        body["id"],
    )
    assert download["url"] not in json.dumps(event.metadata)
    assert event.metadata["fields"] == []


def test_a_not_ready_download_is_not_audited_as_downloaded(
    advisor_client: APIClient, advisor_user: User
) -> None:
    job = ReportExportJob.objects.create(requested_by=advisor_user, report_type="applications")

    assert advisor_client.get(f"/api/v1/report-export-jobs/{job.pk}/download").status_code == 409

    assert not AuditEvent.objects.filter(action=A.REPORT_EXPORT_DOWNLOADED).exists()
