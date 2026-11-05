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
    # Participantes, perfil financiero e ingresos (sección 17)
    path(
        "applications/<uuid:application_id>/participants",
        views.ApplicationParticipantListView.as_view(),
        name="application-participants",
    ),
    path(
        "application-participants/<uuid:participant_id>",
        views.ApplicationParticipantDetailView.as_view(),
        name="application-participant-detail",
    ),
    path(
        "application-participants/<uuid:participant_id>/financial-profile",
        views.FinancialProfileView.as_view(),
        name="application-participant-financial-profile",
    ),
    path(
        "financial-profiles/<uuid:profile_id>/income-sources",
        views.IncomeSourceListView.as_view(),
        name="financial-profile-income-sources",
    ),
    path(
        "income-sources/<uuid:income_source_id>",
        views.IncomeSourceDetailView.as_view(),
        name="income-source-detail",
    ),
    # Inmueble y financiación (sección 18)
    path(
        "applications/<uuid:application_id>/property",
        views.ApplicationPropertyView.as_view(),
        name="application-property",
    ),
    path(
        "applications/<uuid:application_id>/financing",
        views.ApplicationFinancingView.as_view(),
        name="application-financing",
    ),
    # Solicitudes del cliente (sección 13)
    path(
        "clients/<uuid:client_id>/applications",
        views.ClientApplicationsView.as_view(),
        name="client-applications",
    ),
]
