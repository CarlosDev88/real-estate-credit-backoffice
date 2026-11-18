"""Reporte de solicitudes (``/reports/applications``) y su CSV (API §22.2, RNF-08).

Columnas: las mismas en el JSON y en el CSV (``COLUMNS``), en ese orden. Solo datos
operativos: el documento del titular sale enmascarado (``******1234``) y nunca salen el
correo, el teléfono, la dirección, los datos financieros del comprador ni archivos.
``requested_amount`` sí sale (es dato operativo).

CSV: UTF-8 **con BOM** (para que Excel abra bien las tildes), separador ``,`` y
encabezados en español. Las fechas van en hora de Bogotá (``YYYY-MM-DD HH:MM``). Toda
celda de texto que empiece con ``=``, ``+``, ``-``, ``@``, tabulador o retorno de carro
se prefija con ``'`` (inyección de fórmulas).
"""

import csv
from collections.abc import Iterable, Iterator
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db.models import Count, DateTimeField, F, OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.applications.models import ApplicationStatusHistory, CreditApplication
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.services import CrmScope
from apps.filings.models import Filing
from apps.identity.models import User
from apps.reporting.filters import ReportFilters, scoped_applications

REPORT_TYPE_APPLICATIONS = "applications"
FORMAT_CSV = "csv"

# Campo → encabezado del CSV, en el orden del reporte.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("code", "Código"),
    ("created_at", "Fecha de creación"),
    ("status", "Código de estado"),
    ("status_label", "Estado"),
    ("purpose", "Finalidad"),
    ("advisor_name", "Asesor"),
    ("client_name", "Cliente"),
    ("client_document_masked", "Documento del cliente"),
    ("bank_name", "Banco"),
    ("project_name", "Proyecto"),
    ("requested_amount", "Monto solicitado (COP)"),
    ("last_status_change_at", "Último cambio de estado"),
    ("filings_count", "Radicaciones"),
)

MASK = "******"
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
CSV_BOM = "﻿"
CSV_DATETIME_FORMAT = "%Y-%m-%d %H:%M"
ITERATOR_CHUNK_SIZE = 500

_STATUS_LABELS = {str(value): str(label) for value, label in ApplicationStatus.choices}


def mask_document(value: str | None) -> str:
    """``1032445908`` → ``******5908``: una máscara fija, que tampoco revela el largo."""
    if not value:
        return ""
    return f"{MASK}{value[-4:]}"


def neutralize_formula(value: str) -> str:
    """Prefija con ``'`` el texto que Excel interpretaría como fórmula."""
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value


def _filings_count() -> Coalesce:
    count = (
        Filing.objects.filter(application=OuterRef("pk"))
        .order_by()
        .values("application")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    return Coalesce(Subquery(count), 0)


def _last_status_change() -> Coalesce:
    latest = (
        ApplicationStatusHistory.objects.filter(application=OuterRef("pk"))
        .order_by("-created_at")
        .values("created_at")[:1]
    )
    return Coalesce(Subquery(latest, output_field=DateTimeField()), F("current_stage_started_at"))


def report_applications(
    user: User, filters: ReportFilters, scope: CrmScope
) -> QuerySet[CreditApplication]:
    """Solicitudes creadas en el periodo, con el alcance y los filtros, y todo lo que
    muestra cada fila en una sola consulta. Orden: las más nuevas primero."""
    return (
        scoped_applications(user, filters, scope=scope)
        .select_related(
            "opportunity__client",
            "assigned_advisor",
            "purpose_item",
            "bank_product__bank",
            "financing",
        )
        .annotate(
            report_project_name=Coalesce(
                "financed_property__project__name", "opportunity__project__name"
            ),
            last_status_change_at=_last_status_change(),
            filings_count=_filings_count(),
        )
        .order_by("-created_at", "-code")
    )


def application_row(application: CreditApplication) -> dict[str, Any]:
    """Valores de una fila, con los tipos de Python (el serializer y el CSV los
    formatean)."""
    financing = getattr(application, "financing", None)
    client = application.opportunity.client
    bank = application.bank_product.bank if application.bank_product else None
    amount = financing.requested_amount_cop if financing is not None else None
    return {
        "code": application.code,
        "created_at": application.created_at,
        "status": application.status,
        "status_label": _STATUS_LABELS[application.status],
        "purpose": application.purpose_item.label,
        "advisor_name": application.assigned_advisor.get_full_name(),
        "client_name": client.full_name,
        "client_document_masked": mask_document(client.document_number),
        "bank_name": bank.name if bank else None,
        "project_name": application.report_project_name,  # type: ignore[attr-defined]
        "requested_amount": None if amount is None else Decimal(amount).quantize(Decimal("0.01")),
        "last_status_change_at": application.last_status_change_at,  # type: ignore[attr-defined]
        "filings_count": application.filings_count,  # type: ignore[attr-defined]
    }


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime(CSV_DATETIME_FORMAT)
    if isinstance(value, Decimal):
        # COP sin centavos: un entero que Excel suma sin tropezar con el separador.
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return neutralize_formula(str(value))


class _Echo:
    """Pseudo-archivo para ``csv.writer``: devuelve la línea en vez de guardarla."""

    def write(self, value: str) -> str:
        return value


def csv_lines(applications: Iterable[CreditApplication]) -> Iterator[str]:
    """Líneas del CSV: el BOM con los encabezados y una línea por solicitud."""
    writer = csv.writer(_Echo())
    yield CSV_BOM + writer.writerow([header for _, header in COLUMNS])
    for application in applications:
        row = application_row(application)
        yield writer.writerow([_csv_cell(row[name]) for name, _ in COLUMNS])


def csv_filename(filters: ReportFilters) -> str:
    return f"solicitudes_{filters.date_from.isoformat()}_{filters.date_to.isoformat()}.csv"
