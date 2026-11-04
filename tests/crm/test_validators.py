import pytest
from rest_framework.exceptions import ValidationError

from apps.crm.validators import mask_document_number, normalize_document_number


@pytest.mark.parametrize(
    ("document_type", "raw", "expected"),
    [
        ("CC", "1.032.445.908", "1032445908"),
        ("CC", " 1032 445 908 ", "1032445908"),
        ("PPT", "1234-5678", "12345678"),
        ("CE", "e-123.456", "E123456"),
        ("PA", "ax12345", "AX12345"),
    ],
)
def test_normalize_document_number(document_type: str, raw: str, expected: str) -> None:
    assert normalize_document_number(document_type, raw) == expected


@pytest.mark.parametrize(
    ("document_type", "raw"),
    [
        ("CC", "ABC1234"),  # La cédula solo admite dígitos.
        ("CC", "123"),  # Muy corto.
        ("CC", "1234567890123456"),  # Muy largo.
        ("PA", "AB-1"),
        ("PA", "AB#12345"),
        ("CE", ""),
    ],
)
def test_normalize_document_number_rejects_invalid_values(document_type: str, raw: str) -> None:
    with pytest.raises(ValidationError):
        normalize_document_number(document_type, raw)


def test_mask_document_number() -> None:
    assert mask_document_number("1032445908") == "••••••5908"
    assert mask_document_number("1234") == "1234"
    assert mask_document_number("") == ""
