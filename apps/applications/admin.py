from django.contrib import admin
from django.http import HttpRequest

from apps.applications.models import (
    ApplicationAssignment,
    ApplicationParticipant,
    ApplicationStatusHistory,
    BankRuleEvaluation,
    CreditApplication,
    FinancialProfile,
    FinancingPreference,
    IncomeSource,
    Property,
)


class _ReadOnlyAdmin(admin.ModelAdmin):
    """Solo consulta: versión, historial y alcance los mantienen los servicios del módulo."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        return False


@admin.register(CreditApplication)
class CreditApplicationAdmin(_ReadOnlyAdmin):
    list_display = ["code", "status", "purpose_item", "bank_product", "assigned_advisor"]
    list_filter = ["status"]
    search_fields = ["code", "opportunity__client__document_number"]
    list_select_related = ["purpose_item", "bank_product__bank", "assigned_advisor"]


@admin.register(ApplicationAssignment)
class ApplicationAssignmentAdmin(_ReadOnlyAdmin):
    list_display = ["application", "advisor", "assigned_by", "created_at", "ended_at"]
    list_select_related = ["application", "advisor", "assigned_by"]


@admin.register(ApplicationParticipant)
class ApplicationParticipantAdmin(_ReadOnlyAdmin):
    list_display = ["application", "client", "role", "contributes_income", "is_active"]
    list_filter = ["role", "is_active"]
    list_select_related = ["application", "client"]


@admin.register(FinancialProfile)
class FinancialProfileAdmin(_ReadOnlyAdmin):
    list_display = ["participant", "employment_profile_item", "monthly_income_cop"]
    list_select_related = ["participant", "employment_profile_item"]


@admin.register(IncomeSource)
class IncomeSourceAdmin(_ReadOnlyAdmin):
    list_display = ["financial_profile", "source_type_item", "monthly_amount_cop", "is_primary"]
    list_select_related = ["financial_profile", "source_type_item"]


@admin.register(Property)
class PropertyAdmin(_ReadOnlyAdmin):
    list_display = ["application", "property_type_item", "condition_item", "city_item"]
    list_select_related = ["application", "property_type_item", "condition_item", "city_item"]


@admin.register(FinancingPreference)
class FinancingPreferenceAdmin(_ReadOnlyAdmin):
    list_display = ["application", "financing_mode_item", "requested_amount_cop", "term_months"]
    list_select_related = ["application", "financing_mode_item"]


@admin.register(BankRuleEvaluation)
class BankRuleEvaluationAdmin(_ReadOnlyAdmin):
    list_display = [
        "application",
        "bank_product",
        "application_version",
        "is_eligible",
        "blocking_count",
        "warning_count",
        "created_at",
    ]
    list_filter = ["is_eligible"]
    list_select_related = ["application", "bank_product__bank"]


@admin.register(ApplicationStatusHistory)
class ApplicationStatusHistoryAdmin(_ReadOnlyAdmin):
    list_display = ["application", "from_status", "to_status", "actor_user", "created_at"]
    list_filter = ["to_status"]
    list_select_related = ["application", "actor_user"]
