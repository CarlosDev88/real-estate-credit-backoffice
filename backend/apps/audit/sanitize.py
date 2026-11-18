"""Saneamiento único de ``metadata`` antes de guardarla (API §24.1).

- Se descarta toda clave cuyo nombre contenga un término prohibido (``FORBIDDEN_KEY_PARTS``):
  contraseñas, tokens, cookies, cabeceras de autorización, firmas y URLs.
- Los números de documento (``DOCUMENT_KEYS``) se enmascaran: solo quedan los últimos 4.
- Un texto que parece una URL con consulta (posible URL firmada) se reemplaza.
- Los textos largos se recortan a ``MAX_TEXT_LENGTH``.

Se aplica recursivamente a diccionarios y listas.
"""

import re
from typing import Any

FORBIDDEN_KEY_PARTS: tuple[str, ...] = (
    "password",
    "passwd",
    "token",
    "authorization",
    "cookie",
    "secret",
    "signature",
    "url",
    "otp",
    "api_key",
)
DOCUMENT_KEYS: frozenset[str] = frozenset({"document_number", "document", "tax_id"})
MAX_TEXT_LENGTH = 500
URL_WITH_QUERY = re.compile(r"https?://\S*\?", re.IGNORECASE)
OMITTED_URL = "[URL omitida]"


def is_forbidden_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in FORBIDDEN_KEY_PARTS)


def mask_document(value: Any) -> str:
    """``1032445908`` → ``••••5908``."""
    text = re.sub(r"\s", "", str(value))
    return "••••" + text[-4:] if len(text) > 4 else "••••"


def mask_email(email: str) -> str:
    """``laura.gomez@example.com`` → ``l•••@example.com``."""
    local, at, domain = email.partition("@")
    if not at:
        return "•••"
    return f"{local[:1]}•••@{domain}"


def _clean_text(value: str) -> str:
    if URL_WITH_QUERY.search(value):
        return OMITTED_URL
    return value if len(value) <= MAX_TEXT_LENGTH else value[: MAX_TEXT_LENGTH - 1] + "…"


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if is_forbidden_key(name):
                continue
            clean[name] = mask_document(item) if name.lower() in DOCUMENT_KEYS else sanitize(item)
        return clean
    if isinstance(value, list | tuple | set | frozenset):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return _clean_text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    return _clean_text(str(value))


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    result = sanitize(metadata or {})
    assert isinstance(result, dict)
    return result
