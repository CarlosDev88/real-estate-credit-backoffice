"""Paquete ZIP del expediente para radicar (decisiones 14, 15 y 36 a 42; API §19).

**Pedido** (``request_package``): bloquea la solicitud y todos sus slots vigentes
(decisión 22) y exige solo los documentos (decisión 36): ``DOCUMENT_PENDING``,
``DOCUMENT_EXPIRED`` o ``DOCUMENTS_NOT_CONFIGURED`` responden ``422
APPLICATION_NOT_READY``. No evalúa ni guarda reglas bancarias. **El contenido se fija
aquí**: ``manifest`` guarda las versiones (ids, tamaño y SHA-256), la ruta de cada una
dentro del ZIP y la huella documental, y el worker empaqueta exactamente esa lista. Si
ya hay un trabajo ``PENDING``, ``RUNNING`` o ``COMPLETED`` sin vencer con la misma
huella, se devuelve ese (decisión 14), salvo que ya se haya usado en una radicación
(paso 11): cada radicación necesita su propio paquete.

**Contenido:** la versión vigente de cada slot vigente ``APPROVED`` y no vencido, en
carpetas ``00_SOLICITUD`` y ``<nn>_<ROL>_<Nombre_Apellido>``, más ``manifest.json``
para el banco. Los ``WAIVED`` van en los dos manifiestos, sin archivo.

**Dos manifiestos** (decisión 39): el interno (``document_package_jobs.manifest``) lleva
ids, ``client_filename`` y motivos de exoneración; el del ZIP no lleva nada de eso.

**Worker** (``build_package``, decisión 42): toma el trabajo con un ``UPDATE``
condicional (``PENDING`` → ``RUNNING`` con un ``started_at`` nuevo, que hace de marca
del intento). Arma el ZIP en un archivo temporal, verificando el SHA-256 de cada
versión, lo sube a una clave propia del intento y solo lo marca ``COMPLETED`` si sigue
teniendo el trabajo; uno atrasado borra su objeto y no pisa el resultado. Un SHA-256
distinto: ``FAILED`` con ``CHECKSUM_MISMATCH``, sin reintento. Si el almacenamiento
falla, devuelve el trabajo a ``PENDING`` para que la tarea reintente; en el último
intento, ``FAILED`` con ``STORAGE_UNAVAILABLE``.

**Vencimiento:** ``DOCUMENT_PACKAGE_TTL_DAYS`` después de terminar. El estado
``EXPIRED`` se deriva al leer (``effective_status``) y ``expire_packages`` lo persiste y
borra el objeto.
"""

import hashlib
import json
import logging
import re
import tempfile
import unicodedata
import uuid
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import IO, Any, BinaryIO, cast

from botocore.exceptions import BotoCoreError
from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.applications.exceptions import ApplicationClosed, ApplicationNotReady
from apps.applications.models import ApplicationParticipant, CreditApplication
from apps.applications.services import applications_visible_to
from apps.documents.constants import JPEG, PDF, PNG
from apps.documents.dossier_serializers import slot_label
from apps.documents.downloads import DownloadLink
from apps.documents.exceptions import (
    DownloadUnavailable,
    PackageExpired,
    PackageNotReady,
    StorageUnavailable,
)
from apps.documents.fingerprint import dossier_fingerprint
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentPackageJob,
    FileObject,
    HolderScope,
    PackageJobStatus,
    ParticipantRole,
    ScanStatus,
    SlotStatus,
)
from apps.documents.storage import ObjectStorage, get_storage, new_package_key
from apps.documents.verification import check_dossier, is_expired, presentation_order
from apps.identity.models import User

logger = logging.getLogger(__name__)

ZIP = "application/zip"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_FORMAT_VERSION = 1

CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"

# Estados que se reutilizan si la huella coincide (decisión 14).
REUSABLE_STATUSES = (PackageJobStatus.PENDING, PackageJobStatus.RUNNING, PackageJobStatus.COMPLETED)

