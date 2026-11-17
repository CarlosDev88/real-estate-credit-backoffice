"""Semilla del módulo applications: permisos, catálogos y transiciones."""

import importlib

import pytest
from django.db.models import QuerySet

from apps.catalogs.models import Catalog, WorkflowTransition
from apps.catalogs.workflow import (
    ApplicationStatus,
    FlowType,
    OpportunityStatus,
    guards_for,
    statuses_for,
)
from tests.helpers import role_permissions

pytestmark = pytest.mark.django_db

ALL_PERMISSIONS = {
    "applications.read",
    "applications.read_summary",
    "applications.read_history",
    "applications.create",
    "applications.update",
    "applications.transition",
    "applications.assign",
    "applications.withdraw",
}
PRE_FILING = {
    ApplicationStatus.DRAFT,
    ApplicationStatus.WAITING_BUYER_DATA,
    ApplicationStatus.WAITING_DOCUMENTS,
    ApplicationStatus.DOCUMENTS_REVIEW,
    ApplicationStatus.READY_TO_FILE,
}
NON_TERMINAL = PRE_FILING | {
    ApplicationStatus.FILED,
    ApplicationStatus.FILING_VALIDATION,
    ApplicationStatus.CREDIT_ANALYSIS,
    ApplicationStatus.BANK_OBSERVATION,
    ApplicationStatus.APPROVED,
    ApplicationStatus.LEGALIZATION,
}


def application_permissions(role_code: str) -> set[str]:
    return {code for code in role_permissions(role_code) if code.startswith("applications.")}


# Las transiciones de `FILED` en adelante las siembra `filings` (tests/filings/test_seed.py).
FILINGS_CODES = [
    code
    for code, *_ in importlib.import_module(
        "apps.filings.migrations.0002_seed_catalogs_permissions_transitions"
    ).TRANSITIONS
]


def own_transitions(flow_type: str) -> QuerySet[WorkflowTransition]:
    return WorkflowTransition.objects.filter(flow_type=flow_type).exclude(code__in=FILINGS_CODES)


def edges(flow_type: str) -> set[tuple[str, str]]:
    return set(own_transitions(flow_type).values_list("from_status", "to_status"))


# --- Permisos ---------------------------------------------------------------------------


def test_admin_and_advisor_manage_applications() -> None:
    assert application_permissions("ADMIN") == ALL_PERMISSIONS
    assert application_permissions("ADVISOR") == ALL_PERMISSIONS


def test_broker_only_reads_the_summary() -> None:
    assert application_permissions("INDEPENDENT_BROKER") == {
        "applications.read",
        "applications.read_summary",
    }


def test_partner_has_no_access_to_applications() -> None:
    # REQUERIMIENTOS §3 manda sobre API §27.4.
    assert application_permissions("CONSTRUCTION_PARTNER") == set()


# --- Catálogos --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "items", "is_public"),
    [
        ("contract_type", {"INDEFINITE", "FIXED_TERM", "WORK_OR_LABOR", "SERVICES"}, True),
        (
            "funds_origin",
            {"SALARY", "INDEPENDENT_ACTIVITY", "PENSION", "SAVINGS", "OTHER"},
            True,
        ),
        (
            "income_source_type",
            {"SALARY", "INDEPENDENT_ACTIVITY", "PENSION", "RENTAL", "OTHER"},
            True,
        ),
        ("financing_mode", {"BANK_CREDIT", "OWN_FUNDS", "EXTERNAL_CREDIT"}, True),
        ("amortization_mode", {"FIXED_PAYMENT", "FIXED_PRINCIPAL"}, True),
        (
            "application_withdrawal_reason",
            {"BUYER_DECISION", "OTHER_FINANCING", "PROPERTY_CHANGED", "NO_RESPONSE", "OTHER"},
            True,
        ),
        (
            "application_transition_reason",
            {
                "BUYER_DATA_REQUESTED",
                "DOCUMENTS_REQUESTED",
                "DOCUMENTS_RECEIVED",
                "DOCUMENTS_OBSERVED",
                "CHECKLIST_APPROVED",
                "OWN_FUNDS_CONFIRMED",
                "EXTERNAL_CREDIT_CONFIRMED",
                "CANCELLED_BY_OPERATION",
                # Motivos de cierre (migración 0003).
                "CLIENT_UNREACHABLE",
                "INSUFFICIENT_CAPACITY",
                "CLIENT_DECLINED_PURCHASE",
                "BETTER_RATE_ELSEWHERE",
                "FASTER_ELSEWHERE",
                "EXISTING_BANK_RELATIONSHIP",
                "SOLD_OTHER_PROPERTY",
                "OTHER",
            },
            False,
        ),
    ],
)
def test_catalogs_are_seeded_and_manageable(code: str, items: set[str], is_public: bool) -> None:
    catalog = Catalog.objects.get(code=code)

    assert catalog.is_manageable
    assert catalog.is_public is is_public
    assert {item.code for item in catalog.items.all()} == items
    assert all(item.is_active for item in catalog.items.all())


