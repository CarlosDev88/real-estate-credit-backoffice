"""Semilla del expediente documental: permisos, catálogos y titular de los tipos."""

import importlib

import pytest
from django.apps import apps

from apps.catalogs.models import Catalog
from apps.documents.models import DocumentType, HolderScope
from apps.identity.models import Permission
from tests.helpers import role_permissions

pytestmark = pytest.mark.django_db

seed_migration = importlib.import_module("apps.documents.migrations.0004_seed_dossier")

DOSSIER_PERMISSIONS = {
    "documents.read",
    "documents.review",
    "documents.waive",
    "documents.manage_requirements",
    "documents.download",
    "filings.prepare",
}

APPLICATION_TYPES = {
    "PROPERTY_ANALYSIS_DOCUMENTS",
    "PROPERTY_OWNERSHIP_DOCUMENT",
    "REMODELING_BUDGET",
    "TITLE_STUDY_DOCUMENTS",
    "DEED_SIGNATURE_DOCUMENTS",
    "REGISTRATION_DOCUMENTS",
    "EXTERNAL_APPROVAL_LETTER",
}


def test_admin_and_advisor_get_the_dossier_permissions() -> None:
    for role_code in ("ADMIN", "ADVISOR"):
        assert DOSSIER_PERMISSIONS <= set(role_permissions(role_code))
    for role_code in ("INDEPENDENT_BROKER", "CONSTRUCTION_PARTNER"):
        assert DOSSIER_PERMISSIONS.isdisjoint(role_permissions(role_code))
    modules = dict(
        Permission.objects.filter(code__in=DOSSIER_PERMISSIONS).values_list("code", "module")
    )
    assert modules["filings.prepare"] == "filings"
    assert {modules[code] for code in DOSSIER_PERMISSIONS - {"filings.prepare"}} == {"documents"}


def test_rejection_reasons_are_public_and_waiver_reasons_internal() -> None:
    rejection = Catalog.objects.get(code="document_rejection_reason")
    waiver = Catalog.objects.get(code="document_waiver_reason")

    assert (rejection.is_public, rejection.is_manageable) == (True, True)
    assert (waiver.is_public, waiver.is_manageable) == (False, True)
    assert list(rejection.items.values_list("code", flat=True)) == [
        "ILLEGIBLE",
        "INCOMPLETE",
        "OUTDATED",
        "WRONG_DOCUMENT",
        "DATA_MISMATCH",
        "OTHER",
    ]
    assert list(waiver.items.values_list("code", flat=True)) == [
        "NOT_APPLICABLE",
        "BANK_EXEMPTED",
        "REPLACED_BY_OTHER_SUPPORT",
        "OTHER",
    ]


def test_property_legalization_and_external_letter_belong_to_the_application() -> None:
    scopes = dict(DocumentType.objects.values_list("code", "holder_scope"))
    assert {code for code, scope in scopes.items() if scope == HolderScope.APPLICATION} == (
        APPLICATION_TYPES
    )
    assert scopes["IDENTITY_DOCUMENT"] == HolderScope.PARTICIPANT


def test_unseed_reverts_and_seed_is_idempotent() -> None:
    seed_migration.unseed(apps, None)
    assert not Permission.objects.filter(code__in=DOSSIER_PERMISSIONS).exists()
    assert not Catalog.objects.filter(
        code__in=["document_rejection_reason", "document_waiver_reason"]
    ).exists()
    assert not DocumentType.objects.filter(holder_scope=HolderScope.APPLICATION).exists()

    seed_migration.seed(apps, None)
    seed_migration.seed(apps, None)
    assert Permission.objects.filter(code__in=DOSSIER_PERMISSIONS).count() == 6
    assert DocumentType.objects.filter(holder_scope=HolderScope.APPLICATION).count() == 7
    assert DOSSIER_PERMISSIONS <= set(role_permissions("ADVISOR"))
