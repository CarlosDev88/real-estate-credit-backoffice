"""Almacenamiento privado compatible con S3, sin servicios reales."""

import io
import logging
import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.documents.exceptions import StorageUnavailable
from apps.documents.storage import (
    SSE_S3_KEY_VERSION,
    MemoryStorage,
    S3Storage,
    attachment_disposition,
    get_storage,
    new_document_key,
    new_package_key,
    validate_storage_settings,
)


@pytest.fixture(autouse=True)
def fresh_storage() -> Iterator[None]:
    get_storage.cache_clear()
    yield
    get_storage.cache_clear()


def client_error(code: str, operation: str = "HeadBucket") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "x"}}, operation)


def s3(client: Any, **extra: Any) -> S3Storage:
    extra.setdefault("bucket", "documentos")
    extra.setdefault("region", "us-east-1")
    return S3Storage(client=client, **extra)


# --- Claves y cabeceras -------------------------------------------------------------------


def test_keys_never_carry_the_original_name() -> None:
    application_id = uuid.uuid4()

    document = new_document_key(application_id)
    package = new_package_key(application_id)

    assert document.startswith(f"documents/{application_id}/")
    assert package.startswith(f"packages/{application_id}/") and package.endswith(".zip")
    assert new_document_key(application_id) != document


def test_attachment_disposition_has_an_ascii_fallback_and_utf8_name() -> None:
    value = attachment_disposition('Cédula "Laura".pdf')

    assert value == (
        "attachment; filename=\"Cedula Laura.pdf\"; filename*=UTF-8''C%C3%A9dula%20%22Laura%22.pdf"
    )
    assert attachment_disposition("файл").startswith('attachment; filename="documento";')


# --- MemoryStorage ------------------------------------------------------------------------


def test_memory_storage_round_trip() -> None:
    storage = MemoryStorage()
    storage.put("documents/a/b", io.BytesIO(b"%PDF-"), content_type="application/pdf")

    with storage.open("documents/a/b") as stream:
        assert stream.read() == b"%PDF-"
    url = storage.presigned_url(
        "documents/a/b", expires_in=300, filename="cédula.pdf", content_type="application/pdf"
    )
    assert url.startswith("memory://memory-bucket/documents/a/b?")
    assert parse_qs(urlparse(url).query)["filename"] == ["cédula.pdf"]
    assert storage.ensure_bucket() is False
    storage.check()
    assert storage.encryption_key_version is None

    storage.delete("documents/a/b")
    storage.delete("documents/a/b")
    with pytest.raises(StorageUnavailable):
        storage.open("documents/a/b")

    storage.put("documents/c", io.BytesIO(b"x"), content_type="image/png")
    storage.clear()
    assert storage.objects == {}


def test_get_storage_in_tests_is_a_shared_memory_storage() -> None:
    storage = get_storage()
    assert isinstance(storage, MemoryStorage)
    assert get_storage() is storage


# --- S3Storage ----------------------------------------------------------------------------


def test_put_sends_content_type_and_server_side_encryption() -> None:
    client = MagicMock()
    storage = s3(client, sse="AES256")
    content = io.BytesIO(b"%PDF-")

    storage.put("documents/a/b", content, content_type="application/pdf")

    client.upload_fileobj.assert_called_once_with(
        content,
        "documentos",
        "documents/a/b",
        ExtraArgs={"ContentType": "application/pdf", "ServerSideEncryption": "AES256"},
    )
    assert storage.encryption_key_version == SSE_S3_KEY_VERSION


def test_put_without_sse_does_not_ask_for_encryption() -> None:
    client = MagicMock()
    storage = s3(client)

    storage.put("documents/a/b", io.BytesIO(b"x"), content_type="image/png")

    assert client.upload_fileobj.call_args.kwargs["ExtraArgs"] == {"ContentType": "image/png"}
    assert storage.encryption_key_version is None


def test_open_and_delete() -> None:
    client = MagicMock()
    body = io.BytesIO(b"datos")
    client.get_object.return_value = {"Body": body}
    storage = s3(client)

    assert storage.open("documents/a/b") is body
    storage.delete("documents/a/b")

    client.get_object.assert_called_once_with(Bucket="documentos", Key="documents/a/b")
    client.delete_object.assert_called_once_with(Bucket="documentos", Key="documents/a/b")


def test_client_errors_become_storage_unavailable_without_the_key_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = MagicMock()
    client.get_object.side_effect = client_error("AccessDenied", "GetObject")
    client.upload_fileobj.side_effect = EndpointConnectionError(endpoint_url="http://s3")
    storage = s3(client)

    with caplog.at_level(logging.WARNING), pytest.raises(StorageUnavailable):
        storage.open("documents/secreto/clave")
    with pytest.raises(StorageUnavailable):
        storage.put("documents/secreto/clave", io.BytesIO(b"x"), content_type="image/png")

    assert "secreto" not in caplog.text
    assert "ClientError" in caplog.text


