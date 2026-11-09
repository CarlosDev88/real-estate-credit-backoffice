from django.urls import path

from apps.identity import buyer_portal_views as views
from apps.identity import buyer_profile_views as profile_views

app_name = "buyer_portal"

urlpatterns = [
    path("buyer-access/consume", views.BuyerAccessConsumeView.as_view(), name="consume"),
    path("buyer/session", views.BuyerSessionView.as_view(), name="session"),
    path("buyer/session/logout", views.BuyerLogoutView.as_view(), name="logout"),
    path("buyer/processes", views.BuyerProcessesView.as_view(), name="processes"),
    path(
        "buyer/applications/<uuid:application_id>",
        views.BuyerApplicationDetailView.as_view(),
        name="application-detail",
    ),
    path(
        "buyer/applications/<uuid:application_id>/consents",
        views.BuyerConsentsView.as_view(),
        name="consents",
    ),
    path(
        "buyer/applications/<uuid:application_id>/profile",
        profile_views.BuyerProfileView.as_view(),
        name="profile",
    ),
    path(
        "buyer/applications/<uuid:application_id>/participants",
        profile_views.BuyerParticipantsView.as_view(),
        name="participants",
    ),
    path(
        "buyer/participants/<uuid:participant_id>/financial-profile",
        profile_views.BuyerFinancialProfileView.as_view(),
        name="financial-profile",
    ),
    path(
        "buyer/participants/<uuid:participant_id>/financial-profile/confirmation",
        profile_views.BuyerFinancialProfileConfirmationView.as_view(),
        name="financial-profile-confirmation",
    ),
    path(
        "buyer/financial-profiles/<uuid:profile_id>/income-sources",
        profile_views.BuyerIncomeSourcesView.as_view(),
        name="income-sources",
    ),
    path(
        "buyer/income-sources/<uuid:income_source_id>",
        profile_views.BuyerIncomeSourceDetailView.as_view(),
        name="income-source-detail",
    ),
]
