"""Restricciones de PostgreSQL del expediente documental (DER §8 y sus desvíos)."""

import importlib
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.applications.models import ApplicationParticipant, CreditApplication
from apps.catalogs.models import CatalogItem
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentFileStatus,
    DocumentPackageJob,
    DocumentReview,
    DocumentType,
    FileObject,
    HolderScope,
    PackageJobStatus,
    ReviewDecision,
    ScanStatus,
    SlotStatus,
)
from apps.identity.models import User
from tests.applications.dossier.conftest import (
    DocumentFileFactory,
    FileObjectFactory,
    SlotFactory,
)

pytestmark = pytest.mark.django_db

review_migration = importlib.import_module("apps.documents.migrations.0005_review_slot_and_waivers")


def assert_violates(constraint: str, create: Callable[[], Any]) -> None:
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        create()
    assert constraint in str(error.value)


def catalog_item(catalog_code: str, code: str) -> CatalogItem:
    return CatalogItem.objects.get(catalog__code=catalog_code, code=code)


# --- document_types.holder_scope ---------------------------------------------------------


def test_holder_scope_defaults_to_participant_and_is_checked() -> None:
    document_type = DocumentType.objects.create(
        code="TEST_TYPE", name="Prueba", allowed_mime_types=["application/pdf"], max_size_bytes=1
    )
    assert document_type.holder_scope == HolderScope.PARTICIPANT

    assert_violates(
        "ck_document_types_holder_scope",
        lambda: DocumentType.objects.filter(pk=document_type.pk).update(holder_scope="BANK"),
    )


# --- file_objects -----------------------------------------------------------------------


def test_file_object_storage_key_is_unique(make_file_object: FileObjectFactory) -> None:
    existing = make_file_object()
    assert existing.scan_status == ScanStatus.PENDING
    assert existing.is_clean is False

    assert_violates(
        "uq_file_objects_storage_key",
        lambda: make_file_object(bucket_name=existing.bucket_name, object_key=existing.object_key),
    )
    # La misma clave en otro bucket es otro objeto.
    make_file_object(bucket_name="otro-bucket", object_key=existing.object_key)


def test_file_object_scan_date_goes_with_the_result(make_file_object: FileObjectFactory) -> None:
    assert_violates(
        "ck_file_objects_scan_date", lambda: make_file_object(scanned_at=timezone.now())
    )
    assert_violates(
        "ck_file_objects_scan_date", lambda: make_file_object(scan_status=ScanStatus.CLEAN)
    )
    clean = make_file_object(scan_status=ScanStatus.CLEAN, scanned_at=timezone.now())
    assert clean.is_clean is True


def test_file_object_rejects_unknown_status_and_negative_size(
    make_file_object: FileObjectFactory,
) -> None:
    assert_violates(
        "ck_file_objects_scan_status",
        lambda: make_file_object(scan_status="QUARANTINED", scanned_at=timezone.now()),
    )
    assert_violates("ck_file_objects_size_bytes", lambda: make_file_object(size_bytes=-1))


# --- application_document_slots ---------------------------------------------------------


def test_slot_defaults(make_slot: SlotFactory) -> None:
    slot = make_slot()
    assert slot.status == SlotStatus.PENDING
    assert (slot.slot_index, slot.minimum_files) == (1, 1)
    assert slot.current_file is None
    assert slot.is_retired is False


def test_slot_index_goes_from_one_to_minimum_files(make_slot: SlotFactory) -> None:
    payroll = DocumentType.objects.get(code="PAYROLL_SLIP")
    for index in (1, 2, 3):
        make_slot(document_type=payroll, minimum_files=3, slot_index=index)

    assert_violates(
        "ck_document_slots_index",
        lambda: make_slot(document_type=payroll, minimum_files=3, slot_index=4),
    )
    assert_violates(
        "ck_document_slots_index",
        lambda: make_slot(document_type=payroll, minimum_files=3, slot_index=0),
    )


