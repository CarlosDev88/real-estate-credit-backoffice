from django.urls import path

from apps.documents import buyer_views, dossier_views, package_views, views

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
    path(
        "document-slots/<uuid:slot_id>/review",
        dossier_views.DocumentSlotReviewView.as_view(),
        name="document-slot-review",
    ),
    path(
        "document-files/<uuid:file_id>",
        dossier_views.DocumentFileDetailView.as_view(),
        name="document-file-detail",
    ),
    path(
        "document-files/<uuid:file_id>/scan-status",
        dossier_views.DocumentFileScanStatusView.as_view(),
        name="document-file-scan-status",
    ),
    path(
        "document-files/<uuid:file_id>/download",
        dossier_views.DocumentFileDownloadView.as_view(),
        name="document-file-download",
    ),
    # Paquetes para radicar (sección 19)
    path(
        "applications/<uuid:application_id>/document-package-jobs",
        package_views.ApplicationDocumentPackageJobView.as_view(),
        name="application-document-package-job-create",
    ),
    path(
        "document-package-jobs/<uuid:job_id>",
        package_views.DocumentPackageJobDetailView.as_view(),
        name="document-package-job-detail",
    ),
    path(
        "document-package-jobs/<uuid:job_id>/download",
        package_views.DocumentPackageJobDownloadView.as_view(),
        name="document-package-job-download",
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
    path(
        "buyer/document-files/<uuid:file_id>/download",
        buyer_views.BuyerDocumentFileDownloadView.as_view(),
        name="buyer-document-file-download",
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
