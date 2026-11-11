"""Cumplimiento del expediente (decisiones 7, 21 y 24; acordadas 7 y 8; Tanda 4,
decisiones 30 a 34)."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.applications.models import ApplicationParticipant, CreditApplication
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentFileStatus,
    DocumentType,
    FileObject,
    ScanStatus,
    SlotStatus,
)
from apps.documents.verification import NOT_CONFIGURED_MESSAGE, check_dossier
from tests.applications.conftest import catalog_item
from tests.applications.dossier.conftest import DocumentFileFactory, SlotFactory

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate


def doc_type(code: str) -> DocumentType:
    return DocumentType.objects.get(code=code)


@pytest.fixture
def decide(
    make_document_file: DocumentFileFactory, make_file_object: Callable[..., FileObject]
) -> Callable[..., ApplicationDocumentSlot]:
    """Deja el slot en ``status`` con una versión vigente (si corresponde)."""

    def _decide(
        slot: ApplicationDocumentSlot, status: str, *, expires_at: date | None = None
    ) -> ApplicationDocumentSlot:
        extra: dict[str, Any] = {"status": status}
        if status == SlotStatus.WAIVED:
            extra["waiver_reason_item"] = catalog_item("document_waiver_reason", "OTHER")
            ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(is_waivable=True)
        else:
            file_status = {
                SlotStatus.APPROVED: DocumentFileStatus.APPROVED,
                SlotStatus.REJECTED: DocumentFileStatus.REJECTED,
            }.get(SlotStatus(status), DocumentFileStatus.IN_REVIEW)
            document_date = None if expires_at is None else expires_at - timedelta(days=30)
            extra["current_file"] = make_document_file(
                slot=slot,
                file_object=make_file_object(
                    scan_status=ScanStatus.CLEAN, scanned_at=timezone.now()
                ),
                status=file_status,
                document_date=document_date,
                expires_at=expires_at,
            )
        ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(**extra)
        slot.refresh_from_db()
        return slot

    return _decide


def codes(application: CreditApplication) -> list[tuple[str, str]]:
    return [(p["code"], p["resource_id"]) for p in check_dossier(application).problems]


# --- Slots sueltos ----------------------------------------------------------------------


def test_without_required_slots_the_dossier_is_not_configured(
    application: CreditApplication, make_slot: SlotFactory
) -> None:
    make_slot(is_required=False)
    make_slot(document_type=doc_type("PAYROLL_SLIP"), retired_at=timezone.now())

    result = check_dossier(application)

    assert (result.required_total, result.completed_total, result.percentage) == (0, 0, 0)
    assert result.verified is False
    assert result.slots == []
    assert result.message == NOT_CONFIGURED_MESSAGE
    assert result.problems == [
        {
            "field": "documents",
            "code": "DOCUMENTS_NOT_CONFIGURED",
            "message": NOT_CONFIGURED_MESSAGE,
        }
    ]


def test_approved_and_waived_count_as_fulfilled(
    application: CreditApplication,
    primary: ApplicationParticipant,
    make_slot: SlotFactory,
    decide: Callable[..., ApplicationDocumentSlot],
) -> None:
    approved = decide(make_slot(), SlotStatus.APPROVED)
    waived = decide(make_slot(document_type=doc_type("EMPLOYMENT_CERTIFICATE")), SlotStatus.WAIVED)
    pending = make_slot(document_type=doc_type("PAYROLL_SLIP"), minimum_files=2)
    uploaded = decide(
        make_slot(document_type=doc_type("PAYROLL_SLIP"), minimum_files=2, slot_index=2),
        SlotStatus.UPLOADED,
    )
    rejected = decide(make_slot(document_type=doc_type("BANK_STATEMENT")), SlotStatus.REJECTED)
    # Opcionales y retirados no cuentan.
    decide(make_slot(document_type=doc_type("PENSION_CERTIFICATE"), is_required=False), "PENDING")
    make_slot(document_type=doc_type("PENSION_PAYMENT_SLIP"), retired_at=timezone.now())

    result = check_dossier(application)

    assert (result.required_total, result.completed_total, result.percentage) == (5, 2, 40)
    assert result.message == "Faltan 3 de 5 documentos obligatorios."
    # Orden de presentación: `sort_order` y después el código del tipo.
    assert [check.slot_id for check in result.slots if check.complete] == [waived.pk, approved.pk]
    name = primary.client.full_name
    assert result.problems == [
        {
            "field": "documents",
            "code": "DOCUMENT_PENDING",
            "message": f"«{rejected.document_type.name}» de {name} no está aprobado ni exonerado.",
            "resource_id": str(rejected.pk),
        }
    ] + [
        {
            "field": "documents",
            "code": "DOCUMENT_PENDING",
            "message": f"«{slot.document_type.name} {n} de 2» de {name} no está aprobado ni "
            "exonerado.",
            "resource_id": str(slot.pk),
        }
        for n, slot in ((1, pending), (2, uploaded))
    ]


def test_everything_fulfilled_is_verified(
    application: CreditApplication,
    make_slot: SlotFactory,
    decide: Callable[..., ApplicationDocumentSlot],
) -> None:
    decide(make_slot(), SlotStatus.APPROVED, expires_at=TODAY() + timedelta(days=1))

    result = check_dossier(application)

    assert result.verified is True
    assert result.percentage == 100
    assert result.message == "Los documentos obligatorios están completos."


@pytest.mark.parametrize("days", [0, -3])
def test_a_loose_expired_slot_gives_only_document_expired(
    application: CreditApplication,
    primary: ApplicationParticipant,
    make_slot: SlotFactory,
    decide: Callable[..., ApplicationDocumentSlot],
    days: int,
) -> None:
    # Vence el día de `expires_at`: ese día ya no cuenta (decisión 34).
    expires_at = TODAY() + timedelta(days=days)
    slot = decide(make_slot(validity_days=30), SlotStatus.APPROVED, expires_at=expires_at)

    result = check_dossier(application)

    assert result.completed_total == 0
    assert result.problems == [
        {
            "field": "documents",
            "code": "DOCUMENT_EXPIRED",
            "message": (
                f"«Copia del documento de identidad» de {primary.client.full_name} venció el "
                f"{expires_at.isoformat()}: pide uno más reciente."
            ),
            "resource_id": str(slot.pk),
        }
    ]
    assert result.slots[0].expires_at == expires_at


def test_slots_of_the_application_come_first(
    application: CreditApplication,
    make_slot: SlotFactory,
) -> None:
    holder_slot = make_slot()
    application_slot = make_slot(
        document_type=doc_type("PROPERTY_OWNERSHIP_DOCUMENT"), participant=None, sort_order=99
    )

    result = check_dossier(application)

    assert [check.slot_id for check in result.slots] == [application_slot.pk, holder_slot.pk]
    assert result.slots[0].participant_id is None
    assert "de la solicitud" in result.problems[0]["message"]


# --- Grupos alternativos ------------------------------------------------------------------


@pytest.fixture
def income_group(make_slot: SlotFactory) -> dict[str, list[ApplicationDocumentSlot]]:
    """Grupo ``INCOME`` del titular: 3 desprendibles o 3 extractos."""
    return {
        code: [
            make_slot(
                document_type=doc_type(code),
                minimum_files=3,
                slot_index=index,
                alternative_group_code="INCOME",
            )
            for index in (1, 2, 3)
        ]
        for code in ("PAYROLL_SLIP", "BANK_STATEMENT")
    }


def test_two_payroll_slips_and_a_bank_statement_do_not_fulfil_the_group(
    application: CreditApplication,
    primary: ApplicationParticipant,
    income_group: dict[str, list[ApplicationDocumentSlot]],
    decide: Callable[..., ApplicationDocumentSlot],
) -> None:
    payroll, statements = income_group["PAYROLL_SLIP"], income_group["BANK_STATEMENT"]
    decide(payroll[0], SlotStatus.APPROVED)
    decide(payroll[1], SlotStatus.APPROVED)
    decide(statements[0], SlotStatus.APPROVED)

    result = check_dossier(application)

    # Un grupo cuenta como un solo obligatorio.
    assert (result.required_total, result.completed_total) == (1, 0)
    assert not any(check.complete for check in result.slots)
    (problem,) = result.problems
    assert problem == {
        "field": "documents",
        "code": "DOCUMENT_PENDING",
        "message": (
            f"Falta un juego completo del grupo INCOME de {primary.client.full_name}: "
            "Extracto bancario o Desprendible o comprobante de nómina."
        ),
        "resource_id": str(statements[0].pk),
    }


def test_a_complete_set_fulfils_the_group(
    application: CreditApplication,
    income_group: dict[str, list[ApplicationDocumentSlot]],
    decide: Callable[..., ApplicationDocumentSlot],
) -> None:
    for slot in income_group["PAYROLL_SLIP"][:2]:
        decide(slot, SlotStatus.APPROVED)
    decide(income_group["PAYROLL_SLIP"][2], SlotStatus.WAIVED)

    result = check_dossier(application)

    assert (result.required_total, result.completed_total) == (1, 1)
    assert result.verified is True
    # Los extractos pendientes cuentan como cumplidos: el grupo lo está.
    assert all(check.complete for check in result.slots)
    assert [check.label for check in result.slots][3:5] == [
        "Desprendible o comprobante de nómina 1 de 3",
        "Desprendible o comprobante de nómina 2 de 3",
    ]


def test_a_fully_waived_group_is_fulfilled(
    application: CreditApplication,
    income_group: dict[str, list[ApplicationDocumentSlot]],
    decide: Callable[..., ApplicationDocumentSlot],
) -> None:
    for slots in income_group.values():
        for slot in slots:
            decide(slot, SlotStatus.WAIVED)

    assert check_dossier(application).verified is True


def test_an_unfulfilled_group_with_an_expired_slot_gives_pending_and_expired(
    application: CreditApplication,
    income_group: dict[str, list[ApplicationDocumentSlot]],
    decide: Callable[..., ApplicationDocumentSlot],
) -> None:
    payroll = income_group["PAYROLL_SLIP"]
    decide(payroll[0], SlotStatus.APPROVED, expires_at=TODAY() - timedelta(days=1))
    decide(payroll[1], SlotStatus.APPROVED)
    decide(payroll[2], SlotStatus.APPROVED)

    assert codes(application) == [
        ("DOCUMENT_PENDING", str(income_group["BANK_STATEMENT"][0].pk)),
        ("DOCUMENT_EXPIRED", str(payroll[0].pk)),
    ]


def test_a_fulfilled_group_ignores_an_expired_slot_of_the_other_set(
    application: CreditApplication,
    income_group: dict[str, list[ApplicationDocumentSlot]],
    decide: Callable[..., ApplicationDocumentSlot],
) -> None:
    for slot in income_group["PAYROLL_SLIP"]:
        decide(slot, SlotStatus.APPROVED)
    decide(income_group["BANK_STATEMENT"][0], SlotStatus.APPROVED, expires_at=TODAY())

    assert check_dossier(application).problems == []


def test_groups_are_per_holder(
    application: CreditApplication,
    make_slot: SlotFactory,
    decide: Callable[..., ApplicationDocumentSlot],
) -> None:
    holder = decide(make_slot(alternative_group_code="G"), SlotStatus.APPROVED)
    make_slot(
        document_type=doc_type("PROPERTY_OWNERSHIP_DOCUMENT"),
        participant=None,
        alternative_group_code="G",
    )

    result = check_dossier(application)

    assert (result.required_total, result.completed_total) == (2, 1)
    assert [check.complete for check in result.slots] == [False, True]
    assert result.slots[1].slot_id == holder.pk


def test_check_dossier_can_lock_the_slots(
    application: CreditApplication, make_slot: SlotFactory, django_assert_num_queries: Any
) -> None:
    make_slot()

    with django_assert_num_queries(1) as captured:
        check_dossier(application, lock=True)

    assert "FOR UPDATE OF" in captured.captured_queries[0]["sql"]


def test_unused_versions_do_not_count(
    application: CreditApplication,
    make_slot: SlotFactory,
    make_document_file: DocumentFileFactory,
) -> None:
    # Una versión aprobada que ya no es la vigente no cumple el slot.
    slot = make_slot()
    make_document_file(slot=slot, status=DocumentFileStatus.APPROVED)

    assert check_dossier(application).completed_total == 0
    assert DocumentFile.objects.filter(slot=slot).count() == 1


# --- Progreso del comprador (decisión 35) -------------------------------------------------


def test_buyer_progress_counts_documents_without_internal_fields(
    portal: Any,
    application: CreditApplication,
    make_slot: SlotFactory,
    decide: Callable[..., ApplicationDocumentSlot],
) -> None:
    decide(make_slot(), SlotStatus.APPROVED)
    pending = make_slot(document_type=doc_type("EMPLOYMENT_CERTIFICATE"))

    response = portal.get(f"/api/v1/buyer/applications/{application.id}")

    assert response.status_code == 200, response.content
    progress = response.json()["progress"]
    assert set(progress) == {
        "percentage",
        "data_percentage",
        "documents_percentage",
        "documents_required_total",
        "documents_completed_total",
        "items",
    }
    assert (progress["documents_required_total"], progress["documents_completed_total"]) == (2, 1)
    assert progress["documents_percentage"] == 50
    assert progress["percentage"] == (progress["data_percentage"] + 50) // 2
    assert "bank_evaluation" not in {item["code"] for item in progress["items"]}
    text = response.content.decode()
    for internal in (
        "ready_to_file",
        "DOCUMENT_PENDING",
        "no está aprobado",
        "documentos obligatorios",
        str(pending.pk),
    ):
        assert internal not in text
