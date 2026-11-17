"""Semilla de la radicación (Parte 1): catálogos, permisos, transiciones y días de
respuesta del FNA. Las migraciones de datos se revierten y se vuelven a aplicar."""

import importlib

import pytest
from django.apps import apps

from apps.banking.models import Bank
from apps.catalogs.models import Catalog, CatalogItem, WorkflowTransition
from apps.catalogs.workflow import FlowType, guards_for, statuses_for
from apps.identity.models import Permission
from tests.helpers import role_permissions

pytestmark = pytest.mark.django_db

seed_migration = importlib.import_module(
    "apps.filings.migrations.0002_seed_catalogs_permissions_transitions"
)
bank_days_migration = importlib.import_module(
    "apps.banking.migrations.0005_bank_filing_response_days"
)

ALL_PERMISSIONS = {"filings.read", "filings.create", "filings.update", "filings.record_response"}

# (código, origen, destino, de sistema, permiso, guarda)
EXPECTED_TRANSITIONS = {
    ("FILE", "READY_TO_FILE", "FILED", True, "filings.create", ""),
    ("BANK_RECEIVED", "FILED", "FILING_VALIDATION", True, "filings.record_response", ""),
    ("BANK_IN_ANALYSIS_FILED", "FILED", "CREDIT_ANALYSIS", True, "filings.record_response", ""),
    (
        "BANK_IN_ANALYSIS_FILING_VALIDATION",
        "FILING_VALIDATION",
        "CREDIT_ANALYSIS",
        True,
        "filings.record_response",
        "",
    ),
    ("BANK_RETURNED_FILED", "FILED", "BANK_OBSERVATION", True, "filings.record_response", ""),
    (
        "BANK_RETURNED_FILING_VALIDATION",
        "FILING_VALIDATION",
        "BANK_OBSERVATION",
        True,
        "filings.record_response",
        "",
    ),
    (
        "BANK_RETURNED_CREDIT_ANALYSIS",
        "CREDIT_ANALYSIS",
        "BANK_OBSERVATION",
        True,
        "filings.record_response",
        "",
    ),
    ("BANK_APPROVED_FILED", "FILED", "APPROVED", True, "filings.record_response", ""),
    (
        "BANK_APPROVED_FILING_VALIDATION",
        "FILING_VALIDATION",
        "APPROVED",
        True,
        "filings.record_response",
        "",
    ),
    (
        "BANK_APPROVED_CREDIT_ANALYSIS",
        "CREDIT_ANALYSIS",
        "APPROVED",
        True,
        "filings.record_response",
        "",
    ),
    ("BANK_REJECTED_FILED", "FILED", "REJECTED", True, "filings.record_response", ""),
    (
        "BANK_REJECTED_FILING_VALIDATION",
        "FILING_VALIDATION",
        "REJECTED",
        True,
        "filings.record_response",
        "",
    ),
    (
        "BANK_REJECTED_CREDIT_ANALYSIS",
        "CREDIT_ANALYSIS",
        "REJECTED",
        True,
        "filings.record_response",
        "",
    ),
    (
        "BANK_REJECTED_BANK_OBSERVATION",
        "BANK_OBSERVATION",
        "REJECTED",
        True,
        "filings.record_response",
        "",
    ),
    ("BANK_DISBURSED", "LEGALIZATION", "DISBURSED", True, "filings.record_response", ""),
    ("START_LEGALIZATION", "APPROVED", "LEGALIZATION", False, "applications.transition", ""),
    (
        "MARK_READY_TO_REFILE",
        "BANK_OBSERVATION",
        "READY_TO_FILE",
        False,
        "applications.transition",
        "APPLICATION_READY_TO_REFILE",
    ),
}
TRANSITION_CODES = {code for code, *_ in EXPECTED_TRANSITIONS}

CATALOG_ITEMS = {
    "filing_channel": [
        ("BANK_PORTAL", "Portal del banco"),
        ("EMAIL", "Correo electrónico"),
        ("IN_PERSON", "Presencial"),
    ],
    "filing_return_reason": [
        ("DOCUMENT_CORRECTION", "Corrección de documentos"),
        ("MISSING_INFORMATION", "Información incompleta"),
        ("OTHER", "Otro"),
    ],
    "filing_rejection_reason": [
        ("CREDIT_POLICY", "Políticas del banco"),
        ("PAYMENT_CAPACITY", "Capacidad de pago insuficiente"),
        ("CREDIT_HISTORY", "Historial crediticio"),
        ("PROPERTY", "El inmueble no cumple"),
        ("OTHER", "Otro"),
    ],
}
RESPONSE_TYPES = ["RECEIVED", "RETURNED", "IN_ANALYSIS", "APPROVED", "REJECTED", "OTHER"]


def filing_permissions(role_code: str) -> set[str]:
    return {code for code in role_permissions(role_code) if code.startswith("filings.")}


def seeded_transitions() -> set[tuple[str, str, str, bool, str, str]]:
    rows = WorkflowTransition.objects.filter(
        flow_type=FlowType.APPLICATION, code__in=TRANSITION_CODES
    ).select_related("required_permission")
    return {
        (
            row.code,
            row.from_status,
            row.to_status,
            row.system_only,
            row.required_permission.code if row.required_permission else "",
            row.guard_code,
        )
        for row in rows
    }


