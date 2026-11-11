from django.urls import path

from apps.identity import user_views as views

app_name = "users"

urlpatterns = [
    path("users", views.UserListView.as_view(), name="user-list"),
    path("users/<uuid:user_id>", views.UserDetailView.as_view(), name="user-detail"),
    path("users/<uuid:user_id>/activate", views.UserActivateView.as_view(), name="user-activate"),
    path(
        "users/<uuid:user_id>/deactivate",
        views.UserDeactivateView.as_view(),
        name="user-deactivate",
    ),
    path("users/<uuid:user_id>/roles", views.UserRolesView.as_view(), name="user-roles"),
    path("roles", views.RoleListView.as_view(), name="role-list"),
]
