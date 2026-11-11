"""Descarga de objetos del almacenamiento en disco (``DOCUMENT_STORAGE_BACKEND=filesystem``).

Hace el papel de una URL prefirmada de S3 en local: ``GET /api/v1/storage/objects/{token}``.

- La firma es la credencial: sin sesión ni CSRF. Emitir el enlace ya exige permiso y
  está limitado (``document_download``).
- Fuera del modo ``filesystem`` (o sin DEBUG) responde ``404`` con cualquier token.
- Token vencido o alterado: ``403 DOWNLOAD_LINK_INVALID``. Objeto inexistente: ``404``.
- Siempre como adjunto, nunca ``inline``, y con ``nosniff``: el navegador nunca
  interpreta un archivo cargado como una página.
- Fuera del esquema OpenAPI: el frontend solo sigue la ``url`` que recibe.
"""

from typing import Any

from django.http import FileResponse, Http404
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.documents.exceptions import DownloadLinkInvalid, StorageUnavailable
from apps.documents.storage import (
    FilesystemStorage,
    InvalidObjectKey,
    InvalidObjectToken,
    attachment_disposition,
    fake_services_allowed,
    get_storage,
    read_object_token,
)


@extend_schema(exclude=True)
class StorageObjectView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]
    throttle_classes: list[Any] = []

    def get(self, request: Request, token: str) -> FileResponse:
        storage = get_storage()
        if not isinstance(storage, FilesystemStorage) or not fake_services_allowed():
            raise Http404
        try:
            grant = read_object_token(token)
        except InvalidObjectToken as exc:
            raise DownloadLinkInvalid() from exc
        try:
            stream = storage.open(grant.key)
        except (InvalidObjectKey, StorageUnavailable) as exc:
            raise Http404 from exc
        response = FileResponse(stream, content_type=grant.content_type)
        response["Content-Disposition"] = attachment_disposition(grant.filename)
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
