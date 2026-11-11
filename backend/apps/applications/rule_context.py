"""Contexto de evaluación de las reglas bancarias a partir de una solicitud.

Tiene la forma de ``apps.banking.rule_fields.RULE_FIELDS``: grupos ``application``,
``applicant`` (el titular), ``household``, ``property`` y ``financing``. Cada campo de
la lista blanca aparece siempre; un dato que la solicitud todavía no tiene va como
``None`` y la regla que lo use da ``MISSING_DATA``.

``household`` suma a los participantes activos que aportan ingresos. En el ingreso,
``income_share_cop`` (si está informado) reemplaza al del perfil; en gastos y pasivos,
basta que a uno le falte el perfil para que la suma sea ``None``.
"""

from datetime import date
from typing import Any

from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancialProfile,
    FinancingPreference,
    ParticipantRole,
    Property,
)
from apps.banking.rule_engine import validate_context
from apps.catalogs.models import CatalogItem
from apps.catalogs.services import today

RuleContext = dict[str, dict[str, Any]]


def full_months_between(start: date, end: date) -> int:
    """Meses completos entre dos fechas; 0 si ``start`` es posterior a ``end``."""
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def _code(item: CatalogItem | None) -> str | None:
    return item.code if item is not None else None


def _profile(participant: ApplicationParticipant) -> FinancialProfile | None:
    try:
        return participant.financial_profile
    except FinancialProfile.DoesNotExist:
        return None


def _sum_or_none(values: list[int | None]) -> int | None:
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _applicant(participant: ApplicationParticipant | None, on: date) -> dict[str, Any]:
    profile = _profile(participant) if participant is not None else None
    if profile is None:
        return {
            "employment_profile_code": None,
            "contract_type_code": None,
            "employment_months": None,
            "monthly_income_cop": None,
            "monthly_expenses_cop": None,
            "assets_cop": None,
            "liabilities_cop": None,
        }
    start = profile.employment_start_date
    return {
        "employment_profile_code": profile.employment_profile_item.code,
        "contract_type_code": _code(profile.contract_type_item),
        "employment_months": full_months_between(start, on) if start is not None else None,
        "monthly_income_cop": profile.monthly_income_cop,
        "monthly_expenses_cop": profile.monthly_expenses_cop,
        "assets_cop": profile.assets_cop,
        "liabilities_cop": profile.liabilities_cop,
    }


def _household(participants: list[ApplicationParticipant]) -> dict[str, Any]:
    contributors = [p for p in participants if p.contributes_income]
    profiles = [_profile(p) for p in contributors]
    incomes: list[int | None] = []
    for participant, profile in zip(contributors, profiles, strict=True):
        if participant.income_share_cop is not None:
            incomes.append(participant.income_share_cop)
        else:
            incomes.append(profile.monthly_income_cop if profile is not None else None)
    return {
        "monthly_income_cop": _sum_or_none(incomes),
        "monthly_expenses_cop": _sum_or_none(
            [profile.monthly_expenses_cop if profile else None for profile in profiles]
        ),
        "liabilities_cop": _sum_or_none(
            [profile.liabilities_cop if profile else None for profile in profiles]
        ),
    }


def _property(prop: Property | None) -> dict[str, Any]:
    if prop is None:
        return {
            "property_type_code": None,
            "condition_code": None,
            "city_code": None,
            "estimated_value_cop": None,
            "is_owned_by_applicant": None,
            "has_project": None,
        }
    return {
        "property_type_code": prop.property_type_item.code,
        "condition_code": prop.condition_item.code,
        "city_code": prop.city_item.code,
        "estimated_value_cop": prop.estimated_value_cop,
        "is_owned_by_applicant": prop.is_owned_by_applicant,
        "has_project": prop.project_id is not None,
    }


def _financing(financing: FinancingPreference | None) -> dict[str, Any]:
    if financing is None:
        return {
            "financing_mode_code": None,
            "requested_amount_cop": None,
            "term_months": None,
            "own_resources_cop": None,
            "uses_severance_funds": None,
            "severance_funds_cop": None,
            "currency_mode_code": None,
            "amortization_mode_code": None,
            "external_approved_amount_cop": None,
        }
    return {
        "financing_mode_code": financing.financing_mode_item.code,
        "requested_amount_cop": financing.requested_amount_cop,
        "term_months": financing.term_months,
        "own_resources_cop": financing.own_resources_cop,
        "uses_severance_funds": financing.uses_severance_funds,
        "severance_funds_cop": financing.severance_funds_cop,
        "currency_mode_code": _code(financing.currency_mode_item),
        "amortization_mode_code": _code(financing.amortization_mode_item),
        "external_approved_amount_cop": financing.external_approved_amount_cop,
    }


def build_rule_context(application: CreditApplication, *, on: date | None = None) -> RuleContext:
    """Contexto de la solicitud tal como está en la base (``on``: fecha de cálculo).

    Lee los datos de nuevo en lugar de usar relaciones ya cargadas, para reflejar los
    cambios hechos en la misma transacción.
    """
    participants = list(
        ApplicationParticipant.objects.filter(application=application, is_active=True)
        .select_related(
            "financial_profile__employment_profile_item",
            "financial_profile__contract_type_item",
        )
        .order_by("created_at")
    )
    primary = next((p for p in participants if p.role == ParticipantRole.PRIMARY), None)
    prop = (
        Property.objects.filter(application=application)
        .select_related("property_type_item", "condition_item", "city_item")
        .first()
    )
    financing = (
        FinancingPreference.objects.filter(application=application)
        .select_related("financing_mode_item", "currency_mode_item", "amortization_mode_item")
        .first()
    )
    context: RuleContext = {
        "application": {
            "purpose_code": application.purpose_item.code,
            "is_joint": any(p.role == ParticipantRole.CO_APPLICANT for p in participants),
            "participant_count": len(participants),
        },
        "applicant": _applicant(primary, on or today()),
        "household": _household(participants),
        "property": _property(prop),
        "financing": _financing(financing),
    }
    # El contexto lo arma el sistema: un campo fuera de la lista blanca o con otro tipo
    # es un error de programación, no un dato del usuario.
    validate_context(context)
    return context
