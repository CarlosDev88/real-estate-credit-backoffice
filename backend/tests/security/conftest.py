"""Mundo de la matriz de acceso (``specs/TAREA-seguridad.md``, Parte 3.2).

Un "mundo" con dos de cada cosa, una del lado A y otra del lado B, creado **una sola vez
por paquete** (``tests/security``) y revertido al final:

- Lado A: asesora ``asesora.lucia``, broker ``broker`` (originó la oportunidad), el
  comprador A con su sesión. Lado B: asesor ``asesor.andres``, broker ``broker.b`` y el
  comprador B.
- Por lado, dos solicitudes armadas con los servicios del dominio (los mismos
  constructores de ``seed_demo_data``): ``application`` (radicada y ``APPROVED``, con
  participantes, perfil, ingresos, inmueble, financiación, slots con archivos, paquete,
  radicación, respuestas con evidencia, notificaciones, tareas, notas, enlace pendiente y
  sesión del comprador con consentimientos) y ``disbursed`` (``DISBURSED``, liquidada
  sola por el plan de comisión, con sus partes).
- Globales: planes de comisión, regla de banco, catálogo, tipos y requisitos
  documentales, transición de flujo, invitación, exportación de reportes, dos
  constructoras con un proyecto activo cada una (la del actor ``partner`` es la del lado A)
  y un usuario "objetivo" para las rutas ``/users/{user_id}``.

Cómo se aísla: el mundo vive dentro de una transacción externa marcada como de pruebas
(``_from_testcase``, como las de ``TestCase``: así la auditoría se comporta como en
producción). Cada prueba abre su propio punto de guardado (``pytest.mark.django_db``) y
se revierte; al terminar el paquete, se revierte todo el mundo. Los fixtures de
``tests/applications`` son de alcance de función (un mundo por caso no entra en el
presupuesto de 3 minutos del CI): por eso aquí se usan los constructores de la demo.
"""

import io
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth.hashers import make_password
from django.db import connections, transaction
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.applications import services as application_services
from apps.applications.demo_data import (
    ALL_DOCUMENTS,
    BANCOLOMBIA,
    CO,
    DEMO_PASSWORD,
    DEMO_USERS,
    EMPLOYEE,
    MANY,
    NEW,
    RF,
    DemoCase,
    DemoUser,
    _build_case,
    _ensure_leasing_products,
    _ensure_user,
    _fresh,
    _item,
    _Names,
    demo_pdf,
)
from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancialProfile,
    IncomeSource,
)
from apps.audit.models import AuditEvent
from apps.banking.models import Bank, BankPolicyRule, BankProduct
from apps.catalogs.models import Catalog, CatalogItem, WorkflowTransition
from apps.catalogs.workflow import ApplicationStatus, ProjectStatus
from apps.commissions.demo_data import seed_plans
from apps.commissions.models import CommissionPlan, CommissionSettlement, CommissionShare
from apps.crm.models import Client, ClientAddress, Opportunity
from apps.crm.services import add_address
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentPackageJob,
    DocumentRequirement,
    DocumentType,
)
from apps.documents.storage import MemoryStorage, get_storage
from apps.filings import responses
from apps.filings.demo_data import (
    FILED_DEMO_CASES,
    FiledCase,
    _completed_package,
    _file_and_respond,
)
from apps.filings.evidence import attach_evidence
from apps.filings.models import Filing, FilingResponse
from apps.identity import services as identity_services
from apps.identity.buyer_access import default_channel, issue_access_link
from apps.identity.buyer_sessions import consume_access_link
from apps.identity.consents import missing_consents, record_consent
from apps.identity.invitations import create_invitation
from apps.identity.models import (
    BuyerAccessLink,
    BuyerSession,
    ConsentAction,
    InternalInvitation,
    Role,
    RoleCode,
    User,
)
from apps.identity.users import create_user
from apps.notifications.models import Notification
from apps.partners.models import Partner, PartnerMembership, Project
from apps.partners.services import create_partner, create_project, transition_project
from apps.partners.validators import nit_check_digit
from apps.reporting.export_jobs import request_export
from apps.reporting.filters import ReportFilters
from apps.reporting.models import ReportExportJob
from apps.tasks.demo_data import seed_tasks
from apps.tasks.models import Task
from tests.banking.conftest import MAX_LTV_CONDITION