def test_only_one_live_slot_per_holder_type_and_index(make_slot: SlotFactory) -> None:
    slot = make_slot()
    assert_violates("uq_document_slots_active", lambda: make_slot())

    # Un slot retirado no cuenta: el requisito puede volver a crear el suyo.
    slot.retired_at = timezone.now()
    slot.save(update_fields=["retired_at"])
    revived = make_slot()
    assert revived.pk != slot.pk


def test_application_documents_have_no_participant_and_are_also_unique(
    make_slot: SlotFactory,
) -> None:
    budget = DocumentType.objects.get(code="REMODELING_BUDGET")
    make_slot(document_type=budget, participant=None)

    # NULLS NOT DISTINCT: el participante vacío es un valor más.
    assert_violates(
        "uq_document_slots_active", lambda: make_slot(document_type=budget, participant=None)
    )


def test_same_type_for_another_participant_is_another_slot(
    make_slot: SlotFactory, application: CreditApplication, make_client: Callable[..., Any]
) -> None:
    co_applicant = ApplicationParticipant.objects.create(
        application=application, client=make_client(document_number="80123456"), role="CO_APPLICANT"
    )
    make_slot()
    make_slot(participant=co_applicant)
    assert application.document_slots.count() == 2


def test_waived_slot_needs_a_waivable_snapshot_and_a_reason(make_slot: SlotFactory) -> None:
    reason = catalog_item("document_waiver_reason", "NOT_APPLICABLE")
    assert_violates(
        "ck_document_slots_waiver",
        lambda: make_slot(status=SlotStatus.WAIVED, waiver_reason_item=reason),
    )
    assert_violates(
        "ck_document_slots_waiver",
        lambda: make_slot(status=SlotStatus.WAIVED, is_waivable=True),
    )
    waived = make_slot(status=SlotStatus.WAIVED, is_waivable=True, waiver_reason_item=reason)
    assert waived.status == SlotStatus.WAIVED


@pytest.mark.parametrize(
    ("constraint", "values"),
    [
        ("ck_document_slots_status", {"status": "MISSING"}),
        ("ck_document_slots_req_version", {"requirement_version": 0}),
        ("ck_document_slots_validity_days", {"validity_days": 0}),
    ],
)
def test_slot_snapshot_checks(
    make_slot: SlotFactory, constraint: str, values: dict[str, Any]
) -> None:
    assert_violates(constraint, lambda: make_slot(**values))


def test_current_file_is_deferred_until_commit(
    make_slot: SlotFactory, make_document_file: DocumentFileFactory
) -> None:
    slot = make_slot()
    with transaction.atomic():
        # La FK se comprueba al confirmar: el slot puede apuntar antes a su versión.
        version = make_document_file(slot=slot)
        slot.current_file = version
        slot.status = SlotStatus.UPLOADED
        slot.save(update_fields=["current_file", "status"])

    slot.refresh_from_db()
    assert slot.current_file == version
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT condeferrable, condeferred FROM pg_constraint "
            "WHERE conrelid = 'application_document_slots'::regclass AND contype = 'f' "
            "AND conkey = ARRAY[(SELECT attnum FROM pg_attribute WHERE attname = "
            "'current_file_id' AND attrelid = 'application_document_slots'::regclass)]"
        )
        assert cursor.fetchone() == (True, True)


# --- document_files ---------------------------------------------------------------------


def test_version_number_is_unique_within_the_slot(
    make_slot: SlotFactory, make_document_file: DocumentFileFactory
) -> None:
    slot = make_slot()
    first = make_document_file(slot=slot)
    assert first.status == DocumentFileStatus.UPLOADED
    make_document_file(slot=slot, version_number=2)

    assert_violates("uq_document_files_slot_version", lambda: make_document_file(slot=slot))
    # Otro slot empieza su propia numeración.
    other_slot = make_slot(document_type=DocumentType.objects.get(code="INCOME_TAX_RETURN"))
    assert make_document_file(slot=other_slot).version_number == 1


