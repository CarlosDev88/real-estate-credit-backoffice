"""Lecturas del portal del comprador (API §8): su proceso y su solicitud.

Los DTO del portal nunca exponen notas, el asesor interno ni las evaluaciones
bancarias (``specs/TAREA-buyer-access.md``, Parte 3).
"""

from dataclasses import dataclass

from django.db.models import Prefetch, QuerySet

from apps.applications.models import CreditApplication
from apps.applications.services import (
    CompletenessItem,
    data_items,
    items_percentage,
    participants_queryset,
)
from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import ApplicationStatus
from apps.documents.verification import check_dossier
from apps.identity.models import BuyerSession

APPLICATION_STATUS_CATALOG = "application_status"

# Catálogos que el comprador consulta en `/buyer/metadata/catalogs/{code}`: los que
# validan sus formularios (`CatalogItemCodeField` de los serializers que usa el portal) y
# `department`, el padre de `municipality`. Otro código responde `404`.
BUYER_CATALOG_CODES: frozenset[str] = frozenset(
    {
        "address_type",
        "department",
        "municipality",
        "employment_profile",
        "contract_type",
        "funds_origin",
        "income_source_type",
        "property_type",
        "property_condition",
        "financing_mode",
        "currency_mode",
        "amortization_mode",
        "application_withdrawal_reason",
    }
)

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
    """La regla de la completitud (acordada 7 de ``TAREA-document-file``): promedio de
    los datos (sin la evaluación bancaria) y los documentos obligatorios. Sin detalle
    por documento ni mensajes internos: el detalle está en ``/buyer/.../document-slots``."""

    percentage: int
    data_percentage: int
    documents_percentage: int
    documents_required_total: int
    documents_completed_total: int
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
    """Ítems de datos sin los internos y el avance de los documentos obligatorios."""
    items = [item for item in data_items(application) if item.code not in _INTERNAL_PROGRESS_ITEMS]
    data_percentage = items_percentage(items)
    dossier = check_dossier(application)
    return BuyerProgress(
        percentage=(data_percentage + dossier.percentage) // 2,
        data_percentage=data_percentage,
        documents_percentage=dossier.percentage,
        documents_required_total=dossier.required_total,
        documents_completed_total=dossier.completed_total,
        items=items,
    )


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
