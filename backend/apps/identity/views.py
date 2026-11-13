"""Endpoints de autenticación interna: ``/api/v1/auth/*`` (sección 7 de la especificación)."""

from typing import Any

from django.middleware.csrf import rotate_token
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity import services
from apps.identity.authentication import enforce_csrf
from apps.identity.cookies import clear_session_cookies, refresh_cookie_name, set_session_cookies
from apps.identity.exceptions import RefreshSessionExpired
from apps.identity.models import User
from apps.identity.serializers import (
    AcceptedResponseSerializer,
    ChangePasswordSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RefreshResponseSerializer,
)
from apps.identity.throttling import (
    ChangePasswordRateThrottle,
    LoginRateThrottle,
    PasswordResetConfirmRateThrottle,
    PasswordResetRequestRateThrottle,
)
from config.serializers import ErrorSerializer

AUTH_TAG = "Auth"
PASSWORD_RESET_ACCEPTED_MESSAGE = (
    "Si el correo corresponde a un usuario activo, enviaremos instrucciones para "
    "restablecer la contraseña."
)


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


def _apply_issued_session(response: Response, issued: services.IssuedSession) -> None:
    set_session_cookies(
        response,
        access_token=issued.access_token,
        access_expires_at=issued.access_expires_at,
        refresh_token=issued.refresh_token,
        refresh_expires_at=issued.refresh_expires_at,
    )


class PublicAuthView(APIView):
    """Endpoint público: no lee la cookie de acceso, así una cookie vencida no lo bloquea."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]


class LoginView(PublicAuthView):
    throttle_classes = [LoginRateThrottle]

    @extend_schema(
        tags=[AUTH_TAG],
        operation_id="auth_login",
        summary="Iniciar sesión de usuario interno",
        request=LoginSerializer,
        responses={
            200: LoginResponseSerializer,
            400: _error("Datos inválidos."),
            401: _error("INVALID_CREDENTIALS"),
            403: _error("USER_INACTIVE"),
            429: _error("RATE_LIMITED"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user, issued = services.login(
            request=request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        profile = services.get_access_profile(user)

        response = Response(
            LoginResponseSerializer(
                {
                    "user": {
                        "id": user.pk,
                        "name": user.get_full_name(),
                        "email": user.email,
                        "role": profile.role,
                    },
                    "permissions": profile.permissions,
                    "session_expires_at": issued.refresh_expires_at,
                }
            ).data
        )
        _apply_issued_session(response, issued)
        # Nuevo token CSRF por sesión: evita la fijación de sesión. El middleware de
        # CSRF lo entrega en la cookie `app_csrf`.
        rotate_token(request)
        return response


class RefreshView(PublicAuthView):
    @extend_schema(
        tags=[AUTH_TAG],
        operation_id="auth_refresh",
        summary="Rotar el refresh token y emitir un access token nuevo",
        request=None,
        responses={
            200: RefreshResponseSerializer,
            401: _error("SESSION_EXPIRED"),
            403: _error("CSRF_FAILED"),
        },
    )
    def post(self, request: Request) -> Response:
        enforce_csrf(request)
        issued = services.refresh_session(
            request=request,
            refresh_token=request.COOKIES.get(refresh_cookie_name()),
        )
        response = Response(
            RefreshResponseSerializer({"session_expires_at": issued.refresh_expires_at}).data
        )
        _apply_issued_session(response, issued)
        return response

    def handle_exception(self, exc: Exception) -> Response:
        response = super().handle_exception(exc)
        if isinstance(exc, RefreshSessionExpired):
            # Evita que el cliente siga reenviando cookies que ya no sirven.
            clear_session_cookies(response)
        return response


class LogoutView(PublicAuthView):
    @extend_schema(
        tags=[AUTH_TAG],
        operation_id="auth_logout",
        summary="Cerrar la sesión actual",
        request=None,
        responses={204: None, 403: _error("CSRF_FAILED")},
    )
    def post(self, request: Request) -> Response:
        enforce_csrf(request)
        services.logout(
            request=request,
            refresh_token=request.COOKIES.get(refresh_cookie_name()),
        )
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_session_cookies(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[AUTH_TAG],
        operation_id="auth_me",
        summary="Perfil, rol, permisos y alcance del usuario autenticado",
        responses={200: MeSerializer, 401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED")},
    )
    def get(self, request: Request) -> Response:
        user: User = request.user  # type: ignore[assignment]
        profile = services.get_access_profile(user)
        return Response(
            MeSerializer(
                {
                    "id": user.pk,
                    "name": user.get_full_name(),
                    "email": user.email,
                    "role": profile.role,
                    "role_label": profile.role_label,
                    "roles": profile.roles,
                    "permissions": profile.permissions,
                    "scope": {
                        "assigned_applications_only": profile.assigned_applications_only,
                        "partner_id": profile.partner_id,
                    },
                }
            ).data
        )


class PasswordResetRequestView(PublicAuthView):
    throttle_classes = [PasswordResetRequestRateThrottle]

    @extend_schema(
        tags=[AUTH_TAG],
        operation_id="auth_password_reset_requests_create",
        summary="Solicitar enlace de recuperación de contraseña",
        request=PasswordResetRequestSerializer,
        responses={
            202: AcceptedResponseSerializer,
            400: _error("Datos inválidos."),
            429: _error("RATE_LIMITED"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(
            request=request,
            email=serializer.validated_data["email"],
        )
        return Response(
            {"message": PASSWORD_RESET_ACCEPTED_MESSAGE}, status=status.HTTP_202_ACCEPTED
        )


class PasswordResetConfirmView(PublicAuthView):
    throttle_classes = [PasswordResetConfirmRateThrottle]

    @extend_schema(
        tags=[AUTH_TAG],
        operation_id="auth_password_resets_confirm",
        summary="Definir una contraseña nueva con el token de recuperación",
        request=PasswordResetConfirmSerializer,
        responses={
            204: None,
            400: _error("PASSWORD_RESET_TOKEN_INVALID o contraseña que no cumple la política."),
            429: _error("RATE_LIMITED"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.confirm_password_reset(
            token=serializer.validated_data["token"],
            new_password=serializer.validated_data["new_password"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChangePasswordRateThrottle]

    @extend_schema(
        tags=[AUTH_TAG],
        operation_id="auth_change_password",
        summary="Cambiar la contraseña del usuario autenticado",
        request=ChangePasswordSerializer,
        responses={
            204: None,
            400: _error("INVALID_CURRENT_PASSWORD o contraseña que no cumple la política."),
            401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
            403: _error("CSRF_FAILED"),
            429: _error("RATE_LIMITED"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.change_password(
            user=request.user,  # type: ignore[arg-type]
            current_session=request.auth_session,  # type: ignore[attr-defined]
            current_password=serializer.validated_data["current_password"],
            new_password=serializer.validated_data["new_password"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
