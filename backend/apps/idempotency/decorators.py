"""Decorador de las vistas con ``Idempotency-Key`` y su declaración en el contrato."""

import functools
from collections.abc import Callable, Mapping
from typing import Any

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse
from rest_framework.request import Request
from rest_framework.response import Response

from apps.idempotency import services
from config.serializers import ErrorSerializer

Handler = Callable[..., Response]


def idempotent(*, store_response: bool = True) -> Callable[[Handler], Handler]:
    """Aplica ``Idempotency-Key`` a un método ``post`` de una vista de DRF. Corre dentro
    del manejador: la autenticación, los permisos y los límites ya pasaron."""

    def decorator(handler: Handler) -> Handler:
        @functools.wraps(handler)
        def wrapper(view: Any, request: Request, *args: Any, **kwargs: Any) -> Response:
            key = services.request_key(request)
            actor = services.request_actor(request)
            if key is None or actor is None:
                return handler(view, request, *args, **kwargs)
            claimed = services.claim(actor, key, request)
            if claimed.replay is not None:
                return claimed.replay
            try:
                response = handler(view, request, *args, **kwargs)
            except BaseException:
                services.release(claimed.record)
                raise
            if 200 <= response.status_code < 300:
                services.complete(claimed.record, response, store_response=store_response)
            else:
                services.release(claimed.record)
            return response

        return wrapper

    return decorator


IDEMPOTENCY_PARAMETER = OpenApiParameter(
    name=services.HEADER,
    type=str,
    location=OpenApiParameter.HEADER,
    required=False,
    description=(
        "Opcional. Clave única de la operación (1 a 100 caracteres visibles; por ejemplo, "
        "un UUID), válida 24 horas para el actor, el método y la ruta. Repetirla con el "
        "mismo cuerpo devuelve la respuesta original; con otro cuerpo, `422 "
        "IDEMPOTENCY_CONFLICT`; mientras la primera sigue en curso, `409 "
        "IDEMPOTENCY_IN_PROGRESS`. Solo se guardan las respuestas `2xx`."
    ),
)

_ERRORS = {
    400: "VALIDATION_ERROR (`Idempotency-Key` mal formada)",
    409: "IDEMPOTENCY_IN_PROGRESS",
    422: "IDEMPOTENCY_CONFLICT",
}


def idempotency_responses(
    responses: Mapping[int, Any], *, extra_409: str | None = None
) -> dict[int, Any]:
    """Agrega los errores de la idempotencia a las respuestas declaradas de la vista."""
    merged = dict(responses)
    errors = dict(_ERRORS)
    if extra_409:
        errors[409] = f"{errors[409]} o {extra_409}"
    for code, description in errors.items():
        current = merged.get(code)
        if isinstance(current, OpenApiResponse) and current.description:
            description = f"{current.description}; {description}"
        merged[code] = OpenApiResponse(response=ErrorSerializer, description=description)
    return merged
