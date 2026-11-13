"""Respuestas del banco (Parte 3, API §20.2): reglas por tipo, devolución completa,
legalización y desembolso, correcciones, evidencia y lo que ve cada actor."""

import io
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import ApplicationStatusHistory, CreditApplication
from apps.applications.signals import application_status_changed
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Opportunity
from apps.documents import scans, uploads
from apps.documents.exceptions import DocumentLocked, ScannerUnavailable
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentPackageJob,
    DocumentReview,
    FileObject,
    ReviewDecision,
    ScanStatus,
    SlotStatus,
)
from apps.documents.scanning import EICAR
from apps.documents.storage import get_storage
from apps.filings import evidence, tasks
from apps.filings.models import Filing, FilingResponse, FilingResponseObservation, FilingStatus
from apps.filings.signals import filing_response_recorded
from apps.identity.models import BuyerSession, User
from config.celery import app as celery_app
from tests.applications.buyer_access.test_portal_api import buyer_application_url
from tests.applications.filings.test_filings_api import (
    file,
    filing_url,
    new_package,
    package,
    ready,
)
from tests.applications.test_status_api import set_status, transition
from tests.helpers import assert_error

__all__ = ["package", "ready"]

pytestmark = pytest.mark.django_db

PDF_BYTES = b"%PDF-1.7 respuesta del banco"


def responses_url(filing: Filing) -> str:
    return filing_url(filing, "/responses")


def response_url(response: FilingResponse | str, suffix: str = "") -> str:
    response_id = response if isinstance(response, str) else response.pk
    return f"/api/v1/filing-responses/{response_id}{suffix}"


def respond(client: APIClient, filing: Filing, response_type: str, **extra: Any) -> Any:
    application = CreditApplication.objects.get(pk=filing.application_id)
    body = {
        "response_type": response_type,
        "received_at": (timezone.now() - timedelta(minutes=30)).isoformat(),
        "expected_version": application.version,
        **extra,
    }
    return client.post(responses_url(filing), body, format="json")


def recorded(client: APIClient, filing: Filing, response_type: str, **extra: Any) -> FilingResponse:
    response = respond(client, filing, response_type, **extra)
    assert response.status_code == 201, response.content
    return FilingResponse.objects.get(pk=response.json()["id"])


def status_of(application: CreditApplication) -> str:
    application.refresh_from_db()
    return application.status


def required_slots(application: CreditApplication) -> list[ApplicationDocumentSlot]:
    return list(
        ApplicationDocumentSlot.objects.filter(application=application, is_required=True).order_by(
            "pk"
        )
    )


def observation(slot: ApplicationDocumentSlot, **extra: Any) -> dict[str, Any]:
    return {
        "document_slot_id": str(slot.pk),
        "reason_code": "OUTDATED",
        "message": "Carga una versión expedida hace menos de 30 días.",
        **extra,
    }


RETURNED_BODY = {
    "reason_code": "DOCUMENT_CORRECTION",
    "public_message": "El banco pide actualizar un documento.",
    "internal_comment": "Respuesta recibida por correo.",
}
APPROVED_BODY = {
    "approved_amount_cop": 294_000_000,
    "approved_term_months": 240,
    "public_message": "¡Tu crédito fue aprobado!",
}
REJECTED_BODY = {"reason_code": "CREDIT_POLICY", "public_message": "El banco no aprobó."}
DISBURSED_BODY = {"disbursed_amount_cop": 294_000_000}
OTHER_BODY = {"internal_comment": "El banco llamó para pedir paciencia."}


@pytest.fixture
def filed(
    advisor_client: APIClient, ready: CreditApplication, package: DocumentPackageJob
) -> Filing:
    """Radicación #1 de la solicitud, en `FILED` (versión 5)."""
    response = file(advisor_client, ready, package)
    assert response.status_code == 201, response.content
    return Filing.objects.get(pk=response.json()["id"])


@pytest.fixture
def events() -> Iterator[list[tuple[str, dict[str, Any]]]]:
    received: list[tuple[str, dict[str, Any]]] = []

    def on_status(**kwargs: Any) -> None:
        received.append(("status", kwargs))

    def on_response(**kwargs: Any) -> None:
        received.append(("response", kwargs))

    application_status_changed.connect(on_status)
    filing_response_recorded.connect(on_response)
    yield received
    application_status_changed.disconnect(on_status)
    filing_response_recorded.disconnect(on_response)