# Nombres dentro del ZIP (decisión 38).
MAX_NAME_LENGTH = 60
APPLICATION_FOLDER = "00_SOLICITUD"
ROLE_FOLDERS: dict[str, str] = {
    ParticipantRole.PRIMARY: "TITULAR",
    ParticipantRole.CO_APPLICANT: "COSOLICITANTE",
    ParticipantRole.SOLIDARY_DEBTOR: "DEUDOR_SOLIDARIO",
}
EXTENSIONS: dict[str, str] = {PDF: "pdf", JPEG: "jpg", PNG: "png"}

# El ZIP se arma en memoria hasta este tamaño y, por encima, en disco.
SPOOL_MAX_BYTES = 16 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024


class ChecksumMismatch(Exception):
    """Un objeto guardado no coincide con el SHA-256 de su versión."""


# --- Nombres ----------------------------------------------------------------------------


def safe_name(text: str, *, fallback: str = "documento") -> str:
    """ASCII seguro (decisión 38): sin tildes (``ñ`` → ``n``), solo letras y dígitos,
    palabras separadas con guion bajo y como máximo ``MAX_NAME_LENGTH`` caracteres."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    name = "_".join(re.findall(r"[A-Za-z0-9]+", ascii_text))[:MAX_NAME_LENGTH].strip("_")
    return name or fallback


def _with_suffix(stem: str, number: int) -> str:
    suffix = f"_{number}"
    return stem[: MAX_NAME_LENGTH - len(suffix)].rstrip("_") + suffix


def participant_folder(position: int, participant: ApplicationParticipant) -> str:
    """``01_TITULAR_Laura_Gomez``: posición, rol y primer nombre y primer apellido."""
    client = participant.client
    person = " ".join([*client.first_names.split()[:1], *client.last_names.split()[:1]])
    return safe_name(f"{position:02d} {ROLE_FOLDERS[participant.role]} {person}")


def package_filename(application: CreditApplication) -> str:
    # El código lo genera el sistema (`SOL-000123`): ya es ASCII seguro.
    return f"{application.code}_expediente.zip"


# --- Pedido -----------------------------------------------------------------------------


def jobs_visible_to(user: User) -> QuerySet[DocumentPackageJob]:
    """Paquetes de las solicitudes visibles (decisión 37): un asesor reasignado ve los
    anteriores; fuera del alcance, ``404``."""
    return DocumentPackageJob.objects.select_related("requested_by", "output_file_object").filter(
        application__in=applications_visible_to(user)
    )


def _package_slots(application: CreditApplication) -> list[ApplicationDocumentSlot]:
    """Slots vigentes que van en el paquete: exonerados y aprobados no vencidos con su
    versión vigente limpia, en el orden de presentación."""
    today = timezone.localdate()
    slots = (
        ApplicationDocumentSlot.objects.filter(application=application, retired_at__isnull=True)
        .filter(
            Q(status=SlotStatus.WAIVED)
            | Q(status=SlotStatus.APPROVED, current_file__file_object__scan_status=ScanStatus.CLEAN)
        )
        .select_related(
            "document_type",
            "participant__client",
            "current_file__file_object",
            "waiver_reason_item",
        )
    )
    return sorted((slot for slot in slots if not is_expired(slot, today)), key=presentation_order)


def _holder(slot: ApplicationDocumentSlot, folder: str) -> dict[str, Any]:
    participant = slot.participant
    if participant is None:
        return {
            "scope": HolderScope.APPLICATION,
            "participant_id": None,
            "role": None,
            "role_name": None,
            "full_name": None,
            "folder": folder,
        }
    return {
        "scope": HolderScope.PARTICIPANT,
        "participant_id": str(participant.pk),
        "role": participant.role,
        "role_name": participant.get_role_display(),
        "full_name": participant.client.full_name,
        "folder": folder,
    }


def build_manifest(application: CreditApplication, fingerprint: str) -> dict[str, Any]:
    """Manifiesto interno: lo que el worker empaqueta y lo que se guarda en el trabajo."""
    slots = _package_slots(application)
    # El "m" de "Nombre n de m": todos los slots vigentes del juego, no solo los del ZIP.
    sizes: Counter[tuple[uuid.UUID | None, uuid.UUID]] = Counter(
        ApplicationDocumentSlot.objects.filter(
            application=application, retired_at__isnull=True
        ).values_list("participant_id", "document_type_id")
    )
    participants: dict[uuid.UUID, ApplicationParticipant] = {}
    for slot in slots:
        if slot.participant is not None:
            participants[slot.participant.pk] = slot.participant
    ordered = sorted(participants.values(), key=lambda p: (p.created_at, str(p.pk)))
    folders = {p.pk: participant_folder(n, p) for n, p in enumerate(ordered, start=1)}

    used: set[str] = set()
    documents: list[dict[str, Any]] = []
    for slot in slots:
        label = slot_label(slot, sizes[slot.participant_id, slot.document_type_id])
        folder = folders[slot.participant_id] if slot.participant_id else APPLICATION_FOLDER
        entry: dict[str, Any] = {
            "slot_id": str(slot.pk),
            "document_type": {"code": slot.document_type.code, "name": slot.document_type.name},
            "label": label,
            "holder": _holder(slot, folder),
            "status": slot.status,
            "document_date": None,
            "expires_at": None,
            "file": None,
            "waiver_reason": None,
        }
        if slot.status == SlotStatus.WAIVED:
            reason = slot.waiver_reason_item
            if reason is not None:
                entry["waiver_reason"] = {"code": reason.code, "name": reason.label}
        else:
            version = slot.current_file
            assert version is not None
            file_object = version.file_object
            stem = safe_name(label)
            extension = EXTENSIONS.get(file_object.detected_mime_type, "bin")
            path, number = f"{folder}/{stem}.{extension}", 1
            while path.lower() in used:
                number += 1
                path = f"{folder}/{_with_suffix(stem, number)}.{extension}"
            used.add(path.lower())
            entry["document_date"] = _iso(version.document_date)
            entry["expires_at"] = _iso(version.expires_at)
            entry["file"] = {
                "path": path,
                "document_file_id": str(version.pk),
                "file_object_id": str(file_object.pk),
                "version_number": version.version_number,
                "client_filename": version.client_filename,
                "mime_type": file_object.detected_mime_type,
                "size_bytes": file_object.size_bytes,
                "sha256": file_object.sha256,
            }
        documents.append(entry)
    return {
        "format_version": MANIFEST_FORMAT_VERSION,
        "fingerprint": fingerprint,
        "application": {"id": str(application.pk), "code": application.code},
        "application_version": application.version,
        "requested_at": timezone.now().isoformat(),
        "documents": documents,
    }


def bank_manifest(manifest: dict[str, Any], *, generated_at: datetime) -> dict[str, Any]:
    """``manifest.json`` del ZIP: sin ids internos, ``client_filename``, motivos de
    exoneración ni comentarios (decisión 39)."""
    documents = []
    for entry in manifest["documents"]:
        holder = entry["holder"]
        file = entry["file"]
        documents.append(
            {
                "document_type": entry["document_type"],
                "label": entry["label"],
                "holder": {
                    "scope": holder["scope"],
                    "role": holder["role"],
                    "role_name": holder["role_name"],
                    "full_name": holder["full_name"],
                },
                "status": entry["status"],
                "document_date": entry["document_date"],
                "expires_at": entry["expires_at"],
                "file": None
                if file is None
                else {
                    "path": file["path"],
                    "mime_type": file["mime_type"],
                    "size_bytes": file["size_bytes"],
                    "sha256": file["sha256"],
                },
            }
        )
    return {
        "format_version": manifest["format_version"],
        "application_code": manifest["application"]["code"],
        "generated_at": generated_at.isoformat(),
        "documents": documents,
    }


def _iso(value: Any) -> str | None:
    return None if value is None else str(value.isoformat())


def _reusable(application: CreditApplication, fingerprint: str) -> DocumentPackageJob | None:
    return (
        DocumentPackageJob.objects.filter(
            application=application,
            status__in=REUSABLE_STATUSES,
            manifest__fingerprint=fingerprint,
        )
        .exclude(status=PackageJobStatus.COMPLETED, expires_at__lte=timezone.now())
        # Un paquete radicado no se reutiliza (paso 11).
        .exclude(filing__isnull=False)
        .select_related("requested_by", "output_file_object")
        .order_by("-created_at")
        .first()
    )


def _enqueue_build(job_id: str) -> None:
    """Encola el armado. Si el broker no responde, el trabajo queda ``PENDING`` y lo
    retoma ``requeue_document_packages``."""
    from apps.documents.tasks import build_document_package, log_eager_failure

    try:
        result = build_document_package.delay(job_id)
    except OperationalError:
        logger.warning("No se pudo encolar el paquete %s", job_id)
        return
    log_eager_failure(result, f"Paquete {job_id}")


@dataclass(frozen=True)
class PackageRequest:
    job: DocumentPackageJob
    created: bool


def request_package(actor: User, application: CreditApplication) -> PackageRequest:
    """Pide el paquete de la solicitud o devuelve el que ya existe con la misma huella.

    Solicitud terminada: ``409 APPLICATION_CLOSED``. Documentos sin cumplir: ``422
    APPLICATION_NOT_READY`` con los ``details`` de la guarda (solo los documentales).
    """
    with transaction.atomic():
        locked = CreditApplication.objects.select_for_update().get(pk=application.pk)
        if locked.is_terminal:
            raise ApplicationClosed()
        # Solicitud y después todos sus slots vigentes, en orden (decisión 22).
        dossier = check_dossier(locked, lock=True)
        if dossier.problems:
            raise ApplicationNotReady(details=dossier.problems)
        fingerprint = dossier_fingerprint(locked)
        existing = _reusable(locked, fingerprint)
        if existing is not None:
            return PackageRequest(job=existing, created=False)
        job = DocumentPackageJob.objects.create(
            application=locked,
            requested_by=actor,
            application_version=locked.version,
            manifest=build_manifest(locked, fingerprint),
        )
        transaction.on_commit(partial(_enqueue_build, str(job.pk)))
    logger.info("Paquete %s pedido para la solicitud %s", job.pk, locked.pk)
    return PackageRequest(job=job, created=True)


# --- Worker -----------------------------------------------------------------------------


def _claim(job_id: uuid.UUID) -> datetime | None:
    """``PENDING`` → ``RUNNING``. Devuelve el ``started_at`` que marca este intento, o
    ``None`` si otro worker ya lo tomó."""
    started_at = timezone.now()
    claimed = DocumentPackageJob.objects.filter(pk=job_id, status=PackageJobStatus.PENDING).update(
        status=PackageJobStatus.RUNNING, started_at=started_at, updated_at=started_at
    )
    return started_at if claimed else None


def _owned(job_id: uuid.UUID, started_at: datetime) -> QuerySet[DocumentPackageJob]:
    """El trabajo, solo si este intento lo sigue teniendo."""
    return DocumentPackageJob.objects.filter(
        pk=job_id, status=PackageJobStatus.RUNNING, started_at=started_at
    )


def _release(job_id: uuid.UUID, started_at: datetime) -> None:
    _owned(job_id, started_at).update(
        status=PackageJobStatus.PENDING, started_at=None, updated_at=timezone.now()
    )


def _fail(job_id: uuid.UUID, started_at: datetime, error_code: str) -> None:
    now = timezone.now()
    _owned(job_id, started_at).update(
        status=PackageJobStatus.FAILED, error_code=error_code, completed_at=now, updated_at=now
    )


def _copy(source: IO[bytes], target: IO[bytes]) -> str:
    """Copia por bloques y devuelve el SHA-256 de lo copiado."""
    digest = hashlib.sha256()
    try:
        while chunk := source.read(CHUNK_BYTES):
            digest.update(chunk)
            target.write(chunk)
    except BotoCoreError as exc:
        raise StorageUnavailable("El almacenamiento cortó la lectura.") from exc
    return digest.hexdigest()


def _write_zip(buffer: IO[bytes], manifest: dict[str, Any], storage: ObjectStorage) -> None:
    entries = [entry for entry in manifest["documents"] if entry["file"] is not None]
    file_objects = FileObject.objects.in_bulk(
        [uuid.UUID(entry["file"]["file_object_id"]) for entry in entries]
    )
    now = timezone.now()
    date_time = timezone.localtime(now).timetuple()[:6]
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            file = entry["file"]
            file_object = file_objects[uuid.UUID(file["file_object_id"])]
            if file_object.sha256 != file["sha256"]:
                raise ChecksumMismatch(entry["slot_id"])
            info = zipfile.ZipInfo(file["path"], date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            with storage.open(file_object.object_key) as source, archive.open(info, "w") as target:
                sha256 = _copy(source, target)
            if sha256 != file["sha256"]:
                raise ChecksumMismatch(entry["slot_id"])
        content = json.dumps(
            bank_manifest(manifest, generated_at=now), ensure_ascii=False, indent=2
        )
        archive.writestr(MANIFEST_FILENAME, content)


def _digest(buffer: IO[bytes]) -> tuple[int, str]:
    buffer.seek(0)
    digest = hashlib.sha256()
    size = 0
    while chunk := buffer.read(CHUNK_BYTES):
        digest.update(chunk)
        size += len(chunk)
    buffer.seek(0)
    return size, digest.hexdigest()


def _complete(
    job: DocumentPackageJob,
    started_at: datetime,
    *,
    storage: ObjectStorage,
    key: str,
    size: int,
    sha256: str,
) -> bool:
    """Registra el ZIP y marca el trabajo ``COMPLETED`` si este intento lo sigue
    teniendo. Si no, deshace el registro y devuelve ``False``."""
    now = timezone.now()
    with transaction.atomic():
        file_object = FileObject.objects.create(
            storage_provider=storage.provider,
            bucket_name=storage.bucket,
            object_key=key,
            original_filename=package_filename(job.application),
            detected_mime_type=ZIP,
            size_bytes=size,
            sha256=sha256,
            # Decisión 41: limpio por construcción, sin pasar por el antivirus.
            scan_status=ScanStatus.CLEAN,
            scanned_at=now,
            encryption_key_version=storage.encryption_key_version,
        )
        completed = _owned(job.pk, started_at).update(
            status=PackageJobStatus.COMPLETED,
            output_file_object=file_object,
            completed_at=now,
            expires_at=now + timedelta(days=settings.DOCUMENT_PACKAGE_TTL_DAYS),
            updated_at=now,
        )
        if not completed:
            transaction.set_rollback(True)
    return bool(completed)


def _discard(storage: ObjectStorage, key: str, job_id: uuid.UUID) -> None:
    try:
        storage.delete(key)
    except StorageUnavailable:
        logger.warning(
            "No se pudo borrar un ZIP descartado del paquete %s (objeto huérfano)", job_id
        )


def _status(job_id: uuid.UUID) -> str | None:
    return DocumentPackageJob.objects.filter(pk=job_id).values_list("status", flat=True).first()


def build_package(job_id: uuid.UUID, *, last_attempt: bool = True) -> str | None:
    """Arma el ZIP de un trabajo ``PENDING``. Devuelve el estado en que queda, o
    ``None`` si el trabajo no existe. Lanza ``StorageUnavailable`` (con el trabajo de
    nuevo ``PENDING``) para que la tarea reintente, salvo en el último intento."""
    job = DocumentPackageJob.objects.select_related("application").filter(pk=job_id).first()
    if job is None:
        logger.warning("Paquete pedido para un trabajo que no existe: %s", job_id)
        return None
    if job.status != PackageJobStatus.PENDING:
        return job.status
    started_at = _claim(job_id)
    if started_at is None:
        return _status(job_id)
    assert job.manifest is not None
    storage = get_storage()
    key = new_package_key(job.application_id)
    try:
        with tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_BYTES) as buffer:
            _write_zip(buffer, job.manifest, storage)
            size, sha256 = _digest(buffer)
            storage.put(key, cast(BinaryIO, buffer), content_type=ZIP)
    except ChecksumMismatch as exc:
        logger.error("Paquete %s: el slot %s no coincide con su SHA-256", job_id, exc)
        _fail(job_id, started_at, CHECKSUM_MISMATCH)
        return _status(job_id)
    except StorageUnavailable:
        if last_attempt:
            logger.error("Paquete %s fallido: el almacenamiento no respondió", job_id)
            _fail(job_id, started_at, STORAGE_UNAVAILABLE)
            return _status(job_id)
        _release(job_id, started_at)
        raise
    if not _complete(job, started_at, storage=storage, key=key, size=size, sha256=sha256):
        # Otro intento tomó el trabajo mientras este armaba el ZIP.
        logger.warning("Paquete %s: un intento atrasado descarta su ZIP", job_id)
        _discard(storage, key, job_id)
        return _status(job_id)
    logger.info("Paquete %s listo (%s bytes)", job_id, size)
    return PackageJobStatus.COMPLETED


# --- Descarga, reencolado y vencimiento -------------------------------------------------


def package_download(job: DocumentPackageJob, *, requested_by: str) -> DownloadLink:
    """URL prefirmada del ZIP, como las versiones (decisión 40)."""
    status = job.effective_status
    if status == PackageJobStatus.EXPIRED:
        raise PackageExpired()
    if status != PackageJobStatus.COMPLETED:
        raise PackageNotReady()
    file_object = job.output_file_object
    assert file_object is not None
    seconds = settings.DOCUMENT_DOWNLOAD_URL_SECONDS
    expires_at = timezone.now() + timedelta(seconds=seconds)
    try:
        url = get_storage().presigned_url(
            file_object.object_key,
            expires_in=seconds,
            filename=file_object.original_filename,
            content_type=file_object.detected_mime_type,
        )
    except StorageUnavailable as exc:
        logger.warning("No se pudo firmar la descarga del paquete %s", job.pk)
        raise DownloadUnavailable() from exc
    logger.info("Descarga del paquete %s firmada para %s", job.pk, requested_by)
    return DownloadLink(url=url, expires_at=expires_at)


def requeue_stale_packages(older_than: timedelta) -> int:
    """Devuelve a ``PENDING`` los ``RUNNING`` colgados y encola los ``PENDING`` de más de
    ``older_than``. Un worker atrasado pierde el trabajo: no lo marcará ``COMPLETED``."""
    from apps.documents.tasks import build_document_package, log_eager_failure

    now = timezone.now()
    cutoff = now - older_than
    DocumentPackageJob.objects.filter(
        status=PackageJobStatus.RUNNING, started_at__lt=cutoff
    ).update(status=PackageJobStatus.PENDING, started_at=None, updated_at=now)
    pending = (
        DocumentPackageJob.objects.filter(status=PackageJobStatus.PENDING, created_at__lt=cutoff)
        .order_by("created_at")
        .values_list("pk", flat=True)
    )
    count = 0
    for job_id in pending.iterator():
        log_eager_failure(build_document_package.delay(str(job_id)), f"Paquete {job_id}")
        count += 1
    return count


def expire_packages() -> int:
    """Persiste ``EXPIRED`` en los paquetes vencidos y borra su ZIP. El registro de
    ``file_objects`` se conserva. Si el borrado falla, el paquete queda para la próxima
    vez (igual se lee como ``EXPIRED``)."""
    now = timezone.now()
    due = DocumentPackageJob.objects.filter(
        status=PackageJobStatus.COMPLETED, expires_at__lte=now
    ).select_related("output_file_object")
    storage = get_storage()
    count = 0
    for job in due.iterator():
        file_object = job.output_file_object
        assert file_object is not None
        try:
            storage.delete(file_object.object_key)
        except StorageUnavailable:
            logger.warning("No se pudo borrar el ZIP vencido del paquete %s", job.pk)
            continue
        count += DocumentPackageJob.objects.filter(
            pk=job.pk, status=PackageJobStatus.COMPLETED
        ).update(status=PackageJobStatus.EXPIRED, updated_at=now)
    return count
