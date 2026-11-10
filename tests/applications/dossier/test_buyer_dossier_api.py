"""Expediente en el portal del comprador: lectura, carga y reemplazo (decisiones 2, 4,
5, 11 y 12)."""

import io
import threading
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.http import Http404
from django.test import RequestFactory, override_settings
from django.utils import timezone
from kombu.exceptions import OperationalError
from rest_framework.request import Request
from rest_framework.test import APIClient

from apps.applications.exceptions import ApplicationClosed
from apps.applications.models import ApplicationParticipant, CreditApplication
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client
from apps.documents import buyer_views, tasks, uploads
from apps.documents.constants import PDF, PNG
from apps.documents.exceptions import StorageUnavailable
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentFileStatus,
    DocumentReview,
    DocumentType,
    FileObject,
    ReviewDecision,
    ScanStatus,
    SlotStatus,
)
from apps.documents.scanning import EICAR
from apps.documents.scans import SECURITY_REJECTION_MESSAGE
from apps.documents.storage import MemoryStorage, get_storage
from apps.identity.models import BuyerSession, User
from tests.applications.buyer_access.conftest import set_status
from tests.applications.conftest import catalog_item
from tests.applications.dossier.conftest import DocumentFileFactory, SlotFactory
from tests.helpers import assert_error, csrf_token

pytestmark = pytest.mark.django_db

SLOTS_URL = "/api/v1/buyer/document-slots"
PDF_BYTES = b"%PDF-1.7\n" + b"contenido de prueba " * 20
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def slot_url(slot: ApplicationDocumentSlot, suffix: str = "") -> str:
    return f"{SLOTS_URL}/{slot.id}{suffix}"


def list_url(application: CreditApplication) -> str:
    return f"/api/v1/buyer/applications/{application.id}/document-slots"


def pdf(name: str = "cedula.pdf", content: bytes = PDF_BYTES, **extra: Any) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type=extra.get("content_type", PDF))


def upload(client: APIClient, slot: ApplicationDocumentSlot, **data: Any) -> Any:
    data.setdefault("file", pdf())
    return client.post(slot_url(slot, "/uploads"), data, format="multipart")


def memory() -> MemoryStorage:
    storage = get_storage()
    assert isinstance(storage, MemoryStorage)
    return storage


def session_of(application: CreditApplication) -> BuyerSession:
    return BuyerSession.objects.filter(application=application).latest("created_at")


@pytest.fixture
def slot(make_slot: SlotFactory) -> ApplicationDocumentSlot:
    return make_slot(validity_days=30)


def decide(slot: ApplicationDocumentSlot, status: str, **extra: Any) -> None:
    ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(status=status, **extra)


# --- Carga ------------------------------------------------------------------------------


def test_upload_creates_the_first_version(
    portal: APIClient, application: CreditApplication, slot: ApplicationDocumentSlot
) -> None:
    yesterday = timezone.localdate() - timedelta(days=1)

    response = upload(portal, slot, file=pdf("C:\\fotos\\cédula.pdf"), document_date=yesterday)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["id"] == str(slot.id)
    assert body["status"] == "UPLOADED"
    current = body["current_file"]
    assert current["version_number"] == 1
    assert current["status"] == "UPLOADED"
    assert current["client_filename"] == "cédula.pdf"
    assert current["document_date"] == yesterday.isoformat()
    assert current["expires_at"] == (yesterday + timedelta(days=30)).isoformat()
    assert current["mime_type"] == PDF
    assert current["size_bytes"] == len(PDF_BYTES)

    version = DocumentFile.objects.get(slot=slot)
    assert version.uploaded_by_buyer_session == session_of(application)
    file_object = version.file_object
    assert file_object.scan_status == ScanStatus.PENDING
    assert file_object.object_key.startswith(f"documents/{application.id}/")
    assert "cédula" not in file_object.object_key
    assert file_object.storage_provider == "memory"
    assert memory().objects[file_object.object_key] == (PDF_BYTES, PDF)
    slot.refresh_from_db()
    assert slot.current_file_id == version.pk
    application.refresh_from_db(fields=["version"])
    assert application.version == 1


