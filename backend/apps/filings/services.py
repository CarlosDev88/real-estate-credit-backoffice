"""Radicación manual (API §20.1, paso 11).

La API no se comunica con el banco: el asesor entrega el paquete por el canal del banco
y aquí registra esa entrega. Alcance:

- lectura (``filings.read``): las radicaciones de las solicitudes visibles; el broker,
  las de las oportunidades que originó, sin el comentario interno;
- escritura y snapshots: el administrador o el asesor asignado
  (``ensure_can_manage``); fuera del alcance, ``404``.

**Registrar** (``create_filing``), en una transacción que bloquea la solicitud, después
sus slots vigentes en orden de id (decisión 22) y después el paquete:

1. la versión (``409 STALE_VERSION``) y el estado `READY_TO_FILE`
   (``409 INVALID_STATE_TRANSITION``; terminada, ``409 APPLICATION_CLOSED``);
2. el producto de la financiación (``422 BANK_PRODUCT_MISMATCH``);
3. la guarda de `READY_TO_FILE`: documentos y reglas del banco
   (``422 APPLICATION_NOT_READY``; la evaluación bancaria que guarde queda guardada);
4. el paquete: de esta solicitud (``400``), sin radicar (``409 PACKAGE_ALREADY_FILED``),
   terminado y vigente (``409 PACKAGE_NOT_READY`` o ``PACKAGE_EXPIRED``) y con la huella
   documental vigente (``409 PACKAGE_OUTDATED``).

Crea la radicación con el consecutivo siguiente, un snapshot por cada versión del
manifiesto del paquete, bloquea esos slots (``locked_at``) y pasa la solicitud a
`FILED` con la transición de sistema `FILE`. Después de confirmar emite
``application_status_changed`` y ``filing_created``.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Count, Max, QuerySet
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.applications.exceptions import ApplicationNotReady
from apps.applications.models import CreditApplication
from apps.applications.services import (
    SystemStatusChange,
    applications_visible_to,
    apply_system_transition,
    get_application_scope,
    lock_for_status_change,
    notify_system_transition,
    ready_to_file_problems,
)
from apps.catalogs.exceptions import InvalidStateTransition
from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import ApplicationStatus
from apps.documents.exceptions import PackageExpired, PackageNotReady
from apps.documents.fingerprint import dossier_fingerprint
from apps.documents.models import ApplicationDocumentSlot, DocumentPackageJob, PackageJobStatus
from apps.documents.verification import check_dossier
from apps.filings.exceptions import (
    BankProductMismatch,
    FilingReferenceExists,
    PackageAlreadyFiled,
    PackageOutdated,
)
from apps.filings.models import Filing, FilingDocumentSnapshot
from apps.filings.signals import filing_created
from apps.identity.models import User

logger = logging.getLogger(__name__)

EXTERNAL_REFERENCE_CONSTRAINT = "uq_filings_external_reference"


# --- Alcance ----------------------------------------------------------------------------


def filings_queryset() -> QuerySet[Filing]:
    """Radicaciones con lo que muestra la respuesta, en una sola consulta."""
    return (
        Filing.objects.select_related(
            "application",
            "bank_product__bank",
            "bank_product__product_type_item",
            "channel_item",
            "filed_by",
        )
        .annotate(responses_count=Count("responses"))
        .order_by("-sequence_number")
    )


def filings_visible_to(user: User) -> QuerySet[Filing]:
    return filings_queryset().filter(application__in=applications_visible_to(user).values("pk"))


def can_manage(user: User, application: CreditApplication) -> bool:
    """El administrador o el asesor asignado. El broker solo lee."""
    scope = get_application_scope(user)
    return scope.sees_everything or application.assigned_advisor_id == user.pk


def ensure_can_manage(user: User, application: CreditApplication) -> None:
    if not can_manage(user, application):
        raise PermissionDenied()


def is_restricted(user: User) -> bool:
    """El broker: no ve el comentario interno de la radicación."""
    return get_application_scope(user).is_restricted


# --- Registrar --------------------------------------------------------------------------


def _detail(field: str, code: str, message: str) -> list[dict[str, Any]]:
    return [{"field": field, "code": code, "message": message}]


def _ensure_ready_status(locked: CreditApplication) -> None:
    if locked.status != ApplicationStatus.READY_TO_FILE:
        raise InvalidStateTransition(
            f"Solo se radica una solicitud en {ApplicationStatus.READY_TO_FILE}; esta está "
            f"en {locked.status}."
        )


def _ensure_product(locked: CreditApplication, bank_product_id: uuid.UUID) -> None:
    if locked.bank_product_id != bank_product_id:
        raise BankProductMismatch(
            details=_detail(
                "bank_product_id",
                "BANK_PRODUCT_MISMATCH",
                "Radica con el producto que tiene la financiación de la solicitud.",
            )
        )


def _locked_package(locked: CreditApplication, package_job_id: uuid.UUID) -> DocumentPackageJob:
    job = (
        DocumentPackageJob.objects.select_for_update()
        .filter(application=locked, pk=package_job_id)
        .first()
    )
    if job is None:
        raise ValidationError({"package_job_id": ["El paquete no existe en esta solicitud."]})
    if Filing.objects.filter(package_job=job).exists():
        raise PackageAlreadyFiled()
    job_status = job.effective_status
    if job_status == PackageJobStatus.EXPIRED:
        raise PackageExpired("El paquete venció: pide otro antes de radicar.")
    if job_status != PackageJobStatus.COMPLETED:
        raise PackageNotReady("El paquete todavía no está listo: espera a que termine.")
    if (job.manifest or {}).get("fingerprint") != dossier_fingerprint(locked):
        raise PackageOutdated()
    return job


def _target_response_at(locked: CreditApplication, filed_at: datetime) -> datetime | None:
    product = locked.bank_product
    assert product is not None
    days = product.bank.filing_response_days
    return None if days is None else filed_at + timedelta(days=days)


def _raise_reference_conflict(exc: IntegrityError) -> None:
    """La referencia del banco es única por producto (``uq_filings_external_reference``)."""
    if EXTERNAL_REFERENCE_CONSTRAINT in str(exc):
        raise FilingReferenceExists(
            details=_detail(
                "external_reference",
                "FILING_REFERENCE_EXISTS",
                "Ya hay una radicación con esa referencia para el producto.",
            )
        ) from exc


def _create_filing_row(**values: Any) -> Filing:
    try:
        with transaction.atomic():
            return Filing.objects.create(**values)
    except IntegrityError as exc:
        _raise_reference_conflict(exc)
        raise


def _snapshot_documents(filing: Filing, job: DocumentPackageJob) -> None:
    """Un snapshot por cada versión del manifiesto (los exonerados no tienen archivo) y
    el bloqueo posterior a la radicación de esos slots."""
    documents = (job.manifest or {}).get("documents", [])
    FilingDocumentSnapshot.objects.bulk_create(
        [
            FilingDocumentSnapshot(
                filing=filing,
                document_file_id=entry["file"]["document_file_id"],
                file_object_id=entry["file"]["file_object_id"],
                sha256=entry["file"]["sha256"],
                document_type_code=entry["document_type"]["code"],
            )
            for entry in documents
            if entry["file"] is not None
        ]
    )
    ApplicationDocumentSlot.objects.filter(
        pk__in=[entry["slot_id"] for entry in documents], locked_at__isnull=True
    ).update(locked_at=timezone.now())


def create_filing(
    actor: User,
    application: CreditApplication,
    *,
    bank_product_id: uuid.UUID,
    package_job_id: uuid.UUID,
    channel: CatalogItem,
    filed_at: datetime,
    expected_version: int,
    external_reference: str | None = None,
    comment: str | None = None,
) -> Filing:
    """Registra la radicación manual. Ver las precondiciones en el docstring del módulo."""
    problems: list[dict[str, Any]] = []
    filing: Filing | None = None
    status_change: SystemStatusChange | None = None
    with transaction.atomic():
        locked = lock_for_status_change(application, expected_version)
        _ensure_ready_status(locked)
        _ensure_product(locked, bank_product_id)
        # Solicitud y después todos sus slots vigentes, en orden (decisión 22).
        dossier = check_dossier(locked, lock=True)
        problems = ready_to_file_problems(locked, dossier=dossier, evaluate_as=actor)
        if not problems:
            job = _locked_package(locked, package_job_id)
            last = Filing.objects.filter(application=locked).aggregate(last=Max("sequence_number"))
            filing = _create_filing_row(
                application=locked,
                bank_product_id=bank_product_id,
                package_job=job,
                sequence_number=(last["last"] or 0) + 1,
                channel_item=channel,
                external_reference=external_reference,
                filed_by=actor,
                filed_at=filed_at,
                target_response_at=_target_response_at(locked, filed_at),
                comment=comment,
            )
            _snapshot_documents(filing, job)
            status_change = apply_system_transition(
                actor, locked, to_status=ApplicationStatus.FILED
            )
    if problems:
        # Fuera del bloque: la evaluación que guardó la guarda queda confirmada.
        raise ApplicationNotReady(details=problems)
    assert filing is not None and status_change is not None
    logger.info("Solicitud %s radicada (#%s) por %s", locked.code, filing.sequence_number, actor.pk)
    notify_system_transition(actor, status_change)
    filing_created.send(sender=Filing, filing=filing, application=locked, actor=actor)
    return filing


# --- Corregir ---------------------------------------------------------------------------

EDITABLE_FIELDS = ("external_reference", "comment")


def update_filing(actor: User, filing: Filing, changes: dict[str, Any]) -> None:
    """Corrige la referencia del banco o el comentario. No toca el estado, los snapshots
    ni las respuestas, y no cambia la versión de la solicitud."""
    with transaction.atomic():
        locked = Filing.objects.select_for_update().get(pk=filing.pk)
        fields = [
            name
            for name in EDITABLE_FIELDS
            if name in changes and getattr(locked, name) != changes[name]
        ]
        if not fields:
            return
        for name in fields:
            setattr(locked, name, changes[name])
        try:
            with transaction.atomic():
                locked.save(update_fields=[*fields, "updated_at"])
        except IntegrityError as exc:
            _raise_reference_conflict(exc)
            raise
    logger.info("Radicación %s corregida (%s) por %s", filing.pk, ", ".join(fields), actor.pk)


def snapshots_queryset(filing: Filing) -> QuerySet[FilingDocumentSnapshot]:
    return (
        FilingDocumentSnapshot.objects.filter(filing=filing)
        .select_related("document_file", "file_object")
        .order_by("created_at", "id")
    )
