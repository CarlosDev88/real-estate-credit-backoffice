"""Etapas de avance: ``stages`` del portal y ``progress_stages`` del expediente interno."""

from collections.abc import Callable

import pytest
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.applications.stages import BUYER_STAGES, INTERNAL_STAGES, StageTrack, progress_stages
from apps.catalogs.workflow import ApplicationStatus as S
from apps.catalogs.workflow import OpportunityStatus
from apps.crm.models import Client, Opportunity
from apps.identity.models import User
from tests.applications.conftest import application_url, catalog_item

D, C, P = "done", "current", "pending"
HIDDEN = (S.WITHDRAWN, S.CANCELLED, S.OWN_FUNDS, S.EXTERNAL_CREDIT_APPROVED)


def states(track: StageTrack, status: str) -> list[str]:
    return [stage["state"] for stage in progress_stages(track, status)]


@pytest.mark.parametrize("track", [BUYER_STAGES, INTERNAL_STAGES])
def test_every_application_status_has_a_rule(track: StageTrack) -> None:
    assert set(track.rules) == set(S.values)
    codes = [stage.code for stage in track.stages]
    assert all(rule.stage in (None, *codes) for rule in track.rules.values())


def test_buyer_stages_are_the_four_fixed_ones() -> None:
    stages = progress_stages(BUYER_STAGES, S.WAITING_DOCUMENTS)
    assert [(stage["code"], stage["label"]) for stage in stages] == [
        ("DATA", "Tus datos"),
        ("DOCUMENTS", "Documentos"),
        ("FILING", "Radicación en el banco"),
        ("BANK_RESPONSE", "Respuesta del banco"),
    ]
    assert [stage["state_label"] for stage in stages] == [
        "Listo",
        "En curso",
        "Pendiente",
        "Pendiente",
    ]


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((S.DRAFT, S.WAITING_BUYER_DATA), [C, P, P, P]),
        ((S.WAITING_DOCUMENTS, S.DOCUMENTS_REVIEW, S.BANK_OBSERVATION), [D, C, P, P]),
        ((S.READY_TO_FILE, S.FILED, S.FILING_VALIDATION), [D, D, C, P]),
        ((S.CREDIT_ANALYSIS, S.APPROVED, S.LEGALIZATION, S.REJECTED), [D, D, D, C]),
        ((S.DISBURSED,), [D, D, D, D]),
        (HIDDEN, []),
    ],
)
def test_buyer_stage_states_by_status(statuses: tuple[str, ...], expected: list[str]) -> None:
    for status in statuses:
        assert states(BUYER_STAGES, status) == expected, status


def test_internal_stages_are_the_eight_fixed_ones() -> None:
    stages = progress_stages(INTERNAL_STAGES, S.DRAFT)
    assert [(stage["code"], stage["label"]) for stage in stages] == [
        ("BUYER_DATA", "Datos del comprador"),
        ("DOCUMENT_UPLOAD", "Carga de documentos"),
        ("DOCUMENT_REVIEW", "Revisión documental"),
        ("READY_TO_FILE", "Lista para radicar"),
        ("FILED", "Radicada"),
        ("BANK_ANALYSIS", "Análisis del banco"),
        ("APPROVED", "Aprobada"),
        ("DISBURSED", "Desembolsada"),
    ]


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((S.DRAFT, S.WAITING_BUYER_DATA), [C, P, P, P, P, P, P, P]),
        ((S.WAITING_DOCUMENTS,), [D, C, P, P, P, P, P, P]),
        ((S.DOCUMENTS_REVIEW,), [D, D, C, P, P, P, P, P]),
        ((S.READY_TO_FILE,), [D, D, D, C, P, P, P, P]),
        ((S.FILED, S.FILING_VALIDATION), [D, D, D, D, C, P, P, P]),
        ((S.CREDIT_ANALYSIS, S.BANK_OBSERVATION), [D, D, D, D, D, C, P, P]),
        ((S.APPROVED, S.LEGALIZATION), [D, D, D, D, D, D, C, P]),
        ((S.REJECTED,), [D, D, D, D, D, D, P, P]),
        ((S.DISBURSED,), [D, D, D, D, D, D, D, D]),
        (HIDDEN, []),
    ],
)
def test_internal_stage_states_by_status(statuses: tuple[str, ...], expected: list[str]) -> None:
    for status in statuses:
        assert states(INTERNAL_STAGES, status) == expected, status


@pytest.mark.django_db
def test_the_internal_detail_has_progress_stages(
    admin_client: APIClient, application: CreditApplication
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(status=S.DOCUMENTS_REVIEW)

    body = admin_client.get(application_url(application)).json()

    assert body["progress_stages"] == progress_stages(INTERNAL_STAGES, S.DOCUMENTS_REVIEW)
    assert body["progress_stages"][2] == {
        "code": "DOCUMENT_REVIEW",
        "label": "Revisión documental",
        "state": "current",
        "state_label": "En curso",
    }


@pytest.mark.django_db
def test_the_broker_summary_gets_nothing_new(
    broker_client: APIClient,
    broker_user: User,
    make_application: Callable[..., CreditApplication],
    buyer: Client,
) -> None:
    opportunity = Opportunity.objects.create(
        client=buyer,
        origin_item=catalog_item("lead_origin", "BROKER"),
        origin_user=broker_user,
        status=OpportunityStatus.ASSIGNED,
    )
    application = make_application(opportunity)

    body = broker_client.get(application_url(application)).json()

    assert body["id"] == str(application.pk)
    assert not {"progress_stages", "stages", "advisor"} & set(body)