# Actores de la matriz (spec §3.1). Los internos inician sesión con la contraseña de demo.
ANON = "anon"
ADMIN = "admin"
ADVISOR_OWNER = "advisor_owner"
ADVISOR_OTHER = "advisor_other"
BROKER_OWNER = "broker_owner"
BROKER_OTHER = "broker_other"
PARTNER = "partner"
BUYER_OWNER = "buyer_owner"
BUYER_OTHER = "buyer_other"
ACTORS = (
    ANON,
    ADMIN,
    ADVISOR_OWNER,
    ADVISOR_OTHER,
    BROKER_OWNER,
    BROKER_OTHER,
    PARTNER,
    BUYER_OWNER,
    BUYER_OTHER,
)
INTERNAL_ACTORS = (ADMIN, ADVISOR_OWNER, ADVISOR_OTHER, BROKER_OWNER, BROKER_OTHER, PARTNER)
BUYER_ACTORS = (BUYER_OWNER, BUYER_OTHER)

BROKER_B = DemoUser("broker.b@demo.local", "Bruno", "Segundo", "", RoleCode.INDEPENDENT_BROKER)
PARTNER_EMAIL = "constructora@demo.local"
TARGET_EMAIL = "objetivo@demo.local"

# Las dos solicitudes de cada lado: la del portal (aprobada) y la desembolsada.
PORTAL_CASE = FiledCase(
    DemoCase(
        RF,
        NEW,
        BANCOLOMBIA,
        EMPLOYEE,
        extra_role=CO,
        origin="BROKER",
        documents=ALL_DOCUMENTS,
        approve=MANY,
    ),
    channel="IN_PERSON",
    responses=FILED_DEMO_CASES[2].responses,  # RECEIVED, IN_ANALYSIS, APPROVED
)
DRAFT_CASE = DemoCase(ApplicationStatus.DRAFT, NEW, BANCOLOMBIA, EMPLOYEE, origin="BROKER")
DISBURSED_CASE = FiledCase(PORTAL_CASE.case, channel="BANK_PORTAL", responses=PORTAL_CASE.responses)


@dataclass
class Side:
    """Lo de un lado (A o B)."""

    advisor: User
    broker: User
    application: CreditApplication
    disbursed: CreditApplication
    draft: CreditApplication
    ready: CreditApplication
    ready_package: DocumentPackageJob
    client: Client
    opportunity: Opportunity
    participant: ApplicationParticipant
    profile: FinancialProfile
    income_source: IncomeSource
    slot: ApplicationDocumentSlot
    file: DocumentFile
    package_job: DocumentPackageJob
    filing: Filing
    response: FilingResponse
    notification: Notification
    task: Task
    address: ClientAddress
    pending_link: BuyerAccessLink
    buyer_session: BuyerSession
    buyer_token: str
    settlement: CommissionSettlement
    share: CommissionShare


