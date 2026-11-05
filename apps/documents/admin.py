from django.contrib import admin
from django.http import HttpRequest

from apps.documents.models import DocumentRequirement, DocumentType


class _ReadOnlyAdmin(admin.ModelAdmin):
    """Solo consulta: la API valida formatos, alcance y versiones antes de guardar."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        return False


@admin.register(DocumentType)
class DocumentTypeAdmin(_ReadOnlyAdmin):
    list_display = ["name", "code", "max_size_bytes", "is_repeatable", "is_active"]
    list_filter = ["is_active", "is_repeatable"]
    search_fields = ["name", "code"]


@admin.register(DocumentRequirement)
class DocumentRequirementAdmin(_ReadOnlyAdmin):
    list_display = [
        "document_type",
        "version",
        "bank_product",
        "participant_role",
        "minimum_files",
        "alternative_group_code",
        "status",
        "valid_from",
    ]
    list_filter = ["status", "participant_role", "is_required"]
    search_fields = ["document_type__code", "document_type__name", "alternative_group_code"]
    list_select_related = ["document_type", "bank_product__bank"]