def test_a_clean_scan_leaves_the_version_in_review(
    portal: APIClient,
    slot: ApplicationDocumentSlot,
    django_capture_on_commit_callbacks: Callable[..., Any],
) -> None:
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = upload(portal, slot)

    assert response.status_code == 201, response.content
    assert len(callbacks) == 1
    version = DocumentFile.objects.select_related("file_object").get(slot=slot)
    assert version.status == DocumentFileStatus.IN_REVIEW
    assert version.file_object.scan_status == ScanStatus.CLEAN
    assert version.file_object.scanned_at is not None
    slot.refresh_from_db()
    assert slot.status == SlotStatus.UPLOADED


def test_an_infected_file_rejects_the_slot_with_a_fixed_message(
    portal: APIClient,
    slot: ApplicationDocumentSlot,
    django_capture_on_commit_callbacks: Callable[..., Any],
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        response = upload(portal, slot, file=pdf(content=b"%PDF-1.4\n" + EICAR))
    assert response.status_code == 201, response.content

    body = portal.get(slot_url(slot)).json()

    assert body["status"] == "REJECTED"
    assert body["current_file"]["status"] == "REJECTED"
    assert body["rejection"]["reason"] is None
    assert body["rejection"]["buyer_comment"] == SECURITY_REJECTION_MESSAGE
    assert body["current_file"]["rejection"]["buyer_comment"] == SECURITY_REJECTION_MESSAGE
    assert body["can_upload"] is True
    assert not DocumentReview.objects.exists()
    assert "Eicar" not in str(body)


def test_a_new_upload_replaces_the_current_version_and_keeps_the_old_one(
    portal: APIClient,
    slot: ApplicationDocumentSlot,
    django_capture_on_commit_callbacks: Callable[..., Any],
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        upload(portal, slot)
    decide(slot, SlotStatus.REJECTED)

    response = upload(portal, slot, file=pdf("cedula-legible.pdf"))

    assert response.status_code == 201, response.content
    assert response.json()["current_file"]["version_number"] == 2
    versions = list(DocumentFile.objects.filter(slot=slot).order_by("version_number"))
    assert [v.status for v in versions] == [DocumentFileStatus.IN_REVIEW, "UPLOADED"]
    slot.refresh_from_db()
    assert slot.current_file_id == versions[1].pk
    assert slot.status == SlotStatus.UPLOADED


@pytest.mark.parametrize("decided", [SlotStatus.APPROVED, SlotStatus.WAIVED])
def test_an_approved_or_waived_slot_is_locked(
    portal: APIClient, slot: ApplicationDocumentSlot, decided: str
) -> None:
    extra: dict[str, Any] = {}
    if decided == SlotStatus.WAIVED:
        extra = {
            "is_waivable": True,
            "waiver_reason_item": catalog_item("document_waiver_reason", "NOT_APPLICABLE"),
        }
    decide(slot, decided, **extra)

    assert_error(upload(portal, slot), 409, "DOCUMENT_LOCKED")
    assert portal.get(slot_url(slot)).json()["can_upload"] is False
    assert memory().objects == {}


# --- Después de la radicación (decisión 5) --------------------------------------------


def test_after_filing_nothing_is_replaced_without_an_observation(
    portal: APIClient, application: CreditApplication, slot: ApplicationDocumentSlot
) -> None:
    set_status(application, ApplicationStatus.FILED)
    decide(slot, SlotStatus.REJECTED)

    assert_error(upload(portal, slot), 409, "DOCUMENT_NOT_REJECTED")

    decide(slot, SlotStatus.APPROVED, locked_at=timezone.now())
    assert_error(upload(portal, slot), 409, "DOCUMENT_LOCKED")


def test_after_filing_an_observed_rejected_slot_accepts_a_replacement(
    portal: APIClient,
    application: CreditApplication,
    slot: ApplicationDocumentSlot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(uploads, "slot_has_open_observation", lambda slot: True)
    set_status(application, ApplicationStatus.FILED)
    decide(slot, SlotStatus.REJECTED, locked_at=timezone.now())

    response = upload(portal, slot)

    assert response.status_code == 201, response.content

    decide(slot, SlotStatus.APPROVED)
    assert_error(upload(portal, slot), 409, "DOCUMENT_NOT_REJECTED")


def test_a_closed_application_rejects_uploads(
    portal: APIClient, application: CreditApplication, slot: ApplicationDocumentSlot
) -> None:
    set_status(application, ApplicationStatus.WITHDRAWN)

    assert_error(upload(portal, slot), 409, "APPLICATION_CLOSED")


def test_the_service_rechecks_a_closed_application(
    portal: APIClient,
    application: CreditApplication,
    slot: ApplicationDocumentSlot,
) -> None:
    set_status(application, ApplicationStatus.WITHDRAWN)

    with pytest.raises(ApplicationClosed):
        uploads.upload_document(
            session_of(application),
            slot,
            uploads.Upload(
                stream=io.BytesIO(PDF_BYTES), filename="cedula.pdf", declared_mime_type=PDF
            ),
        )


# --- Sesión, CSRF, consentimientos y alcance -----------------------------------------


def test_upload_requires_csrf(
    buyer_csrf_client: APIClient,
    accept_consents: Callable[[], None],
    slot: ApplicationDocumentSlot,
) -> None:
    accept_consents()

    assert_error(upload(buyer_csrf_client, slot), 403, "CSRF_FAILED")

    response = buyer_csrf_client.post(
        slot_url(slot, "/uploads"),
        {"file": pdf()},
        format="multipart",
        headers={"X-CSRFToken": csrf_token(buyer_csrf_client)},
    )
    assert response.status_code == 201, response.content


def test_upload_requires_the_consents(
    buyer_client: APIClient, slot: ApplicationDocumentSlot
) -> None:
    assert_error(upload(buyer_client, slot), 403, "CONSENT_REQUIRED")
    # Las lecturas no exigen consentimientos.
    assert buyer_client.get(slot_url(slot)).status_code == 200


def test_internal_users_and_anonymous_visitors_cannot_use_the_portal(
    advisor_client: APIClient, slot: ApplicationDocumentSlot
) -> None:
    assert_error(advisor_client.get(slot_url(slot)), 401, "NOT_AUTHENTICATED")
    assert_error(APIClient().post(slot_url(slot, "/uploads")), 401, "NOT_AUTHENTICATED")


def test_slots_of_another_application_or_retired_are_404(
    portal: APIClient,
    application: CreditApplication,
    make_application: Callable[..., CreditApplication],
    make_opportunity: Callable[..., Any],
    make_client: Callable[..., Client],
    make_slot: SlotFactory,
) -> None:
    other = make_application(make_opportunity(make_client(document_number="79111222")))
    foreign = make_slot(application=other, participant=other.participants.get())
    retired = make_slot(retired_at=timezone.now())

    for target in (foreign, retired):
        assert_error(portal.get(slot_url(target)), 404, "RESOURCE_NOT_FOUND")
        assert_error(portal.get(slot_url(target, "/versions")), 404, "RESOURCE_NOT_FOUND")
        assert_error(upload(portal, target), 404, "RESOURCE_NOT_FOUND")
    assert_error(portal.get(list_url(other)), 404, "RESOURCE_NOT_FOUND")


# --- Validación del archivo (decisión 11) ---------------------------------------------


def test_the_real_type_must_be_allowed_by_the_document(
    portal: APIClient, slot: ApplicationDocumentSlot
) -> None:
    DocumentType.objects.filter(pk=slot.document_type_id).update(allowed_mime_types=[PDF])
    png = SimpleUploadedFile("foto.png", PNG_BYTES, content_type=PNG)

    body = assert_error(upload(portal, slot, file=png), 422, "UNSUPPORTED_FILE_TYPE")

    assert body["details"][0]["code"] == "TYPE_NOT_ALLOWED"
    assert memory().objects == {}


def test_executables_and_disguised_files_are_rejected(
    portal: APIClient, slot: ApplicationDocumentSlot
) -> None:
    exe = SimpleUploadedFile("cedula.pdf.exe", PDF_BYTES, content_type=PDF)
    body = assert_error(upload(portal, slot, file=exe), 422, "UNSUPPORTED_FILE_TYPE")
    assert body["details"][0]["code"] == "BLOCKED_EXTENSION"

    fake_pdf = SimpleUploadedFile("cedula.pdf", PNG_BYTES, content_type=PDF)
    body = assert_error(upload(portal, slot, file=fake_pdf), 422, "UNSUPPORTED_FILE_TYPE")
    assert body["details"][0]["code"] == "EXTENSION_MISMATCH"


def test_the_document_size_limit_applies(portal: APIClient, slot: ApplicationDocumentSlot) -> None:
    DocumentType.objects.filter(pk=slot.document_type_id).update(max_size_bytes=50)

    assert_error(upload(portal, slot), 422, "FILE_TOO_LARGE")


@override_settings(DOCUMENT_UPLOAD_MAX_REQUEST_BYTES=1000)
def test_a_body_over_the_global_limit_is_cut_with_413(
    portal: APIClient, slot: ApplicationDocumentSlot
) -> None:
    big = pdf(content=b"%PDF-1.7\n" + b"x" * 2000)

    assert_error(upload(portal, slot, file=big), 413, "PAYLOAD_TOO_LARGE")
    assert not DocumentFile.objects.exists()


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"file": SimpleUploadedFile("vacio.pdf", b"", content_type=PDF)}, "file"),
        ({"file": ""}, "file"),
        ({"document_date": (date.today() + timedelta(days=2)).isoformat()}, "document_date"),
        ({"comment": "hola"}, "comment"),
    ],
)
def test_invalid_upload_bodies_are_400(
    portal: APIClient, slot: ApplicationDocumentSlot, data: dict[str, Any], field: str
) -> None:
    body = assert_error(upload(portal, slot, **data), 400, "VALIDATION_ERROR")

    assert field in {detail["field"] for detail in body["details"]}


