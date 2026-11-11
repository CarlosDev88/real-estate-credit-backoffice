"""Consentimientos del comprador (``specs/TAREA-buyer-access.md``, decisión 16).

- **Vigente**: la versión mayor de cada código con ``effective_from <= now`` y sin
  retirar a esa fecha (``retired_at`` nulo o futuro).
- **Obligatorio**: ``DATA_PROCESSING`` siempre; ``CO_APPLICANT_AUTHORIZATION`` solo si la
  solicitud tiene co-solicitantes activos (decisión 18: todo participante activo que
  no es el titular).
- **Estado** de una definición para el cliente y la solicitud: la última acción sobre
  esa versión exacta. Aceptar una versión anterior no cuenta para la nueva.
- Los registros son evidencia inmutable: retirar agrega una fila ``WITHDRAWN``.

Está separado de ``services.py`` porque depende de ``applications``.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import models, transaction
from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from apps.applications.exceptions import ApplicationClosed
from apps.applications.models import ApplicationParticipant, CreditApplication, ParticipantRole
from apps.identity.exceptions import ConsentNotAccepted, ConsentNotEffective, ConsentRequired
from apps.identity.models import (
    BuyerSession,
    ConsentAction,
    ConsentDefinition,
    ConsentRecord,
)
from apps.identity.services import client_ip, user_agent_summary

logger = logging.getLogger(__name__)

DATA_PROCESSING = "DATA_PROCESSING"
CO_APPLICANT_AUTHORIZATION = "CO_APPLICANT_AUTHORIZATION"


class ConsentStatus(models.TextChoices):
    """Estado de una definición para un cliente: su última acción, o pendiente."""

    PENDING = "PENDING", "Pendiente"
    ACCEPTED = "ACCEPTED", "Aceptado"
    WITHDRAWN = "WITHDRAWN", "Retirado"


@dataclass(frozen=True)
class ConsentState:
    definition: ConsentDefinition
    required: bool
    last_record: ConsentRecord | None

    @property
    def status(self) -> ConsentStatus:
        if self.last_record is None:
            return ConsentStatus.PENDING
        return ConsentStatus(self.last_record.action)

    @property
    def accepted_at(self) -> datetime | None:
        if self.status != ConsentStatus.ACCEPTED or self.last_record is None:
            return None
        return self.last_record.created_at

    @property
    def is_missing(self) -> bool:
        return self.required and self.status != ConsentStatus.ACCEPTED


def _effective_filter(moment: datetime) -> Q:
    return Q(effective_from__lte=moment) & (Q(retired_at__isnull=True) | Q(retired_at__gt=moment))


def effective_definitions(moment: datetime | None = None) -> list[ConsentDefinition]:
    """La versión vigente de cada código, ordenadas por código."""
    moment = moment or timezone.now()
    latest: dict[str, ConsentDefinition] = {}
    for definition in ConsentDefinition.objects.filter(_effective_filter(moment)).order_by(
        "code", "-version"
    ):
        latest.setdefault(definition.code, definition)
    return list(latest.values())


def has_co_applicants(application_id: uuid.UUID) -> bool:
    return (
        ApplicationParticipant.objects.filter(application_id=application_id, is_active=True)
        .exclude(role=ParticipantRole.PRIMARY)
        .exists()
    )


def required_codes(application_id: uuid.UUID) -> set[str]:
    codes = {DATA_PROCESSING}
    if has_co_applicants(application_id):
        codes.add(CO_APPLICANT_AUTHORIZATION)
    return codes


def _last_records(
    application_id: uuid.UUID, client_id: uuid.UUID, definitions: list[ConsentDefinition]
) -> dict[uuid.UUID, ConsentRecord]:
    records = ConsentRecord.objects.filter(
        application_id=application_id,
        client_id=client_id,
        consent_definition__in=definitions,
    ).order_by("consent_definition_id", "-created_at")
    latest: dict[uuid.UUID, ConsentRecord] = {}
    for record in records:
        latest.setdefault(record.consent_definition_id, record)
    return latest


def consent_states(session: BuyerSession) -> list[ConsentState]:
    """Definiciones vigentes con su obligatoriedad y su estado para la sesión."""
    definitions = effective_definitions()
    required = required_codes(session.application_id)
    last = _last_records(session.application_id, session.client_id, definitions)
    return [
        ConsentState(
            definition=definition,
            required=definition.code in required,
            last_record=last.get(definition.pk),
        )
        for definition in definitions
    ]


def missing_consents(session: BuyerSession) -> list[ConsentDefinition]:
    return [state.definition for state in consent_states(session) if state.is_missing]


def ensure_consents_accepted(session: BuyerSession) -> None:
    """``403 CONSENT_REQUIRED``, con un detalle por consentimiento pendiente."""
    missing = missing_consents(session)
    if missing:
        raise ConsentRequired(
            details=[
                {
                    "field": None,
                    "code": definition.code,
                    "message": f"Acepta «{definition.title}» (versión {definition.version}).",
                    "resource_id": definition.pk,
                }
                for definition in missing
            ]
        )


@dataclass(frozen=True)
class RecordedConsent:
    record: ConsentRecord
    created: bool


def record_consent(
    *,
    request: HttpRequest,
    session: BuyerSession,
    definition: ConsentDefinition,
    action: str,
) -> RecordedConsent:
    """Acepta o retira una versión vigente. Repetir la última acción no crea otra fila.

    - Versión no vigente (futura, retirada o reemplazada): ``422 CONSENT_NOT_EFFECTIVE``.
    - Retirar sin una aceptación vigente: ``409 CONSENT_NOT_ACCEPTED``.
    - Solicitud terminada: ``409 APPLICATION_CLOSED``.
    """
    with transaction.atomic():
        # Serializa las acciones de la misma sesión: dos aceptaciones simultáneas no
        # dejan dos filas.
        locked = BuyerSession.objects.select_for_update().get(pk=session.pk)
        if CreditApplication.objects.filter(pk=locked.application_id).get().is_terminal:
            raise ApplicationClosed()
        if definition not in effective_definitions():
            raise ConsentNotEffective()

        last = _last_records(locked.application_id, locked.client_id, [definition]).get(
            definition.pk
        )
        if last is not None and last.action == action:
            return RecordedConsent(record=last, created=False)
        if action == ConsentAction.WITHDRAWN and last is None:
            raise ConsentNotAccepted()

        record = ConsentRecord.objects.create(
            consent_definition=definition,
            client_id=locked.client_id,
            application_id=locked.application_id,
            action=action,
            ip_address=client_ip(request),
            user_agent_summary=user_agent_summary(request),
            buyer_session=locked,
        )
    logger.info(
        "Consentimiento %s v%s %s en la sesión de comprador %s",
        definition.code,
        definition.version,
        action,
        locked.pk,
    )
    return RecordedConsent(record=record, created=True)


def application_consent_records(application: CreditApplication) -> QuerySet[ConsentRecord]:
    """Evidencias de la solicitud, de la más reciente a la más antigua."""
    return (
        ConsentRecord.objects.select_related("consent_definition", "client", "user")
        .filter(application=application)
        .order_by("-created_at")
    )
