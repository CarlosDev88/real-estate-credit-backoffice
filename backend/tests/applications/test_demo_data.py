"""Comando ``seed_demo_data``: datos de demo para correr en local (TAREA-brechas-3-demo).

Sembrar es lento (un par de minutos), así que una sola prueba siembra **dos veces** y
verifica todo: que cada estado de la lista de la spec existe al menos una vez, que las
fechas van hacia atrás y son coherentes, la demo base de siempre, la salida del comando y
que la segunda corrida dice "ya existían" en todos los bloques sin cambiar ningún conteo.

En las pruebas la transacción nunca confirma; para sembrar como en local (donde cada
``on_commit`` corre al confirmar), aquí corre en el acto.
"""

import io
import re
from collections.abc import Callable, Iterator
from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest import mock

import pytest
from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Count, Q
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.activity.models import ActivityEventType, ActivityLog
from apps.applications.demo_data import (
    DEMO_CASES,
    DEMO_DOCUMENT_PREFIX,
    DEMO_PASSWORD,
    DEMO_USERS,
    demo_pdf,
    demo_png,
)
from apps.applications.demo_history import HISTORY_CASES, HISTORY_DOCUMENT_PREFIX
from apps.applications.management.commands.seed_demo_data import EXISTED
from apps.applications.models import ApplicationStatusHistory, CreditApplication
from apps.audit.actions import AuditAction
from apps.audit.demo_data import REQUEST_ID_PREFIX
from apps.audit.models import AuditEvent
from apps.banking.demo_data import TERM_RULE
from apps.banking.models import BankPolicyRule, BankProduct
from apps.catalogs.workflow import ApplicationStatus, OpportunityStatus, ProjectStatus
from apps.commissions.models import CommissionPlan, CommissionSettlement, CommissionShare
from apps.crm.models import Client, Opportunity
from apps.documents.file_validation import detect_mime_type
from apps.documents.models import DocumentReview, ReviewDecision, SlotStatus
from apps.filings.demo_data import FILED_DEMO_CASES, FILED_DEMO_STATUSES
from apps.filings.models import Filing, FilingResponse, FilingResponseObservation, FilingStatus
from apps.filings.serializers import FilingSerializer
from apps.identity.demo_data import INACTIVE_EMAIL
from apps.identity.models import BuyerAccessLink, InternalInvitation, User
from apps.notifications.models import DeliveryStatus, Notification, NotificationDelivery
from apps.partners.demo_data import PARTNER_EMAIL
from apps.partners.models import PartnerMembership, Project
from apps.reporting.models import ReportExportJob
from apps.tasks.demo_data import DEMO_TASKS
from apps.tasks.models import Task, TaskStatus
from tests.applications.conftest import APPLICATIONS_URL
from tests.helpers import login

pytestmark = pytest.mark.django_db

E2E_EMAIL = "asesor.e2e@example.com"
BASE_APPLICATIONS = len(DEMO_CASES) + len(FILED_DEMO_CASES)
TOTAL_APPLICATIONS = BASE_APPLICATIONS + len(HISTORY_CASES)


@pytest.fixture
def immediate_on_commit() -> Iterator[None]:
    with mock.patch("django.db.transaction.on_commit", lambda func, *a, **k: func()):
        yield


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
        model._meta.db_table: model._default_manager.count()
        for model in apps.get_models()
        if model.__module__.startswith("apps.")
    }


def values(queryset: Any, field: str) -> set[Any]:
    return set(queryset.values_list(field, flat=True))


@pytest.fixture
def e2e_advisor(make_user: Callable[..., User]) -> User:
    return make_user(email=E2E_EMAIL, role_code="ADVISOR")


def test_the_seed_creates_every_state_once_and_twice_changes_nothing(
    e2e_advisor: User, immediate_on_commit: None
) -> None:
    output = seed(advisor_email=E2E_EMAIL)

    check_output(output)
    check_users()
    check_applications()
    check_filings()
    check_commissions()
    check_crm_partners_and_invitations()
    check_tasks_notes_and_notifications(e2e_advisor)
    check_exports_rules_and_audit()
    check_base_demo(e2e_advisor)

    before = counts()
    again = seed(advisor_email=E2E_EMAIL)

    lines = again.split("Usuarios por rol")[0].splitlines()[1:]
    blocks = [line for line in lines if line.strip()]
    assert len(blocks) == 16
    assert all(line.rstrip().endswith(EXISTED) for line in blocks), blocks
    assert "ya hay un enlace sin usar" in again
    assert counts() == before


