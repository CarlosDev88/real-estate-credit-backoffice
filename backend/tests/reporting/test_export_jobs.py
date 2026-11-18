"""Exportación asíncrona del reporte de solicitudes (solo CSV)."""

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.catalogs.workflow import ApplicationStatus as S
from apps.documents.exceptions import StorageUnavailable
from apps.documents.models import FileObject, ScanStatus
from apps.documents.storage import MemoryStorage, get_storage
from apps.identity.models import RolePermission, User
from apps.reporting import export_jobs
from apps.reporting.models import ExportJobStatus, ReportExportJob
from apps.reporting.signals import report_exported

pytestmark = pytest.mark.django_db

JOBS_URL = "/api/v1/reports/applications/export-jobs"

AppFactory = Callable[..., CreditApplication]
Capture = Callable[..., Any]


def job_url(job: ReportExportJob | str, suffix: str = "") -> str:
    job_id = job if isinstance(job, str) else job.pk
    return f"/api/v1/report-export-jobs/{job_id}{suffix}"


def storage() -> MemoryStorage:
    current = get_storage()
    assert isinstance(current, MemoryStorage)
    return current


def csv_of(job: ReportExportJob) -> str:
    job.refresh_from_db()
    assert job.output_file_object is not None
    content, content_type = storage().objects[job.output_file_object.object_key]
    assert content_type == "text/csv"
    return content.decode("utf-8")


def make_job(user: User, **extra: Any) -> ReportExportJob:
    today = timezone.localdate()
    extra.setdefault(
        "filters",
        {
            "date_from": today.replace(day=1).isoformat(),
            "date_to": today.isoformat(),
            "advisor_id": None,
            "partner_id": None,
            "project_id": None,
            "bank_id": None,
            "purpose_code": None,
            "status": [],
        },
    )
    return ReportExportJob.objects.create(requested_by=user, report_type="applications", **extra)


def completed_job(user: User, *, expires_in: timedelta = timedelta(hours=24)) -> ReportExportJob:
    job = make_job(user)
    assert export_jobs.build_export(job.pk) == ExportJobStatus.COMPLETED
    job.refresh_from_db()
    if expires_in != timedelta(hours=24):
        # Se corre todo el trabajo en el tiempo para respetar `ck_report_export_jobs_dates`.
        expires_at = timezone.now() + expires_in
        completed_at = expires_at - timedelta(hours=24)
        ReportExportJob.objects.filter(pk=job.pk).update(
            started_at=completed_at, completed_at=completed_at, expires_at=expires_at
        )
        job.refresh_from_db()
    return job