@dataclass
class World:
    a: Side
    b: Side
    admin: User
    partner_user: User
    target_user: User
    partner_a: Partner
    partner_b: Partner
    project_a: Project
    project_b: Project
    membership: PartnerMembership
    plan: CommissionPlan
    bank: Bank
    product: BankProduct
    rule: BankPolicyRule
    catalog: Catalog
    catalog_item: CatalogItem
    document_type: DocumentType
    requirement: DocumentRequirement
    transition: WorkflowTransition
    invitation: InternalInvitation
    export_job: ReportExportJob
    audit_event: AuditEvent
    # Token de acceso (JWT) de cada actor interno y token de sesión de cada comprador.
    access_tokens: dict[str, str] = field(default_factory=dict)
    users: dict[str, User] = field(default_factory=dict)

    def path_ids(self) -> dict[str, str]:
        """Parámetros de ruta: siempre los ids del lado A (spec §3.2)."""
        a = self.a
        return {
            "application_id": str(a.application.pk),
            "participant_id": str(a.participant.pk),
            "profile_id": str(a.profile.pk),
            "income_source_id": str(a.income_source.pk),
            "slot_id": str(a.slot.pk),
            "file_id": str(a.file.pk),
            "filing_id": str(a.filing.pk),
            "response_id": str(a.response.pk),
            "notification_id": str(a.notification.pk),
            "task_id": str(a.task.pk),
            "client_id": str(a.client.pk),
            "opportunity_id": str(a.opportunity.pk),
            "address_id": str(a.address.pk),
            "link_id": str(a.pending_link.pk),
            "settlement_id": str(a.settlement.pk),
            "share_id": str(a.share.pk),
            "user_id": str(self.target_user.pk),
            "partner_id": str(self.partner_a.pk),
            "project_id": str(self.project_a.pk),
            "membership_id": str(self.membership.pk),
            "plan_id": str(self.plan.pk),
            "bank_id": str(self.bank.pk),
            "product_id": str(self.product.pk),
            "rule_id": str(self.rule.pk),
            "catalog_id": str(self.catalog.pk),
            # Un catálogo pequeño que el portal también entrega (`BUYER_CATALOG_CODES`).
            "catalog_code": "contract_type",
            "item_id": str(self.catalog_item.pk),
            "document_type_id": str(self.document_type.pk),
            "requirement_id": str(self.requirement.pk),
            "transition_id": str(self.transition.pk),
            "invitation_id": str(self.invitation.pk),
            "event_id": str(self.audit_event.pk),
            # `job_id` depende de la ruta: paquete documental o exportación de reportes.
            "package_job_id": str(a.package_job.pk),
            "export_job_id": str(self.export_job.pk),
        }


def _request() -> Any:
    return RequestFactory().post("/", REMOTE_ADDR="127.0.0.1", HTTP_USER_AGENT="tests/security")


class _SideNames(_Names):
    """Nombres de la demo con documentos y correos propios de cada lado."""

    def __init__(self, prefix: str) -> None:
        super().__init__()
        self.prefix = prefix

    def next(self) -> dict[str, Any]:
        data = super().next()
        data["document_number"] = f"{self.prefix}{self.number:06d}"
        data["email"] = f"comprador.{self.prefix}.{self.number}@example.com"
        return data


def _internal_user(admin: User, email: str, role: str, partner: Partner | None) -> User:
    user, _ = create_user(
        actor=admin,
        email=email,
        first_name="Usuario",
        last_name=role.title(),
        phone="",
        roles=[Role.objects.get(code=role)],
        partner=partner,
        send_invitation=False,
    )
    user.password = make_password(DEMO_PASSWORD)
    user.save(update_fields=["password", "updated_at"])
    return user


def _partner(admin: User, number: str, name: str) -> tuple[Partner, Project]:
    partner = create_partner({"legal_name": name, "tax_id": f"{number}-{nit_check_digit(number)}"})
    project = create_project(
        admin,
        {
            "partner_id": partner.pk,
            "name": f"Proyecto {name}",
            "city_item": _item("municipality", "11001"),
            "address": "Calle 100 # 10-10",
        },
    )
    project = transition_project(admin, project, to_status=ProjectStatus.PENDING_REVIEW)
    project = transition_project(admin, project, to_status=ProjectStatus.ACTIVE)
    return partner, project


def _buyer_session(advisor: User, application: CreditApplication) -> tuple[BuyerSession, str]:
    issued = issue_access_link(advisor, application, channel=default_channel(), expires_in_hours=72)
    token = issued.url.split("token=", 1)[1]
    opened = consume_access_link(request=_request(), raw_token=token)
    for definition in missing_consents(opened.session):
        record_consent(
            request=_request(),
            session=opened.session,
            definition=definition,
            action=ConsentAction.ACCEPTED,
        )
    return opened.session, opened.token


def _disburse(advisor: User, application: CreditApplication) -> CreditApplication:
    application_services.transition_application(
        advisor,
        _fresh(application),
        to_status=ApplicationStatus.LEGALIZATION,
        expected_version=_fresh(application).version,
    )
    filing = Filing.objects.filter(application=application).latest("filed_at")
    responses.record_response(
        advisor,
        filing,
        responses.ResponseInput(
            response_type=_item(responses.RESPONSE_TYPE_CATALOG, responses.DISBURSED),
            received_at=timezone.now(),
            disbursed_amount_cop=200_000_000,
        ),
        expected_version=_fresh(application).version,
    )
    return _fresh(application)


