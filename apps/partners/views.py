"""Endpoints de constructoras y membresías (sección 11) y de proyectos (sección 12)."""

from typing import Any, cast

from django.db.models import QuerySet
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
from rest_framework.request import Request
from rest_framework.response import Response

from apps.catalogs.workflow import ProjectStatus
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from apps.partners import services
from apps.partners.models import Partner, PartnerMembership, PartnerStatus, Project
from apps.partners.serializers import (
    MembershipCreateSerializer,
    MembershipSerializer,
    MembershipUpdateSerializer,
    OptionalReasonSerializer,
    PartnerCreateSerializer,
    PartnerDetailSerializer,
    PartnerSerializer,
    PartnerUpdateSerializer,
    ProjectCreateSerializer,
    ProjectDetailSerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
    ReasonSerializer,
)
from config.filters import StrictOrderingFilter, parse_uuid_param
from config.serializers import ErrorSerializer

PARTNERS_TAG = "Partners"
PROJECTS_TAG = "Projects"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND (inexistente o fuera del alcance)")}


class PermissionCodeView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {}

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)


def _choice_param(request: Request, name: str, choices: list[str]) -> str | None:
    value = request.query_params.get(name)
    if not value:
        return None
    if value not in choices:
        raise ValidationError({name: [f"Valor no permitido. Opciones: {', '.join(choices)}."]})
    return value


# --------------------------------------------------------------------------------------
# Constructoras
# --------------------------------------------------------------------------------------