# --- Cada tipo --------------------------------------------------------------------------


def test_received_moves_to_validation_once(
    advisor_client: APIClient,
    advisor_user: User,
    filed: Filing,
    events: list[tuple[str, dict[str, Any]]],
) -> None:
    response = respond(advisor_client, filed, "RECEIVED", external_reference="RAD-1")

    assert response.status_code == 201, response.content
    assert response["ETag"] == '"6"'
    body = response.json()
    assert (body["response_type"], body["response_type_label"]) == ("RECEIVED", "Recibida")
    assert body["recorded_by"] == {"id": str(advisor_user.id), "name": advisor_user.get_full_name()}
    assert status_of(filed.application) == ApplicationStatus.FILING_VALIDATION
    filed.refresh_from_db()
    assert filed.status == FilingStatus.RECEIVED
    history = ApplicationStatusHistory.objects.select_related("transition").latest("created_at")
    assert history.transition is not None and history.transition.code == "BANK_RECEIVED"
    assert [name for name, _ in events] == ["status", "response"]
    assert events[1][1]["status_changed"] is True

    # Ya en validación: se registra sin cambiar el estado ni la versión.
    again = respond(advisor_client, filed, "RECEIVED")
    assert again.status_code == 201, again.content
    assert again["ETag"] == '"6"'
    assert events[-1][1]["status_changed"] is False


@pytest.mark.parametrize(
    ("status", "transition_code"),
    [
        ("FILED", "BANK_IN_ANALYSIS_FILED"),
        ("FILING_VALIDATION", "BANK_IN_ANALYSIS_FILING_VALIDATION"),
    ],
)
def test_in_analysis_moves_to_credit_analysis(
    advisor_client: APIClient, filed: Filing, status: str, transition_code: str
) -> None:
    set_status(filed.application, status)

    recorded(advisor_client, filed, "IN_ANALYSIS")

    assert status_of(filed.application) == ApplicationStatus.CREDIT_ANALYSIS
    history = ApplicationStatusHistory.objects.select_related("transition").latest("created_at")
    assert history.transition is not None and history.transition.code == transition_code


def test_approved_records_the_conditions(advisor_client: APIClient, filed: Filing) -> None:
    set_status(filed.application, ApplicationStatus.CREDIT_ANALYSIS)
    valid_until = (timezone.localdate() + timedelta(days=90)).isoformat()

    response = respond(advisor_client, filed, "APPROVED", **APPROVED_BODY, valid_until=valid_until)

    assert response.status_code == 201, response.content
    body = response.json()
    assert (body["approved_amount_cop"], body["approved_term_months"], body["valid_until"]) == (
        294_000_000,
        240,
        valid_until,
    )
    assert status_of(filed.application) == ApplicationStatus.APPROVED
    filed.refresh_from_db()
    assert filed.status == FilingStatus.APPROVED


def test_rejected_closes_the_application(advisor_client: APIClient, filed: Filing) -> None:
    set_status(filed.application, ApplicationStatus.BANK_OBSERVATION)

    response = respond(advisor_client, filed, "REJECTED", **REJECTED_BODY)

    assert response.status_code == 201, response.content
    assert response.json()["reason"] == {"code": "CREDIT_POLICY", "label": "Políticas del banco"}
    filed.application.refresh_from_db()
    assert filed.application.status == ApplicationStatus.REJECTED
    assert filed.application.closed_at is not None


def test_other_keeps_the_status(advisor_client: APIClient, filed: Filing) -> None:
    set_status(filed.application, ApplicationStatus.CREDIT_ANALYSIS)

    response = respond(advisor_client, filed, "OTHER", **OTHER_BODY)

    assert response.status_code == 201, response.content
    assert status_of(filed.application) == ApplicationStatus.CREDIT_ANALYSIS
    filed.refresh_from_db()
    assert filed.status == FilingStatus.FILED