def test_a_file_object_backs_a_single_version(
    make_document_file: DocumentFileFactory, make_slot: SlotFactory
) -> None:
    version = make_document_file()
    other_slot = make_slot(document_type=DocumentType.objects.get(code="INCOME_TAX_RETURN"))
    assert_violates(
        "document_files_file_object_id",
        lambda: make_document_file(slot=other_slot, file_object=version.file_object),
    )


def test_document_file_checks(make_document_file: DocumentFileFactory) -> None:
    assert_violates("ck_document_files_version", lambda: make_document_file(version_number=0))
    assert_violates("ck_document_files_status", lambda: make_document_file(status="PENDING"))


def test_expiry_comes_after_the_document_date(make_document_file: DocumentFileFactory) -> None:
    issued = date(2026, 10, 1)
    assert_violates(
        "ck_document_files_expiry", lambda: make_document_file(expires_at=date(2026, 10, 31))
    )
    assert_violates(
        "ck_document_files_expiry",
        lambda: make_document_file(document_date=issued, expires_at=issued),
    )
    version = make_document_file(document_date=issued, expires_at=issued + timedelta(days=30))
    assert version.expires_at == date(2026, 10, 31)


# --- document_reviews -------------------------------------------------------------------


def test_rejection_needs_a_reason_and_a_buyer_comment(
    make_document_file: DocumentFileFactory, advisor_user: User
) -> None:
    version = make_document_file()
    reason = catalog_item("document_rejection_reason", "ILLEGIBLE")

    def review(**extra: Any) -> DocumentReview:
        return DocumentReview.objects.create(
            slot=version.slot, document_file=version, reviewer=advisor_user, **extra
        )

    assert_violates(
        "ck_document_reviews_rejection",
        lambda: review(decision=ReviewDecision.REJECTED, buyer_comment="No se lee."),
    )
    assert_violates(
        "ck_document_reviews_rejection",
        lambda: review(decision=ReviewDecision.REJECTED, reason_item=reason),
    )
    assert_violates("ck_document_reviews_decision", lambda: review(decision="PENDING"))

    review(decision=ReviewDecision.APPROVED)
    review(
        decision=ReviewDecision.REJECTED,
        reason_item=reason,
        buyer_comment="La foto está borrosa.",
        internal_comment="Corrige la decisión anterior.",
    )
    # Corregir una decisión crea otra fila; la más reciente va primero.
    assert [item.decision for item in version.reviews.all()] == [
        ReviewDecision.REJECTED,
        ReviewDecision.APPROVED,
    ]


# --- document_package_jobs --------------------------------------------------------------


def test_package_job_defaults_and_checks(
    application: CreditApplication, advisor_user: User, make_file_object: FileObjectFactory
) -> None:
    def job(**extra: Any) -> DocumentPackageJob:
        extra.setdefault("application_version", application.version)
        return DocumentPackageJob.objects.create(
            application=application, requested_by=advisor_user, **extra
        )

    pending = job(manifest={"fingerprint": "abc", "files": []})
    assert pending.status == PackageJobStatus.PENDING

    now = timezone.now()
    assert_violates("ck_document_package_jobs_version", lambda: job(application_version=0))
    assert_violates("ck_document_package_jobs_status", lambda: job(status="QUEUED"))
    assert_violates("ck_document_package_jobs_dates", lambda: job(completed_at=now))
    assert_violates(
        "ck_document_package_jobs_dates",
        lambda: job(started_at=now, completed_at=now - timedelta(seconds=1)),
    )
    assert_violates(
        "ck_document_package_jobs_dates",
        lambda: job(started_at=now, completed_at=now, expires_at=now - timedelta(seconds=1)),
    )

    output = make_file_object(
        original_filename="SOL-0001.zip", detected_mime_type="application/zip"
    )
    done = job(
        status=PackageJobStatus.COMPLETED,
        output_file_object=output,
        started_at=now,
        completed_at=now,
        expires_at=now + timedelta(days=7),
    )
    assert output.package_job == done
    assert_violates(
        "document_package_jobs_output_file_object_id",
        lambda: job(output_file_object=output),
    )


