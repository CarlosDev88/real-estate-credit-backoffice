from django.urls import path

from apps.catalogs import views

app_name = "catalogs"

urlpatterns = [
    # Catálogos y valores (sección 23.1)
    path("catalogs", views.CatalogListView.as_view(), name="catalog-list"),
    path("catalogs/<uuid:catalog_id>", views.CatalogDetailView.as_view(), name="catalog-detail"),
    path(
        "catalogs/<uuid:catalog_id>/items",
        views.CatalogItemListView.as_view(),
        name="catalog-item-list",
    ),
    path(
        "catalogs/<uuid:catalog_id>/items/order",
        views.CatalogItemOrderView.as_view(),
        name="catalog-item-order",
    ),
    path(
        "catalog-items/<uuid:item_id>",
        views.CatalogItemDetailView.as_view(),
        name="catalog-item-detail",
    ),
    path(
        "catalog-items/<uuid:item_id>/activate",
        views.CatalogItemActivateView.as_view(),
        name="catalog-item-activate",
    ),
    path(
        "catalog-items/<uuid:item_id>/deactivate",
        views.CatalogItemDeactivateView.as_view(),
        name="catalog-item-deactivate",
    ),
    # Transiciones de estado (sección 23.5)
    path(
        "workflow-transitions",
        views.WorkflowTransitionListView.as_view(),
        name="workflow-transition-list",
    ),
    path(
        "workflow-transitions/<uuid:transition_id>",
        views.WorkflowTransitionDetailView.as_view(),
        name="workflow-transition-detail",
    ),
    path(
        "workflow-transitions/<uuid:transition_id>/activate",
        views.WorkflowTransitionActivateView.as_view(),
        name="workflow-transition-activate",
    ),
    path(
        "workflow-transitions/<uuid:transition_id>/deactivate",
        views.WorkflowTransitionDeactivateView.as_view(),
        name="workflow-transition-deactivate",
    ),
    # Metadatos para el frontend (sección 9)
    path("metadata/bootstrap", views.MetadataBootstrapView.as_view(), name="metadata-bootstrap"),
    path(
        "metadata/catalogs/<str:catalog_code>",
        views.MetadataCatalogView.as_view(),
        name="metadata-catalog",
    ),
]