@pytest.mark.parametrize(
    ("response_type", "status", "body"),
    [
        ("RECEIVED", "CREDIT_ANALYSIS", {}),
        ("IN_ANALYSIS", "CREDIT_ANALYSIS", {}),
        ("RETURNED", "BANK_OBSERVATION", RETURNED_BODY),
        ("APPROVED", "BANK_OBSERVATION", APPROVED_BODY),
        ("REJECTED", "APPROVED", REJECTED_BODY),
        ("DISBURSED", "APPROVED", DISBURSED_BODY),
        ("DISBURSED", "CREDIT_ANALYSIS", DISBURSED_BODY),
    ],
)
def test_types_only_apply_in_their_statuses(
    advisor_client: APIClient,
    filed: Filing,
    response_type: str,
    status: str,
    body: dict[str, Any],
) -> None:
    set_status(filed.application, status)
    if response_type == "RETURNED":
        body = {**body, "observations": [observation(required_slots(filed.application)[0])]}

    response = respond(advisor_client, filed, response_type, **body)

    assert_error(response, 409, "INVALID_STATE_TRANSITION")
    assert not FilingResponse.objects.exists()
    assert status_of(filed.application) == status


def test_a_closed_application_takes_no_responses(advisor_client: APIClient, filed: Filing) -> None:
    set_status(filed.application, ApplicationStatus.WITHDRAWN)

    assert_error(respond(advisor_client, filed, "OTHER", **OTHER_BODY), 409, "APPLICATION_CLOSED")


def test_expected_version_must_match(advisor_client: APIClient, filed: Filing) -> None:
    body = assert_error(
        respond(advisor_client, filed, "RECEIVED", expected_version=1), 409, "STALE_VERSION"
    )
    assert body["details"][0]["current_version"] == 5


# --- Campos obligatorios ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("response_type", "body", "fields"),
    [
        ("RETURNED", {}, ["reason_code", "public_message", "observations"]),
        ("APPROVED", {}, ["approved_amount_cop", "approved_term_months", "public_message"]),
        ("REJECTED", {"public_message": " "}, ["reason_code", "public_message"]),
        ("DISBURSED", {}, ["disbursed_amount_cop"]),
        ("OTHER", {"public_message": "Hola"}, ["internal_comment"]),
        # Campos que no aplican al tipo.
        ("RECEIVED", {"reason_code": "OTHER"}, ["reason_code"]),
        ("OTHER", {**OTHER_BODY, "approved_amount_cop": 1}, ["approved_amount_cop"]),
        ("APPROVED", {**APPROVED_BODY, "disbursed_amount_cop": 1}, ["disbursed_amount_cop"]),
        # El motivo es del catálogo de su tipo.
        ("REJECTED", {**REJECTED_BODY, "reason_code": "DOCUMENT_CORRECTION"}, ["reason_code"]),
        ("APPROVED", {**APPROVED_BODY, "approved_term_months": 0}, ["approved_term_months"]),
        ("APPROVED", {**APPROVED_BODY, "valid_until": "2020-01-01"}, ["valid_until"]),
        ("RECEIVED", {"received_at": "2999-01-01T00:00:00Z"}, ["received_at"]),
        ("SENT", {}, ["response_type"]),
        ("RECEIVED", {"bank": "x"}, ["bank"]),
    ],
)
def test_required_and_typed_fields(
    advisor_client: APIClient,
    filed: Filing,
    response_type: str,
    body: dict[str, Any],
    fields: list[str],
) -> None:
    response = respond(advisor_client, filed, response_type, **body)

    error = assert_error(response, 400, "VALIDATION_ERROR")
    assert sorted(detail["field"] for detail in error["details"]) == sorted(fields)


def test_received_at_is_not_before_the_filing(advisor_client: APIClient, filed: Filing) -> None:
    before = (filed.filed_at - timedelta(minutes=1)).isoformat()

    error = assert_error(
        respond(advisor_client, filed, "RECEIVED", received_at=before), 400, "VALIDATION_ERROR"
    )
    assert error["details"][0]["field"] == "received_at"


def test_observations_must_be_current_documents_of_the_application(
    advisor_client: APIClient, filed: Filing
) -> None:
    first, second, *_ = required_slots(filed.application)
    ApplicationDocumentSlot.objects.filter(pk=second.pk).update(current_file=None)
    unknown = {**observation(first), "document_slot_id": "00000000-0000-0000-0000-000000000000"}

    error = assert_error(
        respond(
            advisor_client,
            filed,
            "RETURNED",
            **RETURNED_BODY,
            observations=[observation(first), observation(first), observation(second), unknown],
        ),
        400,
        "VALIDATION_ERROR",
    )

    assert sorted(detail["field"] for detail in error["details"]) == [
        "observations",
        "observations[2].document_slot_id",
        "observations[3].document_slot_id",
    ]


