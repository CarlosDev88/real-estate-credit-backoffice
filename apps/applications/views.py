"""Endpoints de solicitudes de crédito (API §16) y `GET /clients/{id}/applications` (§13)."""

from typing import Any, cast

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications import services
from apps.applications.concurrency import IF_MATCH_HEADER, expected_version, with_etag
from apps.applications.models import CreditApplication
from apps.applications.serializers import (
    ApplicationCreateSerializer,
    ApplicationDetailSerializer,
    ApplicationSerializer,
    ApplicationSummarySerializer,
    ApplicationUpdateSerializer,
    AssignmentCreateSerializer,
)
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.services import CrmScope, clients_visible_to
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from config.filters import StrictOrderingFilter, parse_uuid_param
from config.serializers import ErrorSerializer

APPLICATIONS_TAG = "Applications"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND (inexistente o fuera del alcance)")}
IF_MATCH = OpenApiParameter(
    IF_MATCH_HEADER,
    OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    description='Versión de la solicitud que se editó, tal como llegó en `ETag` (`"3"`).',
)
STATUS_PARAM = OpenApiParameter("status", OpenApiTypes.STR, enum=ApplicationStatus.values)


class ApplicationView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {}

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)

    @property
    def scope(self) -> CrmScope:
        if not hasattr(self, "_scope"):
            self._scope = services.get_application_scope(self.actor)
        return self._scope

    def get_application(self, application_id: Any) -> CreditApplication:
        return get_object_or_404(services.applications_visible_to(self.actor), pk=application_id)

    def list_serializer_class(self) -> type[ApplicationSerializer | ApplicationSummarySerializer]:
        return ApplicationSummarySerializer if self.scope.is_restricted else ApplicationSerializer


def _choice_param(request: Request, name: str, choices: list[str]) -> str | None:
    value = request.query_params.get(name)
    if not value:
        return None
    if value not in choices:
        raise ValidationError({name: [f"Valor no permitido. Opciones: {', '.join(choices)}."]})
    return value


def _detail_response(view: ApplicationView, application_id: Any, **kwargs: Any) -> Response:
    """Detalle según el actor: el broker solo recibe el resumen."""
    application = view.get_application(application_id)
    serializer_class = (
        ApplicationSummarySerializer if view.scope.is_restricted else ApplicationDetailSerializer
    )
    return with_etag(Response(serializer_class(application).data, **kwargs), application.version)


