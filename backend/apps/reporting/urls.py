from django.urls import path

from apps.reporting import export_views, report_views, views

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
    path(
        "reports/applications/export-jobs",
        export_views.ApplicationExportJobsView.as_view(),
        name="reports-applications-export-jobs",
    ),
    path(
        "report-export-jobs/<uuid:job_id>",
        export_views.ReportExportJobDetailView.as_view(),
        name="report-export-job",
    ),
    path(
        "report-export-jobs/<uuid:job_id>/download",
        export_views.ReportExportJobDownloadView.as_view(),
        name="report-export-job-download",
    ),
]
