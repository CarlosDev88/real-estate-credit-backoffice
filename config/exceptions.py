"""Formato de error común de la API (sección 5.3 de la especificación).

Toda respuesta de error tiene la forma::

    {"code": "...", "message": "...", "details": [...], "request_id": "..."}
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response

from config.request_context import get_request_id

logger = logging.getLogger(__name__)


class ApiError(exceptions.APIException):
    """Error de negocio con un código estable que el frontend puede interpretar."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    error_code = "API_ERROR"
    default_detail = "No fue posible procesar la solicitud."

    def __init__(
        self,
        detail: str | None = None,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.details = details or []


# El orden importa: las subclases van antes que sus clases base.
_DRF_ERROR_CODES: list[tuple[type[exceptions.APIException], str]] = [
    (exceptions.ValidationError, "VALIDATION_ERROR"),
    (exceptions.ParseError, "MALFORMED_REQUEST"),
    (exceptions.NotAuthenticated, "NOT_AUTHENTICATED"),
    (exceptions.AuthenticationFailed, "AUTHENTICATION_FAILED"),
    (exceptions.PermissionDenied, "PERMISSION_DENIED"),
    (exceptions.NotFound, "RESOURCE_NOT_FOUND"),
    (exceptions.MethodNotAllowed, "METHOD_NOT_ALLOWED"),
    (exceptions.NotAcceptable, "NOT_ACCEPTABLE"),
    (exceptions.UnsupportedMediaType, "UNSUPPORTED_MEDIA_TYPE"),
    (exceptions.Throttled, "RATE_LIMITED"),
]

VALIDATION_MESSAGE = "Los datos enviados no son válidos."
INTERNAL_ERROR_MESSAGE = "Ocurrió un error interno. Intenta de nuevo más tarde."


def _error_code(exc: exceptions.APIException) -> str:
    explicit = getattr(exc, "error_code", None)
    if explicit:
        return str(explicit)
    for exc_class, code in _DRF_ERROR_CODES:
        if isinstance(exc, exc_class):
            return code
    return "API_ERROR"


def _flatten_validation_errors(errors: Any, prefix: str | None = None) -> list[dict[str, Any]]:
    """Convierte los errores anidados de DRF en una lista plana de ``details``."""
    details: list[dict[str, Any]] = []
    if isinstance(errors, Mapping):
        for key, value in errors.items():
            if key in ("non_field_errors", settings.REST_FRAMEWORK.get("NON_FIELD_ERRORS_KEY")):
                field = prefix
            else:
                field = f"{prefix}.{key}" if prefix else str(key)
            details.extend(_flatten_validation_errors(value, field))
    elif isinstance(errors, Sequence) and not isinstance(errors, str):
        for index, value in enumerate(errors):
            if isinstance(value, Mapping | list):
                field = f"{prefix}[{index}]" if prefix else f"[{index}]"
                details.extend(_flatten_validation_errors(value, field))
            else:
                details.extend(_flatten_validation_errors(value, prefix))
    else:
        details.append(
            {
                "field": prefix,
                "code": str(getattr(errors, "code", "invalid")).upper(),
                "message": str(errors),
            }
        )
    return details


def build_error_body(
    code: str, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details or [],
        "request_id": get_request_id(),
    }


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    # Import diferido: `rest_framework.views` carga las clases de autenticación al
    # importarse, y estas dependen de este módulo.
    from rest_framework.views import exception_handler as drf_exception_handler

    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    # El manejador de DRF conserva cabeceras como WWW-Authenticate y Retry-After.
    response = drf_exception_handler(exc, context)

    if response is None:
        if settings.DEBUG:
            return None  # Deja que Django muestre la traza en desarrollo.
        logger.exception("Error no controlado en la API", exc_info=exc)
        return Response(
            build_error_body("INTERNAL_ERROR", INTERNAL_ERROR_MESSAGE),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    assert isinstance(exc, exceptions.APIException)

    if isinstance(exc, exceptions.ValidationError):
        message = VALIDATION_MESSAGE
        details = _flatten_validation_errors(exc.detail)
    else:
        message = str(exc.detail)
        details = getattr(exc, "details", None) or []

    response.data = build_error_body(_error_code(exc), message, details)
    return response