def response_type_codes() -> list[str]:
    return list(
        CatalogItem.objects.filter(catalog__code="filing_response_type")
        .order_by("sort_order")
        .values_list("code", flat=True)
    )


# --- Permisos ---------------------------------------------------------------------------


def test_permissions_by_role() -> None:
    # `filings.prepare` (el paquete) lo sembró `documents`.
    assert filing_permissions("ADMIN") == ALL_PERMISSIONS | {"filings.prepare"}
    assert filing_permissions("ADVISOR") == ALL_PERMISSIONS | {"filings.prepare"}
    assert filing_permissions("INDEPENDENT_BROKER") == {"filings.read"}
    assert filing_permissions("CONSTRUCTION_PARTNER") == set()
    modules = set(
        Permission.objects.filter(code__in=ALL_PERMISSIONS).values_list("module", flat=True)
    )
    assert modules == {"filings"}


# --- Catálogos --------------------------------------------------------------------------


def test_response_types_include_disbursed_last() -> None:
    catalog = Catalog.objects.get(code="filing_response_type")

    assert response_type_codes() == [*RESPONSE_TYPES, "DISBURSED"]
    assert catalog.items.get(code="DISBURSED").label == "Desembolsada"
    # Lo administra el backend: cada código dispara una regla.
    assert (catalog.is_manageable, catalog.is_public) == (False, False)
    assert catalog.version == 2


@pytest.mark.parametrize("code", sorted(CATALOG_ITEMS))
def test_new_catalogs_are_internal_and_manageable(code: str) -> None:
    catalog = Catalog.objects.get(code=code)

    assert (catalog.is_manageable, catalog.is_public) == (True, False)
    items = catalog.items.order_by("sort_order")
    assert list(items.values_list("code", "label")) == CATALOG_ITEMS[code]
    assert all(item.is_active for item in items)


# --- Transiciones -----------------------------------------------------------------------


def test_transitions_from_filed_onwards() -> None:
    assert seeded_transitions() == EXPECTED_TRANSITIONS


def test_transitions_are_active_with_known_statuses_guards_and_roles() -> None:
    statuses = statuses_for(FlowType.APPLICATION)
    guards = guards_for(FlowType.APPLICATION) | {""}
    rows = WorkflowTransition.objects.filter(
        flow_type=FlowType.APPLICATION, code__in=TRANSITION_CODES
    ).prefetch_related("roles")
    for row in rows:
        assert {row.from_status, row.to_status} <= statuses
        assert row.guard_code in guards
        assert row.is_active
        assert {role.code for role in row.roles.all()} == {"ADMIN", "ADVISOR"}


def test_only_filings_transitions_are_system_only() -> None:
    system = WorkflowTransition.objects.filter(system_only=True)

    assert set(system.values_list("code", flat=True)) == {
        code for code, _, _, is_system, *_ in EXPECTED_TRANSITIONS if is_system
    }


# --- Banco ------------------------------------------------------------------------------


def seeded_response_days() -> dict[str, int | None]:
    return dict(Bank.objects.values_list("code", "filing_response_days"))


def test_only_the_fna_has_response_days() -> None:
    assert seeded_response_days() == {"BANCOLOMBIA": None, "FNA": 7, "BANCO_BOGOTA": None}


def test_fna_response_days_migration_is_reversible() -> None:
    # El banco se busca por código: renombrarlo no cambia a cuál se le aplica.
    Bank.objects.filter(code="FNA").update(name="FNA renombrado")

    bank_days_migration.clear_fna_response_days(apps, None)
    assert seeded_response_days() == {"BANCOLOMBIA": None, "FNA": None, "BANCO_BOGOTA": None}

    bank_days_migration.set_fna_response_days(apps, None)
    assert seeded_response_days() == {"BANCOLOMBIA": None, "FNA": 7, "BANCO_BOGOTA": None}


# --- Ida y vuelta -----------------------------------------------------------------------


def test_unseed_reverts_and_seed_is_idempotent() -> None:
    seed_migration.unseed(apps, None)

    assert not Permission.objects.filter(code__in=ALL_PERMISSIONS).exists()
    assert not Catalog.objects.filter(code__in=CATALOG_ITEMS).exists()
    assert response_type_codes() == RESPONSE_TYPES
    assert not WorkflowTransition.objects.filter(code__in=TRANSITION_CODES).exists()
    # Lo que sembraron otros módulos sigue ahí.
    assert Permission.objects.filter(code="filings.prepare").exists()
    assert WorkflowTransition.objects.filter(code="MARK_READY_TO_FILE").exists()

    seed_migration.seed(apps, None)
    seed_migration.seed(apps, None)

    assert filing_permissions("ADVISOR") == ALL_PERMISSIONS | {"filings.prepare"}
    assert filing_permissions("INDEPENDENT_BROKER") == {"filings.read"}
    assert response_type_codes() == [*RESPONSE_TYPES, "DISBURSED"]
    for code, items in CATALOG_ITEMS.items():
        assert Catalog.objects.get(code=code).items.count() == len(items)
    assert seeded_transitions() == EXPECTED_TRANSITIONS
    # Agregar y quitar `DISBURSED` cambia la versión del catálogo; repetir la semilla, no.
    assert Catalog.objects.get(code="filing_response_type").version == 4