def _build_side(prefix: str, *, advisor: User, broker: User, admin: User, first_index: int) -> Side:
    names = _SideNames(prefix)
    filed_at = timezone.now() - timedelta(days=6)
    application = _build_case(
        PORTAL_CASE.case, first_index, advisor=advisor, admin=admin, broker=broker, names=names
    )
    application = _file_and_respond(advisor, application, PORTAL_CASE, filed_at=filed_at)
    disbursed = _build_case(
        DISBURSED_CASE.case,
        first_index + 1,
        advisor=advisor,
        admin=admin,
        broker=broker,
        names=names,
    )
    disbursed = _file_and_respond(advisor, disbursed, DISBURSED_CASE, filed_at=filed_at)
    disbursed = _disburse(advisor, disbursed)
    # Borrador con inmueble y financiación: las escrituras de los casos explícitos (ids
    # ajenos en el cuerpo) no se frenan por el estado de la solicitud.
    draft = _build_case(
        DRAFT_CASE, first_index + 2, advisor=advisor, admin=admin, broker=broker, names=names
    )
    # Lista para radicar, con su paquete armado y sin radicar: para radicar y revisar en
    # los casos explícitos.
    ready = _build_case(
        PORTAL_CASE.case, first_index + 3, advisor=advisor, admin=admin, broker=broker, names=names
    )
    ready_package = _completed_package(advisor, ready)

    filing = Filing.objects.filter(application=application).latest("filed_at")
    response = FilingResponse.objects.filter(filing=filing).order_by("received_at").first()
    assert response is not None
    attach_evidence(
        advisor,
        response,
        stream=io.BytesIO(demo_pdf("Evidencia")),
        filename="evidencia.pdf",
        declared_mime_type="application/pdf",
    )
    session, token = _buyer_session(advisor, application)
    pending = issue_access_link(
        advisor, application, channel=default_channel(), expires_in_hours=24
    )
    tasks = seed_tasks(advisor, [application])
    participant = application.participants.get(role="PRIMARY")
    profile = FinancialProfile.objects.get(participant=participant)
    slot = (
        ApplicationDocumentSlot.objects.filter(application=application, current_file__isnull=False)
        .order_by("sort_order", "slot_index")
        .first()
    )
    assert slot is not None and slot.current_file is not None
    client = application.opportunity.client
    address = add_address(
        client,
        {
            "address_type_item": CatalogItem.objects.filter(catalog__code="address_type").first(),
            "city_item": _item("municipality", "11001"),
            "line1": "Carrera 7 # 71-21",
        },
    )
    settlement = CommissionSettlement.objects.get(application=disbursed)
    return Side(
        advisor=advisor,
        broker=broker,
        application=_fresh(application),
        disbursed=disbursed,
        draft=_fresh(draft),
        ready=_fresh(ready),
        ready_package=ready_package,
        client=client,
        opportunity=application.opportunity,
        participant=participant,
        profile=profile,
        income_source=IncomeSource.objects.filter(financial_profile=profile).first(),  # type: ignore[arg-type]
        slot=slot,
        file=slot.current_file,
        package_job=DocumentPackageJob.objects.filter(application=application).latest("created_at"),
        filing=filing,
        response=response,
        notification=Notification.objects.filter(application=application).latest("created_at"),
        task=tasks[0],
        address=address,
        pending_link=BuyerAccessLink.objects.get(pk=pending.link.pk),
        buyer_session=session,
        buyer_token=token,
        settlement=settlement,
        share=settlement.shares.order_by("created_at").first(),  # type: ignore[arg-type]
    )


