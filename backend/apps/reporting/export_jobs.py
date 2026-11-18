"""Exportación asíncrona del reporte de solicitudes en CSV (API §22.2, MODELO §10.7).

**Pedido** (``request_export``): guarda los filtros ya validados (``ReportFilters.as_dict``)
y encola el trabajo después del commit. Cada usuario tiene como máximo
``REPORTS_EXPORT_MAX_ACTIVE`` (3) trabajos ``PENDING``/``RUNNING``; uno más responde
``429 TOO_MANY_EXPORTS``. La cuenta se hace con la fila del usuario bloqueada, para que
dos pedidos simultáneos no pasen los dos.

**Worker** (``build_export``), como el paquete documental: toma el trabajo con un
``UPDATE`` condicional (``PENDING`` → ``RUNNING`` con un ``started_at`` nuevo que marca el
intento) y solo lo marca ``COMPLETED`` si sigue teniéndolo. Recalcula con el alcance
**del solicitante al momento de ejecutar**: si ya no puede exportar (usuario inactivo o
sin ``reports.export``) o un filtro quedó fuera de su alcance, ``FAILED`` con
``PERMISSION_REVOKED``. El CSV tiene el formato y el saneamiento de la descarga directa,
sin el límite de 5000; por encima de ``REPORTS_EXPORT_MAX_ROWS`` (100000), ``FAILED`` con
``EXPORT_TOO_LARGE``. Se sube con ``get_storage().put`` como un ``FileObject`` limpio por
construcción y vence a las ``REPORTS_EXPORT_TTL_HOURS`` (24). Si el almacenamiento falla,
el trabajo vuelve a ``PENDING`` y la tarea reintenta; en el último intento, ``FAILED`` con
``STORAGE_UNAVAILABLE``.

**Vencimiento:** ``effective_status`` lee ``EXPIRED`` en cuanto pasa ``expires_at``;
``purge_exports`` (comando ``purge_report_exports``) lo persiste y borra el objeto. En
producción el comando se agenda con Celery beat (no está agendado en este repositorio).
"""

import hashlib
import logging
import tempfile
import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta
from functools import partial
from typing import IO, BinaryIO, cast

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from kombu.exceptions import OperationalError
from rest_framework.exceptions import ValidationError

from apps.applications.models import CreditApplication
from apps.applications.services import get_application_scope
from apps.documents.downloads import DownloadLink, file_object_link
from apps.documents.exceptions import StorageUnavailable
from apps.documents.models import FileObject, ScanStatus
from apps.documents.storage import ObjectStorage, get_storage
from apps.identity.models import User
from apps.identity.services import get_access_profile
from apps.reporting import exports
from apps.reporting.exceptions import (
    ExportExpired,
    ExportNotReady,
    FilterOutOfScope,
    TooManyExports,
)
from apps.reporting.filters import ReportFilters, ReportFilterSerializer, parse_filters
from apps.reporting.models import (
    ACTIVE_EXPORT_STATUSES,
    ExportJobStatus,
    ReportExportJob,
    ReportType,
)
from apps.reporting.signals import report_exported

logger = logging.getLogger(__name__)

EXPORT_PERMISSION = "reports.export"
MANAGE_PERMISSION = "reports.manage"

CSV_CONTENT_TYPE = "text/csv"
REPORTS_PREFIX = "reports"

PERMISSION_REVOKED = "PERMISSION_REVOKED"
EXPORT_TOO_LARGE = "EXPORT_TOO_LARGE"
STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
INVALID_FILTERS = "INVALID_FILTERS"

# El CSV se arma en memoria hasta este tamaño y, por encima, en disco.
SPOOL_MAX_BYTES = 16 * 1024 * 1024


def new_report_key(job_id: uuid.UUID) -> str:
    """Clave propia de cada intento: sin nombres ni datos personales."""
    return f"{REPORTS_PREFIX}/{job_id}/{uuid.uuid4()}.csv"


# --- Pedido y consulta ------------------------------------------------------------------


def jobs_visible_to(user: User, *, manager: bool) -> QuerySet[ReportExportJob]:
    """Los trabajos propios; con ``reports.manage``, todos. Fuera de eso, ``404``."""
    jobs = ReportExportJob.objects.select_related("requested_by", "output_file_object")
    return jobs if manager else jobs.filter(requested_by=user)


def _enqueue_export(job_id: str) -> None:
    """Encola el trabajo. Si el broker no responde, queda ``PENDING`` (se ve en la lista y
    ocupa su cupo hasta que se procese)."""
    from apps.documents.tasks import log_eager_failure
    from apps.reporting.tasks import build_report_export

    try:
        result = build_report_export.delay(job_id)
    except OperationalError:
        logger.warning("No se pudo encolar la exportación %s", job_id)
        return
    log_eager_failure(result, f"Exportación {job_id}")


