from django.urls import path

from apps.reporting import views

app_name = "reporting"

urlpatterns = [
    path("dashboard/summary", views.DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("dashboard/funnel", views.DashboardFunnelView.as_view(), name="dashboard-funnel"),
    path("dashboard/workload", views.DashboardWorkloadView.as_view(), name="dashboard-workload"),
    path(
        "dashboard/bank-results",
        views.DashboardBankResultsView.as_view(),
        name="dashboard-bank-results",
    ),
]
