"""Lectura interna del expediente documental y recálculo manual (API §19).

Acceso (decisión 10):

- ``documents.read`` (``ADMIN`` y ``ADVISOR``): slots, versiones y metadatos.
- ``documents.manage_requirements`` (``ADMIN`` y ``ADVISOR``): ``refresh``.
- El asesor solo dentro de su alcance (solicitudes asignadas): fuera de él, ``404``.
  Broker y partner no tienen estos permisos: ``403``.

Vive aparte de ``slots.py`` porque depende de ``applications.services`` (alcance y
bloqueo), que a su vez llama a ``sync_slots``.
"""

import logging
import uuid

from django.db import transaction
from django.db.models import Count, F, OuterRef, Prefetch, QuerySet, Subquery, UUIDField, Value
from django.db.models.functions import Coalesce

from apps.applications.models import CreditApplication
from apps.applications.services import applications_visible_to, lock_for_edit
from apps.documents.models import ApplicationDocumentSlot, DocumentFile, DocumentReview
from apps.documents.models.review import FILE_DECISIONS, SLOT_DECISIONS
from apps.documents.slots import SlotSync, sync_slots
from apps.identity.models import BuyerSession, User

logger = logging.getLogger(__name__)

# Sustituto de un participante vacío (documento de la solicitud) para comparar titulares.
_NO_PARTICIPANT = Value(uuid.UUID(int=0), output_field=UUIDField())


def _set_size() -> Subquery:
    """Slots vigentes del mismo juego (titular + tipo): el "m" de "Nombre n de m"."""
    siblings = (
        ApplicationDocumentSlot.objects.filter(
            application=OuterRef("application"),
            document_type=OuterRef("document_type"),
            retired_at__isnull=True,
        )
        .annotate(holder=Coalesce("participant_id", _NO_PARTICIPANT))
        .filter(holder=Coalesce(OuterRef("participant_id"), _NO_PARTICIPANT))
        .order_by()
        .values("application")
        .annotate(total=Count("pk"))
        .values("total")
    )
    return Subquery(siblings)


def slots_queryset() -> QuerySet[ApplicationDocumentSlot]:
    """Slots con lo que serializa la respuesta. Primero los documentos de la solicitud,
    después los de cada participante en el orden en que entraron."""
    return (
        ApplicationDocumentSlot.objects.select_related(
            "document_type",
            "participant__client",
            "waiver_reason_item",
            "current_file__file_object",
        )
        .annotate(set_size=_set_size())
        .order_by(
            F("participant__created_at").asc(nulls_first=True),
            "sort_order",
            "document_type__code",
            "slot_index",
            "created_at",
        )
    )


def slots_visible_to(user: User) -> QuerySet[ApplicationDocumentSlot]:
    """Slots de las solicitudes visibles; el resto responde 404."""
    return slots_queryset().filter(application__in=applications_visible_to(user))


def application_slots(
    application: CreditApplication, *, include_retired: bool = False
) -> QuerySet[ApplicationDocumentSlot]:
    slots = slots_queryset().filter(application=application)
    return slots if include_retired else slots.filter(retired_at__isnull=True)


def _file_reviews() -> Prefetch:
    """Aprobaciones y rechazos de la versión, de la más reciente a la primera. Las
    exoneraciones y reaperturas son del slot (``waiver_history``)."""
    reviews = (
        DocumentReview.objects.filter(decision__in=FILE_DECISIONS)
        .select_related("reviewer", "reason_item")
        .order_by("-created_at")
    )
    return Prefetch("reviews", queryset=reviews)


def slot_versions(slot: ApplicationDocumentSlot) -> QuerySet[DocumentFile]:
    """Versiones del slot, de la más reciente a la primera, con sus revisiones."""
    return (
        DocumentFile.objects.filter(slot=slot)
        .select_related("file_object")
        .prefetch_related(_file_reviews())
        .order_by("-version_number")
    )


def slot_detail_queryset(user: User) -> QuerySet[ApplicationDocumentSlot]:
    """Slots visibles con el historial de exoneraciones y reaperturas
    (``waiver_history``), de la más reciente a la primera."""
    history = (
        DocumentReview.objects.filter(decision__in=SLOT_DECISIONS)
        .select_related("reviewer", "reason_item")
        .order_by("-created_at")
    )
    return slots_visible_to(user).prefetch_related(
        Prefetch("reviews", queryset=history, to_attr="waiver_history")
    )


def files_visible_to(user: User) -> QuerySet[DocumentFile]:
    """Versiones de las solicitudes visibles, también las de slots retirados."""
    return (
        DocumentFile.objects.filter(slot__application__in=applications_visible_to(user))
        .select_related("file_object", "slot")
        .prefetch_related(_file_reviews())
    )


def refresh_slots(actor: User, application: CreditApplication) -> SlotSync:
    """Recalcula la lista documental. Solo antes de `FILED` (``409
    APPLICATION_NOT_EDITABLE``). No exige ``If-Match`` ni aumenta la versión de la
    solicitud (acordada 6)."""
    with transaction.atomic():
        locked = lock_for_edit(application, None)
        result = sync_slots(locked)
    logger.info("Expediente de %s recalculado por %s", locked.code, actor.pk)
    return result


# --------------------------------------------------------------------------------------
# Portal del comprador
# --------------------------------------------------------------------------------------


def _buyer_reviews() -> Prefetch:
    """Revisiones para mostrar el último rechazo al comprador, de la más reciente a la
    primera."""
    return Prefetch("reviews", queryset=_buyer_review_queryset())


def _buyer_review_queryset() -> QuerySet[DocumentReview]:
    """Solo aprobaciones y rechazos: las exoneraciones, reaperturas y sus notas son
    internas."""
    return (
        DocumentReview.objects.filter(decision__in=FILE_DECISIONS)
        .select_related("reason_item")
        .order_by("-created_at")
    )


def buyer_slot_queryset(session: BuyerSession) -> QuerySet[ApplicationDocumentSlot]:
    """Slots vigentes de la solicitud de la sesión, con lo que muestra el portal."""
    return (
        slots_queryset()
        .filter(application_id=session.application_id, retired_at__isnull=True)
        .prefetch_related(Prefetch("current_file__reviews", queryset=_buyer_review_queryset()))
    )


def buyer_versions(slot: ApplicationDocumentSlot) -> QuerySet[DocumentFile]:
    return (
        DocumentFile.objects.filter(slot=slot)
        .select_related("file_object")
        .prefetch_related(_buyer_reviews())
        .order_by("-version_number")
    )


def buyer_files(session: BuyerSession) -> QuerySet[DocumentFile]:
    """Versiones de los slots vigentes de la solicitud de la sesión."""
    return DocumentFile.objects.filter(
        slot__application_id=session.application_id, slot__retired_at__isnull=True
    ).select_related("file_object")