class ApplicationListView(ApplicationView):
    required_permissions = {"GET": "applications.read", "POST": "applications.create"}
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = [
        "code",
        "opportunity__client__first_names",
        "opportunity__client__last_names",
        "opportunity__client__document_number",
    ]
    ordering_fields = ["created_at", "updated_at", "status", "code"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[CreditApplication]:
        applications = services.applications_visible_to(self.actor)
        application_status = _choice_param(self.request, "status", ApplicationStatus.values)
        if application_status:
            applications = applications.filter(status=application_status)
        for param, field in (
            ("bank_id", "bank_product__bank_id"),
            ("product_id", "bank_product_id"),
            ("advisor_id", "assigned_advisor_id"),
            ("project_id", "financed_property__project_id"),
        ):
            value = parse_uuid_param(self.request, param)
            if value:
                applications = applications.filter(**{field: value})
        for param, field in (
            ("purpose", "purpose_item__code"),
            ("origin", "opportunity__origin_item__code"),
        ):
            code = self.request.query_params.get(param)
            if code:
                applications = applications.filter(**{field: code})
        return applications

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_list",
        summary="Solicitudes según el alcance",
        description=(
            "El administrador ve todas, el asesor las asignadas y el broker el resumen de "
            "las solicitudes de las oportunidades que originó."
        ),
        parameters=[
            STATUS_PARAM,
            OpenApiParameter("bank_id", OpenApiTypes.UUID),
            OpenApiParameter("product_id", OpenApiTypes.UUID),
            OpenApiParameter("purpose", OpenApiTypes.STR, description="Código `loan_purpose`."),
            OpenApiParameter("advisor_id", OpenApiTypes.UUID),
            OpenApiParameter("project_id", OpenApiTypes.UUID),
            OpenApiParameter("origin", OpenApiTypes.STR, description="Código `lead_origin`."),
        ],
        responses={200: ApplicationSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        serializer_class = self.list_serializer_class()
        return self.get_paginated_response(serializer_class(page, many=True).data)

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_create",
        summary="Crear una solicitud DRAFT a partir de una oportunidad",
        description=(
            "Convierte la oportunidad (`CONVERTED`) en la misma transacción y crea el "
            "titular, el inmueble inicial, la asignación y el primer registro del "
            "historial. Sin `assigned_advisor_id` usa el asesor de la oportunidad. "
            "Una oportunidad ya convertida admite otro intento solo si los anteriores "
            "terminaron en `REJECTED`, `WITHDRAWN` o `CANCELLED`."
        ),
        request=ApplicationCreateSerializer,
        responses={
            201: ApplicationDetailSerializer,
            409: _error("APPLICATION_ALREADY_OPEN o INVALID_STATE_TRANSITION"),
            422: _error("ADVISOR_NOT_ELIGIBLE o PROJECT_NOT_ACTIVE"),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        opportunity = services.resolve_visible_opportunity(self.actor, data["opportunity_id"])
        property_data = serializer.property_values()
        if property_data is not None:
            property_data["project"] = services.resolve_property_project(
                self.actor, data["project_id"]
            )
        application = services.create_application(
            self.actor,
            opportunity=opportunity,
            purpose=data["purpose_code"],
            advisor=data["assigned_advisor_id"],
            property_data=property_data,
        )
        # Se responde con lo creado aunque quien lo creó no quede como asesor asignado.
        created = services.applications_queryset().get(pk=application.pk)
        return with_etag(
            Response(ApplicationDetailSerializer(created).data, status=status.HTTP_201_CREATED),
            created.version,
        )


class ApplicationDetailView(ApplicationView):
    required_permissions = {"GET": "applications.read", "PATCH": "applications.update"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_retrieve",
        summary="Expediente según el rol",
        description=(
            "Responde `ETag` con la versión, que se reenvía en `If-Match` al editar. El "
            "broker recibe solo el resumen."
        ),
        responses={200: ApplicationDetailSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        return _detail_response(self, application_id)

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_partial_update",
        summary="Cambiar la finalidad o el producto antes de radicar",
        description=(
            "El estado nunca cambia por `PATCH` (usa `/status-transitions`) ni el asesor "
            "(usa `/assignments`). Montos, plazo y modalidades van por `/financing`."
        ),
        parameters=[IF_MATCH],
        request=ApplicationUpdateSerializer,
        responses={
            200: ApplicationDetailSerializer,
            409: _error("STALE_VERSION o APPLICATION_NOT_EDITABLE"),
            428: _error("PRECONDITION_REQUIRED (falta If-Match)"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        version = expected_version(request)
        serializer = ApplicationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changes: dict[str, Any] = {}
        if "purpose_code" in serializer.validated_data:
            changes["purpose_item"] = serializer.validated_data["purpose_code"]
        if "bank_product_id" in serializer.validated_data:
            changes["bank_product"] = services.resolve_bank_product(
                serializer.validated_data["bank_product_id"]
            )
        services.update_application(
            self.actor, application, expected_version=version, changes=changes
        )
        return _detail_response(self, application_id)


class ApplicationSummaryView(ApplicationView):
    required_permissions = {"GET": "applications.read_summary"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_summary",
        summary="Resumen operativo de la solicitud",
        description="Sin datos financieros ni del inmueble. Es lo que ve el broker.",
        responses={200: ApplicationSummarySerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        return Response(ApplicationSummarySerializer(application).data)


class ApplicationAssignmentView(ApplicationView):
    required_permissions = {"POST": "applications.assign"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_assignments_create",
        summary="Reasignar el asesor responsable",
        description=(
            "Conserva el historial. No cambia la versión del expediente. Si quien reasigna "
            "deja de tener acceso, responde `204`."
        ),
        request=AssignmentCreateSerializer,
        responses={
            200: ApplicationDetailSerializer,
            204: OpenApiResponse(description="Reasignada; el actor ya no tiene acceso."),
            409: _error("APPLICATION_CLOSED"),
            422: _error("ADVISOR_NOT_ELIGIBLE"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        serializer = AssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.assign_application(
            self.actor,
            application,
            advisor=serializer.validated_data["advisor_id"],
            reason=serializer.validated_data["reason"],
        )
        if not services.applications_visible_to(self.actor).filter(pk=application.pk).exists():
            return Response(status=status.HTTP_204_NO_CONTENT)
        return _detail_response(self, application_id)


class ClientApplicationsView(ApplicationView):
    required_permissions = {"GET": "applications.read"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="clients_applications_list",
        summary="Solicitudes visibles en las que participa el cliente",
        parameters=[STATUS_PARAM],
        responses={200: ApplicationSerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, client_id: Any) -> Response:
        client = get_object_or_404(clients_visible_to(self.actor), pk=client_id)
        applications = services.client_applications(self.actor, client)
        application_status = _choice_param(request, "status", ApplicationStatus.values)
        if application_status:
            applications = applications.filter(status=application_status)
        page = self.paginate_queryset(applications.order_by("-created_at"))
        serializer_class = self.list_serializer_class()
        return self.get_paginated_response(serializer_class(page, many=True).data)
