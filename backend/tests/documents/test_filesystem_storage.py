"""Almacenamiento en disco (``DOCUMENT_STORAGE_BACKEND=filesystem``) y su URL firmada."""

import io
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from django.conf import settings
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.http import FileResponse
from django.test import override_settings
from drf_spectacular.generators import SchemaGenerator
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.documents.exceptions import StorageUnavailable
from apps.documents.storage import (
    OBJECT_TOKEN_SALT,
    FilesystemStorage,
    InvalidObjectKey,
    InvalidObjectToken,
    get_storage,
    read_object_token,
    sign_object_url,
    validate_storage_settings,
)
from config.log_redaction import RedactObjectTokensFilter
from tests.helpers import assert_error

KEY = "documents/3f1c/7b2e"
URL_PREFIX = "/api/v1/storage/objects/"


@pytest.fixture
def disk(tmp_path: Path) -> Iterator[FilesystemStorage]:
    get_storage.cache_clear()
    with override_settings(
        DEBUG=True,
        DOCUMENT_STORAGE_BACKEND="filesystem",
        DOCUMENT_STORAGE_ROOT=str(tmp_path / "documents"),
    ):
        storage = get_storage()
        assert isinstance(storage, FilesystemStorage)
        storage.ensure_bucket()
        yield storage
        get_storage.cache_clear()


def download(client: APIClient, url: str) -> tuple[FileResponse, bytes]:
    response = cast(FileResponse, client.get(url))
    body = response.getvalue()
    response.close()
    return response, body


def signed(key: str = KEY, *, expires_in: int = 300, **extra: str) -> str:
    extra.setdefault("filename", "cédula.pdf")
    extra.setdefault("content_type", "application/pdf")
    return sign_object_url(key, expires_in=expires_in, **extra)


# --- Guardar, leer y borrar ---------------------------------------------------------------


def test_round_trip(disk: FilesystemStorage) -> None:
    disk.put(KEY, io.BytesIO(b"%PDF-1"), content_type="application/pdf")
    disk.put(KEY, io.BytesIO(b"%PDF-2"), content_type="application/pdf")  # Reemplaza.

    with disk.open(KEY) as stream:
        assert stream.read() == b"%PDF-2"
    assert (disk.root / "documents" / "3f1c" / "7b2e").is_file()
    assert not list(disk.root.rglob(".tmp-*"))

    disk.delete(KEY)
    disk.delete(KEY)  # Borrar lo que no existe no falla.
    with pytest.raises(StorageUnavailable, match="no existe"):
        disk.open(KEY)
    assert disk.provider == "filesystem"
    assert disk.encryption_key_version is None


def test_a_failed_write_leaves_no_partial_object(disk: FilesystemStorage) -> None:
    class Broken(io.BytesIO):
        def read(self, *args: Any) -> bytes:
            raise OSError("disco lleno")

    with pytest.raises(StorageUnavailable, match="put"):
        disk.put(KEY, Broken(), content_type="application/pdf")

    assert not [path for path in disk.root.rglob("*") if path.is_file()]


@pytest.mark.parametrize(
    "key",
    [
        "",
        "/etc/passwd",
        "../secreto",
        "documents/../../secreto",
        "documents/./x",
        "documents//x",
        "documents/",
        "documents\\..\\x",
        "documents/x\x00",
    ],
)
def test_keys_cannot_leave_the_root(disk: FilesystemStorage, key: str) -> None:
    for operation in (
        lambda: disk.put(key, io.BytesIO(b"x"), content_type="text/plain"),
        lambda: disk.open(key),
        lambda: disk.delete(key),
        lambda: disk.presigned_url(key, expires_in=60, filename="x", content_type="text/plain"),
    ):
        with pytest.raises(InvalidObjectKey):
            operation()


def test_symlinks_cannot_leave_the_root(disk: FilesystemStorage, tmp_path: Path) -> None:
    outside = tmp_path / "fuera"
    outside.mkdir()
    (outside / "secreto").write_bytes(b"x")
    (disk.root / "documents").mkdir()
    (disk.root / "documents" / "enlace").symlink_to(outside)

    with pytest.raises(InvalidObjectKey):
        disk.open("documents/enlace/secreto")