def test_a_waived_document_is_not_observed(
    advisor_client: APIClient, filed: Filing, waive_slot: Any
) -> None:
    slot = waive_slot(required_slots(filed.application)[0])

    error = assert_error(
        respond(
            advisor_client, filed, "RETURNED", **RETURNED_BODY, observations=[observation(slot)]
        ),
        400,
        "VALIDATION_ERROR",
    )
    assert error["details"][0]["field"] == "observations[0].document_slot_id"


# --- Devolución completa ----------------------------------------------------------------


def upload(session: BuyerSession, slot: ApplicationDocumentSlot) -> Any:
    return uploads.upload_document(
        session,
        slot,
        uploads.Upload(
            stream=io.BytesIO(b"%PDF-1.7 documento corregido"),
            filename="corregido.pdf",
            declared_mime_type="application/pdf",
        ),
    )


def review(client: APIClient, slot: ApplicationDocumentSlot, **data: Any) -> Any:
    return client.patch(f"/api/v1/document-slots/{slot.pk}/review", data, format="json")


def test_full_return_and_refiling(
    advisor_client: APIClient,
    advisor_user: User,
    filed: Filing,
    buyer_session: BuyerSession,
) -> None:
    application = filed.application
    observed, untouched, *_ = required_slots(application)
    old_version = observed.current_file
    assert old_version is not None

    response = respond(
        advisor_client,
        filed,
        "RETURNED",
        **RETURNED_BODY,
        observations=[observation(observed)],
    )

    # La solicitud queda en observación, con el documento rechazado para el comprador.
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["reason"] == {"code": "DOCUMENT_CORRECTION", "label": "Corrección de documentos"}
    assert [(item["document_slot_id"], item["resolved_at"]) for item in body["observations"]] == [
        (str(observed.pk), None)
    ]
    assert body["observations"][0]["reason"]["code"] == "OUTDATED"
    assert status_of(application) == ApplicationStatus.BANK_OBSERVATION
    observed.refresh_from_db()
    assert observed.status == SlotStatus.REJECTED
    rejection = DocumentReview.objects.get(slot=observed, decision=ReviewDecision.REJECTED)
    assert rejection.document_file == old_version
    assert rejection.buyer_comment == "Carga una versión expedida hace menos de 30 días."
    assert rejection.internal_comment == "Observación del banco en la radicación #1."
    assert rejection.reviewer == advisor_user
    filed.refresh_from_db()
    assert filed.status == FilingStatus.RETURNED

    # El comprador solo reemplaza el documento observado.
    untouched.refresh_from_db()
    assert isinstance(uploads.upload_block(application, untouched), DocumentLocked)
    assert uploads.upload_block(application, observed) is None
    # Aprobar otra vez la versión observada no resuelve la observación.
    assert_error(
        review(advisor_client, observed, decision="APPROVED", document_file_id=str(old_version.pk)),
        409,
        "DOCUMENT_OBSERVED",
    )
    blocked = transition(advisor_client, application, "READY_TO_FILE", version=6)
    assert "BANK_OBSERVATION_OPEN" in [d["code"] for d in blocked.json()["details"]]

    new_version = upload(buyer_session, observed)
    assert scans.scan_document_file(new_version.file_object_id) == ScanStatus.CLEAN
    approved = review(
        advisor_client, observed, decision="APPROVED", document_file_id=str(new_version.pk)
    )
    assert approved.status_code == 200, approved.content

    # La aprobación resuelve la observación y se puede radicar de nuevo.
    item = FilingResponseObservation.objects.get(document_slot=observed)
    assert (item.resolved_by_file, item.resolved_at is not None) == (new_version, True)
    assert transition(advisor_client, application, "READY_TO_FILE", version=6).status_code == 200
    second_package = new_package(application, advisor_user)
    second = file(advisor_client, application, second_package, external_reference="RAD-2")
    assert second.status_code == 201, second.content
    assert second.json()["sequence_number"] == 2

    # Las respuestas solo se registran en la última radicación.
    assert_error(respond(advisor_client, filed, "RECEIVED"), 409, "FILING_NOT_LATEST")
    latest = Filing.objects.get(pk=second.json()["id"])
    assert respond(advisor_client, latest, "RECEIVED").status_code == 201


# --- Legalización y desembolso ----------------------------------------------------------


