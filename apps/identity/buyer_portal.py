"""Lecturas del portal del comprador (API §8): su proceso y su solicitud.

Los DTO del portal nunca exponen notas, el asesor interno ni las evaluaciones
bancarias (``specs/TAREA-buyer-access.md``, Parte 3).
"""

from dataclasses import dataclass

from django.db.models import Prefetch, QuerySet

from apps.applications.models import CreditApplication
from apps.applications.services import CompletenessItem, completeness, participants_queryset
from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import ApplicationStatus
from apps.identity.models import BuyerSession

APPLICATION_STATUS_CATALOG = "application_status"

# Decisión 17: el estado público es el estado de la solicitud, con un texto fijo.
NEXT_ACTIONS: dict[str, str] = {
    ApplicationStatus.DRAFT: "Tu asesor está preparando la solicitud.",
    ApplicationStatus.WAITING_BUYER_DATA: "Completa tus datos personales y financieros.",
    ApplicationStatus.WAITING_DOCUMENTS: "Carga los documentos que te pidieron.",
    ApplicationStatus.DOCUMENTS_REVIEW: "Estamos revisando tus documentos.",
    ApplicationStatus.READY_TO_FILE: "Tu solicitud está lista para radicarse en el banco.",
    ApplicationStatus.FILED: "Tu solicitud fue radicada en el banco.",
    ApplicationStatus.FILING_VALIDATION: "El banco está validando la radicación.",
    ApplicationStatus.CREDIT_ANALYSIS: "El banco está analizando tu crédito.",
    ApplicationStatus.APPROVED: "Tu crédito fue aprobado. Tu asesor te indicará los pasos.",
    ApplicationStatus.LEGALIZATION: "Tu crédito está en legalización.",
    ApplicationStatus.DISBURSED: "Tu crédito fue desembolsado.",
    ApplicationStatus.BANK_OBSERVATION: "El banco hizo observaciones. Tu asesor te contactará.",
    ApplicationStatus.REJECTED: "El banco no aprobó la solicitud. Tu asesor te contactará.",
    ApplicationStatus.EXTERNAL_CREDIT_APPROVED: "Tu crédito fue aprobado por otra entidad.",
    ApplicationStatus.OWN_FUNDS: "La compra se hará con recursos propios.",
    ApplicationStatus.WITHDRAWN: "La solicitud fue desistida.",
    ApplicationStatus.CANCELLED: "La solicitud fue cancelada.",
}

# La evaluación bancaria es interna: el progreso del comprador no la cuenta.
_INTERNAL_PROGRESS_ITEMS = frozenset({"bank_evaluation"})


@dataclass(frozen=True)
class BuyerProgress:
    percentage: int
    items: list[CompletenessItem]


def public_status_label(status: str) -> str:
    """Etiqueta del catálogo ``application_status``; si falta, la del backend."""
    label = (
        CatalogItem.objects.filter(catalog__code=APPLICATION_STATUS_CATALOG, code=status)
        .values_list("label", flat=True)
        .first()
    )
    return label or str(ApplicationStatus(status).label)


def next_action(status: str) -> str:
    return NEXT_ACTIONS[status]


def buyer_progress(application: CreditApplication) -> BuyerProgress:
    """Ítems de ``completeness`` sin los internos, con su propio porcentaje."""
    items = [
        item
        for item in completeness(application).items
        if item.code not in _INTERNAL_PROGRESS_ITEMS
    ]
    percentage = sum(item.complete for item in items) * 100 // len(items)
    return BuyerProgress(percentage=percentage, items=items)


def session_applications(session: BuyerSession) -> QuerySet[CreditApplication]:
    """La única solicitud a la que da acceso la sesión."""
    return CreditApplication.objects.select_related("purpose_item").filter(
        pk=session.application_id
    )


def buyer_application_detail(session: BuyerSession) -> QuerySet[CreditApplication]:
    return (
        session_applications(session)
        .select_related(
            "bank_product__bank",
            "financed_property__project",
            "financed_property__property_type_item",
            "financed_property__condition_item",
            "financed_property__city_item",
            "financing__financing_mode_item",
            "financing__currency_mode_item",
            "financing__amortization_mode_item",
        )
        .prefetch_related(
            Prefetch(
                "participants",
                queryset=participants_queryset().filter(is_active=True).order_by("created_at"),
                to_attr="active_participants",
            )
        )
    )
