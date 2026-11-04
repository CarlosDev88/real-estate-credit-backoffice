"""Identificador de la petición en curso, disponible para logs y respuestas de error."""

import logging
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


class RequestIDLogFilter(logging.Filter):
    """Añade ``request_id`` a cada registro de log (RNF-16)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True
