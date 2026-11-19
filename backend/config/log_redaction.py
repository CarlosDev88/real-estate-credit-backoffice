"""Filtros de log que ocultan credenciales y datos personales.

Vive en ``config`` y no importa nada de las apps: Django configura el logging antes de
cargarlas.
"""

import logging
import re

# Token de ``GET /api/v1/storage/objects/{token}`` (URL firmada del almacenamiento en disco).
OBJECT_TOKEN = re.compile(r"(/storage/objects/)[^\s\"'?#]+")

# Parámetros de consulta con datos personales (RNF-16, SEC-15): lo que se busca suele ser
# un documento, un nombre o un correo. Su valor se escribe como ``***``.
SENSITIVE_QUERY_PARAMS = ("search", "email", "document_number", "q")
SENSITIVE_QUERY_VALUE = re.compile(
    r"([?&](?:" + "|".join(SENSITIVE_QUERY_PARAMS) + r")=)[^&\s\"'#]*", re.IGNORECASE
)


def redact(message: str) -> str:
    if "/storage/objects/" in message:
        message = OBJECT_TOKEN.sub(r"\1***", message)
    if "=" in message:
        message = SENSITIVE_QUERY_VALUE.sub(r"\1***", message)
    return message


class RedactObjectTokensFilter(logging.Filter):
    """Reemplaza por ``***`` el token de las URL firmadas y el valor de los parámetros de
    búsqueda con datos personales, en cualquier mensaje (también el log de peticiones)."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True
