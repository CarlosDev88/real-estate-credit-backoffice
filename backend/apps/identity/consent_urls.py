from django.urls import path

from apps.identity import consent_views as views

app_name = "consents"

urlpatterns = [
    path(
        "applications/<uuid:application_id>/consents",
        views.ApplicationConsentsView.as_view(),
        name="application-consents",
    ),
]
