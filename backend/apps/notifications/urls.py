from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    # Comprador (API §21.2)
    path(
        "buyer/notifications",
        views.BuyerNotificationListView.as_view(),
        name="buyer-notifications",
    ),
    path(
        "buyer/notifications/unread-count",
        views.BuyerNotificationUnreadCountView.as_view(),
        name="buyer-notifications-unread-count",
    ),
    path(
        "buyer/notifications/read-all",
        views.BuyerNotificationReadAllView.as_view(),
        name="buyer-notifications-read-all",
    ),
    path(
        "buyer/notifications/<uuid:notification_id>/read",
        views.BuyerNotificationReadView.as_view(),
        name="buyer-notification-read",
    ),
    # Backoffice
    path(
        "applications/<uuid:application_id>/notifications",
        views.ApplicationNotificationListView.as_view(),
        name="application-notifications",
    ),
]
