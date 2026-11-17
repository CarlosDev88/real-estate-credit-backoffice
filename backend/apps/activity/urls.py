from django.urls import path

from apps.activity import views

app_name = "activity"

urlpatterns = [
    path(
        "applications/<uuid:application_id>/activity",
        views.ApplicationActivityView.as_view(),
        name="application-activity",
    ),
    path(
        "applications/<uuid:application_id>/notes",
        views.ApplicationNotesView.as_view(),
        name="application-notes",
    ),
    path(
        "buyer/applications/<uuid:application_id>/activity",
        views.BuyerActivityView.as_view(),
        name="buyer-activity",
    ),
]