def test_legalization_and_disbursement(
    advisor_client: APIClient, filed: Filing, events: list[tuple[str, dict[str, Any]]]
) -> None:
    application = filed.application
    recorded(advisor_client, filed, "APPROVED", **APPROVED_BODY)
    application.refresh_from_db()
    legalization = transition(
        advisor_client, application, "LEGALIZATION", version=application.version
    )
    assert legalization.status_code == 200, legalization.content

    disbursed = recorded(advisor_client, filed, "DISBURSED", **DISBURSED_BODY)

    application.refresh_from_db()
    assert application.status == ApplicationStatus.DISBURSED
    assert application.closed_at is not None
    filed.refresh_from_db()
    assert filed.status == FilingStatus.DISBURSED
    assert disbursed.disbursed_amount_cop == 294_000_000
    last = events[-1][1]
    assert (last["response"], last["application"].status) == (disbursed, "DISBURSED")


# --- Correcciones -----------------------------------------------------------------------


def test_correction_of_the_last_response(advisor_client: APIClient, filed: Filing) -> None:
    original = recorded(advisor_client, filed, "RECEIVED")
    application = CreditApplication.objects.get(pk=filed.application_id)

    response = respond(
        advisor_client,
        filed,
        "RECEIVED",
        corrects_response_id=str(original.pk),
        external_reference="RAD-CORREGIDA",
    )

    assert response.status_code == 201, response.content
    assert response.json()["corrects_response_id"] == str(original.pk)
    assert response["ETag"] == f'"{application.version}"'
    assert status_of(filed.application) == ApplicationStatus.FILING_VALIDATION
    # La corregida ya no es la última: no se corrige otra vez.
    again = respond(advisor_client, filed, "RECEIVED", corrects_response_id=str(original.pk))
    assert_error(again, 409, "RESPONSE_CORRECTION_NOT_ALLOWED")


def test_corrections_outside_the_mvp_are_rejected(advisor_client: APIClient, filed: Filing) -> None:
    received = recorded(advisor_client, filed, "RECEIVED")
    other = recorded(advisor_client, filed, "OTHER", **OTHER_BODY)

    not_last = respond(advisor_client, filed, "RECEIVED", corrects_response_id=str(received.pk))
    other_type = respond(advisor_client, filed, "RECEIVED", corrects_response_id=str(other.pk))
    unknown = respond(
        advisor_client,
        filed,
        "OTHER",
        **OTHER_BODY,
        corrects_response_id="00000000-0000-0000-0000-000000000000",
    )

    assert_error(not_last, 409, "RESPONSE_CORRECTION_NOT_ALLOWED")
    assert_error(other_type, 409, "RESPONSE_CORRECTION_NOT_ALLOWED")
    assert assert_error(unknown, 400, "VALIDATION_ERROR")["details"][0]["field"] == (
        "corrects_response_id"
    )
    approved = recorded(advisor_client, filed, "APPROVED", **APPROVED_BODY)
    assert_error(
        respond(
            advisor_client,
            filed,
            "APPROVED",
            **APPROVED_BODY,
            corrects_response_id=str(approved.pk),
        ),
        409,
        "RESPONSE_CORRECTION_NOT_ALLOWED",
    )
    corrected = respond(
        advisor_client, filed, "OTHER", **OTHER_BODY, corrects_response_id=str(other.pk)
    )
    assert_error(corrected, 409, "RESPONSE_CORRECTION_NOT_ALLOWED")


# --- Evidencia --------------------------------------------------------------------------


def attach(
    client: APIClient, response: FilingResponse, content: bytes = PDF_BYTES, **extra: Any
) -> Any:
    name = extra.pop("name", "respuesta.pdf")
    content_type = extra.pop("content_type", "application/pdf")
    uploaded = SimpleUploadedFile(name, content, content_type=content_type)
    return client.post(response_url(response, "/evidence"), {"file": uploaded}, format="multipart")


def download(client: APIClient, response: FilingResponse) -> Any:
    return client.get(response_url(response, "/evidence/download"))


