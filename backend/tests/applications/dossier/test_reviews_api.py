"""Revisión, exoneración y reapertura de slots (decisiones 7, 8 y 22; acordadas 6 y 8;
decisiones de la Parte 5)."""

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import ApplicationParticipant, CreditApplication
from apps.catalogs.workflow import ApplicationStatus
from apps.documents import uploads
from apps.documents.fingerprint import dossier_fingerprint
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
from apps.documents.reviews import restored_status
from apps.identity.models import RolePermission, User
from tests.applications.buyer_access.conftest import set_status
from tests.applications.conftest import catalog_item
from tests.applications.dossier.conftest import DocumentFileFactory, SlotFactory
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

VersionFactory = Callable[..., DocumentFile]


def review_url(slot: ApplicationDocumentSlot) -> str:
    return f"/api/v1/document-slots/{slot.id}/review"


def review(client: APIClient, slot: ApplicationDocumentSlot, **data: Any) -> Any:
    return client.patch(review_url(slot), data, format="json")


def approve(client: APIClient, slot: ApplicationDocumentSlot, **data: Any) -> Any:
    slot.refresh_from_db()
    data.setdefault("document_file_id", str(slot.current_file_id))
    return review(client, slot, decision="APPROVED", **data)


def reject(client: APIClient, slot: ApplicationDocumentSlot, **data: Any) -> Any:
    slot.refresh_from_db()
    data.setdefault("document_file_id", str(slot.current_file_id))
    data.setdefault("reason_code", "ILLEGIBLE")
    data.setdefault("buyer_comment", "La foto está borrosa.")
    return review(client, slot, decision="REJECTED", **data)


def waive(client: APIClient, slot: ApplicationDocumentSlot, **data: Any) -> Any:
    data.setdefault("reason_code", "NOT_APPLICABLE")
    return review(client, slot, decision="WAIVED", **data)


def reopen(client: APIClient, slot: ApplicationDocumentSlot, **data: Any) -> Any:
    data.setdefault("internal_comment", "Se exoneró por error.")
    return review(client, slot, decision="REOPENED", **data)


def doc_type(code: str) -> DocumentType:
    return DocumentType.objects.get(code=code)


def details(response: Any) -> list[dict[str, Any]]:
    return list(response.json()["details"])


def reload(slot: ApplicationDocumentSlot) -> ApplicationDocumentSlot:
    return ApplicationDocumentSlot.objects.select_related("current_file").get(pk=slot.pk)


@pytest.fixture
def with_version(
    make_document_file: DocumentFileFactory, make_file_object: Callable[..., FileObject]
) -> VersionFactory:
    """Carga una versión vigente en el slot: análisis limpio y en revisión por omisión."""

    def _with_version(slot: ApplicationDocumentSlot, **extra: Any) -> DocumentFile:
        scan = extra.pop("scan_status", ScanStatus.CLEAN)
        scanned_at = None if scan == ScanStatus.PENDING else timezone.now()
        extra.setdefault(
            "status",
            DocumentFileStatus.UPLOADED
            if scan == ScanStatus.PENDING
            else DocumentFileStatus.IN_REVIEW,
        )
        extra.setdefault("version_number", slot.files.count() + 1)
        version = make_document_file(
            slot=slot,
            file_object=make_file_object(scan_status=scan, scanned_at=scanned_at),
            **extra,
        )
        slot_status: str = {
            DocumentFileStatus.APPROVED: SlotStatus.APPROVED,
            DocumentFileStatus.REJECTED: SlotStatus.REJECTED,
        }.get(DocumentFileStatus(version.status), SlotStatus.UPLOADED)
        ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(
            current_file=version, status=slot_status
        )
        slot.refresh_from_db()
        return version

    return _with_version


@pytest.fixture
def slot(make_slot: SlotFactory) -> ApplicationDocumentSlot:
    return make_slot()


@pytest.fixture
def no_waive_permission() -> None:
    RolePermission.objects.filter(role__code="ADVISOR", permission__code="documents.waive").delete()


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
def test_review_access_matrix(
    request: pytest.FixtureRequest,
    slot: ApplicationDocumentSlot,
    with_version: VersionFactory,
    client_name: str,
    expected: int,
) -> None:
    client: APIClient = request.getfixturevalue(client_name)
    with_version(slot)

    assert approve(client, slot).status_code == expected


@pytest.fixture
def anonymous() -> APIClient:
    return APIClient()


