"""Validación técnica de archivos antes de guardarlos (REQUERIMIENTOS §9.5)."""

import hashlib
import io
from typing import Any

import pytest
from rest_framework.exceptions import ValidationError

from apps.documents.constants import JPEG, PDF, PNG
from apps.documents.exceptions import FileTooLarge, UnsupportedFileType
from apps.documents.file_validation import (
    MAX_FILENAME_LENGTH,
    detect_mime_type,
    inspect_upload,
    sanitize_filename,
)

PDF_BYTES = b"%PDF-1.7\n" + b"0" * 200
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"1" * 200
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"2" * 200
ALL_TYPES = [PDF, JPEG, PNG]


def inspect(content: bytes, filename: str = "cedula.pdf", **extra: Any) -> Any:
    extra.setdefault("declared_mime_type", None)
    extra.setdefault("allowed_mime_types", ALL_TYPES)
    extra.setdefault("max_size_bytes", 10 * 1024 * 1024)
    return inspect_upload(io.BytesIO(content), filename=filename, **extra)


def error_code(error: pytest.ExceptionInfo[Any]) -> str:
    details: list[dict[str, str]] = error.value.details
    assert details[0]["field"] == "file"
    return details[0]["code"]


@pytest.mark.parametrize(
    ("content", "filename", "mime_type"),
    [
        (PDF_BYTES, "cedula.pdf", PDF),
        (JPEG_BYTES, "foto.JPG", JPEG),
        (JPEG_BYTES, "foto.jpeg", JPEG),
        (PNG_BYTES, "captura.png", PNG),
    ],
)
def test_detects_the_real_type_and_hashes_the_content(
    content: bytes, filename: str, mime_type: str
) -> None:
    stream = io.BytesIO(content)

    result = inspect_upload(
        stream,
        filename=filename,
        declared_mime_type=mime_type,
        allowed_mime_types=ALL_TYPES,
        max_size_bytes=len(content),
    )

    assert result.mime_type == mime_type
    assert result.size_bytes == len(content)
    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert result.filename == filename
    # El flujo queda al inicio, listo para guardarlo.
    assert stream.tell() == 0


def test_reads_large_files_in_chunks() -> None:
    content = b"%PDF-1.4\n" + b"x" * (200 * 1024)

    result = inspect(content)

    assert result.size_bytes == len(content)
    assert result.sha256 == hashlib.sha256(content).hexdigest()


def test_detect_mime_type_only_knows_the_closed_list() -> None:
    assert detect_mime_type(b"%PDF-") == PDF
    assert detect_mime_type(b"GIF89a") is None
    assert detect_mime_type(b"") is None


def test_uninformative_or_alias_declared_types_are_accepted() -> None:
    for declared in ("", "application/octet-stream", "image/jpg", "IMAGE/JPEG; charset=binary"):
        assert inspect(JPEG_BYTES, "foto.jpg", declared_mime_type=declared).mime_type == JPEG


def test_declared_type_that_contradicts_the_content_is_rejected() -> None:
    with pytest.raises(UnsupportedFileType) as error:
        inspect(PDF_BYTES, declared_mime_type="image/png")
    assert error_code(error) == "DECLARED_TYPE_MISMATCH"


def test_unknown_content_is_rejected_even_with_a_pdf_name() -> None:
    with pytest.raises(UnsupportedFileType) as error:
        inspect(b"<html><script>alert(1)</script></html>", "factura.pdf")
    assert error_code(error) == "UNKNOWN_CONTENT"


def test_type_not_allowed_by_the_document_type() -> None:
    with pytest.raises(UnsupportedFileType) as error:
        inspect(PNG_BYTES, "captura.png", allowed_mime_types=[PDF])
    assert error_code(error) == "TYPE_NOT_ALLOWED"
    assert "application/pdf" in str(error.value.details[0]["message"])


@pytest.mark.parametrize("filename", ["cedula.png", "cedula", "cedula.txt"])
def test_extension_must_match_the_content(filename: str) -> None:
    with pytest.raises(UnsupportedFileType) as error:
        inspect(PDF_BYTES, filename)
    assert error_code(error) == "EXTENSION_MISMATCH"


@pytest.mark.parametrize("filename", ["foto.png.pdf", "cedula.jpg.pdf"])
def test_double_extension_is_rejected(filename: str) -> None:
    with pytest.raises(UnsupportedFileType) as error:
        inspect(PDF_BYTES, filename)
    assert error_code(error) == "DOUBLE_EXTENSION"


@pytest.mark.parametrize("filename", ["cedula.pdf.exe", "cedula.exe.pdf", "pagina.HTML", "a.svg"])
def test_executable_extensions_are_rejected_before_reading(filename: str) -> None:
    stream = io.BytesIO(PDF_BYTES)
    with pytest.raises(UnsupportedFileType) as error:
        inspect_upload(
            stream,
            filename=filename,
            declared_mime_type=None,
            allowed_mime_types=ALL_TYPES,
            max_size_bytes=1024,
        )
    assert error_code(error) == "BLOCKED_EXTENSION"
    assert stream.tell() == 0


def test_dots_that_are_not_extensions_are_fine() -> None:
    assert inspect(PDF_BYTES, "certificado.laboral.v2.pdf").filename == (
        "certificado.laboral.v2.pdf"
    )


def test_file_over_the_type_limit_stops_reading() -> None:
    with pytest.raises(FileTooLarge) as error:
        inspect(PDF_BYTES, max_size_bytes=100)
    assert error_code(error) == "FILE_TOO_LARGE"
    assert "100 bytes" in error.value.details[0]["message"]


def test_empty_file_is_a_validation_error() -> None:
    with pytest.raises(ValidationError) as error:
        inspect(b"")
    detail = error.value.detail
    assert isinstance(detail, dict)
    assert "file" in detail


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("C:\\Users\\laura\\Escritorio\\cédula.pdf", "cédula.pdf"),
        ("/tmp/../../etc/passwd.pdf", "passwd.pdf"),
        ("  extracto\tde   enero .pdf  ", "extracto de enero .pdf"),
        ("nómina\x00\u200b.pdf", "nómina.pdf"),
        # NFD → NFC: la "é" compuesta queda como un solo carácter.
        ("cede\u0301dula.pdf", "cedédula.pdf"),
    ],
)
def test_sanitize_filename(raw: str, expected: str) -> None:
    assert sanitize_filename(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "C:\\carpeta\\", "...", "\x00\x01"])
def test_sanitize_filename_rejects_empty_names(raw: str) -> None:
    with pytest.raises(ValidationError):
        sanitize_filename(raw)


def test_long_names_keep_their_extension() -> None:
    long_name = sanitize_filename("a" * 300 + ".pdf")
    assert len(long_name) == MAX_FILENAME_LENGTH
    assert long_name.endswith(".pdf")

    no_extension = sanitize_filename("b" * 300)
    assert no_extension == "b" * MAX_FILENAME_LENGTH
