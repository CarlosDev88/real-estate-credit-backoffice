from django.urls import path

from apps.partners import views

app_name = "partners"

urlpatterns = [
    # Constructoras (sección 11.1)
    path("partners", views.PartnerListView.as_view(), name="partner-list"),
    path("partners/<uuid:partner_id>", views.PartnerDetailView.as_view(), name="partner-detail"),
    path(
        "partners/<uuid:partner_id>/activate",
        views.PartnerActivateView.as_view(),
        name="partner-activate",
    ),
    path(
        "partners/<uuid:partner_id>/deactivate",
        views.PartnerDeactivateView.as_view(),
        name="partner-deactivate",
    ),
    # Membresías (sección 11.2)
    path(
        "partners/<uuid:partner_id>/members",
        views.PartnerMemberListView.as_view(),
        name="partner-member-list",
    ),
    path(
        "partner-memberships/<uuid:membership_id>",
        views.MembershipDetailView.as_view(),
        name="partner-membership-detail",
    ),
    # Proyectos (sección 12)
    path("projects", views.ProjectListView.as_view(), name="project-list"),
    path("projects/<uuid:project_id>", views.ProjectDetailView.as_view(), name="project-detail"),
    path(
        "projects/<uuid:project_id>/submit",
        views.ProjectSubmitView.as_view(),
        name="project-submit",
    ),
    path(
        "projects/<uuid:project_id>/activate",
        views.ProjectActivateView.as_view(),
        name="project-activate",
    ),
    path(
        "projects/<uuid:project_id>/reject",
        views.ProjectRejectView.as_view(),
        name="project-reject",
    ),
    path(
        "projects/<uuid:project_id>/archive",
        views.ProjectArchiveView.as_view(),
        name="project-archive",
    ),
]