def test_unknown_slot_is_404(advisor_client: APIClient) -> None:
    response = advisor_client.patch(
        "/api/v1/document-slots/00000000-0000-0000-0000-000000000000/review",
        {"decision": "WAIVED", "reason_code": "OTHER"},
        format="json",
    )

    assert_error(response, 404, "RESOURCE_NOT_FOUND")


# --- Aprobar ----------------------------------------------------------------------------


def test_approve_the_current_clean_version(
    advisor_client: APIClient,
    advisor_user: User,
    application: CreditApplication,
    slot: ApplicationDocumentSlot,
    with_version: VersionFactory,
) -> None:
    version = with_version(slot)

    response = approve(advisor_client, slot, internal_comment="Coincide con la base.")

    assert response.status_code == 200, response.content
    (row,) = response.json()["slots"]
    assert row["id"] == str(slot.id)
    assert row["status"] == "APPROVED"
    assert row["current_file"]["status"] == "APPROVED"
    version.refresh_from_db()
    assert version.status == DocumentFileStatus.APPROVED
    saved = DocumentReview.objects.get()
    assert saved.slot_id == slot.pk
    assert saved.document_file_id == version.pk
    assert saved.reviewer == advisor_user
    assert saved.decision == ReviewDecision.APPROVED
    assert saved.internal_comment == "Coincide con la base."
    assert saved.decision_batch_id is None
    # Los documentos no tocan la versión de la solicitud (acordada 6).
    application.refresh_from_db(fields=["version"])
    assert application.version == 1


@pytest.mark.parametrize("scan", [ScanStatus.PENDING, ScanStatus.INFECTED, ScanStatus.INVALID])
def test_approve_needs_a_clean_scan(
    advisor_client: APIClient,
    slot: ApplicationDocumentSlot,
    with_version: VersionFactory,
    scan: str,
) -> None:
    with_version(slot, scan_status=scan)

    assert_error(approve(advisor_client, slot), 409, "FILE_NOT_CLEAN")
    assert not DocumentReview.objects.exists()


def test_a_version_that_is_no_longer_current_is_409(
    advisor_client: APIClient, slot: ApplicationDocumentSlot, with_version: VersionFactory
) -> None:
    old = with_version(slot)
    with_version(slot)

    response = approve(advisor_client, slot, document_file_id=str(old.pk))

    assert_error(response, 409, "DOCUMENT_NOT_CURRENT")
    old.refresh_from_db()
    assert old.status == DocumentFileStatus.IN_REVIEW


def test_a_version_of_another_slot_is_400(
    advisor_client: APIClient,
    slot: ApplicationDocumentSlot,
    make_slot: SlotFactory,
    with_version: VersionFactory,
) -> None:
    with_version(slot)
    other = make_slot(document_type=doc_type("EMPLOYMENT_CERTIFICATE"))
    foreign = with_version(other)

    response = approve(advisor_client, slot, document_file_id=str(foreign.pk))

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"] == [
        {
            "field": "document_file_id",
            "code": "NOT_A_VERSION",
            "message": "El archivo no es una versión de este documento.",
            "resource_id": str(slot.pk),
        }
    ]


def test_approve_with_validity_needs_a_document_date(
    advisor_client: APIClient, make_slot: SlotFactory, with_version: VersionFactory
) -> None:
    slot = make_slot(validity_days=30)
    with_version(slot)

    body = assert_error(approve(advisor_client, slot), 400, "VALIDATION_ERROR")

    assert [(row["field"], row["code"]) for row in body["details"]] == [
        ("document_date", "REQUIRED")
    ]


def test_approve_uses_the_buyer_date_or_the_corrected_one(
    advisor_client: APIClient, make_slot: SlotFactory, with_version: VersionFactory
) -> None:
    today = timezone.localdate()
    slot = make_slot(validity_days=30)
    version = with_version(
        slot, document_date=today - timedelta(days=40), expires_at=today - timedelta(days=10)
    )
    corrected = today - timedelta(days=5)

    response = approve(advisor_client, slot, document_date=corrected.isoformat())

    assert response.status_code == 200, response.content
    version.refresh_from_db()
    assert version.document_date == corrected
    assert version.expires_at == corrected + timedelta(days=30)

    other = make_slot(document_type=doc_type("EMPLOYMENT_CERTIFICATE"), validity_days=30)
    kept = with_version(other, document_date=today - timedelta(days=2))
    assert approve(advisor_client, other).status_code == 200
    kept.refresh_from_db()
    assert kept.expires_at == today + timedelta(days=28)


