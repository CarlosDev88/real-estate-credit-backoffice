"""Título y mensaje de cada notificación del comprador: una sola fuente.

Los textos son públicos. Solo se completan con datos que el comprador ya conoce o que
son suyos: el nombre del documento y del titular, el mensaje al comprador de la
revisión, el banco, las fechas, el mensaje público de la respuesta del banco y el monto
y el plazo aprobados. Nunca llevan notas internas (``internal_comment``), números de
identificación ni ingresos.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from django.utils import timezone

from apps.notifications.models import NotificationType

TITLE_MAX_LENGTH = 180

_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


@dataclass(frozen=True)
class Template:
    title: str
    message: str


MESSAGES: dict[str, Template] = {
    NotificationType.ACCESS_GRANTED: Template(
        title="Bienvenido a tu portal",
        message="Desde aquí sigues tu solicitud de crédito. Siguiente paso: {next_action}",
    ),
    NotificationType.DOCUMENT_REJECTED: Template(
        title="Debes corregir: {document}",
        message="{buyer_comment}",
    ),
    NotificationType.READY_TO_FILE: Template(
        title="Tu expediente está completo",
        message=(
            "Revisamos tus datos y documentos y están completos. Tu asesor radicará la "
            "solicitud en el banco y te avisaremos cuando lo haga."
        ),
    ),
    NotificationType.FILED: Template(
        title="Radicamos tu solicitud en {bank}",
        message=(
            "Tu asesor radicó tu solicitud en {bank} el {date}. Te avisaremos cuando el "
            "banco responda."
        ),
    ),
    NotificationType.BANK_RETURNED: Template(
        title="El banco pidió correcciones",
        message="{public_message}",
    ),
    NotificationType.BANK_APPROVED: Template(
        title="¡Tu crédito fue aprobado!",
        message="{public_message}{approval}",
    ),
    NotificationType.BANK_REJECTED: Template(
        title="El banco rechazó tu solicitud",
        message="{public_message}",
    ),
    NotificationType.DISBURSED: Template(
        title="Se desembolsó tu crédito",
        message=(
            "El banco desembolsó tu crédito el {date}. Tu asesor te indicará los pasos que siguen."
        ),
    ),
}


@dataclass(frozen=True)
class Rendered:
    title: str
    message: str


def render(notification_type: str, **values: Any) -> Rendered:
    template = MESSAGES[notification_type]
    title = template.title.format(**values)
    if len(title) > TITLE_MAX_LENGTH:
        title = title[: TITLE_MAX_LENGTH - 1].rstrip() + "…"
    return Rendered(title=title, message=template.message.format(**values).strip())


def long_date(moment: datetime | date) -> str:
    """``17 de noviembre de 2026``, en la zona horaria local."""
    day = timezone.localdate(moment) if isinstance(moment, datetime) else moment
    return f"{day.day} de {_MONTHS[day.month - 1]} de {day.year}"


def pesos(amount: int) -> str:
    """``$350.000.000``."""
    return "$" + f"{amount:,}".replace(",", ".")
