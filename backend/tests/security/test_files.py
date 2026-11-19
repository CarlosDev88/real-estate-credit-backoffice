"""Archivos (``specs/TAREA-seguridad.md``, Parte 4.3): los casos concretos de la spec.

Lo general ya está en ``tests/documents`` y ``tests/applications/dossier`` (firma de
bytes, extensión, doble extensión, nombres, claves sin el nombre original,
``Content-Disposition``, tokens que vencen o se alteran, redacción de los tokens en el log,
solo archivos limpios en la descarga). Aquí: las cargas maliciosas que nombra la spec, y
que un archivo ``PENDING`` o ``INFECTED`` nunca se firma, ni para el asesor ni para el
comprador.
"""

import io
import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.conf import settings
from django.utils import timezone
from freezegun import freeze_time

from apps.applications.demo_data import demo_pdf, demo_png
from apps.documents.constants import JPEG, MAX_FILE_SIZE_BYTES, PDF, PNG
from apps.documents.exceptions import FileTooLarge, UnsupportedFileType
from apps.documents.file_validation import inspect_upload
from apps.documents.models import FileObject
from apps.documents.models.file_object import ScanStatus
from apps.documents.storage import (
    InvalidObjectToken,
    new_document_key,
    read_object_token,
    sign_object_url,
)
from tests.security.conftest import ADVISOR_OWNER, BUYER_OWNER, World
from tests.security.requests import client_for

ALLOWED = (PDF, JPEG, PNG)


def _inspect(content: bytes, filename: str, declared: str | None = None) -> Any:
    return inspect_upload(
        io.BytesIO(content),
        filename=filename,
        declared_mime_type=declared,
        allowed_mime_types=ALLOWED,
        max_size_bytes=MAX_FILE_SIZE_BYTES,
    )


PDF_WITH_JS = (
    b"%PDF-1.4\n1 0 obj << /Type /Catalog /OpenAction << /S /JavaScript "
    b"/JS (app.alert('x')) >> >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"
)
HTML = b"<!doctype html><script>alert(document.cookie)</script>"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
ZIP = b"PK\x03\x04" + b"\x00" * 64


@pytest.mark.parametrize(
    ("content", "filename", "declared", "code"),
    [
        (HTML, "cedula.pdf", "application/pdf", "UNKNOWN_CONTENT"),
        (HTML, "cedula.html", "text/html", "BLOCKED_EXTENSION"),
        (SVG, "foto.svg", "image/svg+xml", "BLOCKED_EXTENSION"),
        (SVG, "foto.png", "image/png", "UNKNOWN_CONTENT"),
        (ZIP, "soportes.zip", "application/zip", "UNKNOWN_CONTENT"),
        (ZIP, "soportes.pdf", "application/pdf", "UNKNOWN_CONTENT"),
        (demo_pdf("x"), "cedula.pdf.exe", "application/pdf", "BLOCKED_EXTENSION"),
        (demo_png(), "foto.pdf", "application/pdf", "EXTENSION_MISMATCH"),
    ],
    ids=[
        "html-como-pdf",
        "html",
        "svg",
        "svg-como-png",
        "zip",
        "zip-como-pdf",
        "pdf.exe",
        "png-como-pdf",
    ],
)
def test_malicious_uploads_are_rejected(
    content: bytes, filename: str, declared: str, code: str
) -> None:
    with pytest.raises(UnsupportedFileType) as error:
        _inspect(content, filename, declared)
    assert error.value.details[0]["code"] == code


def test_polyglots_keep_their_real_type() -> None:
    """Un PDF con JavaScript y un PNG con HTML al final pasan la validación (la firma es
    válida), pero quedan con su tipo real: se sirven como ``application/pdf`` o
    ``image/png``, siempre adjuntos y con ``nosniff`` (``storage_views.py``,
    ``tests/documents``). El JavaScript del PDF lo trata el antivirus y el visor; se anota
    en ``docs/seguridad/04-manual.md``."""
    assert _inspect(PDF_WITH_JS, "cedula.pdf", "application/pdf").mime_type == PDF
    assert _inspect(demo_png() + HTML, "foto.png", "image/png").mime_type == PNG


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("..\\..\\windows\\cedula.pdf", "cedula.pdf"),
        ("cedula\x00.pdf", "cedula.pdf"),
        ("cedula‮fdp.pdf", "cedulafdp.pdf"),  # Sin el carácter de control RTL.
    ],
)
def test_client_names_lose_paths_and_control_characters(raw: str, expected: str) -> None:
    assert _inspect(demo_pdf("x"), raw).filename == expected


def test_a_300_character_name_is_cut_to_255_and_keeps_the_extension() -> None:
    inspected = _inspect(demo_pdf("x"), "a" * 296 + ".pdf")
    assert len(inspected.filename) == 255
    assert inspected.filename.endswith(".pdf")


def test_storage_key_is_built_from_ids_only() -> None:
    """La clave es ``documents/<solicitud>/<uuid>``: el nombre del cliente nunca llega a
    ella (solo al ``Content-Disposition``)."""
    application_id = uuid.uuid4()
    prefix, folder, name = new_document_key(application_id).split("/")
    assert (prefix, folder) == ("documents", str(application_id))
    assert uuid.UUID(name)


def test_ten_megabytes_pass_and_one_more_byte_does_not() -> None:
    limit = MAX_FILE_SIZE_BYTES
    assert limit == 10 * 1024 * 1024
    body = demo_pdf("x")
    exact = body + b"0" * (limit - len(body))
    assert _inspect(exact, "grande.pdf").size_bytes == limit
    with pytest.raises(FileTooLarge):
        _inspect(exact + b"0", "grande.pdf")


def test_signed_url_lasts_five_minutes_and_is_bound_to_its_key() -> None:
    assert settings.DOCUMENT_DOWNLOAD_URL_SECONDS == 300
    url = sign_object_url(
        "documents/a/b", expires_in=300, filename="c.pdf", content_type="application/pdf"
    )
    token = url.rsplit("/", 1)[-1]
    assert read_object_token(token).key == "documents/a/b"
    middle = len(token) // 2
    altered = token[:middle] + ("A" if token[middle] != "A" else "B") + token[middle + 1 :]
    with pytest.raises(InvalidObjectToken):
        read_object_token(altered)
    with pytest.raises(InvalidObjectToken), freeze_time(timezone.now() + timedelta(seconds=301)):
        read_object_token(token)


@pytest.mark.django_db
@pytest.mark.parametrize("status", [ScanStatus.PENDING, ScanStatus.INFECTED, ScanStatus.INVALID])
def test_unclean_files_are_never_signed(world: World, status: str) -> None:
    # Un PENDING no tiene fecha de análisis (restricción `ck_file_objects_scan_date`).
    scanned_at = None if status == ScanStatus.PENDING else timezone.now()
    FileObject.objects.filter(pk=world.a.file.file_object_id).update(
        scan_status=status, scanned_at=scanned_at
    )
    advisor = client_for(world, ADVISOR_OWNER).get(
        f"/api/v1/document-files/{world.a.file.pk}/download"
    )
    buyer = client_for(world, BUYER_OWNER).get(
        f"/api/v1/buyer/document-files/{world.a.file.pk}/download"
    )
    for response in (advisor, buyer):
        assert response.status_code == 409, response.content
        assert response.json()["code"] == "FILE_NOT_CLEAN"
        assert "url" not in response.json()
