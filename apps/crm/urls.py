from django.urls import path

from apps.crm import views

app_name = "crm"

urlpatterns = [
    # Clientes (sección 13)
    path("clients", views.ClientListView.as_view(), name="client-list"),
    path("clients/<uuid:client_id>", views.ClientDetailView.as_view(), name="client-detail"),
    path(
        "clients/<uuid:client_id>/opportunities",
        views.ClientOpportunitiesView.as_view(),
        name="client-opportunities",
    ),
    path(
        "clients/<uuid:client_id>/addresses",
        views.ClientAddressListView.as_view(),
        name="client-address-list",
    ),
    path(
        "client-addresses/<uuid:address_id>",
        views.ClientAddressDetailView.as_view(),
        name="client-address-detail",
    ),
    # Oportunidades (sección 14)
    path("opportunities", views.OpportunityListView.as_view(), name="opportunity-list"),
    path(
        "opportunities/<uuid:opportunity_id>",
        views.OpportunityDetailView.as_view(),
        name="opportunity-detail",
    ),
    path(
        "opportunities/<uuid:opportunity_id>/assignments",
        views.OpportunityAssignmentView.as_view(),
        name="opportunity-assignments",
    ),
    path(
        "opportunities/<uuid:opportunity_id>/transitions",
        views.OpportunityTransitionView.as_view(),
        name="opportunity-transitions",
    ),
    path(
        "broker/opportunities",
        views.BrokerOpportunityListView.as_view(),
        name="broker-opportunity-list",
    ),
]
