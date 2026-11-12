"""Pestañas rápidas del listado de solicitudes (TAREA-applications-listado, precisión B).

Configuración fija en el código, no un catálogo: los estados son código
(``ApplicationStatus``) y cada uno está en exactamente una pestaña (sin contar ``all``),
así que la suma de las pestañas es igual a "Todas". Las usan ``quick_filter=<code>`` en
el listado y ``GET /applications/quick-filters`` con sus conteos.
"""

from dataclasses import dataclass

from apps.catalogs.workflow import ApplicationStatus


@dataclass(frozen=True)
class QuickFilter:
    code: str
    label: str
    # Vacío solo en `all`, que no filtra.
    statuses: tuple[str, ...]


ALL = "all"
WAITING = "waiting"

QUICK_FILTERS: tuple[QuickFilter, ...] = (
    QuickFilter(ALL, "Todas", ()),
    QuickFilter("draft", "Borradores", (ApplicationStatus.DRAFT,)),
    QuickFilter(
        WAITING,
        "Esperando al comprador",
        (ApplicationStatus.WAITING_BUYER_DATA, ApplicationStatus.WAITING_DOCUMENTS),
    ),
    QuickFilter("review", "En revisión", (ApplicationStatus.DOCUMENTS_REVIEW,)),
    QuickFilter("ready", "Listas para radicar", (ApplicationStatus.READY_TO_FILE,)),
    QuickFilter(
        "bank",
        "En el banco",
        (
            ApplicationStatus.FILED,
            ApplicationStatus.FILING_VALIDATION,
            ApplicationStatus.CREDIT_ANALYSIS,
            ApplicationStatus.BANK_OBSERVATION,
            ApplicationStatus.APPROVED,
            ApplicationStatus.LEGALIZATION,
        ),
    ),
    QuickFilter(
        "closed",
        "Cerradas",
        (
            ApplicationStatus.DISBURSED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.EXTERNAL_CREDIT_APPROVED,
            ApplicationStatus.OWN_FUNDS,
            ApplicationStatus.WITHDRAWN,
            ApplicationStatus.CANCELLED,
        ),
    ),
)
QUICK_FILTER_CODES = [quick.code for quick in QUICK_FILTERS]
QUICK_FILTERS_BY_CODE = {quick.code: quick for quick in QUICK_FILTERS}

# Estados de la pestaña "Esperando al comprador": allí aplica el aviso de inactividad.
WAITING_STATUSES = QUICK_FILTERS_BY_CODE[WAITING].statuses
