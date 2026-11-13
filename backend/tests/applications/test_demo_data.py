"""Comando ``seed_demo_data``: datos de demo para correr en local."""

import io
from collections.abc import Callable
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from rest_framework.test import APIClient

from apps.applications.demo_data import (
    DEMO_CASES,
    DEMO_DOCUMENT_PREFIX,
    DEMO_PASSWORD,
    DEMO_USERS,
    demo_pdf,
    demo_png,
)
from apps.applications.management.commands.seed_demo_data import EXISTS_MESSAGE
from apps.applications.models import ApplicationStatusHistory, CreditApplication
from apps.crm.models import Client
from apps.documents.file_validation import detect_mime_type
from apps.documents.models import DocumentFile, DocumentReview, ReviewDecision, SlotStatus
from apps.identity.models import BuyerAccessLink, User
from tests.applications.conftest import APPLICATIONS_URL
from tests.helpers import login

pytestmark = pytest.mark.django_db

E2E_EMAIL = "asesor.e2e@example.com"


def seed(**options: Any) -> str:
    out = io.StringIO()
    with override_settings(DEBUG=True):
        call_command("seed_demo_data", stdout=out, **options)
    return out.getvalue()


def demo_client(email: str) -> APIClient:
    client = APIClient()
    assert login(client, email=email, password=DEMO_PASSWORD).status_code == 200
    return client


def counts() -> dict[str, int]:
    return {
        "users": User.objects.count(),
        "clients": Client.objects.count(),
        "applications": CreditApplication.objects.count(),
        "history": ApplicationStatusHistory.objects.count(),
        "files": DocumentFile.objects.count(),
        "links": BuyerAccessLink.objects.count(),
    }


@pytest.fixture
def e2e_advisor(make_user: Callable[..., User]) -> User:
    return make_user(email=E2E_EMAIL, role_code="ADVISOR")


def test_seed_creates_the_demo_data(e2e_advisor: User) -> None:
    output = seed(advisor_email=E2E_EMAIL)

    assert CreditApplication.objects.count() == len(DEMO_CASES) == 30
    assert "http://localhost:3000/acceso?token=" in output
    for spec in DEMO_USERS:
        assert spec.email in output
        assert User.objects.get(email=spec.email).check_password(DEMO_PASSWORD)
    assert Client.objects.exclude(document_number__startswith=DEMO_DOCUMENT_PREFIX).count() == 0
    # El asesor existente también recibe solicitudes.
    assert CreditApplication.objects.filter(assigned_advisor=e2e_advisor).exists()
    # Titulares y participantes adicionales de los dos papeles.
    roles = set(CreditApplication.objects.values_list("participants__role", flat=True).distinct())
    assert roles == {"PRIMARY", "CO_APPLICANT", "SOLIDARY_DEBTOR"}
    # Bancos y tipos de producto variados.
    products = set(
        CreditApplication.objects.filter(bank_product__isnull=False).values_list(
            "bank_product__bank__code", "bank_product__product_type_item__code"
        )
    )
    assert {bank for bank, _ in products} == {"BANCOLOMBIA", "FNA", "BANCO_BOGOTA"}
    assert {kind for _, kind in products} == {"MORTGAGE", "HOUSING_LEASING"}
    # Revisiones: aprobadas y rechazadas; el historial parte siempre de `DRAFT`.
    decisions = set(DocumentReview.objects.values_list("decision", flat=True))
    assert {ReviewDecision.APPROVED, ReviewDecision.REJECTED} <= decisions
    assert ApplicationStatusHistory.objects.filter(from_status__isnull=True).count() == 30
    # Un solo enlace pendiente: el que imprime el comando.
    pending = BuyerAccessLink.objects.filter(consumed_at__isnull=True, revoked_at__isnull=True)
    assert pending.count() == 1

    # Conteos por pestaña y avisos del listado (en la misma prueba: sembrar es lento).
    admin = demo_client(DEMO_USERS[0].email)

    response = admin.get(f"{APPLICATIONS_URL}/quick-filters")
    assert response.status_code == 200
    tabs = {row["code"]: row["count"] for row in response.json()}
    for code in ("draft", "waiting", "review", "ready"):
        assert tabs[code] > 0, tabs
    assert tabs["all"] == 30

    def rows(quick_filter: str, client: APIClient = admin) -> list[dict[str, Any]]:
        params = {"quick_filter": quick_filter, "page_size": "50"}
        return list(client.get(APPLICATIONS_URL, params).json()["items"])

    assert any(row["ready_to_file_blocked"] is True for row in rows("ready"))
    assert any(row["ready_to_file_blocked"] is False for row in rows("ready"))
    # Las que siguen listas tienen la evaluación bancaria al día: completitud de 100.
    assert {
        row["completeness_pct"] for row in rows("ready") if not row["ready_to_file_blocked"]
    } == {100}
    waiting = rows("waiting")
    assert any(row["buyer_inactive"] is True for row in waiting)
    assert any(row["buyer_inactive"] is False for row in waiting)
    # Cada asesor, con su propia sesión, ve al menos una inactiva en su pestaña `waiting`.
    advisors = [demo_client(DEMO_USERS[1].email), demo_client(DEMO_USERS[2].email)]
    e2e = APIClient()
    assert login(e2e, email=E2E_EMAIL).status_code == 200
    for advisor in [*advisors, e2e]:
        assert any(row["buyer_inactive"] is True for row in rows("waiting", advisor))
    review = CreditApplication.objects.filter(status="DOCUMENTS_REVIEW")
    slot_statuses = set(review.values_list("document_slots__status", flat=True))
    assert {SlotStatus.UPLOADED, SlotStatus.APPROVED, SlotStatus.REJECTED} <= slot_statuses
    # El broker ve las solicitudes que originó.
    broker = demo_client(DEMO_USERS[3].email)
    assert broker.get(APPLICATIONS_URL).json()["items"]


def test_second_run_creates_nothing(e2e_advisor: User) -> None:
    seed()
    before = counts()

    output = seed(advisor_email=E2E_EMAIL)

    assert EXISTS_MESSAGE in output
    assert counts() == before


def test_without_debug_it_fails_without_writing() -> None:
    before = counts()
    with override_settings(DEBUG=False), pytest.raises(CommandError, match="DEBUG"):
        call_command("seed_demo_data", stdout=io.StringIO())
    assert counts() == before


@pytest.mark.parametrize("role_code", [None, "INDEPENDENT_BROKER"])
def test_extra_advisor_must_be_an_existing_advisor(
    make_user: Callable[..., User], role_code: str | None
) -> None:
    if role_code is not None:
        make_user(email=E2E_EMAIL, role_code=role_code)
    before = counts()
    with pytest.raises(CommandError, match=E2E_EMAIL):
        seed(advisor_email=E2E_EMAIL)
    assert counts() == before


def test_demo_files_are_valid_pdf_and_png() -> None:
    pdf = demo_pdf("Cédula (frente)")
    assert detect_mime_type(pdf) == "application/pdf"
    assert pdf.rstrip().endswith(b"%%EOF")
    assert b"startxref" in pdf
    assert detect_mime_type(demo_png()) == "image/png"