@pytest.mark.parametrize("age_days", [30, 45])
def test_an_expired_document_is_not_approved(
    advisor_client: APIClient,
    make_slot: SlotFactory,
    with_version: VersionFactory,
    age_days: int,
) -> None:
    # Con 30 días de vigencia, el documento vence el día 30: ese día ya no se aprueba.
    slot = make_slot(validity_days=30)
    with_version(slot)
    document_date = timezone.localdate() - timedelta(days=age_days)

    response = approve(advisor_client, slot, document_date=document_date.isoformat())

    body = assert_error(response, 422, "DOCUMENT_EXPIRED")
    assert body["details"][0]["field"] == "document_date"
    assert reload(slot).status == SlotStatus.UPLOADED


def test_a_future_document_date_is_400(
    advisor_client: APIClient, slot: ApplicationDocumentSlot, with_version: VersionFactory
) -> None:
    with_version(slot)
    tomorrow = timezone.localdate() + timedelta(days=1)

    body = assert_error(
        approve(advisor_client, slot, document_date=tomorrow.isoformat()), 400, "VALIDATION_ERROR"
    )

    assert body["details"][0]["field"] == "document_date"


def test_a_slot_without_validity_keeps_no_expiry(
    advisor_client: APIClient, slot: ApplicationDocumentSlot, with_version: VersionFactory
) -> None:
    version = with_version(slot)
    yesterday = timezone.localdate() - timedelta(days=1)

    assert approve(advisor_client, slot, document_date=yesterday.isoformat()).status_code == 200

    version.refresh_from_db()
    assert version.document_date == yesterday
    assert version.expires_at is None


# --- Rechazar y corregir -----------------------------------------------------------------


def test_reject_the_current_version(
    advisor_client: APIClient, slot: ApplicationDocumentSlot, with_version: VersionFactory
) -> None:
    version = with_version(slot)

    response = reject(advisor_client, slot, internal_comment="Revisar con el banco.")

    assert response.status_code == 200, response.content
    assert response.json()["slots"][0]["status"] == "REJECTED"
    version.refresh_from_db()
    assert version.status == DocumentFileStatus.REJECTED
    saved = DocumentReview.objects.get()
    assert saved.reason_item == catalog_item("document_rejection_reason", "ILLEGIBLE")
    assert saved.buyer_comment == "La foto está borrosa."


def test_a_pending_scan_can_be_rejected(
    advisor_client: APIClient, slot: ApplicationDocumentSlot, with_version: VersionFactory
) -> None:
    with_version(slot, scan_status=ScanStatus.PENDING)

    assert reject(advisor_client, slot).status_code == 200
    assert reload(slot).status == SlotStatus.REJECTED


def test_reject_needs_a_reason_and_a_buyer_comment(
    advisor_client: APIClient, slot: ApplicationDocumentSlot, with_version: VersionFactory
) -> None:
    with_version(slot)

    response = reject(advisor_client, slot, reason_code=None, buyer_comment=None)

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert {(row["field"], row["code"]) for row in body["details"]} == {
        ("reason_code", "REQUIRED"),
        ("buyer_comment", "REQUIRED"),
    }


@pytest.mark.parametrize("code", ["NOT_APPLICABLE", "UNKNOWN"])
def test_reject_takes_the_reason_from_the_rejection_catalog(
    advisor_client: APIClient,
    slot: ApplicationDocumentSlot,
    with_version: VersionFactory,
    code: str,
) -> None:
    with_version(slot)

    body = assert_error(reject(advisor_client, slot, reason_code=code), 400, "VALIDATION_ERROR")

    assert body["details"][0]["field"] == "reason_code"
    assert body["details"][0]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    ("decision", "data", "field"),
    [
        ("REJECTED", {"document_date": "2026-01-01"}, "document_date"),
        ("APPROVED", {"buyer_comment": "Bien."}, "buyer_comment"),
        ("APPROVED", {"reason_code": "ILLEGIBLE"}, "reason_code"),
        ("WAIVED", {"buyer_comment": "Exonerado."}, "buyer_comment"),
        (
            "WAIVED",
            {"document_file_id": "00000000-0000-0000-0000-000000000000"},
            "document_file_id",
        ),
        ("REOPENED", {"reason_code": "OTHER"}, "reason_code"),
    ],
)
def test_fields_that_do_not_apply_to_the_decision_are_400(
    advisor_client: APIClient,
    slot: ApplicationDocumentSlot,
    with_version: VersionFactory,
    decision: str,
    data: dict[str, Any],
    field: str,
) -> None:
    version = with_version(slot)
    payload = {"decision": decision, **data}
    if decision in ("APPROVED", "REJECTED"):
        payload.setdefault("document_file_id", str(version.pk))
    if decision == "REJECTED":
        payload.update(reason_code="ILLEGIBLE", buyer_comment="No se lee.")
    if decision == "WAIVED":
        payload.setdefault("reason_code", "OTHER")
    if decision == "REOPENED":
        payload["internal_comment"] = "Error."

    body = assert_error(review(advisor_client, slot, **payload), 400, "VALIDATION_ERROR")

    assert [(row["field"], row["code"]) for row in body["details"]] == [(field, "NOT_ALLOWED")]


