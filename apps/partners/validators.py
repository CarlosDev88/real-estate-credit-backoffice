import re

from rest_framework import serializers

# Pesos de la DIAN para calcular el dígito de verificación, de derecha a izquierda.
_NIT_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)
_NIT_PATTERN = re.compile(r"^(\d{6,15})-(\d)$")
_E164_PATTERN = re.compile(r"^\+[1-9]\d{6,14}$")


def nit_check_digit(number: str) -> int:
    total = sum(
        int(digit) * weight for digit, weight in zip(reversed(number), _NIT_WEIGHTS, strict=False)
    )
    remainder = total % 11
    return remainder if remainder in (0, 1) else 11 - remainder


def normalize_nit(value: str) -> str:
    """Normaliza un NIT a ``<número>-<dígito>`` y valida el dígito de verificación.

    Acepta puntos, espacios y guiones (``900.123.456-8``). El dígito de verificación
    es obligatorio para que un mismo NIT no pueda registrarse de dos formas.
    """
    compact = re.sub(r"[\s.]", "", value or "")
    compact = re.sub(r"-+", "-", compact)
    match = _NIT_PATTERN.match(compact)
    if not match:
        raise serializers.ValidationError(
            "Escribe el NIT con su dígito de verificación, por ejemplo 900123456-8."
        )
    number, check_digit = match.groups()
    number = number.lstrip("0") or "0"
    if nit_check_digit(number) != int(check_digit):
        raise serializers.ValidationError("El dígito de verificación del NIT no es correcto.")
    return f"{number}-{check_digit}"


def validate_e164_phone(value: str) -> str:
    compact = re.sub(r"[\s()-]", "", value or "")
    if compact and not _E164_PATTERN.match(compact):
        raise serializers.ValidationError(
            "Usa el formato internacional E.164, por ejemplo +573001234567."
        )
    return compact