def request_export(actor: User, filters: ReportFilters) -> ReportExportJob:
    with transaction.atomic():
        # La fila del usuario serializa sus pedidos: la cuenta del cupo no tiene carreras.
        User.objects.select_for_update().filter(pk=actor.pk).values_list("pk").first()
        active = ReportExportJob.objects.filter(
            requested_by=actor, status__in=ACTIVE_EXPORT_STATUSES
        ).count()
        if active >= settings.REPORTS_EXPORT_MAX_ACTIVE:
            raise TooManyExports()
        job = ReportExportJob.objects.create(
            requested_by=actor,
            report_type=ReportType.APPLICATIONS,
            filters=filters.as_dict(),
        )
        transaction.on_commit(partial(_enqueue_export, str(job.pk)))
    logger.info("Exportación %s pedida por el usuario %s", job.pk, actor.pk)
    return job


# --- Worker -----------------------------------------------------------------------------


def _claim(job_id: uuid.UUID) -> datetime | None:
    started_at = timezone.now()
    claimed = ReportExportJob.objects.filter(pk=job_id, status=ExportJobStatus.PENDING).update(
        status=ExportJobStatus.RUNNING, started_at=started_at, updated_at=started_at
    )
    return started_at if claimed else None


def _owned(job_id: uuid.UUID, started_at: datetime) -> QuerySet[ReportExportJob]:
    return ReportExportJob.objects.filter(
        pk=job_id, status=ExportJobStatus.RUNNING, started_at=started_at
    )


def _release(job_id: uuid.UUID, started_at: datetime) -> None:
    _owned(job_id, started_at).update(
        status=ExportJobStatus.PENDING, started_at=None, updated_at=timezone.now()
    )


def _fail(job_id: uuid.UUID, started_at: datetime, error_code: str) -> None:
    now = timezone.now()
    _owned(job_id, started_at).update(
        status=ExportJobStatus.FAILED, error_code=error_code, completed_at=now, updated_at=now
    )


def _status(job_id: uuid.UUID) -> str | None:
    return ReportExportJob.objects.filter(pk=job_id).values_list("status", flat=True).first()


def can_export(user: User) -> bool:
    return user.can_authenticate and EXPORT_PERMISSION in get_access_profile(user).permissions


def stored_filters(job: ReportExportJob, user: User) -> ReportFilters:
    """Vuelve a validar los filtros guardados con el alcance actual del usuario."""
    data = {name: value for name, value in job.filters.items() if value not in (None, "", [])}
    return parse_filters(data, user, serializer_class=ReportFilterSerializer)


def _write_csv(
    buffer: IO[bytes], applications: Iterable[CreditApplication]
) -> tuple[int, int, str]:
    """Escribe el CSV y devuelve ``(filas, bytes, sha256)``."""
    digest = hashlib.sha256()
    size = 0
    lines = 0
    for line in exports.csv_lines(applications):
        data = line.encode("utf-8")
        digest.update(data)
        buffer.write(data)
        size += len(data)
        lines += 1
    buffer.seek(0)
    # La primera línea son los encabezados.
    return lines - 1, size, digest.hexdigest()


def _complete(
    job: ReportExportJob,
    started_at: datetime,
    *,
    storage: ObjectStorage,
    key: str,
    filename: str,
    row_count: int,
    size: int,
    sha256: str,
) -> bool:
    now = timezone.now()
    with transaction.atomic():
        file_object = FileObject.objects.create(
            storage_provider=storage.provider,
            bucket_name=storage.bucket,
            object_key=key,
            original_filename=filename,
            detected_mime_type=CSV_CONTENT_TYPE,
            size_bytes=size,
            sha256=sha256,
            # Lo arma el sistema con datos de la base: limpio por construcción.
            scan_status=ScanStatus.CLEAN,
            scanned_at=now,
            encryption_key_version=storage.encryption_key_version,
        )
        completed = _owned(job.pk, started_at).update(
            status=ExportJobStatus.COMPLETED,
            output_file_object=file_object,
            row_count=row_count,
            completed_at=now,
            expires_at=now + timedelta(hours=settings.REPORTS_EXPORT_TTL_HOURS),
            updated_at=now,
        )
        if not completed:
            transaction.set_rollback(True)
    return bool(completed)


def _discard(storage: ObjectStorage, key: str, job_id: uuid.UUID) -> None:
    try:
        storage.delete(key)
    except StorageUnavailable:
        logger.warning("No se pudo borrar un CSV descartado de la exportación %s", job_id)


