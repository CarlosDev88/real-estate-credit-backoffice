"""Endpoints de invitaciones internas: ``/api/v1/invitations`` (sección 10.2)."""

from typing import Any, cast

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.identity import invitations
from apps.identity.models import (
    InternalInvitation,
    InvitationStatus,
    User,
    UserManager,
    invitation_status_filter,
)
from apps.identity.permissions import HasPermissionCode
from apps.identity.serializers import (
    AcceptedUserSerializer,
    InvitationAcceptSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
)
from apps.identity.services import get_access_profile
from apps.identity.throttling import InvitationAcceptRateThrottle
from config.filters import StrictOrderingFilter, parse_uuid_param
from config.serializers import ErrorSerializer

INVITATIONS_TAG = "Users"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}


class _InvitationView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {}

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)


class InvitationListView(_InvitationView):
    required_permissions = {"GET": "invitations.read", "POST": "invitations.create"}
    filter_backends = [StrictOrderingFilter]
    ordering_fields = ["created_at", "expires_at", "email"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[InternalInvitation]:
        params = self.request.query_params
        queryset = invitations.invitations_queryset()
        if params.get("email"):
            queryset = queryset.filter(email=UserManager.normalize_email(params["email"]))
        if params.get("role"):
            queryset = queryset.filter(role__code=params["role"])
        if params.get("status"):
            if params["status"] not in InvitationStatus.values:
                raise ValidationError({"status": ["Estado no válido."]})
            queryset = queryset.filter(invitation_status_filter(params["status"]))
        partner_id = parse_uuid_param(self.request, "partner_id")
        if partner_id:
            queryset = queryset.filter(partner_id=partner_id)
        return queryset

    @extend_schema(
        tags=[INVITATIONS_TAG],
        operation_id="invitations_list",
        summary="Listar invitaciones internas",
        parameters=[
            OpenApiParameter("email", OpenApiTypes.EMAIL),
            OpenApiParameter("role", OpenApiTypes.STR, description="Código del rol."),
            OpenApiParameter("status", OpenApiTypes.STR, enum=InvitationStatus.values),
            OpenApiParameter("partner_id", OpenApiTypes.UUID),
        ],
        responses={200: InvitationSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(InvitationSerializer(page, many=True).data)

    @extend_schema(
        tags=[INVITATIONS_TAG],
        operation_id="invitations_create",
        summary="Invitar a un usuario interno",
        description=(
            "Envía un correo con un enlace de un solo uso. `partner_id` es obligatorio "
            "para el rol `CONSTRUCTION_PARTNER` y no se permite para los demás."
        ),
        request=InvitationCreateSerializer,
        responses={
            201: InvitationSerializer,
            409: _error(
                "USER_ALREADY_EXISTS, INVITATION_ALREADY_PENDING o USER_ALREADY_IN_PARTNER"
            ),
            422: _error("PARTNER_NOT_ACTIVE"),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = invitations.create_invitation(
            email=serializer.validated_data["email"],
            role=serializer.validated_data["role"],
            partner=serializer.validated_data["partner_id"],
            invited_by=self.actor,
        )
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


def _get_invitation(invitation_id: Any) -> InternalInvitation:
    return get_object_or_404(invitations.invitations_queryset(), pk=invitation_id)


class InvitationResendView(_InvitationView):
    required_permissions = {"POST": "invitations.create"}

    @extend_schema(
        tags=[INVITATIONS_TAG],
        operation_id="invitations_resend",
        summary="Revocar el token anterior y reenviar la invitación",
        request=None,
        responses={
            201: InvitationSerializer,
            404: _error("RESOURCE_NOT_FOUND"),
            409: _error("INVITATION_NOT_PENDING o USER_ALREADY_EXISTS"),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, invitation_id: Any) -> Response:
        invitation = invitations.resend_invitation(_get_invitation(invitation_id), actor=self.actor)
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


class InvitationDetailView(_InvitationView):
    required_permissions = {"DELETE": "invitations.revoke"}

    @extend_schema(
        tags=[INVITATIONS_TAG],
        operation_id="invitations_destroy",
        summary="Revocar una invitación pendiente",
        responses={
            204: None,
            404: _error("RESOURCE_NOT_FOUND"),
            409: _error("INVITATION_NOT_PENDING"),
            **COMMON_ERRORS,
        },
    )
    def delete(self, request: Request, invitation_id: Any) -> Response:
        invitations.revoke_invitation(_get_invitation(invitation_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationAcceptView(GenericAPIView):
    """Endpoint público: el token de la invitación es la credencial."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]
    throttle_classes = [InvitationAcceptRateThrottle]

    @extend_schema(
        tags=[INVITATIONS_TAG],
        operation_id="invitations_accept",
        summary="Aceptar la invitación y definir la contraseña",
        description=(
            "`first_name` y `last_name` son obligatorios si el usuario todavía no existe. "
            "No inicia sesión: después se usa `POST /auth/login`."
        ),
        request=InvitationAcceptSerializer,
        responses={
            200: AcceptedUserSerializer,
            400: _error("INVITATION_INVALID o contraseña que no cumple la política"),
            409: _error("USER_ALREADY_EXISTS o USER_ALREADY_IN_PARTNER"),
            422: _error("PARTNER_NOT_ACTIVE"),
            429: _error("RATE_LIMITED"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = InvitationAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = invitations.accept_invitation(**serializer.validated_data)
        return Response(
            AcceptedUserSerializer(
                {
                    "id": user.pk,
                    "email": user.email,
                    "name": user.get_full_name(),
                    "roles": get_access_profile(user).roles,
                }
            ).data
        )