def check_output(output: str) -> None:
    summary, rest = output.split("Usuarios por rol")
    assert "Bloques de la demo:" in summary
    assert "creados (" in summary
    assert DEMO_PASSWORD in rest
    for email in [*(spec.email for spec in DEMO_USERS), PARTNER_EMAIL, INACTIVE_EMAIL]:
        assert email in rest
    code = re.search(r"Portal del comprador \((SOL-\d+)\), un solo uso:", rest)
    assert code is not None
    assert "http://localhost:3000/acceso?token=" in rest
    portal = CreditApplication.objects.get(code=code.group(1))
    pending = BuyerAccessLink.objects.filter(consumed_at__isnull=True, revoked_at__isnull=True)
    assert list(pending.values_list("application_id", flat=True)) == [portal.pk]


def check_users() -> None:
    # Un usuario por cada uno de los 5 roles (más el inactivo), todos con la contraseña.
    for email in [*(spec.email for spec in DEMO_USERS), PARTNER_EMAIL]:
        client = demo_client(email)
        assert client.get("/api/v1/auth/me").status_code == 200
    roles = values(
        User.objects.filter(email__endswith="@demo.local"), "user_role_assignments__role__code"
    )
    assert roles == {"ADMIN", "ADVISOR", "INDEPENDENT_BROKER", "CONSTRUCTION_PARTNER"}
    inactive = User.objects.get(email=INACTIVE_EMAIL)
    assert inactive.status == "INACTIVE"
    assert login(APIClient(), email=INACTIVE_EMAIL, password=DEMO_PASSWORD).status_code == 403
    partner_user = User.objects.get(email=PARTNER_EMAIL)
    membership = PartnerMembership.objects.get(user=partner_user)
    assert membership.partner.projects.filter(status=ProjectStatus.ACTIVE).exists()


def check_applications() -> None:
    applications = CreditApplication.objects.all()
    assert applications.count() == TOTAL_APPLICATIONS >= 60
    # Todos los estados del flujo.
    assert values(applications, "status") == set(ApplicationStatus.values)
    # Seis meses de historia: al menos una solicitud creada en cada uno.
    now = timezone.now()
    for month in range(6):
        window = Q(created_at__lte=now - timedelta(days=30 * month)) & Q(
            created_at__gt=now - timedelta(days=30 * (month + 1))
        )
        assert applications.filter(window).exists(), month
    # Nada en el futuro, y el historial empieza cuando se creó la solicitud.
    assert not ApplicationStatusHistory.objects.filter(created_at__gt=now).exists()
    for application in applications.filter(
        opportunity__client__document_number__startswith=HISTORY_DOCUMENT_PREFIX
    ):
        history = list(application.status_history.order_by("created_at"))
        assert history[0].from_status is None
        assert abs(history[0].created_at - application.created_at) < timedelta(minutes=1)
        assert application.current_stage_started_at <= now
    # Repartidas entre los dos asesores de demo, con el broker originando una parte.
    advisors = values(applications, "assigned_advisor__email")
    assert {DEMO_USERS[1].email, DEMO_USERS[2].email} <= advisors
    broker = User.objects.get(email=DEMO_USERS[3].email)
    assert applications.filter(opportunity__origin_user=broker).count() >= 8


def check_filings() -> None:
    responses = FilingResponse.objects.all()
    assert values(responses, "response_type_item__code") >= {
        "RECEIVED",
        "IN_ANALYSIS",
        "RETURNED",
        "APPROVED",
        "REJECTED",
        "DISBURSED",
    }
    # Un desembolso nunca antes de su radicación; ninguna respuesta antes de radicar.
    for response in responses.select_related("filing"):
        assert response.received_at >= response.filing.filed_at
    for settlement in CommissionSettlement.objects.select_related("filing_response__filing"):
        assert settlement.created_at >= settlement.filing_response.filing.filed_at
    # Devuelta y corregida: segunda radicación y la observación resuelta.
    refiled = Filing.objects.filter(sequence_number=2)
    assert refiled.exists()
    assert FilingResponseObservation.objects.filter(
        resolved_at__isnull=False, document_slot__application__filings__sequence_number=2
    ).exists()
    # Una vencida sin respuesta y otra todavía en plazo.
    overdue = [
        FilingSerializer(filing).data["is_response_overdue"]
        for filing in Filing.objects.filter(responses__isnull=True)
    ]
    assert True in overdue and False in overdue


