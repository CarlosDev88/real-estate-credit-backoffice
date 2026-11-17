"""Etapas de avance de la solicitud: las del portal (``stages``) y las del expediente
interno (``progress_stages``).

Configuración fija en el código, como las pestañas rápidas: cada estado de
``ApplicationStatus`` tiene exactamente una regla en cada lista (lo verifica una prueba),
y las dos listas comparten la función y el tipo de respuesta.
"""

from dataclasses import dataclass
from enum import Enum

from django.db import models

from apps.catalogs.workflow import ApplicationStatus as S


class StageState(models.TextChoices):
    DONE = "done", "Listo"
    CURRENT = "current", "En curso"
    PENDING = "pending", "Pendiente"


class Rule(Enum):
    CURRENT = "current"  # La etapa indicada está en curso; las anteriores, listas.
    DONE_THROUGH = "done_through"  # Listas hasta la indicada (incluida); sin etapa en curso.
    ALL_DONE = "all_done"
    HIDDEN = "hidden"  # Lista vacía: el frontend oculta las etapas.


@dataclass(frozen=True)
class StageRule:
    kind: Rule
    stage: str | None = None


@dataclass(frozen=True)
class Stage:
    code: str
    label: str


@dataclass(frozen=True)
class StageTrack:
    stages: tuple[Stage, ...]
    rules: dict[str, StageRule]


def _current(stage: str) -> StageRule:
    return StageRule(Rule.CURRENT, stage)


_ALL_DONE = StageRule(Rule.ALL_DONE)
_HIDDEN = StageRule(Rule.HIDDEN)
_HIDDEN_STATUSES = (S.WITHDRAWN, S.CANCELLED, S.OWN_FUNDS, S.EXTERNAL_CREDIT_APPROVED)

# Portal del comprador (``BuyerApplicationDetail.stages``).
BUYER_STAGES = StageTrack(
    stages=(
        Stage("DATA", "Tus datos"),
        Stage("DOCUMENTS", "Documentos"),
        Stage("FILING", "Radicación en el banco"),
        Stage("BANK_RESPONSE", "Respuesta del banco"),
    ),
    rules={
        S.DRAFT: _current("DATA"),
        S.WAITING_BUYER_DATA: _current("DATA"),
        S.WAITING_DOCUMENTS: _current("DOCUMENTS"),
        S.DOCUMENTS_REVIEW: _current("DOCUMENTS"),
        S.BANK_OBSERVATION: _current("DOCUMENTS"),
        S.READY_TO_FILE: _current("FILING"),
        S.FILED: _current("FILING"),
        S.FILING_VALIDATION: _current("FILING"),
        S.CREDIT_ANALYSIS: _current("BANK_RESPONSE"),
        S.APPROVED: _current("BANK_RESPONSE"),
        S.LEGALIZATION: _current("BANK_RESPONSE"),
        S.REJECTED: _current("BANK_RESPONSE"),
        S.DISBURSED: _ALL_DONE,
        **{status: _HIDDEN for status in _HIDDEN_STATUSES},
    },
)

# Expediente interno (``ApplicationDetail.progress_stages``).
INTERNAL_STAGES = StageTrack(
    stages=(
        Stage("BUYER_DATA", "Datos del comprador"),
        Stage("DOCUMENT_UPLOAD", "Carga de documentos"),
        Stage("DOCUMENT_REVIEW", "Revisión documental"),
        Stage("READY_TO_FILE", "Lista para radicar"),
        Stage("FILED", "Radicada"),
        Stage("BANK_ANALYSIS", "Análisis del banco"),
        Stage("APPROVED", "Aprobada"),
        Stage("DISBURSED", "Desembolsada"),
    ),
    rules={
        S.DRAFT: _current("BUYER_DATA"),
        S.WAITING_BUYER_DATA: _current("BUYER_DATA"),
        S.WAITING_DOCUMENTS: _current("DOCUMENT_UPLOAD"),
        S.DOCUMENTS_REVIEW: _current("DOCUMENT_REVIEW"),
        S.READY_TO_FILE: _current("READY_TO_FILE"),
        S.FILED: _current("FILED"),
        S.FILING_VALIDATION: _current("FILED"),
        S.CREDIT_ANALYSIS: _current("BANK_ANALYSIS"),
        S.BANK_OBSERVATION: _current("BANK_ANALYSIS"),
        S.APPROVED: _current("APPROVED"),
        S.LEGALIZATION: _current("APPROVED"),
        S.REJECTED: StageRule(Rule.DONE_THROUGH, "BANK_ANALYSIS"),
        S.DISBURSED: _ALL_DONE,
        **{status: _HIDDEN for status in _HIDDEN_STATUSES},
    },
)


def progress_stages(track: StageTrack, status: str) -> list[dict[str, str]]:
    """Las etapas de ``track`` con su estado para la solicitud en ``status``."""
    rule = track.rules[status]
    if rule.kind == Rule.HIDDEN:
        return []
    codes = [stage.code for stage in track.stages]
    position = codes.index(rule.stage) if rule.stage is not None else len(codes)

    def state(index: int) -> StageState:
        if rule.kind == Rule.ALL_DONE or index < position:
            return StageState.DONE
        if index == position:
            return StageState.CURRENT if rule.kind == Rule.CURRENT else StageState.DONE
        return StageState.PENDING

    return [
        {
            "code": stage.code,
            "label": stage.label,
            "state": str(state(index)),
            "state_label": str(state(index).label),
        }
        for index, stage in enumerate(track.stages)
    ]