def test_str_representations(
    make_document_file: DocumentFileFactory,
    advisor_user: User,
    application: CreditApplication,
) -> None:
    version = make_document_file()
    review = DocumentReview.objects.create(
        slot=version.slot,
        document_file=version,
        reviewer=advisor_user,
        decision=ReviewDecision.APPROVED,
    )
    job = DocumentPackageJob.objects.create(
        application=application, requested_by=advisor_user, application_version=1
    )
    assert str(version.file_object) == "documento.pdf (PENDING)"
    assert str(version.slot).endswith("#1 (PENDING)")
    assert str(version) == "cedula.pdf v1 (UPLOADED)"
    assert str(review).endswith(": APPROVED")
    assert str(job).endswith("(PENDING)")
    assert isinstance(ApplicationDocumentSlot.objects.first(), ApplicationDocumentSlot)
    assert FileObject.objects.count() == DocumentFile.objects.count() == 1


# --- document_reviews: exoneraciones y reaperturas (Parte 5) -----------------------------


def test_slot_decisions_need_a_batch_and_file_decisions_a_file(
    make_slot: SlotFactory, make_document_file: DocumentFileFactory, advisor_user: User
) -> None:
    slot = make_slot(is_waivable=True)
    version = make_document_file(slot=slot)
    reason = catalog_item("document_waiver_reason", "OTHER")

    def review(**extra: Any) -> DocumentReview:
        return DocumentReview.objects.create(slot=slot, reviewer=advisor_user, **extra)

    assert_violates("ck_document_reviews_file", lambda: review(decision=ReviewDecision.APPROVED))
    assert_violates(
        "ck_document_reviews_file",
        lambda: review(
            decision=ReviewDecision.APPROVED, document_file=version, decision_batch_id=uuid.uuid4()
        ),
    )
    assert_violates(
        "ck_document_reviews_batch",
        lambda: review(decision=ReviewDecision.WAIVED, reason_item=reason),
    )
    assert_violates(
        "ck_document_reviews_waiver",
        lambda: review(decision=ReviewDecision.WAIVED, decision_batch_id=uuid.uuid4()),
    )

    def reopening(comment: str | None) -> Callable[[], DocumentReview]:
        return lambda: review(
            decision=ReviewDecision.REOPENED,
            decision_batch_id=uuid.uuid4(),
            internal_comment=comment,
        )

    assert_violates("ck_document_reviews_reopen", reopening(None))
    assert_violates("ck_document_reviews_reopen", reopening(""))
    assert_violates(
        "ck_document_reviews_decision",
        lambda: review(decision="PENDING", document_file=version),
    )

    waived = review(
        decision=ReviewDecision.WAIVED, reason_item=reason, decision_batch_id=uuid.uuid4()
    )
    reopened = review(
        decision=ReviewDecision.REOPENED, decision_batch_id=uuid.uuid4(), internal_comment="Error."
    )
    assert waived.document_file_id is None
    assert str(reopened).endswith(": REOPENED")


def test_reverting_the_migration_drops_waivers_and_reopenings(
    make_slot: SlotFactory, make_document_file: DocumentFileFactory, advisor_user: User
) -> None:
    slot = make_slot(is_waivable=True)
    approval = DocumentReview.objects.create(
        slot=slot,
        document_file=make_document_file(slot=slot),
        reviewer=advisor_user,
        decision=ReviewDecision.APPROVED,
    )
    DocumentReview.objects.create(
        slot=slot,
        reviewer=advisor_user,
        decision=ReviewDecision.WAIVED,
        reason_item=catalog_item("document_waiver_reason", "OTHER"),
        decision_batch_id=uuid.uuid4(),
    )

    review_migration.drop_slot_decisions(apps, connection.schema_editor())
    # Las revisiones ya tienen slot: llenarlo otra vez no cambia nada.
    review_migration.fill_review_slots(apps, connection.schema_editor())

    assert list(DocumentReview.objects.values_list("pk", "slot_id")) == [(approval.pk, slot.pk)]