def test_os_errors_become_storage_unavailable(
    disk: FilesystemStorage, caplog: pytest.LogCaptureFixture
) -> None:
    (disk.root / "documents").mkdir()

    with caplog.at_level(logging.WARNING), pytest.raises(StorageUnavailable, match="open"):
        disk.open("documents")  # Es una carpeta.
    with pytest.raises(StorageUnavailable, match="delete"):
        disk.delete("documents")
    # El log dice qué operación falló, nunca la clave.
    assert caplog.messages == [
        "Almacenamiento en disco: open falló (IsADirectoryError)",
        "Almacenamiento en disco: delete falló (IsADirectoryError)",
    ]


def test_ensure_bucket_and_check(tmp_path: Path) -> None:
    storage = FilesystemStorage(root=tmp_path / "a" / "documents", bucket="local")

    with pytest.raises(StorageUnavailable, match="check"):
        storage.check()  # La carpeta no existe.
    assert storage.ensure_bucket() is True
    assert storage.ensure_bucket() is False
    storage.check()
    assert list(storage.root.iterdir()) == []  # La prueba de escritura no deja rastro.

    blocked = FilesystemStorage(root=tmp_path / "archivo" / "documents", bucket="local")
    (tmp_path / "archivo").write_bytes(b"")
    with pytest.raises(StorageUnavailable, match="ensure_bucket"):
        blocked.ensure_bucket()


# --- URL firmada --------------------------------------------------------------------------


def test_presigned_url_is_a_relative_signed_path(disk: FilesystemStorage) -> None:
    url = disk.presigned_url(KEY, expires_in=300, filename="cédula.pdf", content_type="image/png")

    assert url.startswith(URL_PREFIX)
    assert "://" not in url
    grant = read_object_token(url.removeprefix(URL_PREFIX))
    assert (grant.key, grant.filename, grant.content_type) == (KEY, "cédula.pdf", "image/png")


def test_tokens_expire() -> None:
    with freeze_time("2026-11-11 12:00:00"):
        token = signed(expires_in=300).removeprefix(URL_PREFIX)
    with freeze_time("2026-11-11 12:04:59"):
        assert read_object_token(token).key == KEY
    with freeze_time("2026-11-11 12:05:00"), pytest.raises(InvalidObjectToken):
        read_object_token(token)


@pytest.mark.parametrize(
    "token",
    [
        signing.dumps({"k": KEY, "f": "x", "t": "text/plain", "e": 4_102_444_800}),  # Otra sal.
        signing.dumps({"k": KEY}, salt=OBJECT_TOKEN_SALT),  # Incompleto.
        signing.dumps({"k": KEY, "f": "x", "t": "t", "e": "mañana"}, salt=OBJECT_TOKEN_SALT),
        "no-es-un-token",
    ],
)
def test_foreign_or_malformed_tokens_are_rejected(token: str) -> None:
    with pytest.raises(InvalidObjectToken):
        read_object_token(token)


# --- Endpoint -----------------------------------------------------------------------------


def test_download_with_a_valid_link(disk: FilesystemStorage, api_client: APIClient) -> None:
    disk.put(KEY, io.BytesIO(b"%PDF-1.7 contenido"), content_type="application/pdf")

    response, body = download(api_client, signed())  # Sin sesión: la firma es la credencial.

    assert response.status_code == 200
    assert body == b"%PDF-1.7 contenido"
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Length"] == str(len(body))
    assert response["Content-Disposition"] == (
        "attachment; filename=\"cedula.pdf\"; filename*=UTF-8''c%C3%A9dula.pdf"
    )
    assert response["Cache-Control"] == "no-store"
    assert response["X-Content-Type-Options"] == "nosniff"


def test_uploaded_html_is_always_an_attachment(
    disk: FilesystemStorage, api_client: APIClient
) -> None:
    disk.put(KEY, io.BytesIO(b"<script>alert(1)</script>"), content_type="text/html")

    response, _ = download(api_client, signed(filename="pagina.html", content_type="text/html"))

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")
    assert "inline" not in response["Content-Disposition"]
    assert response["X-Content-Type-Options"] == "nosniff"


