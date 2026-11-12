"""Endpoints de catálogos (23.1), transiciones (23.5) y metadatos (sección 9)."""

import hashlib
import json
from collections.abc import Collection
from typing import Any, cast

from django.db.models import Count, QuerySet
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.catalogs import services
from apps.catalogs.models import Catalog, CatalogItem, WorkflowTransition
from apps.catalogs.serializers import (
    BootstrapSerializer,
    CatalogCreateSerializer,
    CatalogItemCreateSerializer,
    CatalogItemOrderSerializer,
    CatalogItemSerializer,
    CatalogItemUpdateSerializer,
    CatalogSerializer,
    CatalogUpdateSerializer,
    MetadataCatalogSerializer,
    WorkflowTransitionCreateSerializer,
    WorkflowTransitionSerializer,
    WorkflowTransitionUpdateSerializer,
)
from apps.catalogs.workflow import FlowType
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from config.filters import StrictOrderingFilter, parse_bool_param, parse_uuid_param
from config.serializers import ErrorSerializer

CATALOGS_TAG = "Configuration"
METADATA_TAG = "Metadata"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}


class PermissionCodeView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {}


# --------------------------------------------------------------------------------------
# Catálogos
# --------------------------------------------------------------------------------------


def _catalogs_queryset() -> QuerySet[Catalog]:
    return Catalog.objects.annotate(items_count=Count("items"))


