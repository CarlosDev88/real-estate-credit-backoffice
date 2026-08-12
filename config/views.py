from django.db import connections
from django.db.utils import DatabaseError
from django.http import JsonResponse
from django.http.request import HttpRequest
from django.views.decorators.http import require_GET


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
