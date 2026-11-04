import pytest
from rest_framework.exceptions import ValidationError

from apps.partners.validators import nit_check_digit, normalize_nit
from config.validators import validate_e164_phone


@pytest.mark.parametrize(
    ("number", "check_digit"),
    [
        ("890903938", 8),  # Bancolombia
        ("899999068", 1),  # Ecopetrol
        ("800197268", 4),  # DIAN
        ("860002964", 4),  # Banco de Bogotá
    ],
)
def test_nit_check_digit_matches_known_nits(number, check_digit):
    assert nit_check_digit(number) == check_digit


@pytest.mark.parametrize(
    "raw", ["890903938-8", "890.903.938-8", " 890 903 938 - 8 ", "0890903938-8"]
)
def test_normalize_nit_accepts_common_formats(raw):
    assert normalize_nit(raw) == "890903938-8"


@pytest.mark.parametrize("raw", ["890903938", "890903938-1", "ABC-1", "123-4", ""])
def test_normalize_nit_rejects_invalid_values(raw):
    with pytest.raises(ValidationError):
        normalize_nit(raw)


def test_validate_e164_phone():
    assert validate_e164_phone("+57 300 123 4567") == "+573001234567"
    assert validate_e164_phone("") == ""
    with pytest.raises(ValidationError):
        validate_e164_phone("3001234567")