# --- Transiciones de la solicitud -------------------------------------------------------


def test_application_transitions_only_reach_ready_to_file_before_filing() -> None:
    assert edges(FlowType.APPLICATION) == {
        (ApplicationStatus.DRAFT, ApplicationStatus.WAITING_BUYER_DATA),
        (ApplicationStatus.WAITING_BUYER_DATA, ApplicationStatus.WAITING_DOCUMENTS),
        (ApplicationStatus.DRAFT, ApplicationStatus.WAITING_DOCUMENTS),
        (ApplicationStatus.WAITING_DOCUMENTS, ApplicationStatus.DOCUMENTS_REVIEW),
        (ApplicationStatus.DOCUMENTS_REVIEW, ApplicationStatus.WAITING_DOCUMENTS),
        (ApplicationStatus.DOCUMENTS_REVIEW, ApplicationStatus.READY_TO_FILE),
        (ApplicationStatus.READY_TO_FILE, ApplicationStatus.DOCUMENTS_REVIEW),
        *{(status, ApplicationStatus.CANCELLED) for status in PRE_FILING},
        *{(status, ApplicationStatus.OWN_FUNDS) for status in PRE_FILING},
        *{(status, ApplicationStatus.EXTERNAL_CREDIT_APPROVED) for status in PRE_FILING},
        *{(status, ApplicationStatus.WITHDRAWN) for status in NON_TERMINAL},
    }


def test_application_transitions_use_structural_statuses_and_known_guards() -> None:
    statuses = statuses_for(FlowType.APPLICATION)
    for transition in WorkflowTransition.objects.filter(flow_type=FlowType.APPLICATION):
        assert {transition.from_status, transition.to_status} <= statuses
        assert transition.guard_code in guards_for(FlowType.APPLICATION) | {""}
        assert transition.is_active
        assert {role.code for role in transition.roles.all()} == {"ADMIN", "ADVISOR"}


def test_only_ready_to_file_has_the_guard() -> None:
    guarded = WorkflowTransition.objects.filter(
        flow_type=FlowType.APPLICATION, guard_code="APPLICATION_READY_TO_FILE"
    )
    assert list(guarded.values_list("code", "from_status", "to_status")) == [
        ("MARK_READY_TO_FILE", "DOCUMENTS_REVIEW", "READY_TO_FILE")
    ]


def test_withdrawal_has_its_own_permission() -> None:
    transitions = own_transitions(FlowType.APPLICATION)
    for transition in transitions.select_related("required_permission"):
        expected = (
            "applications.withdraw"
            if transition.to_status == ApplicationStatus.WITHDRAWN
            else "applications.transition"
        )
        assert transition.required_permission is not None
        assert transition.required_permission.code == expected


# --- Conversión de la oportunidad -------------------------------------------------------


def test_opportunity_is_converted_from_managed_statuses() -> None:
    conversions = WorkflowTransition.objects.filter(
        flow_type=FlowType.OPPORTUNITY, to_status=OpportunityStatus.CONVERTED
    ).select_related("required_permission")

    assert {transition.from_status for transition in conversions} == {
        OpportunityStatus.ASSIGNED,
        OpportunityStatus.CONTACTED,
        OpportunityStatus.IN_PROGRESS,
    }
    for transition in conversions:
        assert transition.code == f"CONVERT_{transition.from_status}"
        assert transition.is_active
        assert transition.required_permission is not None
        assert transition.required_permission.code == "applications.create"
        assert {role.code for role in transition.roles.all()} == {"ADMIN", "ADVISOR"}


def test_other_stays_last_among_transition_reasons() -> None:
    catalog = Catalog.objects.get(code="application_transition_reason")

    codes = list(catalog.items.order_by("sort_order").values_list("code", flat=True))

    assert codes[-1] == "OTHER"
    assert codes[-2] == "SOLD_OTHER_PROPERTY"
