"""Endpoints de clientes (sección 13) y oportunidades (sección 14)."""

from typing import Any, cast

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.catalogs.workflow import OpportunityStatus
from apps.crm import services
from apps.crm.models import Client, ClientAddress, Opportunity
from apps.crm.serializers import (
    AddressCreateSerializer,
    AddressSerializer,
    AddressUpdateSerializer,
    AssignmentCreateSerializer,
    BrokerClientSerializer,
    BrokerClientUpdateSerializer,
    BrokerOpportunitySerializer,
    ClientCreateSerializer,
    ClientDetailSerializer,
    ClientSerializer,
    ClientUpdateSerializer,
    OpportunityCreateSerializer,
    OpportunityDetailSerializer,
    OpportunitySerializer,
    OpportunityTransitionSerializer,
    OpportunityUpdateSerializer,
)
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from config.filters import StrictOrderingFilter, parse_uuid_param
from config.serializers import ErrorSerializer

CLIENTS_TAG = "Clients"
OPPORTUNITIES_TAG = "Opportunities"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND (inexistente o fuera del alcance)")}


class CrmView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {}

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)

    @property
    def scope(self) -> services.CrmScope:
        if not hasattr(self, "_scope"):
            self._scope = services.get_scope(self.actor)
        return self._scope


def _choice_param(request: Request, name: str, choices: list[str]) -> str | None:
    value = request.query_params.get(name)
    if not value:
        return None
    if value not in choices:
        raise ValidationError({name: [f"Valor no permitido. Opciones: {', '.join(choices)}."]})
    return value


# --------------------------------------------------------------------------------------
# Clientes
# --------------------------------------------------------------------------------------


def _client_data(view: CrmView, client: Client, *, detail: bool = False) -> dict[str, Any]:
    if view.scope.is_restricted:
        return BrokerClientSerializer(client).data
    if detail:
        client = view_client_queryset(view).get(pk=client.pk)
        return ClientDetailSerializer(client).data
    return ClientSerializer(client).data


def view_client_queryset(view: CrmView) -> QuerySet[Client]:
    return services.clients_visible_to(view.actor).prefetch_related(
        "addresses__address_type_item", "addresses__city_item"
    )


