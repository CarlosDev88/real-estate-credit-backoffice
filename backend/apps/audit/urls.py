from django.urls import path

from apps.audit import views

app_name = "audit"

urlpatterns = [
    path("audit-events", views.AuditEventListView.as_view(), name="list"),
    path("audit-events/<uuid:event_id>", views.AuditEventDetailView.as_view(), name="detail"),
]
