from django.contrib import admin

from apps.catalogs.models import Catalog, CatalogItem, WorkflowTransition, WorkflowTransitionRole


class CatalogItemInline(admin.TabularInline):
    model = CatalogItem
    fk_name = "catalog"
    extra = 0
    fields = ["code", "label", "sort_order", "is_active", "valid_from", "valid_to"]
    ordering = ["sort_order", "label"]
    show_change_link = True


@admin.register(Catalog)
class CatalogAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "is_public", "is_manageable", "version", "updated_at"]
    list_filter = ["is_public", "is_manageable"]
    search_fields = ["code", "name"]
    readonly_fields = ["version", "created_at", "updated_at"]
    inlines = [CatalogItemInline]


@admin.register(CatalogItem)
class CatalogItemAdmin(admin.ModelAdmin):
    list_display = ["code", "label", "catalog", "parent_item", "sort_order", "is_active"]
    list_filter = ["catalog", "is_active"]
    search_fields = ["code", "label"]
    autocomplete_fields = ["parent_item"]
    readonly_fields = ["created_at", "updated_at"]


class WorkflowTransitionRoleInline(admin.TabularInline):
    model = WorkflowTransitionRole
    extra = 0
    autocomplete_fields = ["role"]


@admin.register(WorkflowTransition)
class WorkflowTransitionAdmin(admin.ModelAdmin):
    list_display = ["code", "flow_type", "from_status", "to_status", "is_active", "system_only"]
    list_filter = ["flow_type", "is_active", "system_only"]
    search_fields = ["code", "label"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [WorkflowTransitionRoleInline]
