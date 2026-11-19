import math
from typing import Any

from django.db import connections
from django.db.utils import DatabaseError
from django.http import HttpResponse, JsonResponse
from django.http.request import HttpRequest
from django.views import defaults
from django.views.decorators.http import require_GET
from rest_framework import exceptions

from config.exceptions import INTERNAL_ERROR_MESSAGE, build_error_body, rate_limited_message


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """Comprueba que el proceso HTTP responde sin consultar dependencias."""
    return JsonResponse({"status": "ok"})


@require_GET
def ready(request: HttpRequest) -> JsonResponse:
    """Comprueba la conexión a PostgreSQL antes de aceptar tráfico."""
    try:
        connections["default"].cursor()
    except DatabaseError:
        return JsonResponse({"status": "not_ready"}, status=503)
    return JsonResponse({"status": "ready"})


# --- Errores fuera de DRF (SEC-12) ---------------------------------------------------


def _is_api(request: HttpRequest) -> bool:
    return request.path.startswith("/api/")


def page_not_found(request: HttpRequest, exception: Exception) -> HttpResponse:
    """``handler404``: una ruta inexistente o un id que no es UUID (la ruta usa
    ``<uuid:...>``) no llega a DRF. En ``/api/`` responde el formato de error de la API;
    fuera, la página de Django."""
    if not _is_api(request):
        return defaults.page_not_found(request, exception)
    return JsonResponse(
        build_error_body("RESOURCE_NOT_FOUND", str(exceptions.NotFound.default_detail)),
        status=404,
    )


def server_error(request: HttpRequest) -> HttpResponse:
    """``handler500``: un error fuera de las vistas de DRF (un middleware, por ejemplo)."""
    if not _is_api(request):
        return defaults.server_error(request)
    return JsonResponse(build_error_body("INTERNAL_ERROR", INTERNAL_ERROR_MESSAGE), status=500)


# --- Login de /admin/ (SEC-18) ---------------------------------------------------------


def admin_login(request: HttpRequest, **kwargs: Any) -> HttpResponse:
    """El login de ``/admin/`` con un límite por IP (``AUTH_RATE_LIMITS["admin_login"]``).
    Solo cuentan los ``POST``. Solo existe si ``/admin/`` se publica (``config/urls.py``)."""
    from django.contrib import admin

    from apps.identity.throttling import AdminLoginRateThrottle

    if request.method == "POST":
        throttle = AdminLoginRateThrottle()
        if not throttle.allow_request(request, None):  # type: ignore[arg-type]
            wait = throttle.wait()
            response = HttpResponse(rate_limited_message(wait), status=429)
            if wait is not None:
                response["Retry-After"] = str(math.ceil(wait))
            return response
    return admin.site.login(request, **kwargs)
