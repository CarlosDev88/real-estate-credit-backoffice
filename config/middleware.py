import re
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from config.request_context import set_request_id

REQUEST_ID_HEADER = "X-Request-ID"
# Solo se acepta un identificador entrante corto y sin caracteres de control, para que no
# pueda inyectar contenido en logs ni en cabeceras.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestIDMiddleware:
    """Asigna un ``request_id`` a cada petición y lo devuelve en ``X-Request-ID``."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else str(uuid.uuid4())
        request.request_id = request_id  # type: ignore[attr-defined]

        # No se restablece al terminar: Django registra los errores 4xx/5xx
        # (`django.request`) después de recorrer los middlewares, y esos logs también
        # deben llevar el request_id. Cada petición nueva sobrescribe el valor.
        set_request_id(request_id)
        response = self.get_response(request)

        response[REQUEST_ID_HEADER] = request_id
        return response