def test_expired_or_altered_links_are_forbidden(
    disk: FilesystemStorage, api_client: APIClient
) -> None:
    disk.put(KEY, io.BytesIO(b"x"), content_type="application/pdf")
    with freeze_time("2026-11-11 12:00:00"):
        url = signed(expires_in=300)
    altered = url[:-1] + ("A" if url[-1] != "A" else "B")

    with freeze_time("2026-11-11 12:05:01"):
        assert_error(api_client.get(url), 403, "DOWNLOAD_LINK_INVALID")
    assert_error(api_client.get(altered), 403, "DOWNLOAD_LINK_INVALID")


def test_missing_objects_and_invalid_keys_are_not_found(
    disk: FilesystemStorage, api_client: APIClient
) -> None:
    assert_error(api_client.get(signed()), 404, "RESOURCE_NOT_FOUND")
    token = signing.dumps(
        {"k": "../fuera", "f": "x", "t": "text/plain", "e": 4_102_444_800},
        salt=OBJECT_TOKEN_SALT,
        compress=True,
    )
    assert_error(api_client.get(URL_PREFIX + token), 404, "RESOURCE_NOT_FOUND")


def test_endpoint_does_not_exist_outside_filesystem_mode(
    disk: FilesystemStorage, api_client: APIClient
) -> None:
    disk.put(KEY, io.BytesIO(b"x"), content_type="application/pdf")
    url = signed()

    # Sin DEBUG (ni pruebas), aunque el token sea válido.
    with override_settings(DEBUG=False, DOCUMENT_ALLOW_FAKE_SERVICES=False):
        assert_error(api_client.get(url), 404, "RESOURCE_NOT_FOUND")

    # Con otro almacenamiento.
    get_storage.cache_clear()
    with override_settings(DOCUMENT_STORAGE_BACKEND="memory"):
        assert_error(api_client.get(url), 404, "RESOURCE_NOT_FOUND")
        get_storage.cache_clear()


def test_endpoint_is_not_in_the_openapi_schema() -> None:
    schema = SchemaGenerator().get_schema(request=None, public=True)

    assert not [path for path in schema["paths"] if "storage" in path]


# --- Configuración y logs -----------------------------------------------------------------


@override_settings(DOCUMENT_STORAGE_BACKEND="filesystem", DOCUMENT_STORAGE_ROOT="/data/documents")
def test_filesystem_settings_are_validated() -> None:
    validate_storage_settings()

    with (
        override_settings(DOCUMENT_STORAGE_ROOT="data/documents"),
        pytest.raises(ImproperlyConfigured, match="absoluta"),
    ):
        validate_storage_settings()
    with (
        override_settings(DEBUG=False, DOCUMENT_ALLOW_FAKE_SERVICES=False),
        pytest.raises(ImproperlyConfigured, match="filesystem"),
    ):
        validate_storage_settings()


@override_settings(
    DOCUMENT_STORAGE_BACKEND="filesystem",
    DOCUMENT_STORAGE_ROOT="/data/documents",
    DOCUMENT_STORAGE_BUCKET="local-docs",
)
def test_get_storage_builds_the_filesystem_storage() -> None:
    get_storage.cache_clear()
    try:
        storage = get_storage()
        assert isinstance(storage, FilesystemStorage)
        assert (storage.root, storage.bucket) == (Path("/data/documents"), "local-docs")
    finally:
        get_storage.cache_clear()


def test_tokens_are_redacted_from_logs() -> None:
    def record(msg: str, *args: Any) -> logging.LogRecord:
        return logging.LogRecord("django.server", logging.INFO, __file__, 1, msg, args, None)

    access = record('"%s" %s %s', "GET /api/v1/storage/objects/eyJr:1t:sig HTTP/1.1", 200, 9)
    other = record("Paquete %s pedido", "abc")
    redactor = RedactObjectTokensFilter()

    assert redactor.filter(access) and redactor.filter(other)
    assert access.getMessage() == '"GET /api/v1/storage/objects/*** HTTP/1.1" 200 9'
    assert other.getMessage() == "Paquete abc pedido"
    logging_config = cast(dict[str, Any], settings.LOGGING)
    assert "redact_object_tokens" in logging_config["handlers"]["console"]["filters"]
