from django.urls import path

from apps.identity import buyer_portal_views as views

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
]
