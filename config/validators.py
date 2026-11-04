"""Validadores compartidos por varios módulos."""

import re

from rest_framework import serializers

_E164_PATTERN = re.compile(r"^\+[1-9]\d{6,14}$")


def validate_e164_phone(value: str) -> str:
    """Normaliza un teléfono al formato E.164 (``+573001234567``). Vacío es válido."""
    compact = re.sub(r"[\s()-]", "", value or "")
    if compact and not _E164_PATTERN.match(compact):
        raise serializers.ValidationError(
            "Usa el formato internacional E.164, por ejemplo +573001234567."
        )
    return compact
