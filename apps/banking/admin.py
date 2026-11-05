from django.contrib import admin
from django.http import HttpRequest

from apps.banking.models import Bank, BankPolicyRule, BankProduct, BankProductPurpose


class BankProductInline(admin.TabularInline):
    model = BankProduct
    extra = 0
    fields = ["code", "name", "status", "valid_from", "valid_to"]
    readonly_fields = ["code", "name", "status", "valid_from", "valid_to"]
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: Bank | None = None) -> bool:
        return False


@admin.register(Bank)
class BankAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "tax_id", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["name", "code", "tax_id"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [BankProductInline]


class BankProductPurposeInline(admin.TabularInline):
    model = BankProductPurpose
    extra = 0
    autocomplete_fields = ["purpose_item"]
    fields = ["purpose_item", "is_active"]


@admin.register(BankProduct)
class BankProductAdmin(admin.ModelAdmin):
    list_display = ["name", "bank", "code", "status", "valid_from", "valid_to"]
    list_filter = ["status", "bank"]
    search_fields = ["name", "code", "bank__name"]
    autocomplete_fields = ["bank", "product_type_item"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [BankProductPurposeInline]


@admin.register(BankPolicyRule)
class BankPolicyRuleAdmin(admin.ModelAdmin):
    """Solo consulta: las versiones son inmutables y la condición se valida por la API."""

    list_display = ["code", "version", "bank_product", "severity", "status", "valid_from"]
    list_filter = ["status", "severity"]
    search_fields = ["code", "message"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: BankPolicyRule | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: BankPolicyRule | None = None
    ) -> bool:
        return False
