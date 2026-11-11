from django.urls import path

from apps.identity import buyer_access_views as views

app_name = "buyer_access"

urlpatterns = [
    path(
        "applications/<uuid:application_id>/buyer-access-links",
        views.ApplicationBuyerAccessLinksView.as_view(),
        name="application-buyer-access-links",
    ),
    path(
        "buyer-access-links/<uuid:link_id>",
        views.BuyerAccessLinkDetailView.as_view(),
        name="buyer-access-link-detail",
    ),
]
