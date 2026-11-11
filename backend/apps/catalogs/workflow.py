"""Estados estructurales de cada flujo de negocio (sección 4 de los requerimientos).

Los estados son constantes del backend y protegen las invariantes del dominio. Las
transiciones (`workflow_transitions`) solo deciden qué saltos entre estos estados
están disponibles, para qué roles y bajo qué guarda; nunca pueden inventar estados.

Las etiquetas visibles de cada estado viven en los catálogos `*_status`, que se
siembran con estos mismos códigos.
"""

from django.db import models


class FlowType(models.TextChoices):
    OPPORTUNITY = "OPPORTUNITY", "Oportunidad comercial"
    APPLICATION = "APPLICATION", "Solicitud de crédito"
    PROJECT = "PROJECT", "Proyecto inmobiliario"


class OpportunityStatus(models.TextChoices):
    NEW = "NEW", "Nueva"
    ASSIGNED = "ASSIGNED", "Asignada"
    CONTACTED = "CONTACTED", "Contactada"
    IN_PROGRESS = "IN_PROGRESS", "En gestión"
    CONVERTED = "CONVERTED", "Convertida"
    LOST = "LOST", "Perdida"
    CANCELLED = "CANCELLED", "Cancelada"


class ApplicationStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    WAITING_BUYER_DATA = "WAITING_BUYER_DATA", "Esperando datos del comprador"
    WAITING_DOCUMENTS = "WAITING_DOCUMENTS", "Esperando documentos"
    DOCUMENTS_REVIEW = "DOCUMENTS_REVIEW", "Documentos en revisión"
    READY_TO_FILE = "READY_TO_FILE", "Lista para radicar"
    FILED = "FILED", "Radicada"
    FILING_VALIDATION = "FILING_VALIDATION", "Validación de radicación"
    CREDIT_ANALYSIS = "CREDIT_ANALYSIS", "Análisis de crédito"
    APPROVED = "APPROVED", "Aprobada"
    LEGALIZATION = "LEGALIZATION", "Legalización"
    DISBURSED = "DISBURSED", "Desembolsada"
    BANK_OBSERVATION = "BANK_OBSERVATION", "Observación del banco"
    REJECTED = "REJECTED", "Rechazada"
    EXTERNAL_CREDIT_APPROVED = "EXTERNAL_CREDIT_APPROVED", "Crédito aprobado externamente"
    OWN_FUNDS = "OWN_FUNDS", "Recursos propios"
    WITHDRAWN = "WITHDRAWN", "Desistida"
    CANCELLED = "CANCELLED", "Cancelada"


class ProjectStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    PENDING_REVIEW = "PENDING_REVIEW", "En validación"
    ACTIVE = "ACTIVE", "Activo"
    ARCHIVED = "ARCHIVED", "Archivado"


class DocumentStatus(models.TextChoices):
    PENDING = "PENDING", "Pendiente"
    UPLOADED = "UPLOADED", "Cargado"
    APPROVED = "APPROVED", "Aprobado"
    REJECTED = "REJECTED", "Rechazado"
    WAIVED = "WAIVED", "Exonerado"


FLOW_STATUSES: dict[str, type[models.TextChoices]] = {
    FlowType.OPPORTUNITY: OpportunityStatus,
    FlowType.APPLICATION: ApplicationStatus,
    FlowType.PROJECT: ProjectStatus,
}

# Guardas de dominio que una transición puede exigir. Cada código corresponde a una
# regla que el módulo dueño del flujo evalúa antes de ejecutar el cambio de estado
# (por ejemplo, `applications` evalúa `APPLICATION_READY_TO_FILE`).
TRANSITION_GUARDS: dict[str, dict[str, str]] = {
    FlowType.OPPORTUNITY: {},
    FlowType.APPLICATION: {
        "APPLICATION_READY_TO_FILE": (
            "Banco y producto seleccionados, y todos los documentos obligatorios "
            "aprobados o exonerados."
        ),
    },
    FlowType.PROJECT: {},
}


def statuses_for(flow_type: str) -> set[str]:
    choices = FLOW_STATUSES.get(flow_type)
    return set(choices.values) if choices else set()


def guards_for(flow_type: str) -> set[str]:
    return set(TRANSITION_GUARDS.get(flow_type, {}))
