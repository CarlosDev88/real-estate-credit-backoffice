from django.urls import path

from apps.documents import buyer_views, dossier_views, views

app_name = "documents"

urlpatterns = [
    # Expediente documental (sección 19)
    path(
        "applications/<uuid:application_id>/document-slots",
        dossier_views.ApplicationDocumentSlotListView.as_view(),
        name="application-document-slot-list",
    ),
    path(
        "applications/<uuid:application_id>/document-slots/refresh",
        dossier_views.ApplicationDocumentSlotRefreshView.as_view(),
        name="application-document-slot-refresh",
    ),
    path(
        "document-slots/<uuid:slot_id>",
        dossier_views.DocumentSlotDetailView.as_view(),
        name="document-slot-detail",
    ),
    path(
        "document-slots/<uuid:slot_id>/versions",
        dossier_views.DocumentSlotVersionListView.as_view(),
        name="document-slot-version-list",
    ),
    # Expediente en el portal del comprador
    path(
        "buyer/applications/<uuid:application_id>/document-slots",
        buyer_views.BuyerDocumentSlotListView.as_view(),
        name="buyer-document-slot-list",
    ),
    path(
        "buyer/document-slots/<uuid:slot_id>",
        buyer_views.BuyerDocumentSlotDetailView.as_view(),
        name="buyer-document-slot-detail",
    ),
    path(
        "buyer/document-slots/<uuid:slot_id>/versions",
        buyer_views.BuyerDocumentSlotVersionListView.as_view(),
        name="buyer-document-slot-version-list",
    ),
    path(
        "buyer/document-slots/<uuid:slot_id>/uploads",
        buyer_views.BuyerDocumentUploadView.as_view(),
        name="buyer-document-upload",
    ),
    # Tipos documentales (sección 23.4)
    path("document-types", views.DocumentTypeListView.as_view(), name="document-type-list"),
    path(
        "document-types/<uuid:document_type_id>",
        views.DocumentTypeDetailView.as_view(),
        name="document-type-detail",
    ),
    path(
        "document-types/<uuid:document_type_id>/activate",
        views.DocumentTypeActivateView.as_view(),
        name="document-type-activate",
    ),
    path(
        "document-types/<uuid:document_type_id>/deactivate",
        views.DocumentTypeDeactivateView.as_view(),
        name="document-type-deactivate",
    ),
    # Requisitos documentales (sección 23.4)
    path(
        "document-requirements",
        views.DocumentRequirementListView.as_view(),
        name="document-requirement-list",
    ),
    path(
        "document-requirements/preview",
        views.DocumentRequirementPreviewView.as_view(),
        name="document-requirement-preview",
    ),
    path(
        "document-requirements/<uuid:requirement_id>",
        views.DocumentRequirementDetailView.as_view(),
        name="document-requirement-detail",
    ),
    path(
        "document-requirements/<uuid:requirement_id>/activate",
        views.DocumentRequirementActivateView.as_view(),
        name="document-requirement-activate",
    ),
    path(
        "document-requirements/<uuid:requirement_id>/deactivate",
        views.DocumentRequirementDeactivateView.as_view(),
        name="document-requirement-deactivate",
    ),
]
