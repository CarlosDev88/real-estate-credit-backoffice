"""Almacenamiento privado de archivos, compatible con S3 (DER §8.1, RNF-03 y RNF-15).

Una interfaz propia (``ObjectStorage``) con dos implementaciones:

- ``S3Storage``: ``boto3`` sobre S3 real o SeaweedFS en local. Pasar de uno a otro es
  solo cambiar variables de entorno (``DOCUMENT_STORAGE_*``).
- ``MemoryStorage``: para pruebas y CI, sin servicios externos.

Un solo bucket privado con prefijos ``documents/`` y ``packages/``. La clave nunca lleva
el nombre original ni datos personales, y nunca sale en una respuesta ni en un log: la
descarga es una URL prefirmada de corta duración.
"""

import io
import logging
import unicodedata
import uuid
from collections.abc import Callable
from functools import lru_cache
from typing import Any, BinaryIO, Protocol
from urllib.parse import quote, urlencode

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.documents.exceptions import StorageUnavailable

logger = logging.getLogger(__name__)

S3 = "s3"
MEMORY = "memory"
STORAGE_BACKENDS = (S3, MEMORY)

DOCUMENTS_PREFIX = "documents"
PACKAGES_PREFIX = "packages"

# Valor de `file_objects.encryption_key_version` cuando el proveedor cifra (SSE-S3).
SSE_S3_KEY_VERSION = "SSE-S3"


def new_document_key(application_id: uuid.UUID) -> str:
    return f"{DOCUMENTS_PREFIX}/{application_id}/{uuid.uuid4()}"


def new_package_key(application_id: uuid.UUID) -> str:
    return f"{PACKAGES_PREFIX}/{application_id}/{uuid.uuid4()}.zip"


def attachment_disposition(filename: str) -> str:
    """``Content-Disposition`` de descarga, con nombre ASCII y su versión UTF-8 (RFC 6266)."""
    ascii_name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    ascii_name = "".join(char for char in ascii_name if char not in '"\\' and char.isprintable())
    ascii_name = ascii_name.strip() or "documento"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


class ObjectStorage(Protocol):
    provider: str
    bucket: str
    # `None` si el proveedor no cifra del lado del servidor.
    encryption_key_version: str | None

    def put(self, key: str, content: BinaryIO, *, content_type: str) -> None: ...

    def open(self, key: str) -> BinaryIO:
        """Flujo de lectura del objeto. Quien lo abre lo cierra."""
        ...

    def delete(self, key: str) -> None: ...

    def presigned_url(
        self, key: str, *, expires_in: int, filename: str, content_type: str
    ) -> str: ...

    def ensure_bucket(self) -> bool:
        """Crea el bucket si no existe. ``True`` si lo creó."""
        ...

    def check(self) -> None:
        """``StorageUnavailable`` si el bucket no responde."""
        ...


