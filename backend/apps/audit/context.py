"""Contexto de la petición en curso para la auditoría: la IP de quien llama.

``AuditContextMiddleware`` la guarda al recibir cada petición, así que un evento que se
registra desde una señal (sin la petición a mano) también la lleva. Al devolver la
respuesta, audita lo que no tiene señal (``apps.audit.hooks``).

La IP sale de ``REMOTE_ADDR``. Mientras no haya un proxy de confianza configurado no se
usa ``X-Forwarded-For`` (``AUDIT_TRUST_FORWARDED_FOR``): en local la petición llega por
el rewrite de Next, así que se guarda la IP de ese proxy.
"""

import ipaddress
from collections.abc import Callable
from contextvars import ContextVar

from django.http import HttpRequest, HttpResponse

AUDIT_TRUST_FORWARDED_FOR = False

_client_ip: ContextVar[str | None] = ContextVar("audit_client_ip", default=None)


def request_ip(request: HttpRequest) -> str | None:
    candidate = request.META.get("REMOTE_ADDR", "")
    if AUDIT_TRUST_FORWARDED_FOR:  # pragma: no cover - sin proxy de confianza todavía
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        candidate = forwarded.split(",")[0].strip() or candidate
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def get_client_ip() -> str | None:
    return _client_ip.get()


class AuditContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        token = _client_ip.set(request_ip(request))
        try:
            response = self.get_response(request)
            # Import diferido: el middleware se carga con la configuración, antes que los
            # modelos.
            from apps.audit.hooks import safe_audit_response

            safe_audit_response(response)
        finally:
            # A diferencia del request_id, la IP no la usan los logs: se limpia para que un
            # evento fuera de una petición no herede la de la anterior.
            _client_ip.reset(token)
        return response