class ClientListView(CrmView):
    required_permissions = {"GET": "clients.read", "POST": "clients.create"}
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = ["first_names", "last_names", "email", "document_number"]
    ordering_fields = ["last_names", "first_names", "created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[Client]:
        clients = services.clients_visible_to(self.actor)
        params = self.request.query_params
        if params.get("document_type"):
            clients = clients.filter(document_type_item__code=params["document_type"])
        if params.get("origin"):
            clients = clients.filter(origin_item__code=params["origin"])
        return clients

    @extend_schema(
        tags=[CLIENTS_TAG],
        operation_id="clients_list",
        summary="Clientes dentro del alcance",
        description="El broker recibe solo datos de contacto y el documento enmascarado.",
        parameters=[
            OpenApiParameter("document_type", OpenApiTypes.STR, description="Ej. CC."),
            OpenApiParameter("origin", OpenApiTypes.STR, description="Código de `lead_origin`."),
        ],
        responses={200: ClientSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        serializer_class = BrokerClientSerializer if self.scope.is_restricted else ClientSerializer
        return self.get_paginated_response(serializer_class(page, many=True).data)

    @extend_schema(
        tags=[CLIENTS_TAG],
        operation_id="clients_create",
        summary="Crear un cliente",
        request=ClientCreateSerializer,
        responses={
            201: ClientSerializer,
            409: _error(
                "DUPLICATE_CLIENT_DOCUMENT. Si el cliente es visible para el usuario, "
                "`details[0].resource_id` trae su id."
            ),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ClientCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client = services.create_client(self.actor, serializer.to_service_data())
        return Response(_client_data(self, client), status=status.HTTP_201_CREATED)


class ClientDetailView(CrmView):
    required_permissions = {"GET": "clients.read", "PATCH": "clients.update"}

    def _get_client(self, client_id: Any) -> Client:
        return get_object_or_404(services.clients_visible_to(self.actor), pk=client_id)

    @extend_schema(
        tags=[CLIENTS_TAG],
        operation_id="clients_retrieve",
        summary="Detalle del cliente según el rol",
        responses={200: ClientDetailSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, client_id: Any) -> Response:
        return Response(_client_data(self, self._get_client(client_id), detail=True))

    @extend_schema(
        tags=[CLIENTS_TAG],
        operation_id="clients_partial_update",
        summary="Actualizar un cliente",
        description="El broker solo puede cambiar datos de contacto, no el documento.",
        request=ClientUpdateSerializer,
        responses={
            200: ClientDetailSerializer,
            409: _error("DUPLICATE_CLIENT_DOCUMENT"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, client_id: Any) -> Response:
        client = self._get_client(client_id)
        serializer: ClientUpdateSerializer | BrokerClientUpdateSerializer
        if self.scope.is_restricted:
            serializer = BrokerClientUpdateSerializer(data=request.data)
        else:
            serializer = ClientUpdateSerializer(data=request.data, client=client)
        serializer.is_valid(raise_exception=True)
        services.update_client(self.actor, client, serializer.to_service_data())
        return Response(_client_data(self, client, detail=True))


class ClientOpportunitiesView(CrmView):
    required_permissions = {"GET": "clients.read"}

    @extend_schema(
        tags=[CLIENTS_TAG],
        operation_id="clients_opportunities_list",
        summary="Oportunidades del cliente visibles para el usuario",
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, enum=OpportunityStatus.values),
            OpenApiParameter("project_id", OpenApiTypes.UUID),
        ],
        responses={200: OpportunitySerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, client_id: Any) -> Response:
        client = get_object_or_404(services.clients_visible_to(self.actor), pk=client_id)
        opportunities = services.opportunities_visible_to(self.actor).filter(client=client)
        opportunity_status = _choice_param(request, "status", OpportunityStatus.values)
        if opportunity_status:
            opportunities = opportunities.filter(status=opportunity_status)
        project_id = parse_uuid_param(request, "project_id")
        if project_id:
            opportunities = opportunities.filter(project_id=project_id)
        page = self.paginate_queryset(opportunities.order_by("-created_at"))
        serializer_class = (
            BrokerOpportunitySerializer if self.scope.is_restricted else OpportunitySerializer
        )
        return self.get_paginated_response(serializer_class(page, many=True).data)


class _InternalOnlyMixin(CrmView):
    """Direcciones: no forman parte del resumen que recibe el broker."""

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if self.scope.is_restricted:
            raise PermissionDenied()


class ClientAddressListView(_InternalOnlyMixin):
    required_permissions = {"GET": "clients.read", "POST": "clients.update"}

    @extend_schema(
        tags=[CLIENTS_TAG],
        operation_id="clients_addresses_list",
        summary="Direcciones del cliente",
        responses={200: AddressSerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, client_id: Any) -> Response:
        client = get_object_or_404(services.clients_visible_to(self.actor), pk=client_id)
        addresses = client.addresses.select_related("address_type_item", "city_item")
        page = self.paginate_queryset(addresses)
        return self.get_paginated_response(AddressSerializer(page, many=True).data)

    @extend_schema(
        tags=[CLIENTS_TAG],
        operation_id="clients_addresses_create",
        summary="Agregar una dirección (la primera queda como principal)",
        request=AddressCreateSerializer,
        responses={201: AddressSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def post(self, request: Request, client_id: Any) -> Response:
        client = get_object_or_404(services.clients_visible_to(self.actor), pk=client_id)
        serializer = AddressCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address = services.add_address(client, serializer.to_service_data())
        return Response(AddressSerializer(address).data, status=status.HTTP_201_CREATED)


class ClientAddressDetailView(_InternalOnlyMixin):
    required_permissions = {"PATCH": "clients.update", "DELETE": "clients.update"}

    def _get_address(self, address_id: Any) -> ClientAddress:
        visible_clients = services.clients_visible_to(self.actor)
        return get_object_or_404(
            ClientAddress.objects.select_related("address_type_item", "city_item").filter(
                client__in=visible_clients
            ),
            pk=address_id,
        )

    @extend_schema(
        tags=[CLIENTS_TAG],
        operation_id="client_addresses_partial_update",
        summary="Editar una dirección",
        request=AddressUpdateSerializer,
        responses={200: AddressSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def patch(self, request: Request, address_id: Any) -> Response:
        address = self._get_address(address_id)
        serializer = AddressUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_address(address, serializer.to_service_data())
        return Response(AddressSerializer(self._get_address(address_id)).data)

    @extend_schema(
        tags=[CLIENTS_TAG],
        operation_id="client_addresses_destroy",
        summary="Eliminar una dirección",
        responses={204: None, **NOT_FOUND, **COMMON_ERRORS},
    )
    def delete(self, request: Request, address_id: Any) -> Response:
        services.delete_address(self._get_address(address_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------------------
# Oportunidades
# --------------------------------------------------------------------------------------


def _opportunity_data(view: CrmView, opportunity_id: Any) -> dict[str, Any]:
    opportunity = _get_opportunity(view, opportunity_id)
    if view.scope.is_restricted:
        return BrokerOpportunitySerializer(opportunity).data
    return OpportunityDetailSerializer(
        opportunity,
        context={"available_actions": services.available_actions(view.actor, opportunity)},
    ).data


def _get_opportunity(view: CrmView, opportunity_id: Any) -> Opportunity:
    return get_object_or_404(services.opportunities_visible_to(view.actor), pk=opportunity_id)


class OpportunityListView(CrmView):
    required_permissions = {"GET": "opportunities.read", "POST": "opportunities.create"}
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = [
        "client__first_names",
        "client__last_names",
        "client__document_number",
        "project__name",
    ]
    ordering_fields = ["created_at", "updated_at", "status"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[Opportunity]:
        opportunities = services.opportunities_visible_to(self.actor)
        opportunity_status = _choice_param(self.request, "status", OpportunityStatus.values)
        if opportunity_status:
            opportunities = opportunities.filter(status=opportunity_status)
        for param, field in (
            ("broker_id", "origin_user_id"),
            ("advisor_id", "assigned_advisor_id"),
            ("project_id", "project_id"),
            ("client_id", "client_id"),
        ):
            value = parse_uuid_param(self.request, param)
            if value:
                opportunities = opportunities.filter(**{field: value})
        return opportunities

    @extend_schema(
        tags=[OPPORTUNITIES_TAG],
        operation_id="opportunities_list",
        summary="Oportunidades según el alcance",
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, enum=OpportunityStatus.values),
            OpenApiParameter("broker_id", OpenApiTypes.UUID, description="Originador."),
            OpenApiParameter("advisor_id", OpenApiTypes.UUID),
            OpenApiParameter("project_id", OpenApiTypes.UUID),
            OpenApiParameter("client_id", OpenApiTypes.UUID),
        ],
        responses={200: OpportunitySerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        serializer_class = (
            BrokerOpportunitySerializer if self.scope.is_restricted else OpportunitySerializer
        )
        return self.get_paginated_response(serializer_class(page, many=True).data)

    @extend_schema(
        tags=[OPPORTUNITIES_TAG],
        operation_id="opportunities_create",
        summary="Crear una oportunidad NEW",
        description="Si llega `project_id`, el proyecto debe estar `ACTIVE`.",
        request=OpportunityCreateSerializer,
        responses={
            201: OpportunityDetailSerializer,
            409: _error("DUPLICATE_OPPORTUNITY"),
            422: _error("PROJECT_NOT_ACTIVE"),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = OpportunityCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        opportunity = services.create_opportunity(
            self.actor,
            client=services.resolve_visible_client(self.actor, data["client_id"]),
            project=services.resolve_project_for_opportunity(self.actor, data["project_id"]),
            origin_item=data["origin_type"],
        )
        return Response(_opportunity_data(self, opportunity.pk), status=status.HTTP_201_CREATED)


class OpportunityDetailView(CrmView):
    required_permissions = {"GET": "opportunities.read", "PATCH": "opportunities.update"}

    @extend_schema(
        tags=[OPPORTUNITIES_TAG],
        operation_id="opportunities_retrieve",
        summary="Detalle de la oportunidad, acciones disponibles e historial de asesores",
        responses={200: OpportunityDetailSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, opportunity_id: Any) -> Response:
        return Response(_opportunity_data(self, opportunity_id))

    @extend_schema(
        tags=[OPPORTUNITIES_TAG],
        operation_id="opportunities_partial_update",
        summary="Cambiar el origen o el proyecto de una oportunidad abierta",
        request=OpportunityUpdateSerializer,
        responses={
            200: OpportunityDetailSerializer,
            409: _error("OPPORTUNITY_NOT_EDITABLE o DUPLICATE_OPPORTUNITY"),
            422: _error("PROJECT_NOT_ACTIVE"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, opportunity_id: Any) -> Response:
        opportunity = _get_opportunity(self, opportunity_id)
        serializer = OpportunityUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changes: dict[str, Any] = {}
        if "origin_type" in serializer.validated_data:
            changes["origin_item"] = serializer.validated_data["origin_type"]
        if "project_id" in serializer.validated_data:
            changes["project"] = services.resolve_project_for_opportunity(
                self.actor, serializer.validated_data["project_id"]
            )
        services.update_opportunity(opportunity, changes)
        return Response(_opportunity_data(self, opportunity_id))


class OpportunityAssignmentView(CrmView):
    required_permissions = {"POST": "opportunities.assign"}

    @extend_schema(
        tags=[OPPORTUNITIES_TAG],
        operation_id="opportunities_assignments_create",
        summary="Asignar o reasignar el asesor responsable",
        description="Conserva el historial. Si la oportunidad estaba `NEW`, pasa a `ASSIGNED`.",
        request=AssignmentCreateSerializer,
        responses={
            200: OpportunityDetailSerializer,
            409: _error("OPPORTUNITY_NOT_EDITABLE"),
            422: _error("ADVISOR_NOT_ELIGIBLE"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, opportunity_id: Any) -> Response:
        opportunity = _get_opportunity(self, opportunity_id)
        serializer = AssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.assign_advisor(
            self.actor,
            opportunity,
            advisor=serializer.validated_data["advisor_id"],
            reason=serializer.validated_data["reason"],
        )
        # Tras reasignar, quien asignó puede quedar sin acceso: se responde con lo asignado.
        detail = services.opportunities_visible_to(self.actor).filter(pk=opportunity.pk).first()
        if detail is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(_opportunity_data(self, opportunity_id))


class OpportunityTransitionView(CrmView):
    required_permissions = {"POST": "opportunities.transition"}

    @extend_schema(
        tags=[OPPORTUNITIES_TAG],
        operation_id="opportunities_transitions_create",
        summary="Cambiar el estado de la oportunidad",
        description="`reason_code` (catálogo `opportunity_lost_reason`) es obligatorio para LOST.",
        request=OpportunityTransitionSerializer,
        responses={
            200: OpportunityDetailSerializer,
            409: _error("INVALID_STATE_TRANSITION"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, opportunity_id: Any) -> Response:
        opportunity = _get_opportunity(self, opportunity_id)
        serializer = OpportunityTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.transition_opportunity(
            self.actor,
            opportunity,
            to_status=serializer.validated_data["target_status"],
            lost_reason=serializer.validated_data["reason_code"],
            comment=serializer.validated_data["comment"],
        )
        return Response(_opportunity_data(self, opportunity_id))


class BrokerOpportunityListView(CrmView):
    required_permissions = {"GET": "opportunities.read"}
    filter_backends = [StrictOrderingFilter]
    ordering_fields = ["created_at", "updated_at", "status"]
    ordering = ["-updated_at"]

    def get_queryset(self) -> QuerySet[Opportunity]:
        if not self.scope.is_broker:
            raise PermissionDenied("Esta bandeja es solo para brokers.")
        opportunities = services.opportunities_visible_to(self.actor).filter(origin_user=self.actor)
        opportunity_status = _choice_param(self.request, "status", OpportunityStatus.values)
        if opportunity_status:
            opportunities = opportunities.filter(status=opportunity_status)
        return opportunities

    @extend_schema(
        tags=[OPPORTUNITIES_TAG],
        operation_id="broker_opportunities_list",
        summary="Bandeja del broker: resumen de sus prospectos",
        parameters=[OpenApiParameter("status", OpenApiTypes.STR, enum=OpportunityStatus.values)],
        responses={200: BrokerOpportunitySerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(BrokerOpportunitySerializer(page, many=True).data)