def test_evidence_upload_scan_and_download(
    advisor_client: APIClient, admin_client: APIClient, filed: Filing
) -> None:
    response = recorded(advisor_client, filed, "RECEIVED")
    assert_error(download(advisor_client, response), 404, "RESOURCE_NOT_FOUND")

    uploaded = attach(advisor_client, response)

    assert uploaded.status_code == 201, uploaded.content
    assert uploaded.json()["evidence"] == {
        **uploaded.json()["evidence"],
        "filename": "respuesta.pdf",
        "mime_type": "application/pdf",
        "size_bytes": len(PDF_BYTES),
        "scan_status": "PENDING",
        "scanned_at": None,
    }
    response.refresh_from_db()
    file_object = response.evidence_file_object
    assert file_object is not None
    assert file_object.object_key.startswith(f"evidence/{filed.application_id}/")
    assert_error(download(advisor_client, response), 409, "FILE_NOT_CLEAN")

    assert evidence.scan_evidence(file_object.pk) == ScanStatus.CLEAN
    assert evidence.scan_evidence(file_object.pk) == ScanStatus.CLEAN  # Idempotente.

    link = download(advisor_client, response)
    assert link.status_code == 200, link.content
    assert link["Cache-Control"] == "no-store"
    assert link.json()["url"].startswith("memory://")
    assert download(admin_client, response).status_code == 200
    # Una sola vez.
    assert_error(attach(advisor_client, response), 409, "EVIDENCE_ALREADY_ATTACHED")


def test_evidence_is_validated(advisor_client: APIClient, filed: Filing) -> None:
    response = recorded(advisor_client, filed, "RECEIVED")

    assert_error(
        attach(advisor_client, response, b"hola", name="nota.txt", content_type="text/plain"),
        422,
        "UNSUPPORTED_FILE_TYPE",
    )
    too_big = b"%PDF-1.7 " + b"0" * evidence.EVIDENCE_MAX_BYTES
    assert_error(attach(advisor_client, response, too_big), 422, "FILE_TOO_LARGE")
    assert_error(
        advisor_client.post(response_url(response, "/evidence"), {}, format="multipart"),
        400,
        "VALIDATION_ERROR",
    )
    response.refresh_from_db()
    assert response.evidence_file_object is None
    assert not get_storage_keys()


def get_storage_keys() -> list[str]:
    storage = get_storage()
    return [key for key in getattr(storage, "objects", {}) if key.startswith("evidence/")]


def test_infected_evidence_is_never_downloaded(advisor_client: APIClient, filed: Filing) -> None:
    response = recorded(advisor_client, filed, "RECEIVED")
    assert attach(advisor_client, response, b"%PDF-1.7 " + EICAR).status_code == 201
    response.refresh_from_db()
    assert response.evidence_file_object is not None

    assert evidence.scan_evidence(response.evidence_file_object.pk) == ScanStatus.INFECTED
    assert_error(download(advisor_client, response), 409, "FILE_NOT_CLEAN")


def test_who_attaches_and_downloads_evidence(
    advisor_client: APIClient,
    admin_client: APIClient,
    broker_client: APIClient,
    broker_user: User,
    filed: Filing,
) -> None:
    # El administrador la registró: el asesor asignado no le adjunta evidencia.
    by_admin = recorded(admin_client, filed, "RECEIVED")
    assert_error(attach(advisor_client, by_admin), 403, "PERMISSION_DENIED")
    assert attach(admin_client, by_admin).status_code == 201
    by_admin.refresh_from_db()
    assert by_admin.evidence_file_object is not None
    evidence.scan_evidence(by_admin.evidence_file_object.pk)

    Opportunity.objects.filter(pk=filed.application.opportunity_id).update(origin_user=broker_user)
    assert_error(download(broker_client, by_admin), 403, "PERMISSION_DENIED")
    assert_error(attach(broker_client, by_admin), 403, "PERMISSION_DENIED")
    assert download(advisor_client, by_admin).status_code == 200


def test_evidence_scan_task_and_requeue(
    advisor_client: APIClient,
    filed: Filing,
    monkeypatch: pytest.MonkeyPatch,
    make_file_object: Any,
) -> None:
    response = recorded(advisor_client, filed, "RECEIVED")
    assert attach(advisor_client, response).status_code == 201
    response.refresh_from_db()
    file_object = response.evidence_file_object
    assert file_object is not None

    # Un archivo que no es evidencia no se analiza aquí.
    assert evidence.scan_evidence(make_file_object().pk) is None

    queued: list[str] = []
    monkeypatch.setattr(tasks.scan_filing_evidence, "delay", queued.append)
    FileObject.objects.filter(pk=file_object.pk).update(
        created_at=timezone.now() - timedelta(hours=1)
    )
    call_command("requeue_pending_scans")
    assert queued == [str(file_object.pk)]

    monkeypatch.undo()
    assert tasks.scan_filing_evidence.delay(str(file_object.pk)).get() == ScanStatus.CLEAN


