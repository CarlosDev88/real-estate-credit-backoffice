from django.urls import path

from apps.identity import invitation_views as views

app_name = "invitations"

urlpatterns = [
    path("invitations", views.InvitationListView.as_view(), name="invitation-list"),
    path("invitations/accept", views.InvitationAcceptView.as_view(), name="invitation-accept"),
    path(
        "invitations/<uuid:invitation_id>",
        views.InvitationDetailView.as_view(),
        name="invitation-detail",
    ),
    path(
        "invitations/<uuid:invitation_id>/resend",
        views.InvitationResendView.as_view(),
        name="invitation-resend",
    ),
]
