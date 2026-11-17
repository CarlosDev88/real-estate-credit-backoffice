from django.urls import path

from apps.workday import views

app_name = "workday"

urlpatterns = [
    path(
        "workday/applications",
        views.WorkdayApplicationListView.as_view(),
        name="applications",
    ),
    path("workday/summary", views.WorkdaySummaryView.as_view(), name="summary"),
]