def test_unknown_fields_and_decisions_are_400(
    advisor_client: APIClient, slot: ApplicationDocumentSlot
) -> None:
    assert_error(review(advisor_client, slot, decision="MAYBE"), 400, "VALIDATION_ERROR")
    response = review(advisor_client, slot, decision="WAIVED", reason_code="OTHER", extra=1)
    assert_error(response, 400, "VALIDATION_ERROR")


def test_a_decision_is_corrected_with_a_new_row(
    advisor_client: APIClient, slot: ApplicationDocumentSlot, with_version: VersionFactory
) -> None:
    version = with_version(slot)

    assert approve(advisor_client, slot).status_code == 200
    assert reject(advisor_client, slot).status_code == 200
    assert approve(advisor_client, slot).status_code == 200

    decisions = list(
        DocumentReview.objects.filter(document_file=version)
        .order_by("created_at")
        .values_list("decision", flat=True)
    )
    assert decisions == ["APPROVED", "REJECTED", "APPROVED"]
    version.refresh_from_db()
    assert version.status == DocumentFileStatus.APPROVED
    assert reload(slot).status == SlotStatus.APPROVED


# --- Estado de la solicitud y del slot ---------------------------------------------------


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (ApplicationStatus.FILED, "APPLICATION_NOT_EDITABLE"),
        (ApplicationStatus.WITHDRAWN, "APPLICATION_CLOSED"),
    ],
)
def test_no_review_after_filing_or_closing(
    advisor_client: APIClient,
    application: CreditApplication,
    slot: ApplicationDocumentSlot,
    make_slot: SlotFactory,
    with_version: VersionFactory,
    status: str,
    code: str,
) -> None:
    with_version(slot)
    waivable = make_slot(document_type=doc_type("EMPLOYMENT_CERTIFICATE"), is_waivable=True)
    set_status(application, status)

    assert_error(approve(advisor_client, slot), 409, code)
    assert_error(reject(advisor_client, slot), 409, code)
    assert_error(waive(advisor_client, waivable), 409, code)
    ApplicationDocumentSlot.objects.filter(pk=waivable.pk).update(
        status=SlotStatus.WAIVED,
        waiver_reason_item=catalog_item("document_waiver_reason", "OTHER"),
    )
    assert_error(reopen(advisor_client, waivable), 409, code)
    assert not DocumentReview.objects.exists()