def check_commissions() -> None:
    settlements = CommissionSettlement.objects.all()
    assert values(settlements, "status") == {"ACTIVE", "VOIDED"}
    assert settlements.filter(needs_review=True).exists()
    shares = CommissionShare.objects.all()
    assert values(shares, "status") == {"PENDING", "PAID", "VOIDED"}
    # Con broker (70/30) y directas (100 %), al menos una con una sola parte pagada.
    assert values(shares, "share_pct") == {
        Decimal("70.0000"),
        Decimal("30.0000"),
        Decimal("100.0000"),
    }
    partly_paid = settlements.annotate(
        paid=Count("shares", filter=Q(shares__status="PAID")), total=Count("shares")
    ).filter(paid=1, total=2)
    assert partly_paid.exists()


def check_crm_partners_and_invitations() -> None:
    assert values(Opportunity.objects.all(), "status") == set(OpportunityStatus.values)
    assert Opportunity.objects.filter(status="LOST", lost_reason_item__isnull=False).exists()
    assert values(Project.objects.all(), "status") == set(ProjectStatus.values)
    statuses = {invitation.status for invitation in InternalInvitation.objects.all()}
    assert statuses == {"PENDING", "ACCEPTED", "EXPIRED", "REVOKED"}
    assert User.objects.get(email="asesora.invitada@demo.local").check_password(DEMO_PASSWORD)


def check_tasks_notes_and_notifications(e2e_advisor: User) -> None:
    now = timezone.now()
    today = timezone.localdate()
    for spec in DEMO_USERS[1:3]:
        tasks = Task.objects.filter(assigned_to__email=spec.email)
        pending = tasks.filter(status=TaskStatus.PENDING)
        assert pending.filter(due_at__lt=now).exclude(due_at__date=today).exists()
        assert pending.filter(due_at__date=today).exists()
        assert pending.filter(due_at__date__gt=today).exists()
        assert values(tasks, "status") == set(TaskStatus.values)
    notes = ActivityLog.objects.filter(event_type=ActivityEventType.NOTE_ADDED)
    assert notes.filter(application__isnull=False).exists()
    assert notes.filter(application__isnull=True, opportunity__isnull=False).exists()
    assert notes.filter(application__isnull=True, opportunity__isnull=True).exists()
    notifications = Notification.objects.filter(client__isnull=False)
    assert notifications.filter(read_at__isnull=False).exists()
    assert notifications.filter(read_at__isnull=True).exists()
    deliveries = NotificationDelivery.objects.all()
    assert deliveries.filter(status=DeliveryStatus.SENT).exists()
    assert deliveries.filter(status=DeliveryStatus.FAILED).exists()
    retry = deliveries.filter(status=DeliveryStatus.PENDING, attempt_count__gte=1)
    assert retry.filter(next_attempt_at__gt=now, last_error_code__isnull=False).exists()


def check_exports_rules_and_audit() -> None:
    assert values(ReportExportJob.objects.all(), "status") == {"COMPLETED", "EXPIRED"}
    family = BankPolicyRule.objects.filter(code=TERM_RULE).order_by("version")
    assert list(family.values_list("version", "status")) == [
        (1, "INACTIVE"),
        (2, "ACTIVE"),
        (3, "DRAFT"),
    ]
    demo = AuditEvent.objects.filter(request_id__startswith=REQUEST_ID_PREFIX)
    assert values(demo, "action") == {
        AuditAction.AUTH_LOGIN,
        AuditAction.AUTH_LOGIN_FAILED,
        AuditAction.ACCESS_DENIED,
        AuditAction.DOCUMENT_DOWNLOADED,
        AuditAction.REPORT_EXPORTED,
    }
    # Con fechas de las últimas semanas, no de la siembra.
    assert demo.filter(created_at__lt=timezone.now() - timedelta(days=1)).count() >= 10


