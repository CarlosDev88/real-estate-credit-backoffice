"""Restricciones de PostgreSQL de las tablas de solicitudes (DER §6 y §7.5, esquema SQL)."""

import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.db.models import RestrictedError
from django.utils import timezone

from apps.applications.models import (
    TERMINAL_APPLICATION_STATUSES,
    ApplicationAssignment,
    ApplicationParticipant,
    ApplicationStatusHistory,
    BankRuleEvaluation,
    CreditApplication,
    FinancialProfile,
    FinancingPreference,
    IncomeSource,
    ParticipantRole,
    Property,
    next_application_code,
)
from apps.banking.models import BankProduct
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, Opportunity
from apps.identity.models import User
from tests.applications.conftest import catalog_item

pytestmark = pytest.mark.django_db


def assert_violates(constraint: str, create: Callable[[], Any]) -> None:
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        create()
    assert constraint in str(error.value)


# --- credit_applications ----------------------------------------------------------------


def test_application_defaults(application: CreditApplication) -> None:
    assert application.status == ApplicationStatus.DRAFT
    assert application.version == 1
    assert application.bank_product is None
    assert application.current_stage_started_at is not None
    assert application.is_editable
    assert not application.is_terminal


def test_application_codes_are_sequential_and_readable() -> None:
    first = next_application_code()
    second = next_application_code()

    assert re.fullmatch(r"SOL-\d{6}", first)
    assert int(second[4:]) == int(first[4:]) + 1


def test_application_code_is_unique(
    make_application: Callable[..., CreditApplication],
    application: CreditApplication,
    make_client: Callable[..., Client],
) -> None:
    other = Opportunity.objects.create(
        client=make_client(document_number="80123456"),
        origin_item=catalog_item("lead_origin", "DIRECT"),
    )
    assert_violates(
        "credit_applications_code", lambda: make_application(other, code=application.code)
    )


@pytest.mark.parametrize("version", [0, -1])
def test_application_version_must_be_positive(
    make_application: Callable[..., CreditApplication], opportunity: Opportunity, version: int
) -> None:
    assert_violates(
        "ck_credit_applications_version", lambda: make_application(opportunity, version=version)
    )


def test_application_status_must_be_structural(
    make_application: Callable[..., CreditApplication], opportunity: Opportunity
) -> None:
    assert_violates(
        "ck_credit_applications_status", lambda: make_application(opportunity, status="PAUSED")
    )


def test_withdrawal_date_and_reason_go_together(
    make_application: Callable[..., CreditApplication], opportunity: Opportunity
) -> None:
    assert_violates(
        "ck_credit_applications_withdrawal",
        lambda: make_application(opportunity, withdrawn_at=timezone.now()),
    )
    assert_violates(
        "ck_credit_applications_withdrawal",
        lambda: make_application(
            opportunity,
            withdrawal_reason_item=catalog_item("application_withdrawal_reason", "OTHER"),
        ),
    )


def test_only_one_open_application_per_opportunity(
    make_application: Callable[..., CreditApplication],
    application: CreditApplication,
    opportunity: Opportunity,
) -> None:
    assert_violates(
        "uq_credit_applications_open_opportunity", lambda: make_application(opportunity)
    )


@pytest.mark.parametrize("status", TERMINAL_APPLICATION_STATUSES)
def test_a_finished_application_allows_a_new_attempt(
    make_application: Callable[..., CreditApplication], opportunity: Opportunity, status: str
) -> None:
    extra: dict[str, Any] = {"status": status}
    if status == ApplicationStatus.WITHDRAWN:
        extra["withdrawn_at"] = timezone.now()
        extra["withdrawal_reason_item"] = catalog_item("application_withdrawal_reason", "OTHER")
    finished = make_application(opportunity, **extra)

    retry = make_application(opportunity)

    assert finished.is_terminal
    assert not finished.is_editable
    assert retry.opportunity_id == finished.opportunity_id


@pytest.mark.parametrize(
    ("status", "editable"),
    [
        (ApplicationStatus.READY_TO_FILE, True),
        (ApplicationStatus.FILED, False),
        (ApplicationStatus.BANK_OBSERVATION, False),
    ],
)
def test_data_is_editable_only_before_filing(
    make_application: Callable[..., CreditApplication],
    opportunity: Opportunity,
    status: str,
    editable: bool,
) -> None:
    assert make_application(opportunity, status=status).is_editable is editable


# --- application_assignments ------------------------------------------------------------


def test_only_one_current_assignment(
    application: CreditApplication, advisor_user: User, admin_user: User
) -> None:
    ApplicationAssignment.objects.create(
        application=application, advisor=advisor_user, assigned_by=admin_user
    )
    assert_violates(
        "uq_application_assignments_active",
        lambda: ApplicationAssignment.objects.create(application=application, advisor=admin_user),
    )