# --- Cuota, límite de consumo y fallos de infraestructura -----------------------------


@override_settings(DOCUMENT_UPLOAD_MAX_VERSIONS_PER_SLOT=1)
def test_versions_per_slot_are_capped(portal: APIClient, slot: ApplicationDocumentSlot) -> None:
    assert upload(portal, slot).status_code == 201

    body = assert_error(upload(portal, slot), 409, "DOCUMENT_QUOTA_EXCEEDED")

    assert body["details"][0]["code"] == "VERSIONS_PER_SLOT"
    assert len(memory().objects) == 1


def test_bytes_per_application_are_capped(
    portal: APIClient, slot: ApplicationDocumentSlot, make_slot: SlotFactory
) -> None:
    other = make_slot(document_type=DocumentType.objects.get(code="BANK_STATEMENT"))
    assert upload(portal, slot).status_code == 201

    with override_settings(DOCUMENT_UPLOAD_QUOTA_BYTES=len(PDF_BYTES) * 2 - 1):
        body = assert_error(upload(portal, other), 409, "DOCUMENT_QUOTA_EXCEEDED")

    assert body["details"][0]["code"] == "APPLICATION_BYTES"


def test_a_failure_after_storing_deletes_the_object(
    portal: APIClient, slot: ApplicationDocumentSlot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La cuota se vuelve a comprobar con los bloqueos: otra carga pudo llegar antes."""
    calls: list[int] = []
    original = uploads._ensure_quota

    def quota_full_on_recheck(target: ApplicationDocumentSlot, size_bytes: int) -> None:
        calls.append(size_bytes)
        if len(calls) > 1:
            raise uploads.DocumentQuotaExceeded()
        original(target, size_bytes)

    monkeypatch.setattr(uploads, "_ensure_quota", quota_full_on_recheck)

    assert_error(upload(portal, slot), 409, "DOCUMENT_QUOTA_EXCEEDED")
    assert memory().objects == {}
    assert not FileObject.objects.exists()


def test_an_orphan_that_cannot_be_deleted_is_logged(
    portal: APIClient,
    slot: ApplicationDocumentSlot,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise StorageUnavailable("sin conexión")

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise uploads.DocumentLocked()

    monkeypatch.setattr(uploads, "_save_version", refuse)
    monkeypatch.setattr(MemoryStorage, "delete", fail)

    assert_error(upload(portal, slot), 409, "DOCUMENT_LOCKED")
    assert "objeto huérfano" in caplog.text


def test_storage_down_answers_503(
    portal: APIClient, slot: ApplicationDocumentSlot, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise StorageUnavailable("sin conexión")

    monkeypatch.setattr(MemoryStorage, "put", fail)

    assert_error(upload(portal, slot), 503, "SERVICE_UNAVAILABLE")
    assert not DocumentFile.objects.exists()


def test_a_broker_outage_keeps_the_upload_pending(
    portal: APIClient,
    slot: ApplicationDocumentSlot,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: Callable[..., Any],
) -> None:
    def broker_down(*args: Any, **kwargs: Any) -> None:
        raise OperationalError("Redis no responde")

    monkeypatch.setattr(tasks.scan_file_object, "delay", broker_down)

    with django_capture_on_commit_callbacks(execute=True):
        response = upload(portal, slot)

    assert response.status_code == 201, response.content
    assert FileObject.objects.get().scan_status == ScanStatus.PENDING


def test_uploads_are_rate_limited(portal: APIClient, slot: ApplicationDocumentSlot) -> None:
    limits = {**settings.AUTH_RATE_LIMITS, "buyer_document_upload": "1/1h"}
    with override_settings(AUTH_RATE_LIMITS=limits):
        assert upload(portal, slot).status_code == 201
        assert_error(upload(portal, slot), 429, "RATE_LIMITED")
        # Las lecturas no consumen el límite.
        assert portal.get(slot_url(slot)).status_code == 200


# --- Lectura ----------------------------------------------------------------------------


def test_the_list_shows_what_the_buyer_needs_to_upload(
    portal: APIClient,
    application: CreditApplication,
    primary: ApplicationParticipant,
    make_slot: SlotFactory,
) -> None:
    payroll = DocumentType.objects.get(code="PAYROLL_SLIP")
    for index in (1, 2):
        make_slot(document_type=payroll, slot_index=index, minimum_files=2, sort_order=20)
    make_slot(
        participant=None,
        document_type=DocumentType.objects.get(code="PROPERTY_OWNERSHIP_DOCUMENT"),
    )
    make_slot(document_type=payroll, slot_index=1, retired_at=timezone.now())

    response = portal.get(list_url(application))

    assert response.status_code == 200, response.content
    rows = response.json()["items"]
    assert [row["label"] for row in rows] == [
        "Documento de propiedad o soporte equivalente",
        "Desprendible o comprobante de nómina 1 de 2",
        "Desprendible o comprobante de nómina 2 de 2",
    ]
    first, payroll_row = rows[0], rows[1]
    assert first["participant"] is None
    assert first["document_type"]["holder_scope"] == "APPLICATION"
    assert payroll_row["participant"] == {
        "id": str(primary.id),
        "role": "PRIMARY",
        "full_name": "Laura Gómez Vélez",
    }
    assert set(payroll_row) == {
        "id",
        "participant",
        "document_type",
        "label",
        "slot_index",
        "is_required",
        "minimum_files",
        "alternative_group_code",
        "validity_days",
        "allowed_mime_types",
        "max_size_bytes",
        "status",
        "can_upload",
        "current_file",
        "rejection",
        "updated_at",
    }
    assert payroll_row["allowed_mime_types"] == ["application/pdf", "image/jpeg", "image/png"]
    assert payroll_row["max_size_bytes"] == 10 * 1024 * 1024
    assert payroll_row["can_upload"] is True
    assert payroll_row["current_file"] is None
    assert payroll_row["rejection"] is None
    assert response["Cache-Control"] == "no-store"


def test_an_advisor_rejection_shows_reason_and_comment_but_never_the_internal_note(
    portal: APIClient,
    advisor_user: User,
    slot: ApplicationDocumentSlot,
    make_document_file: DocumentFileFactory,
    make_file_object: Callable[..., FileObject],
) -> None:
    version = make_document_file(
        slot=slot,
        status=DocumentFileStatus.REJECTED,
        file_object=make_file_object(scan_status=ScanStatus.CLEAN, scanned_at=timezone.now()),
    )
    DocumentReview.objects.create(
        document_file=version,
        reviewer=advisor_user,
        decision=ReviewDecision.REJECTED,
        reason_item=catalog_item("document_rejection_reason", "ILLEGIBLE"),
        buyer_comment="La foto está borrosa: carga una más nítida.",
        internal_comment="Posible alteración, revisar con el banco.",
    )
    decide(slot, SlotStatus.REJECTED, current_file=version)

    detail = portal.get(slot_url(slot))
    versions = portal.get(slot_url(slot, "/versions"))

    assert detail.status_code == versions.status_code == 200
    rejection = detail.json()["rejection"]
    assert rejection["reason"]["code"] == "ILLEGIBLE"
    assert rejection["buyer_comment"] == "La foto está borrosa: carga una más nítida."
    row = versions.json()["items"][0]
    assert row["is_current"] is True
    assert row["rejection"] == rejection
    for response in (detail, versions):
        text = response.content.decode()
        assert "Posible alteración" not in text
        assert "internal_comment" not in text
        assert str(advisor_user.id) not in text
        assert "sha256" not in text


def test_a_rejection_corrected_to_approved_is_no_longer_shown(
    portal: APIClient,
    advisor_user: User,
    slot: ApplicationDocumentSlot,
    make_document_file: DocumentFileFactory,
) -> None:
    version = make_document_file(slot=slot, status=DocumentFileStatus.REJECTED)
    DocumentReview.objects.create(
        document_file=version, reviewer=advisor_user, decision=ReviewDecision.APPROVED
    )

    row = portal.get(slot_url(slot, "/versions")).json()["items"][0]

    assert row["is_current"] is False
    assert row["rejection"] is None


def test_versions_are_listed_newest_first(portal: APIClient, slot: ApplicationDocumentSlot) -> None:
    upload(portal, slot, file=pdf("primera.pdf"))
    upload(portal, slot, file=pdf("segunda.pdf"))

    rows = portal.get(slot_url(slot, "/versions")).json()["items"]

    assert [(row["version_number"], row["is_current"]) for row in rows] == [
        (2, True),
        (1, False),
    ]
    assert [row["client_filename"] for row in rows] == ["segunda.pdf", "primera.pdf"]


# --- Concurrencia -----------------------------------------------------------------------


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_concurrent_uploads_get_consecutive_versions(
    make_session: Callable[..., BuyerSession], make_slot: SlotFactory
) -> None:
    session = make_session()
    target = make_slot()
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def run(name: str) -> None:
        try:
            barrier.wait(timeout=10)
            uploads.upload_document(
                session,
                ApplicationDocumentSlot.objects.select_related("document_type").get(pk=target.pk),
                uploads.Upload(stream=io.BytesIO(PDF_BYTES), filename=name, declared_mime_type=PDF),
            )
        except BaseException as exc:  # pragma: no cover - se reporta abajo
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(f"{n}.pdf",)) for n in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    numbers = sorted(
        DocumentFile.objects.filter(slot=target).values_list("version_number", flat=True)
    )
    assert numbers == [1, 2]
    target.refresh_from_db()
    current = DocumentFile.objects.get(slot=target, version_number=2)
    assert target.current_file_id == current.pk


# --- Bordes -----------------------------------------------------------------------------


def test_a_slot_retired_while_uploading_is_404(
    portal: APIClient, application: CreditApplication, slot: ApplicationDocumentSlot
) -> None:
    """La comprobación con los bloqueos relee el slot: pudo retirarse mientras tanto."""
    ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(retired_at=timezone.now())

    with pytest.raises(Http404):
        uploads.upload_document(
            session_of(application),
            slot,
            uploads.Upload(
                stream=io.BytesIO(PDF_BYTES), filename="cedula.pdf", declared_mime_type=PDF
            ),
        )
    assert memory().objects == {}


def test_uploads_only_accept_post(portal: APIClient, slot: ApplicationDocumentSlot) -> None:
    assert_error(portal.get(slot_url(slot, "/uploads")), 405, "METHOD_NOT_ALLOWED")


def test_an_unreadable_content_length_is_left_to_the_parser() -> None:
    request = RequestFactory().post("/api/v1/buyer/document-slots/x/uploads")
    request.META["CONTENT_LENGTH"] = "no-es-un-numero"

    buyer_views._ensure_request_size(Request(request))
