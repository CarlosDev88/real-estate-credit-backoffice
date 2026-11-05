from django.urls import path

from apps.applications import views

app_name = "applications"

urlpatterns = [
    # Solicitudes (sección 16)
    path("applications", views.ApplicationListView.as_view(), name="application-list"),
    path(
        "applications/<uuid:application_id>",
        views.ApplicationDetailView.as_view(),
        name="application-detail",
    ),
    path(
        "applications/<uuid:application_id>/summary",
        views.ApplicationSummaryView.as_view(),
        name="application-summary",
    ),
    path(
        "applications/<uuid:application_id>/assignments",
        views.ApplicationAssignmentView.as_view(),
        name="application-assignments",
    ),
    # Solicitudes del cliente (sección 13)
    path(
        "clients/<uuid:client_id>/applications",
        views.ClientApplicationsView.as_view(),
        name="client-applications",
    ),
]