class S3Storage:
    provider = S3

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        client: Any,
        public_client: Any | None = None,
        sse: str = "",
    ) -> None:
        self.bucket = bucket
        self.region = region
        self._client = client
        # Firma las URL con el host que ve el navegador.
        self._public_client = public_client or client
        self._sse = sse
        self.encryption_key_version = SSE_S3_KEY_VERSION if sse else None

    def _call(self, operation: str, function: Callable[[], Any]) -> Any:
        try:
            return function()
        except (BotoCoreError, ClientError) as exc:
            logger.warning("Almacenamiento: %s falló (%s)", operation, type(exc).__name__)
            raise StorageUnavailable(f"El almacenamiento no completó {operation}.") from exc

    def put(self, key: str, content: BinaryIO, *, content_type: str) -> None:
        extra: dict[str, str] = {"ContentType": content_type}
        if self._sse:
            extra["ServerSideEncryption"] = self._sse
        self._call(
            "put", lambda: self._client.upload_fileobj(content, self.bucket, key, ExtraArgs=extra)
        )

    def open(self, key: str) -> BinaryIO:
        response = self._call("open", lambda: self._client.get_object(Bucket=self.bucket, Key=key))
        body: BinaryIO = response["Body"]
        return body

    def delete(self, key: str) -> None:
        self._call("delete", lambda: self._client.delete_object(Bucket=self.bucket, Key=key))

    def presigned_url(self, key: str, *, expires_in: int, filename: str, content_type: str) -> str:
        url: str = self._call(
            "presign",
            lambda: self._public_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ResponseContentDisposition": attachment_disposition(filename),
                    "ResponseContentType": content_type,
                },
                ExpiresIn=expires_in,
            ),
        )
        return url

    def ensure_bucket(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return False
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code not in ("404", "NoSuchBucket", "NotFound"):
                raise StorageUnavailable("No se pudo consultar el bucket.") from exc
        except BotoCoreError as exc:
            raise StorageUnavailable("No se pudo consultar el bucket.") from exc

        params: dict[str, Any] = {"Bucket": self.bucket}
        if self.region != "us-east-1":
            params["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
        self._call("create_bucket", lambda: self._client.create_bucket(**params))
        return True

    def check(self) -> None:
        self._call("check", lambda: self._client.head_bucket(Bucket=self.bucket))


class MemoryStorage:
    """Almacenamiento en memoria del proceso, para pruebas. No cifra."""

    provider = MEMORY
    encryption_key_version: str | None = None

    def __init__(self, bucket: str = "memory-bucket") -> None:
        self.bucket = bucket
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, content: BinaryIO, *, content_type: str) -> None:
        self.objects[key] = (content.read(), content_type)

    def open(self, key: str) -> BinaryIO:
        if key not in self.objects:
            raise StorageUnavailable("El objeto no existe.")
        return io.BytesIO(self.objects[key][0])

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def presigned_url(self, key: str, *, expires_in: int, filename: str, content_type: str) -> str:
        query = urlencode({"expires_in": expires_in, "filename": filename, "type": content_type})
        return f"memory://{self.bucket}/{key}?{query}"

    def ensure_bucket(self) -> bool:
        return False

    def check(self) -> None:
        return None

    def clear(self) -> None:
        self.objects.clear()


def _s3_client(endpoint_url: str) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        region_name=settings.DOCUMENT_STORAGE_REGION,
        aws_access_key_id=settings.DOCUMENT_STORAGE_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.DOCUMENT_STORAGE_SECRET_ACCESS_KEY or None,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": settings.DOCUMENT_STORAGE_ADDRESSING_STYLE},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=60,
        ),
    )


def fake_services_allowed() -> bool:
    return bool(settings.DEBUG or settings.DOCUMENT_ALLOW_FAKE_SERVICES)


def validate_storage_settings() -> None:
    """Falla al arrancar si la configuración no es segura (``ImproperlyConfigured``)."""
    backend = settings.DOCUMENT_STORAGE_BACKEND
    if backend not in STORAGE_BACKENDS:
        raise ImproperlyConfigured(f"DOCUMENT_STORAGE_BACKEND debe ser uno de {STORAGE_BACKENDS}.")
    if backend == MEMORY and not fake_services_allowed():
        raise ImproperlyConfigured(
            "DOCUMENT_STORAGE_BACKEND=memory solo se admite con DEBUG o en pruebas."
        )


@lru_cache(maxsize=1)
def get_storage() -> ObjectStorage:
    """El almacenamiento configurado. Se crea una vez por proceso."""
    if settings.DOCUMENT_STORAGE_BACKEND == MEMORY:
        return MemoryStorage()
    endpoint = settings.DOCUMENT_STORAGE_ENDPOINT_URL
    public_endpoint = settings.DOCUMENT_STORAGE_PUBLIC_ENDPOINT_URL
    return S3Storage(
        bucket=settings.DOCUMENT_STORAGE_BUCKET,
        region=settings.DOCUMENT_STORAGE_REGION,
        client=_s3_client(endpoint),
        public_client=_s3_client(public_endpoint) if public_endpoint else None,
        sse=settings.DOCUMENT_STORAGE_SSE,
    )
