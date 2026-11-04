from django.contrib import admin

from apps.crm.models import Client, ClientAddress, Opportunity, OpportunityAssignment


class ClientAddressInline(admin.TabularInline):
    model = ClientAddress
    extra = 0
    autocomplete_fields = ["address_type_item", "city_item"]


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["last_names", "first_names", "document_number", "email", "created_at"]
    search_fields = ["first_names", "last_names", "document_number", "email"]
    autocomplete_fields = ["document_type_item", "origin_item", "created_by"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [ClientAddressInline]


class OpportunityAssignmentInline(admin.TabularInline):
    model = OpportunityAssignment
    fk_name = "opportunity"
    extra = 0
    readonly_fields = ["advisor", "assigned_by", "reason", "created_at", "ended_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ["id", "client", "project", "status", "assigned_advisor", "created_at"]
    list_filter = ["status"]
    search_fields = ["client__first_names", "client__last_names", "client__document_number"]
    autocomplete_fields = [
        "client",
        "project",
        "origin_user",
        "assigned_advisor",
        "origin_item",
        "lost_reason_item",
    ]
    readonly_fields = ["created_at", "updated_at", "converted_at"]
    inlines = [OpportunityAssignmentInline]
