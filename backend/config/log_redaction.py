"""Filtros de log que ocultan credenciales.

Vive en ``config`` y no importa nada de las apps: Django configura el logging antes de
cargarlas.
"""

import logging
import re

# Token de ``GET /api/v1/storage/objects/{token}`` (URL firmada del almacenamiento en disco).
OBJECT_TOKEN = re.compile(r"(/storage/objects/)[^\s\"'?#]+")


class RedactObjectTokensFilter(logging.Filter):
    """Reemplaza el token de las URL firmadas por ``***`` en cualquier mensaje."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "/storage/objects/" in message:
            record.msg = OBJECT_TOKEN.sub(r"\1***", message)
            record.args = None
        return True
