"""Endpoints de usuarios internos y roles: ``/api/v1/users`` y ``/api/v1/roles`` (10.1)."""

from typing import Any, cast

from django.db.models import Prefetch, QuerySet
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

from apps.identity import users
from apps.identity.models import Role, RolePermission, User, UserStatus, user_status_filter
from apps.identity.permissions import HasPermissionCode
from apps.identity.serializers import (
    OptionalStatusReasonSerializer,
    RoleSerializer,
    StatusReasonSerializer,
    UserCreatedSerializer,
    UserCreateSerializer,
    UserRolesSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from config.filters import StrictOrderingFilter
from config.serializers import ErrorSerializer

USERS_TAG = "Users"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND")}


class _UserAdminView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {}

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)


def _get_user(user_id: Any) -> User:
    return get_object_or_404(users.users_queryset(), pk=user_id)


def _user_data(user_id: Any) -> dict[str, Any]:
    """Recarga el usuario con sus roles y constructora para la respuesta."""
    return UserSerializer(_get_user(user_id)).data


class UserListView(_UserAdminView):
    required_permissions = {"GET": "users.read", "POST": "users.create"}
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["email", "first_name", "last_name", "created_at", "last_login"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[User]:
        queryset = users.users_queryset()
        params = self.request.query_params
        if params.get("role"):
            queryset = queryset.filter(user_role_assignments__role__code=params["role"])
        if params.get("status"):
            if params["status"] not in UserStatus.values:
                raise ValidationError({"status": ["Estado no válido."]})
            queryset = queryset.filter(user_status_filter(params["status"]))
        return queryset.distinct()

    @extend_schema(
        tags=[USERS_TAG],
        operation_id="users_list",
        summary="Listar usuarios internos",
        parameters=[
            OpenApiParameter("role", OpenApiTypes.STR, description="Código del rol."),
            OpenApiParameter("status", OpenApiTypes.STR, enum=UserStatus.values),
        ],
        responses={200: UserSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(UserSerializer(page, many=True).data)

    @extend_schema(
        tags=[USERS_TAG],
        operation_id="users_create",
        summary="Crear un usuario interno",
        description=(
            "El usuario queda en estado `PENDING` hasta que define su contraseña con la "
            "invitación. Con `send_invitation: true` (por defecto) la invitación se envía "
            "de inmediato. Un usuario `CONSTRUCTION_PARTNER` requiere `partner_id`."
        ),
        request=UserCreateSerializer,
        responses={
            201: UserCreatedSerializer,
            409: _error("EMAIL_ALREADY_REGISTERED"),
            422: _error("PARTNER_NOT_ACTIVE"),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user, invitation = users.create_user(
            actor=self.actor,
            email=data["email"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            phone=data["phone"],
            roles=data["role_codes"],
            partner=data["partner_id"],
            send_invitation=data["send_invitation"],
        )
        body = UserCreatedSerializer(_get_user(user.pk), context={"invitation": invitation}).data
        return Response(body, status=status.HTTP_201_CREATED)


class UserDetailView(_UserAdminView):
    required_permissions = {"GET": "users.read", "PATCH": "users.update"}

    @extend_schema(
        tags=[USERS_TAG],
        operation_id="users_retrieve",
        summary="Detalle de un usuario interno",
        responses={200: UserSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, user_id: Any) -> Response:
        return Response(_user_data(user_id))

    @extend_schema(
        tags=[USERS_TAG],
        operation_id="users_partial_update",
        summary="Editar nombre y teléfono",
        request=UserUpdateSerializer,
        responses={200: UserSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def patch(self, request: Request, user_id: Any) -> Response:
        user = _get_user(user_id)
        serializer = UserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        users.update_user(user, dict(serializer.validated_data))
        return Response(_user_data(user_id))


class _UserStatusView(_UserAdminView):
    required_permissions = {"POST": "users.manage_status"}
    activate: bool
    input_serializer: type[OptionalStatusReasonSerializer] | type[StatusReasonSerializer]

    def post(self, request: Request, user_id: Any) -> Response:
        user = _get_user(user_id)
        serializer = self.input_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        users.set_user_active(
            user,
            active=self.activate,
            actor=self.actor,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(_user_data(user_id))


@extend_schema_view(
    post=extend_schema(
        tags=[USERS_TAG],
        operation_id="users_activate",
        summary="Activar un usuario",
        request=OptionalStatusReasonSerializer,
        responses={200: UserSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
)
class UserActivateView(_UserStatusView):
    activate = True
    input_serializer = OptionalStatusReasonSerializer


@extend_schema_view(
    post=extend_schema(
        tags=[USERS_TAG],
        operation_id="users_deactivate",
        summary="Desactivar un usuario y revocar sus sesiones",
        request=StatusReasonSerializer,
        responses={
            200: UserSerializer,
            409: _error("CANNOT_MODIFY_OWN_ACCOUNT"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
)
class UserDeactivateView(_UserStatusView):
    activate = False
    input_serializer = StatusReasonSerializer


class UserRolesView(_UserAdminView):
    required_permissions = {"PUT": "roles.assign"}

    @extend_schema(
        tags=[USERS_TAG],
        operation_id="users_roles_update",
        summary="Reemplazar los roles de un usuario",
        description=(
            "Asignar `CONSTRUCTION_PARTNER` a alguien sin membresía exige `partner_id` y "
            "crea la membresía. Quitarle ese rol finaliza su membresía."
        ),
        request=UserRolesSerializer,
        responses={
            200: UserSerializer,
            409: _error("CANNOT_MODIFY_OWN_ACCOUNT o USER_ALREADY_IN_PARTNER"),
            422: _error("PARTNER_NOT_ACTIVE"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def put(self, request: Request, user_id: Any) -> Response:
        user = _get_user(user_id)
        serializer = UserRolesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        users.replace_roles(
            user,
            serializer.validated_data["role_codes"],
            actor=self.actor,
            partner=serializer.validated_data["partner_id"],
        )
        return Response(_user_data(user_id))


class RoleListView(_UserAdminView):
    required_permissions = {"GET": "roles.read"}

    @extend_schema(
        tags=[USERS_TAG],
        operation_id="roles_list",
        summary="Roles y sus permisos",
        responses={200: RoleSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        roles = Role.objects.order_by("code").prefetch_related(
            Prefetch(
                "permission_assignments",
                queryset=RolePermission.objects.select_related("permission").order_by(
                    "permission__code"
                ),
            )
        )
        page = self.paginate_queryset(roles)
        return self.get_paginated_response(RoleSerializer(page, many=True).data)
