"""Piezas del esquema OpenAPI que comparten varias apps."""

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