class CatalogListView(PermissionCodeView):
    required_permissions = {"GET": "catalogs.read", "POST": "catalogs.create"}
    serializer_class = CatalogSerializer
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "created_at", "updated_at"]
    ordering = ["code"]

    def get_queryset(self) -> QuerySet[Catalog]:
        queryset = _catalogs_queryset()
        is_public = parse_bool_param(self.request, "is_public")
        if is_public is not None:
            queryset = queryset.filter(is_public=is_public)
        return queryset

    @extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="catalogs_list",
        summary="Listar catálogos",
        parameters=[OpenApiParameter("is_public", OpenApiTypes.BOOL)],
        responses={200: CatalogSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(CatalogSerializer(page, many=True).data)

    @extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="catalogs_create",
        summary="Crear un catálogo",
        request=CatalogCreateSerializer,
        responses={201: CatalogSerializer, 409: _error("DUPLICATE_CODE"), **COMMON_ERRORS},
    )
    def post(self, request: Request) -> Response:
        serializer = CatalogCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        catalog = services.create_catalog(**serializer.validated_data)
        return Response(
            CatalogSerializer(_catalogs_queryset().get(pk=catalog.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class CatalogDetailView(PermissionCodeView):
    required_permissions = {"GET": "catalogs.read", "PATCH": "catalogs.update"}

    def _get_catalog(self, catalog_id: Any) -> Catalog:
        return get_object_or_404(_catalogs_queryset(), pk=catalog_id)

    @extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="catalogs_retrieve",
        summary="Detalle y versión de un catálogo",
        responses={200: CatalogSerializer, 404: _error("RESOURCE_NOT_FOUND"), **COMMON_ERRORS},
    )
    def get(self, request: Request, catalog_id: Any) -> Response:
        return Response(CatalogSerializer(self._get_catalog(catalog_id)).data)

    @extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="catalogs_partial_update",
        summary="Actualizar los metadatos de un catálogo",
        request=CatalogUpdateSerializer,
        responses={
            200: CatalogSerializer,
            404: _error("RESOURCE_NOT_FOUND"),
            409: _error("CATALOG_NOT_MANAGEABLE"),
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, catalog_id: Any) -> Response:
        catalog = self._get_catalog(catalog_id)
        serializer = CatalogUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_catalog(catalog, dict(serializer.validated_data))
        return Response(CatalogSerializer(self._get_catalog(catalog_id)).data)


# --------------------------------------------------------------------------------------
# Valores de catálogo
# --------------------------------------------------------------------------------------


class CatalogItemListView(PermissionCodeView):
    required_permissions = {"GET": "catalogs.read", "POST": "catalogs.create"}
    serializer_class = CatalogItemSerializer
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = ["code", "label"]
    ordering_fields = ["sort_order", "label", "code", "created_at", "updated_at"]
    ordering = ["sort_order", "label"]

    def get_queryset(self) -> QuerySet[CatalogItem]:
        catalog = get_object_or_404(Catalog, pk=self.kwargs["catalog_id"])
        queryset = catalog.items.select_related("catalog")
        is_active = parse_bool_param(self.request, "is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        parent_id = parse_uuid_param(self.request, "parent_id")
        if parent_id:
            queryset = queryset.filter(parent_item_id=parent_id)
        return queryset

    @extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="catalogs_items_list",
        summary="Listar los valores de un catálogo",
        parameters=[
            OpenApiParameter("is_active", OpenApiTypes.BOOL),
            OpenApiParameter("parent_id", OpenApiTypes.UUID),
        ],
        responses={
            200: CatalogItemSerializer(many=True),
            404: _error("RESOURCE_NOT_FOUND"),
            **COMMON_ERRORS,
        },
    )
    def get(self, request: Request, catalog_id: Any) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(CatalogItemSerializer(page, many=True).data)

    @extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="catalogs_items_create",
        summary="Crear un valor en el catálogo",
        request=CatalogItemCreateSerializer,
        responses={
            201: CatalogItemSerializer,
            404: _error("RESOURCE_NOT_FOUND"),
            409: _error("DUPLICATE_CODE o CATALOG_NOT_MANAGEABLE"),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, catalog_id: Any) -> Response:
        catalog = get_object_or_404(Catalog, pk=catalog_id)
        serializer = CatalogItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.create_item(catalog, serializer.to_service_data())
        return Response(CatalogItemSerializer(item).data, status=status.HTTP_201_CREATED)


class CatalogItemOrderView(PermissionCodeView):
    required_permissions = {"PUT": "catalogs.update"}

    @extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="catalogs_items_order_update",
        summary="Reordenar los valores de un catálogo",
        description="`item_ids` debe incluir todos los valores del catálogo en el orden deseado.",
        request=CatalogItemOrderSerializer,
        responses={
            200: CatalogItemSerializer(many=True),
            404: _error("RESOURCE_NOT_FOUND"),
            409: _error("CATALOG_NOT_MANAGEABLE"),
            **COMMON_ERRORS,
        },
    )
    def put(self, request: Request, catalog_id: Any) -> Response:
        catalog = get_object_or_404(Catalog, pk=catalog_id)
        serializer = CatalogItemOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = services.reorder_items(catalog, serializer.validated_data["item_ids"])
        return Response(CatalogItemSerializer(items, many=True).data)


def _get_item(item_id: Any) -> CatalogItem:
    return get_object_or_404(CatalogItem.objects.select_related("catalog"), pk=item_id)


class CatalogItemDetailView(PermissionCodeView):
    required_permissions = {"GET": "catalogs.read", "PATCH": "catalogs.update"}

    @extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="catalog_items_retrieve",
        summary="Detalle de un valor de catálogo",
        responses={
            200: CatalogItemSerializer,
            404: _error("RESOURCE_NOT_FOUND"),
            **COMMON_ERRORS,
        },
    )
    def get(self, request: Request, item_id: Any) -> Response:
        return Response(CatalogItemSerializer(_get_item(item_id)).data)

    @extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="catalog_items_partial_update",
        summary="Cambiar etiqueta, descripción, metadatos o vigencia",
        request=CatalogItemUpdateSerializer,
        responses={
            200: CatalogItemSerializer,
            404: _error("RESOURCE_NOT_FOUND"),
            409: _error("CATALOG_NOT_MANAGEABLE"),
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, item_id: Any) -> Response:
        item = _get_item(item_id)
        serializer = CatalogItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.update_item(item, dict(serializer.validated_data))
        return Response(CatalogItemSerializer(item).data)


class _CatalogItemActivationView(PermissionCodeView):
    required_permissions = {"POST": "catalogs.update"}
    activate: bool

    def post(self, request: Request, item_id: Any) -> Response:
        item = services.set_item_active(_get_item(item_id), active=self.activate)
        return Response(CatalogItemSerializer(item).data)


_ACTIVATION_RESPONSES = {
    200: CatalogItemSerializer,
    404: _error("RESOURCE_NOT_FOUND"),
    409: _error("CATALOG_NOT_MANAGEABLE"),
    **COMMON_ERRORS,
}


