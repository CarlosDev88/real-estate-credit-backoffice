from django.urls import path

from apps.tasks import views

app_name = "tasks"

urlpatterns = [
    path("tasks", views.TaskListView.as_view(), name="list"),
    path("tasks/<uuid:task_id>", views.TaskDetailView.as_view(), name="detail"),
    path("tasks/<uuid:task_id>/complete", views.TaskCompleteView.as_view(), name="complete"),
    path("tasks/<uuid:task_id>/cancel", views.TaskCancelView.as_view(), name="cancel"),
]