def check_base_demo(e2e_advisor: User) -> None:
    """La demo de siempre (30 en las pestañas y 4 radicadas) sigue igual."""
    base = CreditApplication.objects.filter(
        opportunity__client__document_number__startswith=DEMO_DOCUMENT_PREFIX
    )
    assert base.count() == BASE_APPLICATIONS == 34
    assert CreditApplication.objects.filter(assigned_advisor=e2e_advisor).exists()
    roles = set(base.values_list("participants__role", flat=True).distinct())
    assert roles == {"PRIMARY", "CO_APPLICANT", "SOLIDARY_DEBTOR"}
    products = set(
        base.filter(bank_product__isnull=False).values_list(
            "bank_product__bank__code", "bank_product__product_type_item__code"
        )
    )
    assert {bank for bank, _ in products} == {"BANCOLOMBIA", "FNA", "BANCO_BOGOTA"}
    assert {kind for _, kind in products} == {"MORTGAGE", "HOUSING_LEASING"}
    decisions = set(DocumentReview.objects.values_list("decision", flat=True))
    assert {ReviewDecision.APPROVED, ReviewDecision.REJECTED} <= decisions
    assert (
        Client.objects.exclude(
            Q(document_number__startswith=DEMO_DOCUMENT_PREFIX)
            | Q(document_number__startswith=HISTORY_DOCUMENT_PREFIX)
            | Q(document_number__startswith="9902")
        ).count()
        == 0
    )

    # Las 4 radicadas de la demo base, con su estado y sus respuestas.
    filings = list(
        Filing.objects.filter(
            application__opportunity__client__document_number__startswith=DEMO_DOCUMENT_PREFIX
        ).order_by("created_at")
    )
    assert [filing.application.status for filing in filings] == list(FILED_DEMO_STATUSES)
    assert [filing.status for filing in filings] == [
        FilingStatus.IN_ANALYSIS,
        FilingStatus.RETURNED,
        FilingStatus.APPROVED,
        FilingStatus.DISBURSED,
    ]
    for filing, filed in zip(filings, FILED_DEMO_CASES, strict=True):
        codes = filing.responses.order_by("received_at").values_list(
            "response_type_item__code", flat=True
        )
        assert list(codes) == list(filed.responses)

    # Pestañas, avisos del listado y tareas del asesor e2e (paso 12), como siempre.
    admin = demo_client(DEMO_USERS[0].email)
    tabs = {
        row["code"]: row["count"] for row in admin.get(f"{APPLICATIONS_URL}/quick-filters").json()
    }
    for code in ("draft", "waiting", "review", "ready", "bank", "closed"):
        assert tabs[code] > 0, tabs
    assert tabs["all"] == TOTAL_APPLICATIONS

    def rows(quick_filter: str, client: APIClient = admin) -> list[dict[str, Any]]:
        params = {"quick_filter": quick_filter, "page_size": "100"}
        return list(client.get(APPLICATIONS_URL, params).json()["items"])

    assert any(row["ready_to_file_blocked"] is True for row in rows("ready"))
    assert any(row["ready_to_file_blocked"] is False for row in rows("ready"))
    waiting = rows("waiting")
    assert any(row["buyer_inactive"] is True for row in waiting)
    assert any(row["buyer_inactive"] is False for row in waiting)
    review = base.filter(status="DOCUMENTS_REVIEW")
    slot_statuses = set(review.values_list("document_slots__status", flat=True))
    assert {SlotStatus.UPLOADED, SlotStatus.APPROVED, SlotStatus.REJECTED} <= slot_statuses
    broker = demo_client(DEMO_USERS[3].email)
    assert broker.get(APPLICATIONS_URL).json()["items"]
    assert Task.objects.filter(assigned_to=e2e_advisor).count() == len(DEMO_TASKS) == 8
    e2e = APIClient()
    assert login(e2e, email=E2E_EMAIL).status_code == 200
    due = {
        window: e2e.get("/api/v1/tasks", {"due": window}).json()["total"]
        for window in ("overdue", "today", "upcoming")
    }
    assert due == {"overdue": 2, "today": 2, "upcoming": 3}
    notes = ActivityLog.objects.filter(
        event_type=ActivityEventType.NOTE_ADDED, actor_user=e2e_advisor
    )
    assert notes.count() == 2
    created = ActivityLog.objects.filter(event_type=ActivityEventType.APPLICATION_CREATED)
    assert created.count() == TOTAL_APPLICATIONS
    # Un plan de demo por producto (1 %, 70/30).
    plans = CommissionPlan.objects.all()
    assert plans.count() == BankProduct.objects.count()
    assert set(plans.values_list("rate_pct", "advisor_share_pct", "broker_share_pct")) == {
        (Decimal("1.0000"), Decimal("70.0000"), Decimal("30.0000"))
    }


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