class PartnerListView(PermissionCodeView):
    required_permissions = {"GET": "partners.read", "POST": "partners.create"}
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = ["legal_name", "trade_name", "tax_id"]
    ordering_fields = ["legal_name", "created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[Partner]:
        partners = services.partners_visible_to(self.actor)
        partner_status = _choice_param(self.request, "status", PartnerStatus.values)
        if partner_status:
            partners = partners.filter(status=partner_status)
        city_code = self.request.query_params.get("city_code")
        if city_code:
            partners = partners.filter(
                projects__city_item__code=city_code, projects__deleted_at__isnull=True
            ).distinct()
        return partners

    @extend_schema(
        tags=[PARTNERS_TAG],
        operation_id="partners_list",
        summary="Listar constructoras visibles",
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, enum=PartnerStatus.values),
            OpenApiParameter(
                "city_code", OpenApiTypes.STR, description="Con proyectos en el municipio DANE."
            ),
        ],
        responses={200: PartnerSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(PartnerSerializer(page, many=True).data)

    @extend_schema(
        tags=[PARTNERS_TAG],
        operation_id="partners_create",
        summary="Crear una constructora",
        request=PartnerCreateSerializer,
        responses={201: PartnerSerializer, 409: _error("DUPLICATE_TAX_ID"), **COMMON_ERRORS},
    )
    def post(self, request: Request) -> Response:
        serializer = PartnerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        partner = services.create_partner(dict(serializer.validated_data))
        return Response(PartnerSerializer(partner).data, status=status.HTTP_201_CREATED)


class PartnerDetailView(PermissionCodeView):
    required_permissions = {"GET": "partners.read", "PATCH": "partners.update"}

    def _get_partner(self, partner_id: Any) -> Partner:
        return get_object_or_404(services.partners_visible_to(self.actor), pk=partner_id)

    def _detail(self, partner: Partner) -> dict[str, Any]:
        return PartnerDetailSerializer(
            partner, context={"metrics": services.partner_metrics(partner)}
        ).data

    @extend_schema(
        tags=[PARTNERS_TAG],
        operation_id="partners_retrieve",
        summary="Detalle y métricas básicas de una constructora",
        responses={200: PartnerDetailSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, partner_id: Any) -> Response:
        return Response(self._detail(self._get_partner(partner_id)))

    @extend_schema(
        tags=[PARTNERS_TAG],
        operation_id="partners_partial_update",
        summary="Actualizar datos de contacto de una constructora",
        request=PartnerUpdateSerializer,
        responses={200: PartnerDetailSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def patch(self, request: Request, partner_id: Any) -> Response:
        partner = self._get_partner(partner_id)
        serializer = PartnerUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_partner(partner, dict(serializer.validated_data))
        return Response(self._detail(partner))


class _PartnerStatusView(PermissionCodeView):
    required_permissions = {"POST": "partners.manage_status"}
    activate: bool
    input_serializer: type[OptionalReasonSerializer] | type[ReasonSerializer]

    def post(self, request: Request, partner_id: Any) -> Response:
        partner = get_object_or_404(services.partners_visible_to(self.actor), pk=partner_id)
        serializer = self.input_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_partner_status(
            partner,
            active=self.activate,
            actor=self.actor,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(PartnerSerializer(partner).data)


@extend_schema_view(
    post=extend_schema(
        tags=[PARTNERS_TAG],
        operation_id="partners_activate",
        summary="Activar una constructora",
        request=OptionalReasonSerializer,
        responses={200: PartnerSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
)
class PartnerActivateView(_PartnerStatusView):
    activate = True
    input_serializer = OptionalReasonSerializer


@extend_schema_view(
    post=extend_schema(
        tags=[PARTNERS_TAG],
        operation_id="partners_deactivate",
        summary="Desactivar una constructora (deja de crear proyectos)",
        request=ReasonSerializer,
        responses={200: PartnerSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
)
class PartnerDeactivateView(_PartnerStatusView):
    activate = False
    input_serializer = ReasonSerializer


# --------------------------------------------------------------------------------------
# Membresías
# --------------------------------------------------------------------------------------


class PartnerMemberListView(PermissionCodeView):
    required_permissions = {"GET": "partner_members.read", "POST": "partner_members.create"}
    filter_backends = [StrictOrderingFilter]
    ordering_fields = ["started_at", "created_at"]
    ordering = ["-started_at"]

    def get_queryset(self) -> QuerySet[PartnerMembership]:
        partner = get_object_or_404(
            services.partners_visible_to(self.actor), pk=self.kwargs["partner_id"]
        )
        memberships = services.memberships_visible_to(self.actor).filter(partner=partner)
        membership_status = _choice_param(self.request, "status", PartnerStatus.values)
        if membership_status:
            memberships = memberships.filter(status=membership_status)
        return memberships

    @extend_schema(
        tags=[PARTNERS_TAG],
        operation_id="partners_members_list",
        summary="Usuarios de la constructora",
        description="Un usuario de constructora solo ve su propia membresía.",
        parameters=[OpenApiParameter("status", OpenApiTypes.STR, enum=PartnerStatus.values)],
        responses={200: MembershipSerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, partner_id: Any) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(MembershipSerializer(page, many=True).data)

    @extend_schema(
        tags=[PARTNERS_TAG],
        operation_id="partners_members_create",
        summary="Agregar un usuario existente a la constructora",
        request=MembershipCreateSerializer,
        responses={
            201: MembershipSerializer,
            409: _error("USER_ALREADY_IN_PARTNER"),
            422: _error("PARTNER_NOT_ACTIVE o USER_NOT_ELIGIBLE"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, partner_id: Any) -> Response:
        partner = get_object_or_404(services.partners_visible_to(self.actor), pk=partner_id)
        serializer = MembershipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.add_member(
            partner,
            user=serializer.validated_data["user_id"],
            job_title=serializer.validated_data["job_title"],
            started_at=serializer.validated_data["started_at"],
        )
        return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)


class MembershipDetailView(PermissionCodeView):
    required_permissions = {
        "GET": "partner_members.read",
        "PATCH": "partner_members.update",
        "DELETE": "partner_members.remove",
    }

    def _get_membership(self, membership_id: Any) -> PartnerMembership:
        return get_object_or_404(services.memberships_visible_to(self.actor), pk=membership_id)

    @extend_schema(
        tags=[PARTNERS_TAG],
        operation_id="partner_memberships_retrieve",
        summary="Detalle de una membresía",
        responses={200: MembershipSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, membership_id: Any) -> Response:
        return Response(MembershipSerializer(self._get_membership(membership_id)).data)

    @extend_schema(
        tags=[PARTNERS_TAG],
        operation_id="partner_memberships_partial_update",
        summary="Cambiar cargo o estado de una membresía",
        request=MembershipUpdateSerializer,
        responses={
            200: MembershipSerializer,
            409: _error("MEMBERSHIP_ENDED o USER_ALREADY_IN_PARTNER"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, membership_id: Any) -> Response:
        membership = self._get_membership(membership_id)
        serializer = MembershipUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_membership(membership, dict(serializer.validated_data))
        return Response(MembershipSerializer(membership).data)

    @extend_schema(
        tags=[PARTNERS_TAG],
        operation_id="partner_memberships_destroy",
        summary="Finalizar una membresía (no borra el historial)",
        responses={204: None, **NOT_FOUND, **COMMON_ERRORS},
    )
    def delete(self, request: Request, membership_id: Any) -> Response:
        services.end_membership(self._get_membership(membership_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------------------
# Proyectos
# --------------------------------------------------------------------------------------


def _project_detail(user: User, project: Project) -> dict[str, Any]:
    return ProjectDetailSerializer(
        project, context={"available_actions": services.available_actions(user, project)}
    ).data


class ProjectListView(PermissionCodeView):
    required_permissions = {"GET": "projects.read", "POST": "projects.create"}
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = ["name", "code", "address"]
    ordering_fields = ["name", "status", "estimated_delivery_date", "created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[Project]:
        projects = services.projects_visible_to(self.actor)
        project_status = _choice_param(self.request, "status", ProjectStatus.values)
        if project_status:
            projects = projects.filter(status=project_status)
        partner_id = parse_uuid_param(self.request, "partner_id")
        if partner_id:
            projects = projects.filter(partner_id=partner_id)
        city_code = self.request.query_params.get("city_code")
        if city_code:
            projects = projects.filter(city_item__code=city_code)
        return projects

    @extend_schema(
        tags=[PROJECTS_TAG],
        operation_id="projects_list",
        summary="Proyectos dentro del alcance del usuario",
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, enum=ProjectStatus.values),
            OpenApiParameter("partner_id", OpenApiTypes.UUID),
            OpenApiParameter("city_code", OpenApiTypes.STR, description="Municipio DANE."),
        ],
        responses={200: ProjectSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(ProjectSerializer(page, many=True).data)

    @extend_schema(
        tags=[PROJECTS_TAG],
        operation_id="projects_create",
        summary="Crear un proyecto en borrador",
        description=(
            "Para `CONSTRUCTION_PARTNER`, `partner_id` se ignora y se deriva de su membresía. "
            "Para asesor y administrador es obligatorio."
        ),
        request=ProjectCreateSerializer,
        responses={
            201: ProjectDetailSerializer,
            409: _error("DUPLICATE_PROJECT_NAME"),
            422: _error("PARTNER_NOT_ACTIVE"),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = services.create_project(self.actor, serializer.to_service_data())
        project = services.projects_visible_to(self.actor).get(pk=project.pk)
        return Response(_project_detail(self.actor, project), status=status.HTTP_201_CREATED)


def _get_project(user: User, project_id: Any) -> Project:
    return get_object_or_404(services.projects_visible_to(user), pk=project_id)


class ProjectDetailView(PermissionCodeView):
    required_permissions = {"GET": "projects.read", "PATCH": "projects.update"}

    @extend_schema(
        tags=[PROJECTS_TAG],
        operation_id="projects_retrieve",
        summary="Detalle del proyecto y acciones disponibles para el usuario",
        responses={200: ProjectDetailSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, project_id: Any) -> Response:
        return Response(_project_detail(self.actor, _get_project(self.actor, project_id)))

    @extend_schema(
        tags=[PROJECTS_TAG],
        operation_id="projects_partial_update",
        summary="Editar los datos del proyecto",
        request=ProjectUpdateSerializer,
        responses={
            200: ProjectDetailSerializer,
            409: _error("PROJECT_NOT_EDITABLE o DUPLICATE_PROJECT_NAME"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, project_id: Any) -> Response:
        project = _get_project(self.actor, project_id)
        serializer = ProjectUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_project(self.actor, project, serializer.to_service_data())
        return Response(_project_detail(self.actor, _get_project(self.actor, project_id)))


class _ProjectTransitionView(PermissionCodeView):
    to_status: str
    input_serializer: type[OptionalReasonSerializer] | type[ReasonSerializer]

    def post(self, request: Request, project_id: Any) -> Response:
        project = _get_project(self.actor, project_id)
        serializer = self.input_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.transition_project(
            self.actor,
            project,
            to_status=self.to_status,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(_project_detail(self.actor, _get_project(self.actor, project_id)))


_TRANSITION_RESPONSES = {
    200: ProjectDetailSerializer,
    409: _error("INVALID_STATE_TRANSITION"),
    422: _error("PARTNER_NOT_ACTIVE"),
    **NOT_FOUND,
    **COMMON_ERRORS,
}


@extend_schema_view(
    post=extend_schema(
        tags=[PROJECTS_TAG],
        operation_id="projects_submit",
        summary="Enviar el proyecto a validación",
        request=OptionalReasonSerializer,
        responses=_TRANSITION_RESPONSES,
    )
)
class ProjectSubmitView(_ProjectTransitionView):
    to_status = ProjectStatus.PENDING_REVIEW
    required_permissions = {"POST": "projects.submit"}
    input_serializer = OptionalReasonSerializer


@extend_schema_view(
    post=extend_schema(
        tags=[PROJECTS_TAG],
        operation_id="projects_activate",
        summary="Aprobar el proyecto (queda ACTIVE)",
        request=OptionalReasonSerializer,
        responses=_TRANSITION_RESPONSES,
    )
)
class ProjectActivateView(_ProjectTransitionView):
    to_status = ProjectStatus.ACTIVE
    required_permissions = {"POST": "projects.approve"}
    input_serializer = OptionalReasonSerializer


@extend_schema_view(
    post=extend_schema(
        tags=[PROJECTS_TAG],
        operation_id="projects_reject",
        summary="Devolver el proyecto a borrador con un motivo",
        request=ReasonSerializer,
        responses=_TRANSITION_RESPONSES,
    )
)
class ProjectRejectView(_ProjectTransitionView):
    to_status = ProjectStatus.DRAFT
    required_permissions = {"POST": "projects.approve"}
    input_serializer = ReasonSerializer


@extend_schema_view(
    post=extend_schema(
        tags=[PROJECTS_TAG],
        operation_id="projects_archive",
        summary="Archivar el proyecto (conserva las asociaciones históricas)",
        request=ReasonSerializer,
        responses=_TRANSITION_RESPONSES,
    )
)
class ProjectArchiveView(_ProjectTransitionView):
    to_status = ProjectStatus.ARCHIVED
    required_permissions = {"POST": "projects.archive"}
    input_serializer = ReasonSerializer
