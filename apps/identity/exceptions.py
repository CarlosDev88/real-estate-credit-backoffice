"""Errores estables del módulo identity (sección 5.5 de la especificación)."""

from rest_framework import exceptions, status

from config.exceptions import ApiError


class InvalidCredentials(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "INVALID_CREDENTIALS"
    default_detail = "El correo o la contraseña no son correctos."


class UserInactive(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "USER_INACTIVE"
    default_detail = "El usuario está desactivado."


class SessionExpired(exceptions.AuthenticationFailed):
    """Sesión interna vencida, revocada o con un token inválido.

    Hereda de ``AuthenticationFailed`` para que DRF responda ``401`` con
    ``WWW-Authenticate`` en los endpoints protegidos.
    """

    error_code = "SESSION_EXPIRED"
    default_detail = "La sesión venció o fue cerrada. Inicia sesión de nuevo."


class RefreshSessionExpired(ApiError):
    """Igual que ``SessionExpired``, para los endpoints que leen el refresh token."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "SESSION_EXPIRED"
    default_detail = "La sesión venció o fue cerrada. Inicia sesión de nuevo."


class CsrfFailed(exceptions.PermissionDenied):
    error_code = "CSRF_FAILED"
    default_detail = "Falta el token CSRF o no es válido."


class PasswordResetTokenInvalid(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "PASSWORD_RESET_TOKEN_INVALID"
    default_detail = "El enlace de recuperación no es válido, ya se usó o venció."


class InvalidCurrentPassword(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "INVALID_CURRENT_PASSWORD"
    default_detail = "La contraseña actual no es correcta."