@pytest.fixture
def exported() -> Iterator[list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def receiver(sender: Any, **kwargs: Any) -> None:
        calls.append(kwargs)

    report_exported.connect(receiver, weak=False)
    yield calls
    report_exported.disconnect(receiver)


# --- Ciclo completo -----------------------------------------------------------------------


def test_the_full_cycle_runs_in_eager_mode(
    advisor_client: APIClient,
    advisor_user: User,
    make_report_application: AppFactory,
    django_capture_on_commit_callbacks: Capture,
    exported: list[dict[str, Any]],
) -> None:
    filed = make_report_application(status=S.FILED)
    make_report_application()
    today = timezone.localdate()

    with django_capture_on_commit_callbacks(execute=True):
        response = advisor_client.post(JOBS_URL, {"status": [S.FILED]}, format="json")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["format"] == "csv"
    assert body["report_type_label"] == "Solicitudes"
    assert body["requested_by"] == {"id": str(advisor_user.pk), "name": "Andrea García"}
    assert body["filters"] == {
        "date_from": today.replace(day=1).isoformat(),
        "date_to": today.isoformat(),
        "advisor_id": None,
        "partner_id": None,
        "project_id": None,
        "bank_id": None,
        "purpose_code": None,
        "status": [S.FILED],
    }

    detail = advisor_client.get(job_url(body["id"])).json()
    assert detail["status"] == "COMPLETED"
    assert detail["status_label"] == "Terminada"
    assert detail["row_count"] == 1
    assert detail["error_code"] is None
    job = ReportExportJob.objects.get(pk=body["id"])
    assert job.completed_at is not None and job.expires_at is not None
    assert job.expires_at - job.completed_at == timedelta(hours=24)

    text = csv_of(job)
    assert text.startswith("﻿Código,")
    assert filed.code in text
    assert len(text.strip().splitlines()) == 2
    file_object = job.output_file_object
    assert file_object is not None
    assert file_object.scan_status == ScanStatus.CLEAN
    assert file_object.detected_mime_type == "text/csv"
    assert file_object.original_filename == (
        f"solicitudes_{today.replace(day=1).isoformat()}_{today.isoformat()}.csv"
    )
    assert file_object.object_key.startswith(f"reports/{job.pk}/")

    assert len(exported) == 1
    assert exported[0]["user"] == advisor_user
    assert exported[0]["report_type"] == "applications"
    assert exported[0]["filters"] == body["filters"]
    assert exported[0]["row_count"] == 1
    assert exported[0]["format"] == "csv"


def test_the_export_has_no_5000_row_limit_but_a_hard_cap(
    admin_user: User, make_report_application: AppFactory
) -> None:
    make_report_application()
    make_report_application()

    with override_settings(REPORTS_CSV_MAX_ROWS=1):
        assert completed_job(admin_user).row_count == 2
    with override_settings(REPORTS_EXPORT_MAX_ROWS=1):
        job = make_job(admin_user)
        assert export_jobs.build_export(job.pk) == ExportJobStatus.FAILED

    job.refresh_from_db()
    assert job.error_code == "EXPORT_TOO_LARGE"
    assert job.output_file_object is None


def test_the_request_body_is_validated(advisor_client: APIClient, other_advisor: User) -> None:
    unknown = advisor_client.post(JOBS_URL, {"format": "xlsx"}, format="json")
    out_of_scope = advisor_client.post(
        JOBS_URL, {"advisor_id": str(other_advisor.pk)}, format="json"
    )
    bad_range = advisor_client.post(
        JOBS_URL, {"date_from": "2024-01-01", "date_to": "2025-06-01"}, format="json"
    )

    assert unknown.status_code == 400
    assert out_of_scope.status_code == 403
    assert out_of_scope.json()["code"] == "FILTER_OUT_OF_SCOPE"
    assert bad_range.status_code == 400
    assert not ReportExportJob.objects.exists()


@pytest.mark.parametrize("client_fixture", ["broker_client", "partner_client"])
def test_only_admin_and_advisor_can_export(
    request: pytest.FixtureRequest, client_fixture: str
) -> None:
    client: APIClient = request.getfixturevalue(client_fixture)

    assert client.post(JOBS_URL, {}, format="json").status_code == 403
    assert client.get(JOBS_URL).status_code == 403


# --- Alcance recalculado ------------------------------------------------------------------


def test_the_scope_is_recalculated_when_the_job_runs(
    advisor_client: APIClient, other_advisor: User, make_report_application: AppFactory
) -> None:
    mine = make_report_application()
    leaving = make_report_application()
    # Sin ejecutar los `on_commit`: el trabajo queda pendiente.
    body = advisor_client.post(JOBS_URL, {}, format="json").json()
    CreditApplication.objects.filter(pk=leaving.pk).update(assigned_advisor=other_advisor)

    export_jobs.build_export(body["id"])

    job = ReportExportJob.objects.get(pk=body["id"])
    assert job.row_count == 1
    text = csv_of(job)
    assert mine.code in text
    assert leaving.code not in text


def test_a_user_who_lost_the_permission_gets_permission_revoked(
    advisor_user: User, make_report_application: AppFactory
) -> None:
    make_report_application()
    job = make_job(advisor_user)
    RolePermission.objects.filter(role__code="ADVISOR", permission__code="reports.export").delete()

    assert export_jobs.build_export(job.pk) == ExportJobStatus.FAILED

    job.refresh_from_db()
    assert job.error_code == "PERMISSION_REVOKED"
    assert job.output_file_object is None
    assert storage().objects == {}


def test_an_inactive_user_gets_permission_revoked(advisor_user: User) -> None:
    job = make_job(advisor_user)
    User.objects.filter(pk=advisor_user.pk).update(is_active=False)

    export_jobs.build_export(job.pk)

    job.refresh_from_db()
    assert job.error_code == "PERMISSION_REVOKED"


def test_a_filter_now_out_of_scope_gets_permission_revoked(
    advisor_user: User, other_advisor: User
) -> None:
    """Un administrador que pidió con ``advisor_id`` y después quedó como asesor."""
    job = make_job(advisor_user)
    job.filters = {**job.filters, "advisor_id": str(other_advisor.pk)}
    job.save(update_fields=["filters"])

    export_jobs.build_export(job.pk)

    job.refresh_from_db()
    assert job.error_code == "PERMISSION_REVOKED"


# --- Cupo y reintentos --------------------------------------------------------------------


def test_a_fourth_active_export_is_rejected(advisor_client: APIClient, advisor_user: User) -> None:
    make_job(advisor_user)
    make_job(advisor_user, status=ExportJobStatus.RUNNING, started_at=timezone.now())
    make_job(advisor_user)
    make_job(advisor_user, status=ExportJobStatus.FAILED, error_code="EXPORT_TOO_LARGE")

    response = advisor_client.post(JOBS_URL, {}, format="json")

    assert response.status_code == 429
    assert response.json()["code"] == "TOO_MANY_EXPORTS"
    assert ReportExportJob.objects.filter(requested_by=advisor_user).count() == 4


def test_finished_exports_do_not_use_the_quota(
    advisor_client: APIClient, advisor_user: User
) -> None:
    for _ in range(3):
        make_job(advisor_user, status=ExportJobStatus.FAILED, error_code="EXPORT_TOO_LARGE")

    assert advisor_client.post(JOBS_URL, {}, format="json").status_code == 202


def test_the_same_idempotency_key_returns_the_same_job(advisor_client: APIClient) -> None:
    first = advisor_client.post(JOBS_URL, {}, format="json", HTTP_IDEMPOTENCY_KEY="exp-1")
    second = advisor_client.post(JOBS_URL, {}, format="json", HTTP_IDEMPOTENCY_KEY="exp-1")

    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert ReportExportJob.objects.count() == 1


def test_a_storage_failure_retries_and_fails_on_the_last_attempt(
    admin_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(*args: Any, **kwargs: Any) -> None:
        raise StorageUnavailable("caído")

    monkeypatch.setattr(storage(), "put", unavailable)
    job = make_job(admin_user)

    with pytest.raises(StorageUnavailable):
        export_jobs.build_export(job.pk, last_attempt=False)
    job.refresh_from_db()
    assert job.status == ExportJobStatus.PENDING
    assert job.started_at is None

    assert export_jobs.build_export(job.pk, last_attempt=True) == ExportJobStatus.FAILED
    job.refresh_from_db()
    assert job.error_code == "STORAGE_UNAVAILABLE"


def test_a_finished_job_is_not_built_again(admin_user: User) -> None:
    job = completed_job(admin_user)
    objects = dict(storage().objects)

    assert export_jobs.build_export(job.pk) == ExportJobStatus.COMPLETED
    assert storage().objects == objects


# --- Consulta, lista y descarga -----------------------------------------------------------


def test_another_users_job_is_not_found(advisor_client: APIClient, other_advisor: User) -> None:
    job = completed_job(other_advisor)

    assert advisor_client.get(job_url(job)).status_code == 404
    assert advisor_client.get(job_url(job, "/download")).status_code == 404


def test_the_manager_sees_any_job(admin_client: APIClient, advisor_user: User) -> None:
    job = completed_job(advisor_user)

    assert admin_client.get(job_url(job)).status_code == 200
    assert admin_client.get(job_url(job, "/download")).status_code == 200


def test_the_list_has_own_jobs_and_all_only_for_the_manager(
    admin_client: APIClient,
    advisor_client: APIClient,
    admin_user: User,
    advisor_user: User,
) -> None:
    mine = make_job(advisor_user)
    theirs = make_job(admin_user)

    own = advisor_client.get(JOBS_URL).json()
    everything = admin_client.get(JOBS_URL, {"all": "true"}).json()
    admin_own = admin_client.get(JOBS_URL).json()
    denied = advisor_client.get(JOBS_URL, {"all": "true"})

    assert [item["id"] for item in own["items"]] == [str(mine.pk)]
    assert {item["id"] for item in everything["items"]} == {str(mine.pk), str(theirs.pk)}
    assert [item["id"] for item in admin_own["items"]] == [str(theirs.pk)]
    assert denied.status_code == 403
    assert denied.json()["code"] == "FILTER_OUT_OF_SCOPE"


def test_a_completed_export_downloads_with_a_short_signed_url(
    advisor_client: APIClient, advisor_user: User
) -> None:
    job = completed_job(advisor_user)

    response = advisor_client.get(job_url(job, "/download"))

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    assert "expires_in=300" in body["url"]
    assert "solicitudes_" in body["url"]
    assert set(body) == {"url", "expires_at"}


@pytest.mark.parametrize(
    ("status", "extra"),
    [
        (ExportJobStatus.PENDING, {}),
        (ExportJobStatus.RUNNING, {"started_at": timezone.now()}),
        (
            ExportJobStatus.FAILED,
            {"error_code": "EXPORT_TOO_LARGE"},
        ),
    ],
)
def test_an_unfinished_export_is_not_ready(
    advisor_client: APIClient, advisor_user: User, status: str, extra: dict[str, Any]
) -> None:
    job = make_job(advisor_user, status=status, **extra)

    response = advisor_client.get(job_url(job, "/download"))

    assert response.status_code == 409
    assert response.json()["code"] == "EXPORT_NOT_READY"


def test_an_expired_export_is_gone(advisor_client: APIClient, advisor_user: User) -> None:
    job = completed_job(advisor_user, expires_in=-timedelta(minutes=1))

    detail = advisor_client.get(job_url(job)).json()
    response = advisor_client.get(job_url(job, "/download"))

    assert detail["status"] == "EXPIRED"
    assert response.status_code == 410
    assert response.json()["code"] == "EXPORT_EXPIRED"


# --- Purga --------------------------------------------------------------------------------


def test_purge_marks_expired_and_deletes_the_object_but_keeps_the_records(
    advisor_user: User,
) -> None:
    expired = completed_job(advisor_user, expires_in=-timedelta(minutes=1))
    current = completed_job(advisor_user)
    assert expired.output_file_object is not None
    expired_key = expired.output_file_object.object_key
    expired_file_id = expired.output_file_object.pk

    call_command("purge_report_exports")

    expired.refresh_from_db()
    current.refresh_from_db()
    assert expired.status == ExportJobStatus.EXPIRED
    assert expired_key not in storage().objects
    assert FileObject.objects.filter(pk=expired_file_id).exists()
    assert current.status == ExportJobStatus.COMPLETED
    assert current.output_file_object is not None
    assert current.output_file_object.object_key in storage().objects