def test_ensure_bucket_creates_it_only_when_missing() -> None:
    client = MagicMock()
    storage = s3(client)
    assert storage.ensure_bucket() is False
    client.create_bucket.assert_not_called()

    client.head_bucket.side_effect = client_error("404")
    assert storage.ensure_bucket() is True
    client.create_bucket.assert_called_once_with(Bucket="documentos")


def test_ensure_bucket_outside_us_east_1_sets_the_location() -> None:
    client = MagicMock()
    client.head_bucket.side_effect = client_error("NoSuchBucket")

    s3(client, region="sa-east-1").ensure_bucket()

    client.create_bucket.assert_called_once_with(
        Bucket="documentos", CreateBucketConfiguration={"LocationConstraint": "sa-east-1"}
    )


@pytest.mark.parametrize(
    "error", [client_error("403"), EndpointConnectionError(endpoint_url="http://s3")]
)
def test_ensure_bucket_does_not_create_on_other_errors(error: Exception) -> None:
    client = MagicMock()
    client.head_bucket.side_effect = error

    with pytest.raises(StorageUnavailable):
        s3(client).ensure_bucket()
    client.create_bucket.assert_not_called()


def test_check_uses_head_bucket() -> None:
    client = MagicMock()
    s3(client).check()
    client.head_bucket.assert_called_once_with(Bucket="documentos")

    client.head_bucket.side_effect = client_error("403")
    with pytest.raises(StorageUnavailable):
        s3(client).check()


@override_settings(
    DOCUMENT_STORAGE_BACKEND="s3",
    DOCUMENT_STORAGE_BUCKET="mvp-credit-documents",
    DOCUMENT_STORAGE_REGION="us-east-1",
    DOCUMENT_STORAGE_ENDPOINT_URL="http://seaweedfs:8333",
    DOCUMENT_STORAGE_PUBLIC_ENDPOINT_URL="http://localhost:8333",
    DOCUMENT_STORAGE_ACCESS_KEY_ID="local-key",
    DOCUMENT_STORAGE_SECRET_ACCESS_KEY="local-secret",
    DOCUMENT_STORAGE_ADDRESSING_STYLE="path",
    DOCUMENT_STORAGE_SSE="",
)
def test_presigned_url_is_signed_for_the_public_host() -> None:
    storage = get_storage()
    assert isinstance(storage, S3Storage)
    assert storage.encryption_key_version is None

    # Firmar no hace ninguna llamada de red.
    url = storage.presigned_url(
        "documents/a/b", expires_in=300, filename="cédula.pdf", content_type="application/pdf"
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}" == "http://localhost:8333"
    assert parsed.path == "/mvp-credit-documents/documents/a/b"
    assert query["X-Amz-Expires"] == ["300"]
    assert query["response-content-type"] == ["application/pdf"]
    assert query["response-content-disposition"] == [attachment_disposition("cédula.pdf")]
    assert query["X-Amz-Credential"][0].startswith("local-key/")


@override_settings(
    DOCUMENT_STORAGE_BACKEND="s3",
    DOCUMENT_STORAGE_ENDPOINT_URL="",
    DOCUMENT_STORAGE_PUBLIC_ENDPOINT_URL="",
    DOCUMENT_STORAGE_ACCESS_KEY_ID="aws-key",
    DOCUMENT_STORAGE_SECRET_ACCESS_KEY="aws-secret",
    DOCUMENT_STORAGE_REGION="us-east-1",
    DOCUMENT_STORAGE_ADDRESSING_STYLE="auto",
    DOCUMENT_STORAGE_SSE="AES256",
)
def test_real_s3_uses_the_aws_endpoint_and_encrypts() -> None:
    storage = get_storage()
    assert isinstance(storage, S3Storage)
    assert storage.encryption_key_version == SSE_S3_KEY_VERSION

    url = storage.presigned_url(
        "documents/a/b", expires_in=60, filename="a.pdf", content_type="application/pdf"
    )

    assert urlparse(url).netloc.endswith("amazonaws.com")


# --- Configuración ------------------------------------------------------------------------


def test_storage_settings_are_validated() -> None:
    validate_storage_settings()

    with override_settings(DOCUMENT_STORAGE_BACKEND="disk"), pytest.raises(ImproperlyConfigured):
        validate_storage_settings()
    with (
        override_settings(DEBUG=False, DOCUMENT_ALLOW_FAKE_SERVICES=False),
        pytest.raises(ImproperlyConfigured, match="memory"),
    ):
        validate_storage_settings()
    with override_settings(DEBUG=True, DOCUMENT_ALLOW_FAKE_SERVICES=False):
        validate_storage_settings()
    with override_settings(DOCUMENT_STORAGE_BACKEND="s3", DOCUMENT_ALLOW_FAKE_SERVICES=False):
        validate_storage_settings()
