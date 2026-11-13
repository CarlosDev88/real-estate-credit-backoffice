from django.urls import path

from apps.filings import views

app_name = "filings"

urlpatterns = [
    # Radicaciones (API §20.1)
    path(
        "applications/<uuid:application_id>/filings",
        views.ApplicationFilingListView.as_view(),
        name="application-filings",
    ),
    path("filings/<uuid:filing_id>", views.FilingDetailView.as_view(), name="filing-detail"),
    path(
        "filings/<uuid:filing_id>/document-snapshots",
        views.FilingDocumentSnapshotListView.as_view(),
        name="filing-document-snapshots",
    ),
    # Respuestas del banco (API §20.2)
    path(
        "filings/<uuid:filing_id>/responses",
        views.FilingResponseListView.as_view(),
        name="filing-responses",
    ),
    path(
        "filing-responses/<uuid:response_id>",
        views.FilingResponseDetailView.as_view(),
        name="filing-response-detail",
    ),
    path(
        "filing-responses/<uuid:response_id>/evidence",
        views.FilingResponseEvidenceView.as_view(),
        name="filing-response-evidence",
    ),
    path(
        "filing-responses/<uuid:response_id>/evidence/download",
        views.FilingResponseEvidenceDownloadView.as_view(),
        name="filing-response-evidence-download",
    ),
]
