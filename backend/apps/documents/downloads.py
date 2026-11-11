"""Descarga de versiones por URL prefirmada (decisión 13, API §19, RNF-03).

La URL dura ``DOCUMENT_DOWNLOAD_URL_SECONDS`` (5 minutos por omisión), lleva
``Content-Disposition: attachment`` con el nombre de la versión y el ``Content-Type``
detectado. Solo se firma un archivo ``CLEAN``: ``PENDING``, ``INFECTED`` o ``INVALID``
responden ``409 FILE_NOT_CLEAN``. La URL es una credencial: nunca va a un log.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.documents.exceptions import DownloadUnavailable, FileNotClean, StorageUnavailable
from apps.documents.models import DocumentFile
from apps.documents.storage import get_storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadLink:
    url: str
    expires_at: datetime


def download_link(version: DocumentFile, *, requested_by: str) -> DownloadLink:
    """Firma la descarga de la versión. ``requested_by`` identifica al actor en el log
    (``user:<id>`` o ``buyer_session:<id>``)."""
    file_object = version.file_object
    if not file_object.is_clean:
        raise FileNotClean()
    seconds = settings.DOCUMENT_DOWNLOAD_URL_SECONDS
    expires_at = timezone.now() + timedelta(seconds=seconds)
    try:
        url = get_storage().presigned_url(
            file_object.object_key,
            expires_in=seconds,
            filename=version.client_filename,
            content_type=file_object.detected_mime_type,
        )
    except StorageUnavailable as exc:
        logger.warning("No se pudo firmar la descarga de la versión %s", version.pk)
        raise DownloadUnavailable() from exc
    logger.info("Descarga de la versión %s firmada para %s", version.pk, requested_by)
    return DownloadLink(url=url, expires_at=expires_at)
