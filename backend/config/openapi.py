"""Piezas del esquema OpenAPI que comparten varias apps."""

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter

ETAG_HEADER = "ETag"

VERSION_ETAG = (
    'Versión de la solicitud, por ejemplo `"3"`. Se reenvía en `If-Match` al editar el '
    "expediente (API §6)."
)
CONTENT_ETAG = (
    "Huella del contenido. Reenviada en `If-None-Match`, la respuesta es `304` si no cambió."
)


def etag_response_headers(*codes: int, description: str = VERSION_ETAG) -> OpenApiParameter:
    """Declara la cabecera ``ETag`` en las respuestas ``codes`` de ``extend_schema``.

    Va en ``parameters``: drf-spectacular la publica como ``headers.ETag`` (string) de
    esas respuestas, no como parámetro de la petición. Los códigos son las respuestas
    que de verdad la llevan (un ``204`` que no la envía no se declara).
    """
    if not codes:
        raise ValueError("Indica al menos un código de respuesta.")
    return OpenApiParameter(
        ETAG_HEADER,
        OpenApiTypes.STR,
        OpenApiParameter.HEADER,
        response=sorted(set(codes)),
        required=True,
        description=description,
    )


# --- Respuestas de error comunes (SEC-13) -------------------------------------------------

ERROR_SCHEMA_REF = {"$ref": "#/components/schemas/Error"}
OPERATION_METHODS = ("get", "put", "post", "patch", "delete")
COMMON_ERROR_DESCRIPTIONS = {
    "400": "Datos inválidos (`VALIDATION_ERROR`, `MALFORMED_REQUEST`) o regla de negocio.",
    "400-query": "`VALIDATION_ERROR`: un filtro o parámetro de la consulta no es válido.",
    "404": "`RESOURCE_NOT_FOUND`: no existe o está fuera del alcance del usuario.",
    "404-page": "`RESOURCE_NOT_FOUND`: la página no existe (fuera de rango o no numérica).",
    "428": "`PRECONDITION_REQUIRED`: falta `If-Match` con la versión.",
}
IF_MATCH_PARAMETER = {
    "in": "header",
    "name": "If-Match",
    "schema": {"type": "string"},
    "required": True,
    "description": "Versión que se edita, como la devolvió `ETag` (API §6).",
}


def _error_response(key: str) -> dict[str, Any]:
    return {
        "content": {"application/json": {"schema": ERROR_SCHEMA_REF}},
        "description": COMMON_ERROR_DESCRIPTIONS[key],
    }


def _query_parameters(operation: dict[str, Any]) -> list[str]:
    return [p.get("name", "") for p in operation.get("parameters", []) if p.get("in") == "query"]


def _requires_if_match(operation: dict[str, Any]) -> bool:
    return any(
        parameter.get("in") == "header"
        and str(parameter.get("name", "")).lower() == "if-match"
        and parameter.get("required")
        for parameter in operation.get("parameters", [])
    )


def add_error_responses(
    result: dict[str, Any], generator: Any, request: Any, public: bool
) -> dict[str, Any]:
    """Documenta los errores que la API devuelve en todas partes, sin tocar 66 vistas:

    - ``400`` en toda operación con cuerpo o con parámetros de consulta (filtros);
    - ``404`` en toda operación con un id en la ruta o paginada (página fuera de rango);
    - ``428`` donde se exige ``If-Match`` y, al revés, la cabecera ``If-Match`` donde ya
      se documentaba el ``428``.

    Todos con el esquema de error común. Solo agrega lo que falta: las respuestas 2xx y los
    errores ya declarados en cada vista no cambian.

    Además, las respuestas que cambian de forma según el rol (``*ByRole``, de
    ``PolymorphicProxySerializer``) pasan de ``oneOf`` a ``anyOf`` (SEC-21): una página vacía
    o un objeto con los campos comunes es válido para las dos formas, y ``oneOf`` exige
    exactamente una.
    """
    for name, schema in result.get("components", {}).get("schemas", {}).items():
        if name.endswith("ByRole") and "oneOf" in schema and "discriminator" not in schema:
            schema["anyOf"] = schema.pop("oneOf")
    for path, item in result.get("paths", {}).items():
        for method in OPERATION_METHODS:
            operation = item.get(method)
            if not isinstance(operation, dict):
                continue
            responses = operation.setdefault("responses", {})
            query = _query_parameters(operation)
            if "requestBody" in operation:
                responses.setdefault("400", _error_response("400"))
            elif query:
                responses.setdefault("400", _error_response("400-query"))
            if "{" in path:
                responses.setdefault("404", _error_response("404"))
            elif "page" in query:
                responses.setdefault("404", _error_response("404-page"))
            if _requires_if_match(operation):
                responses.setdefault("428", _error_response("428"))
            elif "428" in responses:
                operation.setdefault("parameters", []).append(dict(IF_MATCH_PARAMETER))
    return result