def test_after_filing_an_observed_slot_can_be_reviewed(
    advisor_client: APIClient,
    application: CreditApplication,
    make_slot: SlotFactory,
    with_version: VersionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slot = make_slot(is_waivable=True)
    with_version(slot)
    set_status(application, ApplicationStatus.FILED)
    monkeypatch.setattr(uploads, "slot_has_open_observation", lambda slot: True)

    assert approve(advisor_client, slot).status_code == 200
    # Exonerar y reabrir siguen cerrados después de la radicación.
    assert_error(waive(advisor_client, slot), 409, "APPLICATION_NOT_EDITABLE")


def test_a_retired_slot_is_locked(
    advisor_client: APIClient, slot: ApplicationDocumentSlot, with_version: VersionFactory
) -> None:
    with_version(slot)
    ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(retired_at=timezone.now())

    body = assert_error(approve(advisor_client, slot), 409, "DOCUMENT_LOCKED")

    assert body["message"] == "El documento ya no aplica a la solicitud."


def test_a_waived_slot_is_reopened_before_reviewing_its_file(
    advisor_client: APIClient, make_slot: SlotFactory, with_version: VersionFactory
) -> None:
    slot = make_slot(is_waivable=True)
    with_version(slot)
    assert waive(advisor_client, slot).status_code == 200

    assert_error(approve(advisor_client, slot), 409, "DOCUMENT_LOCKED")


# --- Exonerar ----------------------------------------------------------------------------


def test_waive_a_single_slot(
    advisor_client: APIClient,
    advisor_user: User,
    make_slot: SlotFactory,
    with_version: VersionFactory,
) -> None:
    slot = make_slot(is_waivable=True)
    version = with_version(slot)

    response = waive(advisor_client, slot, reason_code="BANK_EXEMPTED", internal_comment="Correo.")

    assert response.status_code == 200, response.content
    (row,) = response.json()["slots"]
    assert row["status"] == "WAIVED"
    assert row["waiver_reason"]["code"] == "BANK_EXEMPTED"
    saved = DocumentReview.objects.get()
    assert saved.decision == ReviewDecision.WAIVED
    assert saved.slot_id == slot.pk
    assert saved.document_file_id == version.pk
    assert saved.reviewer == advisor_user
    assert saved.reason_item == catalog_item("document_waiver_reason", "BANK_EXEMPTED")
    assert saved.internal_comment == "Correo."
    assert saved.decision_batch_id is not None
    # La versión no cambia al exonerar.
    version.refresh_from_db()
    assert version.status == DocumentFileStatus.IN_REVIEW


def test_waive_a_slot_without_a_file(advisor_client: APIClient, make_slot: SlotFactory) -> None:
    slot = make_slot(is_waivable=True)

    assert waive(advisor_client, slot).status_code == 200

    saved = DocumentReview.objects.get()
    assert saved.document_file_id is None
    assert reload(slot).status == SlotStatus.WAIVED


def test_a_non_waivable_slot_is_400(
    advisor_client: APIClient, slot: ApplicationDocumentSlot, primary: ApplicationParticipant
) -> None:
    body = assert_error(waive(advisor_client, slot), 400, "VALIDATION_ERROR")

    assert body["details"] == [
        {
            "field": "decision",
            "code": "NOT_WAIVABLE",
            "message": (
                "El documento «Copia del documento de identidad» de "
                f"{primary.client.full_name} no se puede exonerar."
            ),
            "resource_id": str(slot.pk),
        }
    ]
    assert reload(slot).status == SlotStatus.PENDING


def test_waive_takes_the_reason_from_the_waiver_catalog(
    advisor_client: APIClient, make_slot: SlotFactory
) -> None:
    slot = make_slot(is_waivable=True)

    response = waive(advisor_client, slot, reason_code="ILLEGIBLE")

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "reason_code"
    assert_error(waive(advisor_client, slot, reason_code=None), 400, "VALIDATION_ERROR")


@pytest.mark.usefixtures("no_waive_permission")
def test_waive_and_reopen_need_the_waive_permission(
    advisor_client: APIClient, make_slot: SlotFactory, with_version: VersionFactory
) -> None:
    slot = make_slot(is_waivable=True)
    with_version(slot)

    assert_error(waive(advisor_client, slot), 403, "PERMISSION_DENIED")
    assert_error(reopen(advisor_client, slot), 403, "PERMISSION_DENIED")
    # Aprobar sigue permitido con `documents.review`.
    assert approve(advisor_client, slot).status_code == 200


def test_an_approved_slot_has_nothing_to_waive(
    advisor_client: APIClient, make_slot: SlotFactory, with_version: VersionFactory
) -> None:
    slot = make_slot(is_waivable=True)
    with_version(slot, status=DocumentFileStatus.APPROVED)

    body = assert_error(waive(advisor_client, slot), 400, "VALIDATION_ERROR")

    assert body["details"][0]["code"] == "NOTHING_TO_WAIVE"
    assert body["details"][0]["resource_id"] == str(slot.pk)


def test_an_already_waived_slot_has_nothing_to_waive(
    advisor_client: APIClient, make_slot: SlotFactory
) -> None:
    slot = make_slot(is_waivable=True)
    assert waive(advisor_client, slot).status_code == 200

    body = assert_error(waive(advisor_client, slot), 400, "VALIDATION_ERROR")

    assert body["details"][0]["code"] == "NOTHING_TO_WAIVE"
    assert DocumentReview.objects.count() == 1


# --- Grupo alternativo -------------------------------------------------------------------


@pytest.fixture
def group(make_slot: SlotFactory) -> list[ApplicationDocumentSlot]:
    """Tres alternativas del titular en el grupo ``INCOME``."""
    return [
        make_slot(document_type=doc_type(code), is_waivable=True, alternative_group_code="INCOME")
        for code in ("EMPLOYMENT_CERTIFICATE", "PAYROLL_SLIP", "BANK_STATEMENT")
    ]


def test_waive_a_group_keeps_the_approved_slots(
    advisor_client: APIClient,
    make_slot: SlotFactory,
    with_version: VersionFactory,
    group: list[ApplicationDocumentSlot],
) -> None:
    first, approved, third = group
    with_version(approved, status=DocumentFileStatus.APPROVED)
    # Mismo grupo en otro titular (la solicitud) y un slot retirado: no se tocan.
    other_holder = make_slot(
        document_type=doc_type("PROPERTY_OWNERSHIP_DOCUMENT"),
        participant=None,
        is_waivable=True,
        alternative_group_code="INCOME",
    )
    retired = make_slot(
        document_type=doc_type("PENSION_CERTIFICATE"),
        is_waivable=True,
        alternative_group_code="INCOME",
        retired_at=timezone.now(),
    )

    response = waive(advisor_client, first)

    assert response.status_code == 200, response.content
    assert {row["id"] for row in response.json()["slots"]} == {str(first.pk), str(third.pk)}
    assert reload(first).status == reload(third).status == SlotStatus.WAIVED
    assert reload(approved).status == SlotStatus.APPROVED
    assert reload(approved).waiver_reason_item is None
    assert reload(other_holder).status == reload(retired).status == SlotStatus.PENDING
    batches = set(DocumentReview.objects.values_list("decision_batch_id", flat=True))
    assert len(batches) == 1
    assert DocumentReview.objects.count() == 2


def test_waiving_from_an_approved_slot_waives_the_rest_of_the_group(
    advisor_client: APIClient, with_version: VersionFactory, group: list[ApplicationDocumentSlot]
) -> None:
    first, second, third = group
    with_version(first, status=DocumentFileStatus.APPROVED)

    response = waive(advisor_client, first)

    assert response.status_code == 200, response.content
    assert {row["id"] for row in response.json()["slots"]} == {str(second.pk), str(third.pk)}
    assert reload(first).status == SlotStatus.APPROVED


def test_a_group_with_a_non_waivable_slot_waives_nothing(
    advisor_client: APIClient, group: list[ApplicationDocumentSlot]
) -> None:
    first, blocker, _ = group
    ApplicationDocumentSlot.objects.filter(pk=blocker.pk).update(is_waivable=False)

    body = assert_error(waive(advisor_client, first), 400, "VALIDATION_ERROR")

    (detail,) = body["details"]
    assert detail["code"] == "NOT_WAIVABLE"
    assert detail["resource_id"] == str(blocker.pk)
    assert "«Desprendible o comprobante de nómina»" in detail["message"]
    assert not DocumentReview.objects.exists()
    assert not ApplicationDocumentSlot.objects.filter(status=SlotStatus.WAIVED).exists()


def test_an_approved_non_waivable_slot_does_not_block_the_group(
    advisor_client: APIClient, with_version: VersionFactory, group: list[ApplicationDocumentSlot]
) -> None:
    first, approved, third = group
    ApplicationDocumentSlot.objects.filter(pk=approved.pk).update(is_waivable=False)
    with_version(approved, status=DocumentFileStatus.APPROVED)

    response = waive(advisor_client, first)

    assert response.status_code == 200, response.content
    assert reload(approved).status == SlotStatus.APPROVED


def test_a_fully_approved_group_has_nothing_to_waive(
    advisor_client: APIClient, with_version: VersionFactory, group: list[ApplicationDocumentSlot]
) -> None:
    for member in group:
        with_version(member, status=DocumentFileStatus.APPROVED)

    body = assert_error(waive(advisor_client, group[0]), 400, "VALIDATION_ERROR")

    assert body["details"][0]["code"] == "NOTHING_TO_WAIVE"


# --- Reabrir -----------------------------------------------------------------------------


def test_reopen_restores_each_slot_from_its_current_version(
    advisor_client: APIClient,
    advisor_user: User,
    with_version: VersionFactory,
    group: list[ApplicationDocumentSlot],
) -> None:
    empty, in_review, rejected = group
    with_version(in_review)
    with_version(rejected, status=DocumentFileStatus.REJECTED)
    assert waive(advisor_client, empty).status_code == 200
    waiver_batch = DocumentReview.objects.values_list("decision_batch_id", flat=True).first()

    response = reopen(advisor_client, empty)

    assert response.status_code == 200, response.content
    statuses = {row["id"]: row["status"] for row in response.json()["slots"]}
    assert statuses == {
        str(empty.pk): "PENDING",
        str(in_review.pk): "UPLOADED",
        str(rejected.pk): "REJECTED",
    }
    for member in group:
        assert reload(member).waiver_reason_item is None
    reopened = DocumentReview.objects.filter(decision=ReviewDecision.REOPENED)
    assert reopened.count() == 3
    assert {row.internal_comment for row in reopened} == {"Se exoneró por error."}
    assert {row.reviewer_id for row in reopened} == {advisor_user.pk}
    reopen_batches = set(reopened.values_list("decision_batch_id", flat=True))
    assert len(reopen_batches) == 1
    assert reopen_batches != {waiver_batch}
    # La exoneración no se borra ni se edita.
    assert DocumentReview.objects.filter(decision=ReviewDecision.WAIVED).count() == 3


def test_reopen_only_the_slots_of_the_same_waiver(
    advisor_client: APIClient, with_version: VersionFactory, group: list[ApplicationDocumentSlot]
) -> None:
    first, second, third = group
    # El grupo se exonera con `third` aprobado (`first` y `second`); después se rechaza
    # `third` y se exonera solo, en otro lote.
    with_version(third, status=DocumentFileStatus.APPROVED)
    assert waive(advisor_client, first).status_code == 200
    assert reject(advisor_client, third).status_code == 200
    assert waive(advisor_client, third).status_code == 200
    assert reload(second).status == reload(third).status == SlotStatus.WAIVED

    response = reopen(advisor_client, second)

    assert response.status_code == 200, response.content
    assert {row["id"] for row in response.json()["slots"]} == {str(first.pk), str(second.pk)}
    assert reload(third).status == SlotStatus.WAIVED


def test_reopen_skips_slots_retired_or_waived_again_since(
    advisor_client: APIClient, advisor_user: User, group: list[ApplicationDocumentSlot]
) -> None:
    first, retired, rewaived = group
    assert waive(advisor_client, first).status_code == 200
    ApplicationDocumentSlot.objects.filter(pk=retired.pk).update(retired_at=timezone.now())
    # La última exoneración de `rewaived` es de otro lote.
    DocumentReview.objects.create(
        slot=rewaived,
        reviewer=advisor_user,
        decision=ReviewDecision.WAIVED,
        reason_item=catalog_item("document_waiver_reason", "OTHER"),
        decision_batch_id=uuid.uuid4(),
    )

    response = reopen(advisor_client, first)

    assert response.status_code == 200, response.content
    assert {row["id"] for row in response.json()["slots"]} == {str(first.pk)}
    assert reload(retired).status == SlotStatus.WAIVED
    assert reload(rewaived).status == SlotStatus.WAIVED


def test_reopen_a_slot_waived_without_history(
    advisor_client: APIClient, make_slot: SlotFactory
) -> None:
    slot = make_slot(
        is_waivable=True,
        status=SlotStatus.WAIVED,
        waiver_reason_item=catalog_item("document_waiver_reason", "OTHER"),
    )

    response = reopen(advisor_client, slot)

    assert response.status_code == 200, response.content
    assert reload(slot).status == SlotStatus.PENDING


@pytest.mark.parametrize("comment", [None, "", "   "])
def test_reopen_needs_an_internal_comment(
    advisor_client: APIClient, make_slot: SlotFactory, comment: str | None
) -> None:
    slot = make_slot(is_waivable=True)
    assert waive(advisor_client, slot).status_code == 200

    body = assert_error(
        reopen(advisor_client, slot, internal_comment=comment), 400, "VALIDATION_ERROR"
    )

    assert body["details"][0]["field"] == "internal_comment"
    assert reload(slot).status == SlotStatus.WAIVED


def test_reopen_a_slot_that_is_not_waived_is_400(
    advisor_client: APIClient, slot: ApplicationDocumentSlot
) -> None:
    body = assert_error(reopen(advisor_client, slot), 400, "VALIDATION_ERROR")

    assert body["details"][0] == {
        "field": "decision",
        "code": "NOT_WAIVED",
        "message": "Solo se reabre un documento exonerado.",
        "resource_id": str(slot.pk),
    }


def test_restored_status_follows_the_current_version(
    slot: ApplicationDocumentSlot, with_version: VersionFactory
) -> None:
    assert restored_status(slot) == SlotStatus.PENDING
    for status, expected in [
        (DocumentFileStatus.UPLOADED, SlotStatus.UPLOADED),
        (DocumentFileStatus.IN_REVIEW, SlotStatus.UPLOADED),
        (DocumentFileStatus.APPROVED, SlotStatus.APPROVED),
        (DocumentFileStatus.REJECTED, SlotStatus.REJECTED),
    ]:
        with_version(slot, status=status)
        assert restored_status(reload(slot)) == expected


def test_the_slot_detail_shows_who_waived_and_reopened(
    advisor_client: APIClient,
    admin_client: APIClient,
    admin_user: User,
    advisor_user: User,
    make_slot: SlotFactory,
) -> None:
    slot = make_slot(is_waivable=True)
    assert waive(advisor_client, slot, internal_comment="Lo pidió el banco.").status_code == 200
    assert reopen(admin_client, slot).status_code == 200

    response = advisor_client.get(f"/api/v1/document-slots/{slot.id}")

    assert response.status_code == 200, response.content
    history = response.json()["waiver_history"]
    assert [(row["decision"], row["reviewer"]["id"]) for row in history] == [
        ("REOPENED", str(admin_user.pk)),
        ("WAIVED", str(advisor_user.pk)),
    ]
    assert [row["decision_label"] for row in history] == ["Exoneración reabierta", "Exonerado"]
    assert history[0]["internal_comment"] == "Se exoneró por error."
    assert history[1]["reason"]["code"] == "NOT_APPLICABLE"
    assert history[0]["decision_batch_id"] != history[1]["decision_batch_id"]
    # El historial de exoneraciones no se mezcla con las revisiones de las versiones.
    versions = advisor_client.get(f"/api/v1/document-slots/{slot.id}/versions").json()
    assert versions["items"] == []


def test_waiver_notes_never_reach_the_buyer(
    advisor_client: APIClient,
    portal: APIClient,
    group: list[ApplicationDocumentSlot],
    with_version: VersionFactory,
) -> None:
    first, second, _ = group
    with_version(second, status=DocumentFileStatus.REJECTED)
    assert reject_with_note(advisor_client, second).status_code == 200
    assert waive(advisor_client, first, internal_comment="Nota de exoneración.").status_code == 200
    assert reopen(advisor_client, first, internal_comment="Nota de reapertura.").status_code == 200

    texts = [
        portal.get(f"/api/v1/buyer/document-slots/{member.id}").content.decode()
        + portal.get(f"/api/v1/buyer/document-slots/{member.id}/versions").content.decode()
        for member in group
    ]

    joined = "".join(texts)
    assert "Nota de exoneración" not in joined
    assert "Nota de reapertura" not in joined
    assert "Nota del rechazo" not in joined
    assert "internal_comment" not in joined
    assert "waiver" not in joined
    # El rechazo sigue visible para el comprador después de exonerar y reabrir.
    detail = portal.get(f"/api/v1/buyer/document-slots/{second.id}").json()
    assert detail["status"] == "REJECTED"
    assert detail["rejection"]["buyer_comment"] == "La foto está borrosa."


def reject_with_note(client: APIClient, slot: ApplicationDocumentSlot) -> Any:
    return reject(client, slot, internal_comment="Nota del rechazo.")


# --- Huella documental -------------------------------------------------------------------


def test_fingerprint_changes_with_each_decision(
    advisor_client: APIClient,
    application: CreditApplication,
    make_slot: SlotFactory,
    with_version: VersionFactory,
) -> None:
    slot = make_slot(is_waivable=True)
    other = make_slot(document_type=doc_type("EMPLOYMENT_CERTIFICATE"))
    with_version(other)
    start = dossier_fingerprint(application)
    assert dossier_fingerprint(application) == start

    assert waive(advisor_client, slot).status_code == 200
    waived = dossier_fingerprint(application)
    assert reopen(advisor_client, slot).status_code == 200
    reopened = dossier_fingerprint(application)
    assert approve(advisor_client, other).status_code == 200
    approved = dossier_fingerprint(application)

    assert len({start, waived, approved}) == 3
    assert reopened != waived
    # Reabrir deja el expediente como estaba antes de exonerar.
    assert reopened == start
    # No depende de la versión de la solicitud ni de los slots retirados.
    CreditApplication.objects.filter(pk=application.pk).update(version=7)
    make_slot(document_type=doc_type("PAYROLL_SLIP"), retired_at=timezone.now())
    assert dossier_fingerprint(application) == approved