def build_world() -> World:
    admin = _ensure_user(DEMO_USERS[0], actor=None)
    lucia = _ensure_user(DEMO_USERS[1], actor=admin)
    andres = _ensure_user(DEMO_USERS[2], actor=admin)
    broker_a = _ensure_user(DEMO_USERS[3], actor=admin)
    broker_b = _ensure_user(BROKER_B, actor=admin)
    _ensure_leasing_products()
    plans = seed_plans(admin)

    partner_a, project_a = _partner(admin, "990100001", "Constructora Lado A")
    partner_b, project_b = _partner(admin, "990100002", "Constructora Lado B")
    partner_user = _internal_user(admin, PARTNER_EMAIL, RoleCode.CONSTRUCTION_PARTNER, partner_a)
    target_user = _internal_user(admin, TARGET_EMAIL, RoleCode.ADVISOR, None)

    side_a = _build_side("9910", advisor=lucia, broker=broker_a, admin=admin, first_index=0)
    side_b = _build_side("9920", advisor=andres, broker=broker_b, admin=admin, first_index=5)

    product = BankProduct.objects.select_related("bank").get(
        bank__code="BANCOLOMBIA", code="MORTGAGE"
    )
    rule = BankPolicyRule.objects.create(
        bank_product=product,
        code="SEC_MAX_LTV",
        version=1,
        severity="BLOCKING",
        condition=MAX_LTV_CONDITION,
        message="El monto no puede superar el 70% del valor del inmueble.",
        valid_from=timezone.now(),
        created_by=admin,
    )
    catalog = Catalog.objects.get(code="lead_origin")
    invitation = create_invitation(
        email="invitada@example.com",
        role=Role.objects.get(code=RoleCode.ADVISOR),
        partner=None,
        invited_by=admin,
    )
    today = timezone.localdate()
    export_job = request_export(
        lucia, ReportFilters(date_from=today - timedelta(days=30), date_to=today)
    )
    audit_event = AuditEvent.objects.order_by("created_at").first()
    assert audit_event is not None, "la construcción del mundo no dejó eventos de auditoría"

    world = World(
        a=side_a,
        b=side_b,
        admin=admin,
        partner_user=partner_user,
        target_user=target_user,
        partner_a=partner_a,
        partner_b=partner_b,
        project_a=project_a,
        project_b=project_b,
        membership=PartnerMembership.objects.get(user=partner_user),
        plan=plans[0],
        bank=product.bank,
        product=product,
        rule=rule,
        catalog=catalog,
        catalog_item=catalog.items.order_by("sort_order").first(),  # type: ignore[arg-type]
        document_type=DocumentType.objects.order_by("code").first(),  # type: ignore[arg-type]
        requirement=DocumentRequirement.objects.order_by("created_at").first(),  # type: ignore[arg-type]
        transition=WorkflowTransition.objects.order_by("code").first(),  # type: ignore[arg-type]
        invitation=invitation,
        export_job=export_job,
        audit_event=audit_event,
    )
    world.users = {
        ADMIN: admin,
        ADVISOR_OWNER: lucia,
        ADVISOR_OTHER: andres,
        BROKER_OWNER: broker_a,
        BROKER_OTHER: broker_b,
        PARTNER: partner_user,
    }
    for actor, user in world.users.items():
        _, issued = identity_services.login(
            request=_request(), email=user.email, password=DEMO_PASSWORD
        )
        world.access_tokens[actor] = issued.access_token
    return world


@pytest.fixture(scope="package")
def world(django_db_setup: Any, django_db_blocker: Any) -> Iterator[World]:
    with django_db_blocker.unblock():
        outer = transaction.atomic(using="default")
        outer._from_testcase = True  # type: ignore[attr-defined]
        outer.__enter__()
        try:
            with TestCase.captureOnCommitCallbacks(execute=True):
                built = build_world()
            # Las llaves foráneas diferidas del mundo se verifican una vez aquí; si no,
            # ``TestCase`` las vuelve a revisar al cerrar cada caso (~40 ms cada uno).
            connections["default"].check_constraints()
            yield built
        finally:
            transaction.set_rollback(True, using="default")
            outer.__exit__(None, None, None)
            storage = get_storage()
            if isinstance(storage, MemoryStorage):
                storage.clear()


@pytest.fixture(autouse=True)
def _clear_document_storage() -> Iterator[None]:
    """Reemplaza el del ``conftest`` raíz: los archivos del mundo viven todo el paquete y
    se borran al final (fixture ``world``)."""
    yield


__all__ = ["World", "Side", "build_world", "uuid"]
