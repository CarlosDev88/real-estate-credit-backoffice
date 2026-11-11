"""Metadatos, análisis y descarga de versiones (decisión 13, API §19, RNF-03)."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, override_settings
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.crm.models import Client, Opportunity
from apps.documents.constants import PDF
from apps.documents.exceptions import StorageUnavailable
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentFileStatus,
    DocumentReview,
    FileObject,
    ReviewDecision,
    ScanStatus,
)
from apps.documents.storage import MemoryStorage
from apps.identity.models import User
from apps.identity.throttling import DocumentDownloadRateThrottle
from tests.applications.conftest import catalog_item
from tests.applications.dossier.conftest import DocumentFileFactory, SlotFactory
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

FILES_URL = "/api/v1/document-files"
BUYER_FILES_URL = "/api/v1/buyer/document-files"


def file_url(version: DocumentFile, suffix: str = "") -> str:
    return f"{FILES_URL}/{version.id}{suffix}"


def buyer_download_url(version: DocumentFile) -> str:
    return f"{BUYER_FILES_URL}/{version.id}/download"


@pytest.fixture
def anonymous() -> APIClient:
    return APIClient()


@pytest.fixture
def make_version(
    make_slot: SlotFactory,
    make_document_file: DocumentFileFactory,
    make_file_object: Callable[..., FileObject],
) -> Callable[..., DocumentFile]:
    """Versión vigente de un slot nuevo, con análisis limpio por omisión."""

    def _make_version(scan_status: str = ScanStatus.CLEAN, **slot_extra: Any) -> DocumentFile:
        slot = make_slot(**slot_extra)
        scanned_at = None if scan_status == ScanStatus.PENDING else timezone.now()
        version = make_document_file(
            slot=slot,
            file_object=make_file_object(
                scan_status=scan_status,
                scanned_at=scanned_at,
                object_key=f"documents/{slot.application_id}/secret-key",
                bucket_name="mvp-credit-private",
            ),
            client_filename="cédula de Ana.pdf",
            status=DocumentFileStatus.IN_REVIEW,
        )
        ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(current_file=version)
        return version

    return _make_version


@pytest.fixture
def version(make_version: Callable[..., DocumentFile]) -> DocumentFile:
    return make_version()


# --- Acceso -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("client_name", "expected"),
    [
        ("admin_client", 200),
        ("advisor_client", 200),
        ("other_advisor_client", 404),
        ("broker_client", 403),
        ("partner_client", 403),
        ("anonymous", 401),
    ],
)
def test_access_matrix(
    request: pytest.FixtureRequest, version: DocumentFile, client_name: str, expected: int
) -> None:
    client: APIClient = request.getfixturevalue(client_name)

    responses = [
        client.get(file_url(version)),
        client.get(file_url(version, "/scan-status")),
        client.get(file_url(version, "/download")),
    ]

    assert [response.status_code for response in responses] == [expected] * 3


def test_unknown_files_are_404(advisor_client: APIClient, portal: APIClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"

    for suffix in ("", "/scan-status", "/download"):
        assert_error(
            advisor_client.get(f"{FILES_URL}/{missing}{suffix}"), 404, "RESOURCE_NOT_FOUND"
        )
    response = portal.get(f"{BUYER_FILES_URL}/{missing}/download")
    assert_error(response, 404, "RESOURCE_NOT_FOUND")


def test_the_buyer_cannot_use_the_internal_routes(portal: APIClient, version: DocumentFile) -> None:
    assert portal.get(file_url(version, "/download")).status_code == 401


# --- Metadatos y análisis ----------------------------------------------------------------


def test_file_detail(advisor_client: APIClient, advisor_user: User, version: DocumentFile) -> None:
    DocumentReview.objects.create(
        slot=version.slot,
        document_file=version,
        reviewer=advisor_user,
        decision=ReviewDecision.REJECTED,
        reason_item=catalog_item("document_rejection_reason", "ILLEGIBLE"),
        buyer_comment="No se lee.",
        internal_comment="Nota interna.",
    )
    # Una exoneración con la versión vigente no se lista entre sus revisiones.
    DocumentReview.objects.create(
        slot=version.slot,
        document_file=version,
        reviewer=advisor_user,
        decision=ReviewDecision.WAIVED,
        reason_item=catalog_item("document_waiver_reason", "OTHER"),
        decision_batch_id=version.pk,
    )

    response = advisor_client.get(file_url(version))

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["id"] == str(version.pk)
    assert body["slot_id"] == str(version.slot_id)
    assert body["is_current"] is True
    assert body["client_filename"] == "cédula de Ana.pdf"
    assert body["file"]["scan_status"] == "CLEAN"
    assert [row["decision"] for row in body["reviews"]] == ["REJECTED"]
    assert body["reviews"][0]["internal_comment"] == "Nota interna."
    text = response.content.decode()
    assert "secret-key" not in text
    assert "mvp-credit-private" not in text


def test_scan_status(advisor_client: APIClient, version: DocumentFile) -> None:
    response = advisor_client.get(file_url(version, "/scan-status"))

    assert response.status_code == 200, response.content
    body = response.json()
    assert body.pop("scanned_at") is not None
    file_object = version.file_object
    assert body == {
        "document_file_id": str(version.pk),
        "status": "IN_REVIEW",
        "scan_status": "CLEAN",
        "detected_mime_type": PDF,
        "size_bytes": file_object.size_bytes,
        "sha256": file_object.sha256,
    }


def test_scan_status_while_pending(
    advisor_client: APIClient, make_version: Callable[..., DocumentFile]
) -> None:
    pending = make_version(scan_status=ScanStatus.PENDING)

    body = advisor_client.get(file_url(pending, "/scan-status")).json()

    assert body["scan_status"] == "PENDING"
    assert body["scanned_at"] is None


def test_files_of_retired_slots_stay_readable_internally(
    advisor_client: APIClient, portal: APIClient, make_version: Callable[..., DocumentFile]
) -> None:
    retired = make_version(retired_at=timezone.now())

    assert advisor_client.get(file_url(retired)).status_code == 200
    assert advisor_client.get(file_url(retired, "/download")).status_code == 200
    assert_error(portal.get(buyer_download_url(retired)), 404, "RESOURCE_NOT_FOUND")


# --- Descarga ---------------------------------------------------------------------------


def query_of(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


@pytest.mark.parametrize("client_name", ["advisor_client", "portal"])
def test_download_returns_a_short_lived_signed_url(
    request: pytest.FixtureRequest, version: DocumentFile, client_name: str
) -> None:
    client: APIClient = request.getfixturevalue(client_name)
    url = buyer_download_url(version) if client_name == "portal" else file_url(version, "/download")
    before = timezone.now()

    response = client.get(url)

    assert response.status_code == 200, response.content
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    assert set(body) == {"url", "expires_at"}
    query = query_of(body["url"])
    assert query["expires_in"] == [str(settings.DOCUMENT_DOWNLOAD_URL_SECONDS)]
    assert query["filename"] == ["cédula de Ana.pdf"]
    assert query["type"] == [PDF]
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert before + timedelta(seconds=299) <= expires_at <= timezone.now() + timedelta(seconds=300)


@override_settings(DOCUMENT_DOWNLOAD_URL_SECONDS=60)
def test_the_url_lifetime_comes_from_settings(
    advisor_client: APIClient, version: DocumentFile
) -> None:
    body = advisor_client.get(file_url(version, "/download")).json()

    assert query_of(body["url"])["expires_in"] == ["60"]


def test_the_buyer_downloads_any_version_without_consents(
    buyer_client: APIClient, make_version: Callable[..., DocumentFile]
) -> None:
    version = make_version()

    assert buyer_client.get(buyer_download_url(version)).status_code == 200


def test_the_buyer_cannot_download_another_application(
    portal: APIClient,
    make_application: Callable[..., CreditApplication],
    make_opportunity: Callable[..., Opportunity],
    make_client: Callable[..., Client],
    make_slot: SlotFactory,
    make_document_file: DocumentFileFactory,
) -> None:
    other = make_application(make_opportunity(make_client(document_number="900111222")))
    foreign = make_document_file(slot=make_slot(application=other, participant=None))

    assert_error(portal.get(buyer_download_url(foreign)), 404, "RESOURCE_NOT_FOUND")


@pytest.mark.parametrize("scan", [ScanStatus.PENDING, ScanStatus.INFECTED, ScanStatus.INVALID])
def test_only_clean_files_are_downloaded(
    advisor_client: APIClient,
    portal: APIClient,
    make_version: Callable[..., DocumentFile],
    scan: str,
) -> None:
    version = make_version(scan_status=scan)

    assert_error(advisor_client.get(file_url(version, "/download")), 409, "FILE_NOT_CLEAN")
    assert_error(portal.get(buyer_download_url(version)), 409, "FILE_NOT_CLEAN")


def test_the_url_never_reaches_the_logs(
    advisor_client: APIClient,
    portal: APIClient,
    version: DocumentFile,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        internal = advisor_client.get(file_url(version, "/download")).json()["url"]
        buyer = portal.get(buyer_download_url(version)).json()["url"]

    assert any("firmada" in record.getMessage() for record in caplog.records)
    logged = "\n".join(record.getMessage() for record in caplog.records)
    for url in (internal, buyer):
        assert url not in logged
        assert "secret-key" not in logged


def test_storage_failure_is_503(
    advisor_client: APIClient, version: DocumentFile, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: Any, **kwargs: Any) -> str:
        raise StorageUnavailable("sin conexión")

    monkeypatch.setattr(MemoryStorage, "presigned_url", fail)

    body = assert_error(
        advisor_client.get(file_url(version, "/download")), 503, "SERVICE_UNAVAILABLE"
    )

    assert "descarga" in body["message"]


# --- Límite de consumo -------------------------------------------------------------------


@override_settings(AUTH_RATE_LIMITS={**settings.AUTH_RATE_LIMITS, "document_download": "2/1h"})
def test_downloads_are_rate_limited_per_user_and_session(
    advisor_client: APIClient, admin_client: APIClient, portal: APIClient, version: DocumentFile
) -> None:
    url = file_url(version, "/download")
    assert [advisor_client.get(url).status_code for _ in range(2)] == [200, 200]
    assert_error(advisor_client.get(url), 429, "RATE_LIMITED")
    # Leer los metadatos no consume el límite; otro usuario y el comprador tienen el suyo.
    assert advisor_client.get(file_url(version)).status_code == 200
    assert admin_client.get(url).status_code == 200
    buyer_url = buyer_download_url(version)
    assert [portal.get(buyer_url).status_code for _ in range(2)] == [200, 200]
    assert_error(portal.get(buyer_url), 429, "RATE_LIMITED")


def test_the_download_throttle_ignores_anonymous_requests() -> None:
    request = Request(RequestFactory().get("/"))
    request.user = AnonymousUser()

    assert DocumentDownloadRateThrottle().get_cache_key(request, view=None) is None