def test_ended_assignments_are_history(
    application: CreditApplication, advisor_user: User, admin_user: User
) -> None:
    first = ApplicationAssignment.objects.create(application=application, advisor=advisor_user)
    first.ended_at = timezone.now()
    first.save(update_fields=["ended_at"])
    ApplicationAssignment.objects.create(application=application, advisor=admin_user)

    assert application.assignments.count() == 2


def test_assignment_cannot_end_before_it_starts(
    application: CreditApplication, advisor_user: User
) -> None:
    assert_violates(
        "ck_application_assignments_dates",
        lambda: ApplicationAssignment.objects.create(
            application=application,
            advisor=advisor_user,
            ended_at=timezone.now() - timedelta(days=1),
        ),
    )


# --- application_participants -----------------------------------------------------------


def test_participant_defaults(primary: ApplicationParticipant) -> None:
    assert primary.contributes_income
    assert primary.is_active
    assert primary.income_share_cop is None


def test_only_one_active_primary(
    application: CreditApplication,
    primary: ApplicationParticipant,
    make_client: Callable[..., Client],
) -> None:
    other = make_client(document_number="80123456")
    assert_violates(
        "uq_application_participants_primary",
        lambda: ApplicationParticipant.objects.create(
            application=application, client=other, role=ParticipantRole.PRIMARY
        ),
    )


def test_an_inactive_primary_does_not_block_a_new_one(
    application: CreditApplication,
    primary: ApplicationParticipant,
    make_client: Callable[..., Client],
) -> None:
    primary.is_active = False
    primary.save(update_fields=["is_active"])

    ApplicationParticipant.objects.create(
        application=application,
        client=make_client(document_number="80123456"),
        role=ParticipantRole.PRIMARY,
    )


def test_a_client_participates_once_per_application(
    application: CreditApplication, primary: ApplicationParticipant, buyer: Client
) -> None:
    assert_violates(
        "uq_application_participants_client",
        lambda: ApplicationParticipant.objects.create(
            application=application, client=buyer, role=ParticipantRole.CO_APPLICANT
        ),
    )


def test_participant_role_must_be_known(application: CreditApplication, buyer: Client) -> None:
    assert_violates(
        "ck_application_participants_role",
        lambda: ApplicationParticipant.objects.create(
            application=application, client=buyer, role="GUARANTOR"
        ),
    )


def test_income_share_cannot_be_negative(application: CreditApplication, buyer: Client) -> None:
    assert_violates(
        "ck_application_participants_income_share",
        lambda: ApplicationParticipant.objects.create(
            application=application,
            client=buyer,
            role=ParticipantRole.PRIMARY,
            income_share_cop=-1,
        ),
    )


# --- financial_profiles e income_sources ------------------------------------------------


def make_profile(participant: ApplicationParticipant, **extra: Any) -> FinancialProfile:
    return FinancialProfile.objects.create(
        participant=participant,
        employment_profile_item=catalog_item("employment_profile", "EMPLOYEE"),
        **extra,
    )


def test_profile_amounts_default_to_zero(primary: ApplicationParticipant) -> None:
    profile = make_profile(primary)

    assert (
        profile.monthly_income_cop,
        profile.monthly_expenses_cop,
        profile.assets_cop,
        profile.liabilities_cop,
    ) == (0, 0, 0, 0)


def test_one_profile_per_participant(primary: ApplicationParticipant) -> None:
    make_profile(primary)
    assert_violates("participant_id", lambda: make_profile(primary))


@pytest.mark.parametrize(
    ("field", "constraint"),
    [
        ("monthly_income_cop", "ck_financial_profiles_income"),
        ("monthly_expenses_cop", "ck_financial_profiles_expenses"),
        ("assets_cop", "ck_financial_profiles_assets"),
        ("liabilities_cop", "ck_financial_profiles_liabilities"),
    ],
)
def test_profile_amounts_cannot_be_negative(
    primary: ApplicationParticipant, field: str, constraint: str
) -> None:
    assert_violates(constraint, lambda: make_profile(primary, **{field: -1}))


def test_income_source_amount_cannot_be_negative(primary: ApplicationParticipant) -> None:
    profile = make_profile(primary)
    assert_violates(
        "ck_income_sources_amount",
        lambda: IncomeSource.objects.create(
            financial_profile=profile,
            source_type_item=catalog_item("income_source_type", "SALARY"),
            monthly_amount_cop=-1,
        ),
    )


# --- properties -------------------------------------------------------------------------


