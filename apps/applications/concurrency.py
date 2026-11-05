"""Concurrencia optimista del expediente (API §6 y REQUERIMIENTOS §8.3, principio 6).

``credit_applications.version`` crece con cada cambio del expediente. Las respuestas
que exponen una solicitud llevan ``ETag: "<version>"`` y todo ``PUT``/``PATCH`` que
modifica el expediente exige ``If-Match`` con esa versión:

- sin ``If-Match``: ``428 PRECONDITION_REQUIRED``;
- con un valor que no es una versión: ``400 VALIDATION_ERROR``;
- con una versión que ya no es la actual: ``409 STALE_VERSION``, con la versión actual
  en ``details[0].current_version``.
"""

import re
from typing import Any

from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.exceptions import PreconditionRequired, StaleVersion

IF_MATCH_HEADER = "If-Match"
_ETAG = re.compile(r'^(?:W/)?"?(\d{1,9})"?$')


def etag_for(version: int) -> str:
    return f'"{version}"'


def with_etag(response: Response, version: int) -> Response:
    response["ETag"] = etag_for(version)
    return response


def expected_version(request: Request) -> int:
    """Versión que el cliente dice tener, leída de ``If-Match``."""
    raw = request.headers.get(IF_MATCH_HEADER)
    if raw is None or not raw.strip():
        raise PreconditionRequired()
    match = _ETAG.match(raw.strip())
    if match is None or int(match.group(1)) < 1:
        raise ValidationError({IF_MATCH_HEADER: ['Debe ser la versión de la solicitud, como "3".']})
    return int(match.group(1))


def stale_version_error(current_version: int) -> StaleVersion:
    details: list[dict[str, Any]] = [
        {
            "field": IF_MATCH_HEADER,
            "code": "STALE_VERSION",
            "message": f"La versión actual es {current_version}.",
            "current_version": current_version,
        }
    ]
    return StaleVersion(details=details)


def ensure_version(current_version: int, expected: int) -> None:
    if current_version != expected:
        raise stale_version_error(current_version)
