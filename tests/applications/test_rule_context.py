"""Contexto de las reglas bancarias construido desde la solicitud (`rule_context`)."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancialProfile,
    FinancingPreference,
    ParticipantRole,
    Property,
)
from apps.applications.rule_context import build_rule_context, full_months_between
from apps.banking.rule_fields import RULE_FIELDS
from apps.crm.models import Client
from apps.partners.models import Project
from tests.applications.conftest import catalog_item

pytestmark = pytest.mark.django_db

ON = date(2026, 11, 5)


def make_profile(participant: ApplicationParticipant, **extra: Any) -> FinancialProfile:
    extra.setdefault("employment_profile_item", catalog_item("employment_profile", "EMPLOYEE"))
    return FinancialProfile.objects.create(participant=participant, **extra)


def add_participant(
    application: CreditApplication,
    client: Client,
    role: str = ParticipantRole.CO_APPLICANT,
    **extra: Any,
) -> ApplicationParticipant:
    return ApplicationParticipant.objects.create(
        application=application, client=client, role=role, **extra
    )


@pytest.fixture
def second_client(make_client: Callable[..., Client]) -> Client:
    return make_client(document_number="79555111", first_names="Andrés")


@pytest.fixture
def third_client(make_client: Callable[..., Client]) -> Client:
    return make_client(document_number="52444222", first_names="Sofía")


@pytest.mark.parametrize(
    ("start", "end", "months"),
    [
        (date(2026, 1, 15), date(2026, 11, 15), 10),
        (date(2026, 1, 15), date(2026, 11, 14), 9),
        (date(2025, 12, 31), date(2026, 2, 28), 1),
        (date(2026, 11, 5), date(2026, 11, 5), 0),
        (date(2026, 12, 1), date(2026, 11, 5), 0),
    ],
)
def test_full_months_between(start: date, end: date, months: int) -> None:
    assert full_months_between(start, end) == months


def test_new_application_has_every_whitelisted_field_with_missing_data_as_none(
    application: CreditApplication,
) -> None:
    context = build_rule_context(application, on=ON)

    names = {f"{group}.{key}" for group, values in context.items() for key in values}
    assert names == set(RULE_FIELDS)
    assert context["application"] == {
        "purpose_code": "PURCHASE_NEW",
        "is_joint": False,
        "participant_count": 1,
    }
    # El titular aporta ingresos por omisión, pero todavía no tiene perfil.
    assert context["household"] == {
        "monthly_income_cop": None,
        "monthly_expenses_cop": None,
        "liabilities_cop": None,
    }
    for group in ("applicant", "property", "financing"):
        assert set(context[group].values()) == {None}, group


def test_full_application_context(
    application: CreditApplication,
    primary: ApplicationParticipant,
    second_client: Client,
    third_client: Client,
    active_project: Project,
) -> None:
    make_profile(
        primary,
        contract_type_item=catalog_item("contract_type", "INDEFINITE"),
        employment_start_date=date(2024, 3, 10),
        monthly_income_cop=9_000_000,
        monthly_expenses_cop=3_000_000,
        assets_cop=50_000_000,
        liabilities_cop=10_000_000,
    )
    co_applicant = add_participant(application, second_client, income_share_cop=2_500_000)
    make_profile(co_applicant, monthly_income_cop=4_000_000, liabilities_cop=1_000_000)
    # El deudor solidario no aporta ingresos: no entra en el hogar, pero sí en el conteo.
    add_participant(
        application, third_client, ParticipantRole.SOLIDARY_DEBTOR, contributes_income=False
    )
    Property.objects.create(
        application=application,
        project=active_project,
        property_type_item=catalog_item("property_type", "APARTMENT"),
        condition_item=catalog_item("property_condition", "NEW"),
        city_item=catalog_item("municipality", "11001"),
        estimated_value_cop=420_000_000,
    )
    FinancingPreference.objects.create(
        application=application,
        financing_mode_item=catalog_item("financing_mode", "BANK_CREDIT"),
        requested_amount_cop=294_000_000,
        term_months=240,
        currency_mode_item=catalog_item("currency_mode", "COP"),
        amortization_mode_item=catalog_item("amortization_mode", "FIXED_PAYMENT"),
        own_resources_cop=126_000_000,
        uses_severance_funds=True,
        severance_funds_cop=30_000_000,
    )

    assert build_rule_context(application, on=ON) == {
        "application": {"purpose_code": "PURCHASE_NEW", "is_joint": True, "participant_count": 3},
        "applicant": {
            "employment_profile_code": "EMPLOYEE",
            "contract_type_code": "INDEFINITE",
            "employment_months": 31,
            "monthly_income_cop": 9_000_000,
            "monthly_expenses_cop": 3_000_000,
            "assets_cop": 50_000_000,
            "liabilities_cop": 10_000_000,
        },
        "household": {
            # El aporte declarado del co-solicitante reemplaza al ingreso de su perfil.
            "monthly_income_cop": 11_500_000,
            "monthly_expenses_cop": 3_000_000,
            "liabilities_cop": 11_000_000,
        },
        "property": {
            "property_type_code": "APARTMENT",
            "condition_code": "NEW",
            "city_code": "11001",
            "estimated_value_cop": 420_000_000,
            "is_owned_by_applicant": None,
            "has_project": True,
        },
        "financing": {
            "financing_mode_code": "BANK_CREDIT",
            "requested_amount_cop": 294_000_000,
            "term_months": 240,
            "own_resources_cop": 126_000_000,
            "uses_severance_funds": True,
            "severance_funds_cop": 30_000_000,
            "currency_mode_code": "COP",
            "amortization_mode_code": "FIXED_PAYMENT",
            "external_approved_amount_cop": None,
        },
    }


def test_household_income_uses_the_declared_share_when_a_profile_is_missing(
    application: CreditApplication, primary: ApplicationParticipant, second_client: Client
) -> None:
    make_profile(primary, monthly_income_cop=6_000_000, monthly_expenses_cop=1_000_000)
    add_participant(application, second_client, income_share_cop=2_000_000)

    household = build_rule_context(application, on=ON)["household"]

    assert household["monthly_income_cop"] == 8_000_000
    # Sin perfil del co-solicitante, sus gastos y pasivos se desconocen.
    assert household["monthly_expenses_cop"] is None
    assert household["liabilities_cop"] is None


def test_retired_participants_and_solidary_debtors_do_not_make_it_joint(
    application: CreditApplication,
    primary: ApplicationParticipant,
    second_client: Client,
    third_client: Client,
) -> None:
    make_profile(primary, monthly_income_cop=6_000_000)
    retired = add_participant(application, second_client, is_active=False)
    make_profile(retired, monthly_income_cop=9_000_000)
    add_participant(
        application, third_client, ParticipantRole.SOLIDARY_DEBTOR, contributes_income=False
    )

    context = build_rule_context(application, on=ON)

    assert context["application"]["is_joint"] is False
    assert context["application"]["participant_count"] == 2
    assert context["household"]["monthly_income_cop"] == 6_000_000


def test_profile_without_start_date_or_contract_leaves_them_missing(
    application: CreditApplication, primary: ApplicationParticipant
) -> None:
    make_profile(primary, employment_profile_item=catalog_item("employment_profile", "PENSIONER"))

    applicant = build_rule_context(application, on=ON)["applicant"]

    assert applicant["employment_profile_code"] == "PENSIONER"
    assert applicant["contract_type_code"] is None
    assert applicant["employment_months"] is None
    assert applicant["monthly_income_cop"] == 0


def test_property_without_project_and_external_credit(
    application: CreditApplication,
) -> None:
    Property.objects.create(
        application=application,
        property_type_item=catalog_item("property_type", "HOUSE"),
        condition_item=catalog_item("property_condition", "USED"),
        city_item=catalog_item("municipality", "11001"),
        address="Calle 93 # 11-20",
        estimated_value_cop=380_000_000,
        is_owned_by_applicant=True,
    )
    FinancingPreference.objects.create(
        application=application,
        financing_mode_item=catalog_item("financing_mode", "EXTERNAL_CREDIT"),
        requested_amount_cop=0,
        external_approved_amount_cop=250_000_000,
    )

    context = build_rule_context(application, on=ON)

    assert context["property"]["has_project"] is False
    assert context["property"]["is_owned_by_applicant"] is True
    assert context["financing"]["financing_mode_code"] == "EXTERNAL_CREDIT"
    assert context["financing"]["external_approved_amount_cop"] == 250_000_000
    assert context["financing"]["term_months"] is None
    assert context["financing"]["currency_mode_code"] is None