def build_export(job_id: uuid.UUID, *, last_attempt: bool = True) -> str | None:
    """Arma el CSV de un trabajo ``PENDING``. Devuelve el estado en que queda, o ``None``
    si no existe. Lanza ``StorageUnavailable`` (con el trabajo de nuevo ``PENDING``) para
    que la tarea reintente, salvo en el último intento."""
    job = ReportExportJob.objects.select_related("requested_by").filter(pk=job_id).first()
    if job is None:
        logger.warning("Exportación pedida para un trabajo que no existe: %s", job_id)
        return None
    if job.status != ExportJobStatus.PENDING:
        return job.status
    started_at = _claim(job_id)
    if started_at is None:
        return _status(job_id)

    user = job.requested_by
    if not can_export(user):
        logger.warning("Exportación %s: el usuario ya no puede exportar", job_id)
        _fail(job_id, started_at, PERMISSION_REVOKED)
        return _status(job_id)
    try:
        filters = stored_filters(job, user)
    except FilterOutOfScope:
        logger.warning("Exportación %s: un filtro quedó fuera del alcance", job_id)
        _fail(job_id, started_at, PERMISSION_REVOKED)
        return _status(job_id)
    except ValidationError:
        logger.warning("Exportación %s: los filtros guardados ya no son válidos", job_id)
        _fail(job_id, started_at, INVALID_FILTERS)
        return _status(job_id)

    applications = exports.report_applications(user, filters, get_application_scope(user))
    if applications.count() > settings.REPORTS_EXPORT_MAX_ROWS:
        _fail(job_id, started_at, EXPORT_TOO_LARGE)
        return _status(job_id)

    storage = get_storage()
    key = new_report_key(job.pk)
    try:
        with tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_BYTES) as buffer:
            row_count, size, sha256 = _write_csv(
                buffer, applications.iterator(chunk_size=exports.ITERATOR_CHUNK_SIZE)
            )
            storage.put(key, cast(BinaryIO, buffer), content_type=CSV_CONTENT_TYPE)
    except StorageUnavailable:
        if last_attempt:
            logger.error("Exportación %s fallida: el almacenamiento no respondió", job_id)
            _fail(job_id, started_at, STORAGE_UNAVAILABLE)
            return _status(job_id)
        _release(job_id, started_at)
        raise
    completed = _complete(
        job,
        started_at,
        storage=storage,
        key=key,
        filename=exports.csv_filename(filters),
        row_count=row_count,
        size=size,
        sha256=sha256,
    )
    if not completed:
        logger.warning("Exportación %s: un intento atrasado descarta su CSV", job_id)
        _discard(storage, key, job_id)
        return _status(job_id)
    report_exported.send(
        sender=ReportExportJob,
        user=user,
        report_type=job.report_type,
        filters=job.filters,
        row_count=row_count,
        format=exports.FORMAT_CSV,
        job=job,
    )
    logger.info("Exportación %s lista (%s filas)", job_id, row_count)
    return ExportJobStatus.COMPLETED


# --- Descarga y vencimiento -------------------------------------------------------------


def export_download(job: ReportExportJob, *, requested_by: str) -> DownloadLink:
    """URL prefirmada del CSV, como la descarga de documentos (5 minutos, nunca a un
    log). Solo ``COMPLETED`` y sin vencer."""
    status = job.effective_status
    if status == ExportJobStatus.EXPIRED:
        raise ExportExpired()
    if status != ExportJobStatus.COMPLETED:
        raise ExportNotReady()
    file_object = job.output_file_object
    assert file_object is not None
    return file_object_link(
        file_object,
        filename=file_object.original_filename,
        requested_by=requested_by,
        description=f"la exportación {job.pk}",
    )


def purge_exports() -> int:
    """Persiste ``EXPIRED`` en las exportaciones vencidas y borra su CSV. Los registros
    (el trabajo y su ``file_objects``) se conservan. Si el borrado falla, la exportación
    queda para la próxima vez (igual se lee como ``EXPIRED``)."""
    now = timezone.now()
    due = ReportExportJob.objects.filter(
        status=ExportJobStatus.COMPLETED, expires_at__lte=now
    ).select_related("output_file_object")
    storage = get_storage()
    count = 0
    for job in due.iterator():
        file_object = job.output_file_object
        if file_object is not None:
            try:
                storage.delete(file_object.object_key)
            except StorageUnavailable:
                logger.warning("No se pudo borrar el CSV vencido de la exportación %s", job.pk)
                continue
        count += ReportExportJob.objects.filter(pk=job.pk, status=ExportJobStatus.COMPLETED).update(
            status=ExportJobStatus.EXPIRED, updated_at=now
        )
    return count
