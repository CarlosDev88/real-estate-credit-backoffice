"""Endpoints de los paquetes para radicar (API §19, decisiones 14, 37 y 40)."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.catalogs.workflow import ApplicationStatus
from apps.documents.exceptions import StorageUnavailable
from apps.documents.models import DocumentPackageJob, DocumentType, PackageJobStatus
from apps.documents.packages import build_package, request_package
from apps.documents.storage import MemoryStorage, get_storage
from apps.identity.models import User
from tests.applications.buyer_access.conftest import set_status
from tests.applications.dossier.conftest import PackageDossier, SlotFactory
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

JOBS_URL = "/api/v1/document-package-jobs"


def create_url(application: CreditApplication) -> str:
    return f"/api/v1/applications/{application.pk}/document-package-jobs"


def job_url(job: DocumentPackageJob, suffix: str = "") -> str:
    return f"{JOBS_URL}/{job.pk}{suffix}"


@pytest.fixture
def anonymous() -> APIClient:
    return APIClient()


@pytest.fixture
def requested(package_dossier: PackageDossier, advisor_user: User) -> DocumentPackageJob:
    return request_package(advisor_user, package_dossier.application).job


@pytest.fixture
def completed(requested: DocumentPackageJob) -> DocumentPackageJob:
    build_package(requested.pk)
    return DocumentPackageJob.objects.get(pk=requested.pk)


# --- Pedido -----------------------------------------------------------------------------


def test_post_creates_the_job_and_a_repeat_returns_it(
    advisor_client: APIClient,
    package_dossier: PackageDossier,
    advisor_user: User,
) -> None:
    url = create_url(package_dossier.application)

    first = advisor_client.post(url)

    assert first.status_code == 201, first.content
    body = first.json()
    assert set(body) == {
        "id",
        "application_id",
        "application_version",
        "status",
        "error_code",
        "fingerprint",
        "requested_by",
        "created_at",
        "started_at",
        "completed_at",
        "expires_at",
        "output",
        "documents",
    }
    assert body["application_id"] == str(package_dossier.application.pk)
    assert body["status"] == "PENDING"
    assert body["output"] is None
    assert body["requested_by"] == {"id": str(advisor_user.pk), "name": "Andrea García"}
    assert len(body["documents"]) == 6
    assert body["documents"][1]["waiver_reason"] == {"code": "OTHER", "name": "Otro"}
    assert body["documents"][2]["file"]["client_filename"] == "cédula Laura.pdf"
    assert "file_object_id" not in body["documents"][2]["file"]
    assert "object_key" not in first.content.decode()

    second = advisor_client.post(url)

    assert second.status_code == 200
    assert second.json()["id"] == body["id"]


def test_post_runs_the_build_after_commit(
    advisor_client: APIClient,
    package_dossier: PackageDossier,
    django_capture_on_commit_callbacks: Callable[..., Any],
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        response = advisor_client.post(create_url(package_dossier.application))

    assert response.status_code == 201
    job = advisor_client.get(f"{JOBS_URL}/{response.json()['id']}").json()
    assert job["status"] == "COMPLETED"
    assert job["output"]["filename"] == f"{package_dossier.application.code}_expediente.zip"
    assert job["output"]["size_bytes"] > 0
    assert len(job["output"]["sha256"]) == 64


def test_post_with_pending_documents_is_422(
    advisor_client: APIClient, package_dossier: PackageDossier, make_slot: SlotFactory
) -> None:
    pending = make_slot(document_type=DocumentType.objects.get(code="INCOME_TAX_RETURN"))

    response = advisor_client.post(create_url(package_dossier.application))

    body = assert_error(response, 422, "APPLICATION_NOT_READY")
    assert [(d["code"], d["resource_id"]) for d in body["details"]] == [
        ("DOCUMENT_PENDING", str(pending.pk))
    ]


def test_post_on_a_closed_application_is_409(
    advisor_client: APIClient, package_dossier: PackageDossier
) -> None:
    set_status(package_dossier.application, ApplicationStatus.WITHDRAWN)

    assert_error(
        advisor_client.post(create_url(package_dossier.application)), 409, "APPLICATION_CLOSED"
    )


# --- Acceso (decisión 37) ----------------------------------------------------------------


def test_broker_partner_and_anonymous_have_no_access(
    broker_client: APIClient,
    partner_client: APIClient,
    anonymous: APIClient,
    completed: DocumentPackageJob,
) -> None:
    application = completed.application
    urls = [job_url(completed), job_url(completed, "/download")]
    for client, status_code, code in (
        (broker_client, 403, "PERMISSION_DENIED"),
        (partner_client, 403, "PERMISSION_DENIED"),
        (anonymous, 401, "NOT_AUTHENTICATED"),
    ):
        assert_error(client.post(create_url(application)), status_code, code)
        for url in urls:
            assert_error(client.get(url), status_code, code)


def test_an_unassigned_advisor_gets_404(
    other_advisor_client: APIClient, completed: DocumentPackageJob
) -> None:
    assert_error(
        other_advisor_client.post(create_url(completed.application)), 404, "RESOURCE_NOT_FOUND"
    )
    assert_error(other_advisor_client.get(job_url(completed)), 404, "RESOURCE_NOT_FOUND")
    assert_error(
        other_advisor_client.get(job_url(completed, "/download")), 404, "RESOURCE_NOT_FOUND"
    )


def test_a_reassigned_application_moves_its_packages(
    advisor_client: APIClient,
    other_advisor_client: APIClient,
    other_advisor: User,
    completed: DocumentPackageJob,
) -> None:
    """El asesor nuevo ve los paquetes anteriores; al anterior se le quitan."""
    CreditApplication.objects.filter(pk=completed.application_id).update(
        assigned_advisor=other_advisor
    )

    assert other_advisor_client.get(job_url(completed)).status_code == 200
    assert other_advisor_client.get(job_url(completed, "/download")).status_code == 200
    assert_error(advisor_client.get(job_url(completed)), 404, "RESOURCE_NOT_FOUND")
    assert_error(advisor_client.get(job_url(completed, "/download")), 404, "RESOURCE_NOT_FOUND")


def test_admin_sees_every_package(admin_client: APIClient, completed: DocumentPackageJob) -> None:
    assert admin_client.get(job_url(completed)).status_code == 200


# --- Detalle ------------------------------------------------------------------------------


def test_the_detail_derives_expired(
    advisor_client: APIClient, completed: DocumentPackageJob
) -> None:
    assert advisor_client.get(job_url(completed)).json()["status"] == "COMPLETED"

    DocumentPackageJob.objects.filter(pk=completed.pk).update(expires_at=timezone.now())

    assert advisor_client.get(job_url(completed)).json()["status"] == "EXPIRED"


# --- Descarga (decisión 40) ----------------------------------------------------------------


def test_download_returns_a_short_lived_url(
    advisor_client: APIClient,
    completed: DocumentPackageJob,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="apps.documents.packages")
    before = timezone.now()

    response = advisor_client.get(job_url(completed, "/download"))

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    output = completed.output_file_object
    assert output is not None
    url = urlsplit(body["url"])
    query = parse_qs(url.query)
    assert url.path == f"/{output.object_key}"
    assert query["expires_in"] == [str(settings.DOCUMENT_DOWNLOAD_URL_SECONDS)]
    assert query["filename"] == [f"{completed.application.code}_expediente.zip"]
    assert query["type"] == ["application/zip"]
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert expires_at >= before + timedelta(seconds=settings.DOCUMENT_DOWNLOAD_URL_SECONDS)
    assert f"Descarga del paquete {completed.pk} firmada" in caplog.text
    assert body["url"] not in caplog.text
    assert output.object_key not in caplog.text


@pytest.mark.parametrize(
    "status", [PackageJobStatus.PENDING, PackageJobStatus.RUNNING, PackageJobStatus.FAILED]
)
def test_download_of_an_unfinished_package_is_409(
    advisor_client: APIClient, requested: DocumentPackageJob, status: str
) -> None:
    now = timezone.now()
    DocumentPackageJob.objects.filter(pk=requested.pk).update(
        status=status,
        started_at=None if status == PackageJobStatus.PENDING else now,
        completed_at=now if status == PackageJobStatus.FAILED else None,
    )

    assert_error(advisor_client.get(job_url(requested, "/download")), 409, "PACKAGE_NOT_READY")


@pytest.mark.parametrize("persisted", [False, True])
def test_download_of_an_expired_package_is_409(
    advisor_client: APIClient, completed: DocumentPackageJob, persisted: bool
) -> None:
    changes: dict[str, Any] = {"expires_at": timezone.now()}
    if persisted:
        changes["status"] = PackageJobStatus.EXPIRED
    DocumentPackageJob.objects.filter(pk=completed.pk).update(**changes)

    assert_error(advisor_client.get(job_url(completed, "/download")), 409, "PACKAGE_EXPIRED")


def test_download_when_storage_cannot_sign_is_503(
    advisor_client: APIClient, completed: DocumentPackageJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = get_storage()
    assert isinstance(storage, MemoryStorage)

    def no_sign(key: str, **kwargs: Any) -> str:
        raise StorageUnavailable("sin almacenamiento")

    monkeypatch.setattr(storage, "presigned_url", no_sign)

    body = assert_error(
        advisor_client.get(job_url(completed, "/download")), 503, "SERVICE_UNAVAILABLE"
    )
    assert "descarga" in body["message"]


@override_settings(AUTH_RATE_LIMITS={**settings.AUTH_RATE_LIMITS, "document_download": "2/1h"})
def test_package_downloads_share_the_download_limit(
    advisor_client: APIClient, completed: DocumentPackageJob
) -> None:
    url = job_url(completed, "/download")
    assert [advisor_client.get(url).status_code for _ in range(2)] == [200, 200]
    assert_error(advisor_client.get(url), 429, "RATE_LIMITED")
    # Leer el estado no consume el límite.
    assert advisor_client.get(job_url(completed)).status_code == 200