@extend_schema_view(
    post=extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="catalog_items_activate",
        summary="Activar un valor",
        request=None,
        responses=_ACTIVATION_RESPONSES,
    )
)
class CatalogItemActivateView(_CatalogItemActivationView):
    activate = True


@extend_schema_view(
    post=extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="catalog_items_deactivate",
        summary="Desactivar un valor sin afectar los datos históricos",
        request=None,
        responses=_ACTIVATION_RESPONSES,
    )
)
class CatalogItemDeactivateView(_CatalogItemActivationView):
    activate = False


# --------------------------------------------------------------------------------------
# Transiciones de estado
# --------------------------------------------------------------------------------------


def _transitions_queryset() -> QuerySet[WorkflowTransition]:
    return WorkflowTransition.objects.select_related("required_permission").prefetch_related(
        "roles"
    )


class WorkflowTransitionListView(PermissionCodeView):
    required_permissions = {"GET": "workflow.read", "POST": "workflow.create"}
    serializer_class = WorkflowTransitionSerializer
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = ["code", "label"]
    ordering_fields = ["flow_type", "code", "from_status", "to_status", "created_at"]
    ordering = ["flow_type", "from_status", "code"]

    def get_queryset(self) -> QuerySet[WorkflowTransition]:
        queryset = _transitions_queryset()
        params = self.request.query_params
        flow_type = params.get("flow_type")
        if flow_type:
            if flow_type not in FlowType.values:
                raise ValidationError({"flow_type": ["Flujo no válido."]})
            queryset = queryset.filter(flow_type=flow_type)
        for name in ("from_status", "to_status"):
            if params.get(name):
                queryset = queryset.filter(**{name: params[name]})
        is_active = parse_bool_param(self.request, "is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset

    @extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="workflow_transitions_list",
        summary="Listar transiciones configuradas",
        parameters=[
            OpenApiParameter("flow_type", OpenApiTypes.STR, enum=FlowType.values),
            OpenApiParameter("from_status", OpenApiTypes.STR),
            OpenApiParameter("to_status", OpenApiTypes.STR),
            OpenApiParameter("is_active", OpenApiTypes.BOOL),
        ],
        responses={200: WorkflowTransitionSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(WorkflowTransitionSerializer(page, many=True).data)

    @extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="workflow_transitions_create",
        summary="Crear una transición (queda inactiva)",
        request=WorkflowTransitionCreateSerializer,
        responses={
            201: WorkflowTransitionSerializer,
            409: _error("DUPLICATE_CODE"),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = WorkflowTransitionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transition = services.create_transition(dict(serializer.validated_data))
        return Response(
            WorkflowTransitionSerializer(_transitions_queryset().get(pk=transition.pk)).data,
            status=status.HTTP_201_CREATED,
        )


def _get_transition(transition_id: Any) -> WorkflowTransition:
    return get_object_or_404(_transitions_queryset(), pk=transition_id)


class WorkflowTransitionDetailView(PermissionCodeView):
    required_permissions = {"GET": "workflow.read", "PATCH": "workflow.update"}

    @extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="workflow_transitions_retrieve",
        summary="Detalle, guarda y permiso requerido de una transición",
        responses={
            200: WorkflowTransitionSerializer,
            404: _error("RESOURCE_NOT_FOUND"),
            **COMMON_ERRORS,
        },
    )
    def get(self, request: Request, transition_id: Any) -> Response:
        return Response(WorkflowTransitionSerializer(_get_transition(transition_id)).data)

    @extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="workflow_transitions_partial_update",
        summary="Actualizar una transición inactiva",
        request=WorkflowTransitionUpdateSerializer,
        responses={
            200: WorkflowTransitionSerializer,
            404: _error("RESOURCE_NOT_FOUND"),
            409: _error("TRANSITION_NOT_EDITABLE"),
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, transition_id: Any) -> Response:
        transition = _get_transition(transition_id)
        serializer = WorkflowTransitionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_transition(transition, dict(serializer.validated_data))
        return Response(WorkflowTransitionSerializer(_get_transition(transition_id)).data)


class _TransitionActivationView(PermissionCodeView):
    required_permissions = {"POST": "workflow.publish"}
    activate: bool

    def post(self, request: Request, transition_id: Any) -> Response:
        services.set_transition_active(_get_transition(transition_id), active=self.activate)
        return Response(WorkflowTransitionSerializer(_get_transition(transition_id)).data)


_TRANSITION_ACTIVATION_RESPONSES = {
    200: WorkflowTransitionSerializer,
    404: _error("RESOURCE_NOT_FOUND"),
    **COMMON_ERRORS,
}


@extend_schema_view(
    post=extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="workflow_transitions_activate",
        summary="Habilitar una transición",
        request=None,
        responses=_TRANSITION_ACTIVATION_RESPONSES,
    )
)
class WorkflowTransitionActivateView(_TransitionActivationView):
    activate = True


@extend_schema_view(
    post=extend_schema(
        tags=[CATALOGS_TAG],
        operation_id="workflow_transitions_deactivate",
        summary="Deshabilitar una transición para operaciones futuras",
        request=None,
        responses=_TRANSITION_ACTIVATION_RESPONSES,
    )
)
class WorkflowTransitionDeactivateView(_TransitionActivationView):
    activate = False


# --------------------------------------------------------------------------------------
# Metadatos
# --------------------------------------------------------------------------------------


def _etag_for(body: Any) -> str:
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return f'"{hashlib.sha256(raw).hexdigest()[:32]}"'


def _conditional_response(request: Request, body: Any) -> Response:
    """Responde 304 si el cliente ya tiene esta versión (``If-None-Match``)."""
    etag = _etag_for(body)
    candidates = {
        value.strip().removeprefix("W/")
        for value in request.headers.get("If-None-Match", "").split(",")
        if value.strip()
    }
    if etag in candidates or "*" in candidates:
        response = Response(status=status.HTTP_304_NOT_MODIFIED)
    else:
        response = Response(body)
    response["ETag"] = etag
    # El navegador puede guardar la respuesta, pero debe revalidarla cada vez.
    response["Cache-Control"] = "private, no-cache"
    return response


class MetadataBootstrapView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[METADATA_TAG],
        operation_id="metadata_bootstrap",
        summary="Catálogos, permisos y configuración pública para iniciar el frontend",
        description="Soporta `If-None-Match`; responde `304` si los datos no cambiaron.",
        responses={
            200: BootstrapSerializer,
            304: OpenApiResponse(description="Sin cambios."),
            401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
        },
    )
    def get(self, request: Request) -> Response:
        return _conditional_response(request, services.bootstrap(cast(User, request.user)))


