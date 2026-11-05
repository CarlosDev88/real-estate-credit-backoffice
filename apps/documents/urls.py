from django.urls import path

from apps.documents import views

app_name = "documents"

urlpatterns = [
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
