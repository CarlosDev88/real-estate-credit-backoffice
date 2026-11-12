from django.contrib import admin
from django.http import HttpRequest

from apps.filings.models import (
    Filing,
    FilingDocumentSnapshot,
    FilingResponse,
    FilingResponseObservation,
)


class _ReadOnlyAdmin(admin.ModelAdmin):
    """Solo consulta: la radicación y las respuestas pasan por los servicios, que
    cambian el estado de la solicitud y dejan la trazabilidad."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        return False


@admin.register(Filing)
class FilingAdmin(_ReadOnlyAdmin):
    list_display = ["application", "sequence_number", "status", "filed_at", "filed_by"]
    list_filter = ["status"]
    search_fields = ["application__code", "external_reference"]


@admin.register(FilingDocumentSnapshot)
class FilingDocumentSnapshotAdmin(_ReadOnlyAdmin):
    list_display = ["filing", "document_type_code", "document_file", "sha256"]


@admin.register(FilingResponse)
class FilingResponseAdmin(_ReadOnlyAdmin):
    list_display = ["filing", "response_type_item", "received_at", "recorded_by"]


@admin.register(FilingResponseObservation)
class FilingResponseObservationAdmin(_ReadOnlyAdmin):
    list_display = ["filing_response", "document_slot", "reason_item", "resolved_at"]