METADATA_CATALOG_DESCRIPTION = (
    "Para catálogos grandes o dependientes, como `municipality`. Filtra por "
    "`parent_code` (ej. el código DANE del departamento) o `parent_id`. Soporta "
    "`If-None-Match`."
)
METADATA_CATALOG_PARAMETERS = [
    OpenApiParameter("parent_code", OpenApiTypes.STR),
    OpenApiParameter("parent_id", OpenApiTypes.UUID),
]
METADATA_CATALOG_RESPONSES = {
    200: MetadataCatalogSerializer,
    304: OpenApiResponse(description="Sin cambios."),
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    404: _error("RESOURCE_NOT_FOUND"),
}


def metadata_catalog_response(
    request: Request, catalog_code: str, *, allowed: Collection[str] | None = None
) -> Response:
    """Valores activos y vigentes del catálogo, con sus filtros y el ``ETag``.

    La usan la vista interna y la del comprador. Con ``allowed``, un código fuera de la
    lista responde ``404`` igual que uno inexistente: no revela qué catálogos hay.
    """
    if allowed is not None and catalog_code not in allowed:
        raise Http404
    catalog = get_object_or_404(Catalog, code=catalog_code)
    body = services.catalog_metadata(
        catalog,
        parent_id=parse_uuid_param(request, "parent_id"),
        parent_code=request.query_params.get("parent_code") or None,
    )
    return _conditional_response(request, body)


class MetadataCatalogView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[METADATA_TAG],
        operation_id="metadata_catalogs_retrieve",
        summary="Valores activos y vigentes de un catálogo",
        description=METADATA_CATALOG_DESCRIPTION,
        parameters=METADATA_CATALOG_PARAMETERS,
        responses=METADATA_CATALOG_RESPONSES,
    )
    def get(self, request: Request, catalog_code: str) -> Response:
        return metadata_catalog_response(request, catalog_code)
