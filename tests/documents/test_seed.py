from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from apps.documents.constants import ALLOWED_MIME_TYPES, MAX_FILE_SIZE_BYTES
from apps.documents.models import DocumentRequirement, DocumentType
from tests.helpers import role_permissions

pytestmark = pytest.mark.django_db

READ = {"document_requirements.read"}
WRITE = {
    "document_requirements.create",
    "document_requirements.update",
    "document_requirements.publish",
}

# Catálogo documental inicial (sección 7.1 de los requerimientos).
SEEDED_TYPES = {
    "IDENTITY_DOCUMENT",
    "INCOME_RETENTION_CERTIFICATE",
    "INCOME_TAX_RETURN",
    "EMPLOYMENT_CERTIFICATE",
    "PAYROLL_SLIP",
    "BANK_STATEMENT",
    "INDEPENDENT_INCOME_SUPPORT",
    "PENSION_CERTIFICATE",
    "PENSION_PAYMENT_SLIP",
    "CO_APPLICANT_INCOME_SUPPORT",
    "EXTERNAL_APPROVAL_LETTER",
    "PROPERTY_ANALYSIS_DOCUMENTS",
    "TITLE_STUDY_DOCUMENTS",
    "DEED_SIGNATURE_DOCUMENTS",
    "REGISTRATION_DOCUMENTS",
    "PROPERTY_OWNERSHIP_DOCUMENT",
    "REMODELING_BUDGET",
}


def test_seventeen_document_types_from_the_initial_catalog() -> None:
    types = list(DocumentType.objects.all())

    assert len(types) == 17
    assert {item.code for item in types} == SEEDED_TYPES
    for item in types:
        assert item.is_active
        assert item.allowed_mime_types == list(ALLOWED_MIME_TYPES)
        assert item.max_size_bytes == MAX_FILE_SIZE_BYTES
        assert item.default_validity_days is None


def test_income_tax_proof_is_a_group_not_a_type() -> None:
    assert not DocumentType.objects.filter(code="INCOME_TAX_PROOF").exists()


def test_only_periodic_types_are_repeatable() -> None:
    repeatable = set(DocumentType.objects.filter(is_repeatable=True).values_list("code", flat=True))
    assert repeatable == {"PAYROLL_SLIP", "BANK_STATEMENT", "PENSION_PAYMENT_SLIP"}


def test_bancolombia_checklist_is_seeded_as_active_v1() -> None:
    rows = DocumentRequirement.objects.select_related(
        "bank_product__bank", "document_type", "employment_profile_item"
    ).order_by("sort_order")

    assert [
        (
            row.document_type.code,
            row.employment_profile_item.code if row.employment_profile_item else None,
            row.minimum_files,
            row.alternative_group_code,
            row.validity_days,
            row.is_waivable,
        )
        for row in rows
    ] == [
        ("IDENTITY_DOCUMENT", None, 1, None, None, False),
        ("INCOME_RETENTION_CERTIFICATE", None, 1, "INCOME_TAX_PROOF", None, True),
        ("INCOME_TAX_RETURN", None, 1, "INCOME_TAX_PROOF", None, True),
        ("EMPLOYMENT_CERTIFICATE", "EMPLOYEE", 1, None, 30, False),
        ("PAYROLL_SLIP", "EMPLOYEE", 3, None, None, False),
        ("BANK_STATEMENT", "INDEPENDENT", 3, None, None, False),
        ("INDEPENDENT_INCOME_SUPPORT", "INDEPENDENT", 1, None, None, False),
        ("PENSION_CERTIFICATE", "PENSIONER", 1, None, None, False),
        ("PENSION_PAYMENT_SLIP", "PENSIONER", 3, None, None, False),
    ]
    for row in rows:
        assert row.bank_product is not None
        assert (row.bank_product.bank.code, row.bank_product.code) == ("BANCOLOMBIA", "MORTGAGE")
        assert (row.version, row.status, row.is_required) == (1, "ACTIVE", True)
        assert row.purpose_item_id is None
        assert row.participant_role is None
        assert row.property_condition_item_id is None
        assert row.valid_from == datetime(2026, 1, 1, tzinfo=ZoneInfo("America/Bogota"))
        assert row.valid_to is None


def test_fna_and_banco_bogota_have_no_requirements_yet() -> None:
    assert not DocumentRequirement.objects.filter(
        bank_product__bank__code__in=["FNA", "BANCO_BOGOTA"]
    ).exists()
    assert not DocumentRequirement.objects.filter(bank_product__isnull=True).exists()


@pytest.mark.parametrize(
    ("role_code", "expected"),
    [
        ("ADMIN", READ | WRITE),
        ("ADVISOR", READ),
        ("INDEPENDENT_BROKER", set()),
        ("CONSTRUCTION_PARTNER", set()),
    ],
)
def test_document_permissions_by_role(role_code: str, expected: set[str]) -> None:
    granted = {
        code for code in role_permissions(role_code) if code.startswith("document_requirements.")
    }
    assert granted == expected