def test_evidence_scan_task_retries_and_leaves_it_pending(
    advisor_client: APIClient, filed: Filing, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = recorded(advisor_client, filed, "RECEIVED")
    assert attach(advisor_client, response).status_code == 201
    response.refresh_from_db()
    assert response.evidence_file_object is not None
    monkeypatch.setitem(celery_app.conf, "CELERY_TASK_EAGER_PROPAGATES", False)

    def unavailable(file_object: FileObject) -> Any:
        raise ScannerUnavailable("clamd no responde")

    monkeypatch.setattr(evidence, "inspect_file_object", unavailable)

    result = tasks.scan_filing_evidence.apply(args=[str(response.evidence_file_object.pk)])

    assert result.get() == ScanStatus.PENDING


# --- Lo que ve cada actor ---------------------------------------------------------------


PUBLIC_FIELDS = {
    "id",
    "filing_id",
    "response_type",
    "response_type_label",
    "received_at",
    "public_message",
    "created_at",
}


def test_broker_sees_only_the_public_part(
    advisor_client: APIClient,
    broker_client: APIClient,
    broker_user: User,
    filed: Filing,
) -> None:
    Opportunity.objects.filter(pk=filed.application.opportunity_id).update(origin_user=broker_user)
    approved = recorded(
        advisor_client, filed, "APPROVED", **APPROVED_BODY, internal_comment="Tasa 12,5 %."
    )

    listed = broker_client.get(responses_url(filed))
    detail = broker_client.get(response_url(approved))

    assert listed.status_code == 200
    assert [set(item) for item in listed.json()["items"]] == [PUBLIC_FIELDS]
    assert set(detail.json()) == PUBLIC_FIELDS
    assert detail.json()["public_message"] == "¡Tu crédito fue aprobado!"
    assert_error(respond(broker_client, filed, "OTHER", **OTHER_BODY), 403, "PERMISSION_DENIED")
    # El asesor ve todo.
    full = advisor_client.get(response_url(approved)).json()
    assert full["internal_comment"] == "Tasa 12,5 %."
    assert full["approved_amount_cop"] == 294_000_000


def test_out_of_scope_users_get_404(
    advisor_client: APIClient, other_advisor_client: APIClient, filed: Filing
) -> None:
    response = recorded(advisor_client, filed, "RECEIVED")

    assert other_advisor_client.get(responses_url(filed)).status_code == 404
    assert other_advisor_client.get(response_url(response)).status_code == 404
    assert respond(other_advisor_client, filed, "RECEIVED").status_code == 404
    assert advisor_client.get(response_url("00000000-0000-0000-0000-000000000000")).status_code == (
        404
    )


def test_buyer_sees_the_latest_public_update(
    advisor_client: APIClient, portal: APIClient, filed: Filing
) -> None:
    application = filed.application
    assert portal.get(buyer_application_url(application)).json()["latest_bank_update"] is None

    recorded(advisor_client, filed, "RECEIVED", public_message="El banco recibió tu solicitud.")
    recorded(
        advisor_client,
        filed,
        "APPROVED",
        **APPROVED_BODY,
        internal_comment="Nota interna que el comprador no ve.",
    )
    # Una respuesta sin mensaje público no cambia lo que ve el comprador.
    recorded(advisor_client, filed, "OTHER", **OTHER_BODY)

    body = portal.get(buyer_application_url(application)).json()
    update = body["latest_bank_update"]
    assert set(update) == {"response_type", "response_type_label", "received_at", "public_message"}
    assert (update["response_type"], update["public_message"]) == (
        "APPROVED",
        "¡Tu crédito fue aprobado!",
    )
    assert "Nota interna" not in str(body)


def test_responses_list_is_chronological(advisor_client: APIClient, filed: Filing) -> None:
    now = timezone.now()
    recorded(
        advisor_client,
        filed,
        "OTHER",
        **OTHER_BODY,
        received_at=(now - timedelta(minutes=5)).isoformat(),
    )
    recorded(
        advisor_client, filed, "RECEIVED", received_at=(now - timedelta(minutes=10)).isoformat()
    )

    items = advisor_client.get(responses_url(filed)).json()["items"]

    assert [item["response_type"] for item in items] == ["RECEIVED", "OTHER"]
    filing = advisor_client.get(filing_url(filed)).json()
    assert filing["responses_count"] == 2