def make_property(application: CreditApplication, **extra: Any) -> Property:
    extra.setdefault("estimated_value_cop", 420_000_000)
    return Property.objects.create(
        application=application,
        property_type_item=catalog_item("property_type", "APARTMENT"),
        condition_item=catalog_item("property_condition", "NEW"),
        city_item=catalog_item("municipality", "11001"),
        **extra,
    )


def test_one_property_per_application(application: CreditApplication) -> None:
    make_property(application)
    assert_violates("application_id", lambda: make_property(application))


def test_property_value_cannot_be_negative(application: CreditApplication) -> None:
    assert_violates(
        "ck_properties_estimated_value",
        lambda: make_property(application, estimated_value_cop=-1),
    )


# --- financing_preferences --------------------------------------------------------------


def make_financing(application: CreditApplication, **extra: Any) -> FinancingPreference:
    extra.setdefault("requested_amount_cop", 294_000_000)
    return FinancingPreference.objects.create(
        application=application,
        financing_mode_item=catalog_item("financing_mode", "BANK_CREDIT"),
        **extra,
    )


def test_financing_defaults(application: CreditApplication) -> None:
    financing = make_financing(application)

    assert financing.own_resources_cop == 0
    assert not financing.uses_severance_funds
    assert financing.severance_funds_cop == 0


def test_severance_amount_requires_using_severance_funds(application: CreditApplication) -> None:
    assert_violates(
        "ck_financing_severance",
        lambda: make_financing(application, severance_funds_cop=30_000_000),
    )
    financing = make_financing(
        application, uses_severance_funds=True, severance_funds_cop=30_000_000
    )
    assert financing.severance_funds_cop == 30_000_000


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"requested_amount_cop": -1}, "ck_financing_requested_amount"),
        ({"term_months": 0}, "ck_financing_term_months"),
        ({"own_resources_cop": -1}, "ck_financing_own_resources"),
        (
            {"uses_severance_funds": True, "severance_funds_cop": -1},
            "ck_financing_severance_amount",
        ),
        ({"external_approved_amount_cop": -1}, "ck_financing_external_amount"),
    ],
)
def test_financing_values_must_be_valid(
    application: CreditApplication, values: dict[str, Any], constraint: str
) -> None:
    assert_violates(constraint, lambda: make_financing(application, **values))


# --- bank_rule_evaluations --------------------------------------------------------------


def make_evaluation(application: CreditApplication, **extra: Any) -> BankRuleEvaluation:
    extra.setdefault("application_version", 1)
    extra.setdefault("is_eligible", True)
    return BankRuleEvaluation.objects.create(
        application=application,
        bank_product=BankProduct.objects.get(bank__code="BANCOLOMBIA"),
        result_snapshot={"rules": []},
        **extra,
    )


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"application_version": 0}, "ck_bank_rule_evaluations_version"),
        ({"blocking_count": -1}, "ck_bank_rule_evaluations_blocking"),
        ({"warning_count": -1}, "ck_bank_rule_evaluations_warning"),
    ],
)
def test_evaluation_values_must_be_valid(
    application: CreditApplication, values: dict[str, Any], constraint: str
) -> None:
    assert_violates(constraint, lambda: make_evaluation(application, **values))


def test_evaluations_are_kept_newest_first(application: CreditApplication) -> None:
    older = make_evaluation(application)
    newer = make_evaluation(application, application_version=2, is_eligible=False)

    assert list(application.rule_evaluations.all()) == [newer, older]


# --- application_status_history ---------------------------------------------------------


def make_history(application: CreditApplication, **extra: Any) -> ApplicationStatusHistory:
    extra.setdefault("to_status", ApplicationStatus.DRAFT)
    extra.setdefault("application_version", 1)
    return ApplicationStatusHistory.objects.create(application=application, **extra)


def test_creation_entry_has_no_previous_status(application: CreditApplication) -> None:
    entry = make_history(application)
    assert entry.from_status is None


def test_history_entry_must_change_the_status(application: CreditApplication) -> None:
    assert_violates(
        "ck_application_status_change",
        lambda: make_history(
            application,
            from_status=ApplicationStatus.DRAFT,
            to_status=ApplicationStatus.DRAFT,
        ),
    )


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"to_status": "PAUSED"}, "ck_application_status_to_status"),
        ({"from_status": "PAUSED"}, "ck_application_status_from_status"),
        ({"application_version": 0}, "ck_application_status_version"),
    ],
)
def test_history_values_must_be_valid(
    application: CreditApplication, values: dict[str, Any], constraint: str
) -> None:
    assert_violates(constraint, lambda: make_history(application, **values))


# --- Borrado ------------------------------------------------------------------------------


def test_an_application_with_history_cannot_be_deleted(application: CreditApplication) -> None:
    make_history(application)
    with pytest.raises(RestrictedError):
        CreditApplication.objects.filter(pk=application.pk).delete()
