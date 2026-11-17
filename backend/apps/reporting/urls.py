from django.urls import path

from apps.reporting import report_views, views

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
    path("reports/funnel", report_views.ReportFunnelView.as_view(), name="reports-funnel"),
    # `applications.csv` va antes que cualquier ruta con parámetros bajo `applications`.
    path(
        "reports/applications.csv",
        report_views.ReportApplicationsCsvView.as_view(),
        name="reports-applications-csv",
    ),
    path(
        "reports/applications",
        report_views.ReportApplicationsView.as_view(),
        name="reports-applications",
    ),
]
