from django.contrib import admin
from django.http import HttpRequest

from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentPackageJob,
    DocumentRequirement,
    DocumentReview,
    DocumentType,
    FileObject,
)


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
    list_display = ["name", "code", "holder_scope", "max_size_bytes", "is_repeatable", "is_active"]
    list_filter = ["is_active", "is_repeatable", "holder_scope"]
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


# --- Expediente documental ---------------------------------------------------------------
# La ruta interna del almacenamiento (`object_key`) nunca se muestra: la descarga pasa por
# la API, con autorización y URL prefirmada.


@admin.register(FileObject)
class FileObjectAdmin(_ReadOnlyAdmin):
    list_display = [
        "original_filename",
        "detected_mime_type",
        "size_bytes",
        "scan_status",
        "scanned_at",
        "created_at",
    ]
    list_filter = ["scan_status", "detected_mime_type", "storage_provider"]
    search_fields = ["sha256"]
    exclude = ["object_key"]


@admin.register(ApplicationDocumentSlot)
class ApplicationDocumentSlotAdmin(_ReadOnlyAdmin):
    list_display = [
        "application",
        "document_type",
        "participant",
        "slot_index",
        "minimum_files",
        "status",
        "is_required",
        "retired_at",
    ]
    list_filter = ["status", "is_required"]
    search_fields = ["application__code", "document_type__code"]
    list_select_related = ["application", "document_type", "participant__client"]


@admin.register(DocumentFile)
class DocumentFileAdmin(_ReadOnlyAdmin):
    list_display = ["client_filename", "slot", "version_number", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["slot__application__code", "client_filename"]
    list_select_related = ["slot__document_type"]


@admin.register(DocumentReview)
class DocumentReviewAdmin(_ReadOnlyAdmin):
    list_display = ["document_file", "decision", "reason_item", "reviewer", "created_at"]
    list_filter = ["decision"]
    list_select_related = ["document_file", "reason_item", "reviewer"]


@admin.register(DocumentPackageJob)
class DocumentPackageJobAdmin(_ReadOnlyAdmin):
    list_display = ["application", "status", "requested_by", "created_at", "expires_at"]
    list_filter = ["status"]
    search_fields = ["application__code"]
    list_select_related = ["application", "requested_by"]
