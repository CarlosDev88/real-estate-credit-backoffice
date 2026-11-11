import re

from rest_framework import serializers

# Documentos que solo admiten dígitos. Los demás (CE, pasaporte) son alfanuméricos.
_NUMERIC_DOCUMENT_TYPES = {"CC", "PPT"}
_NUMERIC_PATTERN = re.compile(r"^\d{4,15}$")
_ALPHANUMERIC_PATTERN = re.compile(r"^[A-Z0-9]{4,20}$")


def normalize_document_number(document_type_code: str, value: str) -> str:
    """Quita espacios, puntos y guiones, y pasa a mayúsculas: `1.032.445.908` → `1032445908`.

    Normalizar evita que el mismo documento se registre dos veces con otro formato.
    """
    compact = re.sub(r"[\s.\-]", "", value or "").upper()
    pattern = (
        _NUMERIC_PATTERN if document_type_code in _NUMERIC_DOCUMENT_TYPES else _ALPHANUMERIC_PATTERN
    )
    if not pattern.match(compact):
        kind = "solo dígitos" if pattern is _NUMERIC_PATTERN else "letras y dígitos"
        raise serializers.ValidationError(
            f"Número de documento no válido para {document_type_code}: usa {kind}."
        )
    return compact


def mask_document_number(value: str) -> str:
    """Muestra solo los últimos 4 caracteres: `1032445908` → `••••••5908`."""
    visible = value[-4:]
    return "•" * max(len(value) - len(visible), 0) + visible
