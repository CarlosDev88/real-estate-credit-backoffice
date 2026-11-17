from django.urls import path

from apps.commissions import views

app_name = "commissions"

urlpatterns = [
    path("commission-plans", views.CommissionPlanListView.as_view(), name="plan-list"),
    path(
        "commission-plans/<uuid:plan_id>",
        views.CommissionPlanDetailView.as_view(),
        name="plan-detail",
    ),
    path(
        "commission-plans/<uuid:plan_id>/close",
        views.CommissionPlanCloseView.as_view(),
        name="plan-close",
    ),
]
