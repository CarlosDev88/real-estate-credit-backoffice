"""Datos de demo para correr el proyecto en local (``seed_demo_data``).

Crea usuarios, clientes, oportunidades y unas 30 solicitudes repartidas entre las
pestañas ``draft``, ``waiting``, ``review`` y ``ready``, con perfiles financieros,
inmueble, financiación, documentos y revisiones. Todo pasa por los servicios del
dominio, para que el historial, los slots, la completitud guardada y las evaluaciones
queden como los dejaría un uso real. Solo se escribe una cosa por fuera de ellos:
la fecha de inicio de la etapa de una solicitud en `WAITING_BUYER_DATA` por asesor, que
se mueve al pasado para que muestre el aviso de inactividad del comprador (no hay forma
de "esperar" tres días).

- Solo con ``DEBUG``: lo exige el comando.
- Idempotente: los clientes de demo llevan un documento con ``DEMO_DOCUMENT_PREFIX``;
  si alguno existe, no se crea nada.
- No borra nada, nunca.
- Los archivos son PDF y PNG pequeños generados aquí, sin datos reales.
"""

import io
import logging
import struct
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

from django.db import transaction
from django.http import HttpRequest
from django.test import RequestFactory
from django.utils import timezone

from apps.applications import services
from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancialProfile,
    ParticipantRole,
)
from apps.banking.models import Bank, BankProduct
from apps.banking.services import create_product
from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, Opportunity
from apps.crm.services import assign_advisor, create_client, create_opportunity
from apps.documents.models import ApplicationDocumentSlot, ReviewDecision
from apps.documents.reviews import Review, review_slot
from apps.documents.scans import scan_document_file
from apps.documents.uploads import Upload, buyer_slots, upload_document
from apps.identity.buyer_access import default_channel, issue_access_link
from apps.identity.buyer_sessions import consume_access_link
from apps.identity.consents import missing_consents, record_consent
from apps.identity.models import BuyerSession, ConsentAction, Role, RoleCode, User, UserRole
from apps.identity.users import create_user

logger = logging.getLogger(__name__)

# Contraseña de todos los usuarios de demo. Solo para correr en local.
DEMO_PASSWORD = "DemoUmbral2026!"
DEMO_EMAIL_DOMAIN = "demo.local"
# Marca de los clientes de demo: ningún documento real de Colombia empieza así en esta base.
DEMO_DOCUMENT_PREFIX = "9900"
# Días que se mueve al pasado la etapa de la solicitud "inactiva" (el aviso salta a los 3).
INACTIVE_DAYS = 5
LINK_HOURS = 72


def demo_data_exists() -> bool:
    return Client.objects.filter(document_number__startswith=DEMO_DOCUMENT_PREFIX).exists()


# --------------------------------------------------------------------------------------
# Archivos de demo
# --------------------------------------------------------------------------------------


def demo_pdf(title: str) -> bytes:
    """PDF de una página con un título, con su tabla ``xref`` bien armada."""
    safe = "".join(ch for ch in title if ch.isascii() and ch not in "()\\")
    text = f"BT /F1 14 Tf 24 120 Td ({safe}) Tj 0 -24 Td (Documento de demo sin datos reales) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 420 200] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(text), text.encode("ascii")),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n%s\nendobj\n" % (number, body))
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    )
    return out.getvalue()


def demo_png(rgb: tuple[int, int, int] = (46, 92, 138), size: int = 16) -> bytes:
    """PNG de un solo color."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", crc)

    row = b"\x00" + bytes(rgb) * size
    header = struct.pack("!IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(row * size))
        + chunk(b"IEND", b"")
    )


# --------------------------------------------------------------------------------------
# Plan de la demo
# --------------------------------------------------------------------------------------

# Productos: los tres hipotecarios sembrados y dos de leasing que crea la demo. Solo
# el hipotecario de Bancolombia tiene requisitos documentales sembrados: las solicitudes
# en revisión o listas usan ese.
BANCOLOMBIA = "BANCOLOMBIA_MORTGAGE"
FNA = "FNA_MORTGAGE"
BOGOTA = "BANCO_BOGOTA_MORTGAGE"
BANCOLOMBIA_LEASING = "BANCOLOMBIA_LEASING"
BOGOTA_LEASING = "BANCO_BOGOTA_LEASING"
LEASING_CODE = "HOUSING_LEASING"
PRODUCT_KEYS: dict[str, tuple[str, str]] = {
    BANCOLOMBIA: ("BANCOLOMBIA", "MORTGAGE"),
    FNA: ("FNA", "MORTGAGE"),
    BOGOTA: ("BANCO_BOGOTA", "MORTGAGE"),
    BANCOLOMBIA_LEASING: ("BANCOLOMBIA", LEASING_CODE),
    BOGOTA_LEASING: ("BANCO_BOGOTA", LEASING_CODE),
}

EMPLOYEE = "EMPLOYEE"
INDEPENDENT = "INDEPENDENT"
PENSIONER = "PENSIONER"

# Qué documentos se cargan: ninguno, solo el documento de identidad, o todos.
NO_DOCUMENTS = "none"
SOME_DOCUMENTS = "some"
ALL_DOCUMENTS = "all"

# Camino de estados desde `DRAFT`, con el historial completo.
STATUS_PATH: dict[str, tuple[str, ...]] = {
    ApplicationStatus.DRAFT: (),
    ApplicationStatus.WAITING_BUYER_DATA: (ApplicationStatus.WAITING_BUYER_DATA,),
    ApplicationStatus.WAITING_DOCUMENTS: (
        ApplicationStatus.WAITING_BUYER_DATA,
        ApplicationStatus.WAITING_DOCUMENTS,
    ),
    ApplicationStatus.DOCUMENTS_REVIEW: (
        ApplicationStatus.WAITING_BUYER_DATA,
        ApplicationStatus.WAITING_DOCUMENTS,
        ApplicationStatus.DOCUMENTS_REVIEW,
    ),
    ApplicationStatus.READY_TO_FILE: (
        ApplicationStatus.WAITING_BUYER_DATA,
        ApplicationStatus.WAITING_DOCUMENTS,
        ApplicationStatus.DOCUMENTS_REVIEW,
        ApplicationStatus.READY_TO_FILE,
    ),
}


@dataclass(frozen=True)
class DemoCase:
    status: str
    purpose: str
    # Sin producto: la solicitud no tiene financiación ni inmueble (borrador recién creado).
    product: str | None
    # Sin perfil laboral: el titular todavía no tiene perfil financiero.
    employment: str | None
    extra_role: str | None = None
    origin: str = "DIRECT"
    documents: str = NO_DOCUMENTS
    approve: int = 0
    reject: int = 0
    # Todo aprobado y después un documento rechazado: `ready_to_file_blocked`.
    reject_after_ready: bool = False
    portal_link: bool = False


D, WB, WD, R, RF = (
    ApplicationStatus.DRAFT,
    ApplicationStatus.WAITING_BUYER_DATA,
    ApplicationStatus.WAITING_DOCUMENTS,
    ApplicationStatus.DOCUMENTS_REVIEW,
    ApplicationStatus.READY_TO_FILE,
)
NEW, USED, IMPROVEMENT = "PURCHASE_NEW", "PURCHASE_USED", "HOME_IMPROVEMENT"
CO, SOLIDARY = ParticipantRole.CO_APPLICANT, ParticipantRole.SOLIDARY_DEBTOR
MANY = 99  # "Todos los documentos cargados".

DEMO_CASES: tuple[DemoCase, ...] = (
    # Borradores.
    DemoCase(D, NEW, BANCOLOMBIA, EMPLOYEE),
    DemoCase(D, USED, FNA, INDEPENDENT, origin="REFERRAL"),
    DemoCase(D, IMPROVEMENT, BOGOTA, PENSIONER),
    DemoCase(D, NEW, BANCOLOMBIA_LEASING, EMPLOYEE, extra_role=CO),
    DemoCase(D, USED, None, None),
    DemoCase(D, NEW, BOGOTA_LEASING, EMPLOYEE),
    DemoCase(D, USED, None, None, origin="BROKER"),
    # Esperando al comprador.
    DemoCase(WB, NEW, BANCOLOMBIA, None),
    DemoCase(WB, USED, FNA, INDEPENDENT, extra_role=SOLIDARY),
    DemoCase(WB, NEW, BOGOTA_LEASING, None),
    DemoCase(WB, IMPROVEMENT, BANCOLOMBIA_LEASING, PENSIONER, origin="BROKER"),
    DemoCase(WD, NEW, BANCOLOMBIA, EMPLOYEE, portal_link=True),
    DemoCase(WD, USED, BANCOLOMBIA, INDEPENDENT, documents=SOME_DOCUMENTS),
    DemoCase(WD, NEW, FNA, EMPLOYEE, origin="REFERRAL"),
    DemoCase(WD, IMPROVEMENT, BOGOTA, PENSIONER, extra_role=CO),
    DemoCase(WD, NEW, BANCOLOMBIA, EMPLOYEE, documents=ALL_DOCUMENTS, reject=1),
    # En revisión: todo cargado, unos aprobados y uno rechazado.
    DemoCase(R, NEW, BANCOLOMBIA, EMPLOYEE, documents=ALL_DOCUMENTS, approve=2, reject=1),
    DemoCase(R, USED, BANCOLOMBIA, EMPLOYEE, extra_role=CO, documents=ALL_DOCUMENTS, approve=3),
    DemoCase(R, NEW, BANCOLOMBIA, INDEPENDENT, documents=ALL_DOCUMENTS),
    DemoCase(R, IMPROVEMENT, BANCOLOMBIA, PENSIONER, documents=ALL_DOCUMENTS, approve=4),
    DemoCase(
        R, NEW, BANCOLOMBIA, EMPLOYEE, extra_role=SOLIDARY, documents=ALL_DOCUMENTS, approve=1
    ),
    DemoCase(R, USED, BANCOLOMBIA, INDEPENDENT, origin="BROKER", documents=ALL_DOCUMENTS),
    DemoCase(R, NEW, BANCOLOMBIA, EMPLOYEE, documents=ALL_DOCUMENTS, approve=5),
    DemoCase(R, USED, BANCOLOMBIA, PENSIONER, origin="REFERRAL", documents=ALL_DOCUMENTS),
    # Listas para radicar: todo aprobado; la última, bloqueada después.
    DemoCase(RF, NEW, BANCOLOMBIA, EMPLOYEE, documents=ALL_DOCUMENTS, approve=MANY),
    DemoCase(RF, USED, BANCOLOMBIA, INDEPENDENT, documents=ALL_DOCUMENTS, approve=MANY),
    DemoCase(RF, IMPROVEMENT, BANCOLOMBIA, PENSIONER, documents=ALL_DOCUMENTS, approve=MANY),
    DemoCase(
        RF, NEW, BANCOLOMBIA, EMPLOYEE, origin="REFERRAL", documents=ALL_DOCUMENTS, approve=MANY
    ),
    DemoCase(RF, USED, BANCOLOMBIA, EMPLOYEE, documents=ALL_DOCUMENTS, approve=MANY),
    DemoCase(
        RF,
        NEW,
        BANCOLOMBIA,
        EMPLOYEE,
        documents=ALL_DOCUMENTS,
        approve=MANY,
        reject_after_ready=True,
    ),
)

# Nombres de los clientes de demo (titulares y participantes adicionales).
FIRST_NAMES = (
    "Laura", "Santiago", "Valentina", "Mateo", "Camila", "Sebastián", "Isabella", "Nicolás",
    "Mariana", "Samuel", "Daniela", "Alejandro", "Sofía", "Juan Pablo", "Gabriela",
    "Felipe", "Natalia", "Tomás", "Paula", "David", "Carolina", "Esteban", "Juliana",
    "Andrés", "Manuela", "Diego", "Luisa", "Simón", "Ana María", "Martín", "Catalina",
    "Emilio", "Verónica", "Julián", "Lorena", "Miguel",
)  # fmt: skip
LAST_NAMES = (
    "Gómez Vélez", "Restrepo Ochoa", "Martínez Duque", "Cárdenas Ríos", "Londoño Arango",
    "Herrera Salazar", "Quintero Mejía", "Rincón Castaño", "Valencia Torres", "Mora Giraldo",
    "Pineda Zapata", "Ospina Correa", "Suárez Lozano", "Jaramillo Henao", "Cifuentes Parra",
)  # fmt: skip
EMPLOYERS = (
    "Soluciones Andinas S.A.S.",
    "Grupo Cafetero S.A.",
    "Clínica del Norte",
    "Logística Caribe",
)
CITIES = ("11001", "05001", "76001", "08001")
STREETS = ("Calle 93 # 14-20", "Carrera 43A # 1-50", "Avenida 6N # 23-61", "Calle 84 # 51B-30")


@dataclass(frozen=True)
class DemoUser:
    email: str
    first_name: str
    last_name: str
    phone: str
    role: str


DEMO_USERS: tuple[DemoUser, ...] = (
    DemoUser(f"admin@{DEMO_EMAIL_DOMAIN}", "Adriana", "Mejía", "+573005550100", RoleCode.ADMIN),
    DemoUser(
        f"asesora.lucia@{DEMO_EMAIL_DOMAIN}", "Lucía", "Rojas", "+573005550101", RoleCode.ADVISOR
    ),
    # Sin teléfono: el portal muestra el asesor sin el botón de WhatsApp.
    DemoUser(f"asesor.andres@{DEMO_EMAIL_DOMAIN}", "Andrés", "Patiño", "", RoleCode.ADVISOR),
    DemoUser(
        f"broker@{DEMO_EMAIL_DOMAIN}",
        "Camilo",
        "Ortiz",
        "+573005550103",
        RoleCode.INDEPENDENT_BROKER,
    ),
)


@dataclass
class DemoResult:
    users: list[DemoUser]
    applications: list[CreditApplication] = field(default_factory=list)
    portal_url: str = ""
    portal_application_code: str = ""


# --------------------------------------------------------------------------------------
# Ejecución
# --------------------------------------------------------------------------------------


def _item(catalog_code: str, code: str) -> CatalogItem:
    return CatalogItem.objects.get(catalog__code=catalog_code, code=code)


def _request() -> HttpRequest:
    """Petición de mentira para los servicios que registran IP y navegador."""
    return RequestFactory().post("/", REMOTE_ADDR="127.0.0.1", HTTP_USER_AGENT="seed_demo_data")


def _fresh(application: CreditApplication) -> CreditApplication:
    return CreditApplication.objects.select_related("purpose_item", "bank_product").get(
        pk=application.pk
    )


def _ensure_user(spec: DemoUser, actor: User | None) -> User:
    """Crea el usuario con la contraseña de demo; si ya existe (una corrida que falló a
    medias), lo reutiliza tal cual."""
    existing = User.objects.filter(email=spec.email).first()
    if existing is not None:
        return existing
    role = Role.objects.get(code=spec.role)
    if actor is None:
        # El primer administrador no tiene quién lo cree: igual que el usuario de prueba del
        # README.
        user = User.objects.create_user(
            spec.email,
            DEMO_PASSWORD,
            first_name=spec.first_name,
            last_name=spec.last_name,
            phone=spec.phone,
        )
        UserRole.objects.create(user=user, role=role)
        return user
    user, _ = create_user(
        actor=actor,
        email=spec.email,
        first_name=spec.first_name,
        last_name=spec.last_name,
        phone=spec.phone,
        roles=[role],
        partner=None,
        send_invitation=False,
    )
    user.set_password(DEMO_PASSWORD)
    user.save(update_fields=["password", "updated_at"])
    return user


def _ensure_leasing_products() -> None:
    """Leasing habitacional en Bancolombia y Banco de Bogotá, si no existen."""
    product_type = _item("bank_product_type", LEASING_CODE)
    purposes = list(CatalogItem.objects.filter(catalog__code="loan_purpose"))
    for bank_code, code in (PRODUCT_KEYS[BANCOLOMBIA_LEASING], PRODUCT_KEYS[BOGOTA_LEASING]):
        bank = Bank.objects.get(code=bank_code)
        if BankProduct.objects.filter(bank=bank, code=code).exists():
            continue
        create_product(
            {
                "bank": bank,
                "code": code,
                "name": "Leasing habitacional",
                "product_type_item": product_type,
                "valid_from": date(2026, 1, 1),
                "purposes": purposes,
            }
        )


def _product(key: str) -> BankProduct:
    bank_code, code = PRODUCT_KEYS[key]
    return BankProduct.objects.select_related("bank").get(bank__code=bank_code, code=code)


class _Names:
    """Nombres y documentos consecutivos para los clientes de demo."""

    def __init__(self) -> None:
        self.number = 0

    def next(self) -> dict[str, Any]:
        self.number += 1
        first = FIRST_NAMES[(self.number - 1) % len(FIRST_NAMES)]
        last = LAST_NAMES[(self.number * 7) % len(LAST_NAMES)]
        slug = f"{first}.{last.split()[0]}".lower()
        slug = slug.translate(str.maketrans("áéíóúñ ", "aeioun_"))
        return {
            "document_type_item": _item("identity_document_type", "CC"),
            "document_number": f"{DEMO_DOCUMENT_PREFIX}{self.number:06d}",
            "first_names": first,
            "last_names": last,
            "email": f"{slug}.{self.number}@{DEMO_EMAIL_DOMAIN}",
            "phone": f"+57301555{self.number:04d}",
            "birth_date": date(1980 + self.number % 15, 1 + self.number % 12, 1 + self.number % 27),
        }


def _profile_values(employment: str, index: int) -> dict[str, Any]:
    income = 3_500_000 + (index % 9) * 1_000_000
    contract = {EMPLOYEE: "INDEFINITE", INDEPENDENT: "SERVICES", PENSIONER: None}[employment]
    funds = {EMPLOYEE: "SALARY", INDEPENDENT: "INDEPENDENT_ACTIVITY", PENSIONER: "PENSION"}
    return {
        "employment_profile_item": _item("employment_profile", employment),
        "contract_type_item": _item("contract_type", contract) if contract else None,
        "employer_name": EMPLOYERS[index % len(EMPLOYERS)] if employment == EMPLOYEE else "",
        "job_title": {EMPLOYEE: "Analista", INDEPENDENT: "Consultor", PENSIONER: ""}[employment],
        "employment_start_date": date(2015 + index % 8, 3, 1) if employment != PENSIONER else None,
        "monthly_income_cop": income,
        "monthly_expenses_cop": income // 3,
        "assets_cop": 40_000_000 + index * 5_000_000,
        "liabilities_cop": 5_000_000 + (index % 4) * 3_000_000,
        "funds_origin_item": _item("funds_origin", funds[employment]),
    }


def _add_profile(
    actor: User,
    application: CreditApplication,
    participant: ApplicationParticipant,
    *,
    employment: str,
    index: int,
) -> None:
    values = _profile_values(employment, index)
    services.put_financial_profile(
        actor, participant, expected_version=_fresh(application).version, values=values
    )
    profile = FinancialProfile.objects.select_related("participant").get(participant=participant)
    source = {EMPLOYEE: "SALARY", INDEPENDENT: "INDEPENDENT_ACTIVITY", PENSIONER: "PENSION"}
    services.add_income_source(
        actor,
        profile,
        {
            "source_type_item": _item("income_source_type", source[employment]),
            "payer_name": values["employer_name"] or "Colpensiones",
            "monthly_amount_cop": values["monthly_income_cop"],
            "start_date": values["employment_start_date"],
            "is_primary": True,
            "notes": "",
        },
    )


def _add_property_and_financing(
    actor: User, application: CreditApplication, case: DemoCase, index: int
) -> None:
    assert case.product is not None
    value = 180_000_000 + (index % 10) * 45_000_000
    condition = {NEW: "NEW", USED: "USED", IMPROVEMENT: "USED"}[case.purpose]
    services.put_property(
        actor,
        application,
        expected_version=_fresh(application).version,
        values={
            "project": None,
            "property_type_item": _item("property_type", "APARTMENT" if index % 3 else "HOUSE"),
            "condition_item": _item("property_condition", condition),
            "city_item": _item("municipality", CITIES[index % len(CITIES)]),
            "address": STREETS[index % len(STREETS)],
            "unit_reference": f"Apto {200 + index}" if index % 3 else "",
            "estimated_value_cop": value,
            "is_owned_by_applicant": True if case.purpose == IMPROVEMENT else None,
            "ownership_notes": "",
        },
    )
    leasing = case.product in (BANCOLOMBIA_LEASING, BOGOTA_LEASING)
    services.put_financing(
        actor,
        application,
        expected_version=_fresh(application).version,
        values={
            "financing_mode_item": _item("financing_mode", "BANK_CREDIT"),
            "requested_amount_cop": value * 7 // 10,
            "term_months": 180 + (index % 3) * 60,
            "currency_mode_item": _item("currency_mode", "UVR" if index % 4 == 0 else "COP"),
            "amortization_mode_item": _item(
                "amortization_mode", "FIXED_PRINCIPAL" if leasing else "FIXED_PAYMENT"
            ),
            "own_resources_cop": value * 3 // 10,
            "uses_severance_funds": index % 2 == 0,
            "severance_funds_cop": 8_000_000 if index % 2 == 0 else 0,
            "external_approved_amount_cop": None,
        },
        product=_product(case.product),
    )


def _open_buyer_session(actor: User, application: CreditApplication) -> BuyerSession:
    """Emite un enlace, lo consume como lo haría el comprador y acepta los consentimientos."""
    issued = issue_access_link(
        actor, application, channel=default_channel(), expires_in_hours=LINK_HOURS
    )
    token = parse_qs(urlparse(issued.url).query)["token"][0]
    request = _request()
    session = consume_access_link(request=request, raw_token=token).session
    for definition in missing_consents(session):
        record_consent(
            request=request, session=session, definition=definition, action=ConsentAction.ACCEPTED
        )
    return session


def _slots_to_upload(session: BuyerSession, documents: str) -> list[ApplicationDocumentSlot]:
    """Los slots que carga el comprador. En un grupo alternativo, solo el primer tipo."""
    slots = list(
        buyer_slots(session)
        .select_related("document_type")
        .order_by("participant__created_at", "sort_order", "slot_index")
    )
    if documents == SOME_DOCUMENTS:
        return [slot for slot in slots if slot.document_type.code == "IDENTITY_DOCUMENT"][:1]
    chosen: dict[tuple[Any, str], str] = {}
    result = []
    for slot in slots:
        group = slot.alternative_group_code
        if group:
            key = (slot.participant_id, group)
            if chosen.setdefault(key, slot.document_type.code) != slot.document_type.code:
                continue
        result.append(slot)
    return result


def _upload(session: BuyerSession, slot: ApplicationDocumentSlot, index: int) -> None:
    code = slot.document_type.code
    as_image = code == "IDENTITY_DOCUMENT"
    content = demo_png() if as_image else demo_pdf(f"{code} {slot.slot_index}")
    extension = "png" if as_image else "pdf"
    # Fecha reciente: los documentos con vigencia (30 días) siguen vigentes.
    document_date = timezone.localdate() - timedelta(days=3 + index % 10)
    version = upload_document(
        session,
        slot,
        Upload(
            stream=io.BytesIO(content),
            filename=f"{code.lower()}_{slot.slot_index}.{extension}",
            declared_mime_type="image/png" if as_image else "application/pdf",
            document_date=document_date,
        ),
    )
    # El análisis corre después del commit; aquí se corre ya, para revisar enseguida. Es
    # idempotente: el que se encoló al confirmar no hace nada.
    scan_document_file(version.file_object_id)


def _review(actor: User, slot_id: Any, decision: str, reason: str = "") -> None:
    slot = ApplicationDocumentSlot.objects.select_related("document_type").get(pk=slot_id)
    if decision == ReviewDecision.APPROVED:
        review = Review(decision=decision, document_file_id=slot.current_file_id)
    else:
        review = Review(
            decision=decision,
            document_file_id=slot.current_file_id,
            reason_item=_item("document_rejection_reason", reason),
            buyer_comment="El documento no se lee completo. Cárgalo de nuevo, por favor.",
            internal_comment="Rechazo de demo.",
        )
    review_slot(actor, slot, review)


def _transition(actor: User, application: CreditApplication, to_status: str) -> None:
    services.transition_application(
        actor, application, to_status=to_status, expected_version=_fresh(application).version
    )


def _build_case(
    case: DemoCase,
    index: int,
    *,
    advisor: User,
    admin: User,
    broker: User,
    names: _Names,
) -> CreditApplication:
    origin_actor = broker if case.origin == "BROKER" else advisor
    client = create_client(origin_actor, names.next())
    opportunity: Opportunity = create_opportunity(
        origin_actor, client=client, project=None, origin_item=_item("lead_origin", case.origin)
    )
    opportunity = assign_advisor(admin, opportunity, advisor=advisor)
    application = services.create_application(
        advisor, opportunity=opportunity, purpose=_item("loan_purpose", case.purpose)
    )
    primary = application.participants.get(role=ParticipantRole.PRIMARY)

    if case.product is not None:
        _add_property_and_financing(advisor, application, case, index)
    if case.employment is not None:
        _add_profile(advisor, application, primary, employment=case.employment, index=index)
    if case.extra_role is not None:
        extra = services.add_participant(
            advisor, application, role=case.extra_role, client_data=names.next()
        )
        _add_profile(advisor, application, extra, employment=EMPLOYEE, index=index + 3)

    path = STATUS_PATH[case.status]
    for step in path[:2]:
        _transition(advisor, application, step)

    if case.documents != NO_DOCUMENTS:
        session = _open_buyer_session(advisor, _fresh(application))
        uploaded = [slot.pk for slot in _slots_to_upload(session, case.documents)]
        slots = buyer_slots(session).select_related("document_type")
        for position, slot_id in enumerate(uploaded):
            _upload(session, slots.get(pk=slot_id), position)
        if len(path) > 2:
            _transition(advisor, application, path[2])
        approved = uploaded[: case.approve]
        rejected = uploaded[len(approved) : len(approved) + case.reject]
        for slot_id in approved:
            _review(advisor, slot_id, ReviewDecision.APPROVED)
        for slot_id in rejected:
            _review(advisor, slot_id, ReviewDecision.REJECTED, reason="ILLEGIBLE")
        for step in path[3:]:
            _transition(advisor, application, step)
        if case.reject_after_ready:
            # Ya lista, el asesor rechaza un documento aprobado: queda bloqueada.
            _review(advisor, uploaded[-1], ReviewDecision.REJECTED, reason="OUTDATED")

    if case.product is not None:
        # Cada cambio de estado sube la versión: el asesor vuelve a evaluar las reglas para
        # que la última evaluación corresponda a los datos actuales.
        services.evaluate_application(advisor, _fresh(application))

    return _fresh(application)


def _mark_buyer_inactive(application: CreditApplication) -> None:
    """Lo único que no pasa por un servicio: la etapa empezó hace días y el comprador
    nunca entró, para que la lista muestre el aviso de inactividad (``buyer_inactive``)."""
    CreditApplication.objects.filter(pk=application.pk).update(
        current_stage_started_at=timezone.now() - timedelta(days=INACTIVE_DAYS)
    )


def _round_robin(advisors: list[User]) -> Iterator[User]:
    while True:
        yield from advisors


def seed_demo_data(*, extra_advisor: User | None = None) -> DemoResult:
    """Crea los datos de demo. Quien llama comprueba ``DEBUG`` y ``demo_data_exists``.

    No corre en una sola transacción: el análisis de los archivos y la completitud
    guardada se ejecutan al confirmar cada operación, como en un uso real.
    """
    with transaction.atomic():
        admin = _ensure_user(DEMO_USERS[0], actor=None)
        users = {spec.email: _ensure_user(spec, actor=admin) for spec in DEMO_USERS[1:]}
    advisors = [users[DEMO_USERS[1].email], users[DEMO_USERS[2].email]]
    if extra_advisor is not None:
        advisors.append(extra_advisor)
    broker = users[DEMO_USERS[3].email]
    _ensure_leasing_products()

    result = DemoResult(users=list(DEMO_USERS))
    names = _Names()
    assignments = _round_robin(advisors)
    portal: tuple[User, CreditApplication] | None = None
    # Cada asesor ve al menos una solicitud inactiva en su pestaña `waiting`: la primera
    # suya en `WAITING_BUYER_DATA` (el comprador nunca entró, porque esos casos no cargan).
    with_inactive: set[Any] = set()
    for index, case in enumerate(DEMO_CASES):
        advisor = next(assignments)
        application = _build_case(
            case, index, advisor=advisor, admin=admin, broker=broker, names=names
        )
        if case.status == WB and advisor.pk not in with_inactive:
            _mark_buyer_inactive(application)
            with_inactive.add(advisor.pk)
        result.applications.append(application)
        if case.portal_link:
            portal = (advisor, application)

    # Al final, para que ninguna otra emisión lo revoque.
    assert portal is not None
    issued = issue_access_link(
        portal[0], portal[1], channel=default_channel(), expires_in_hours=LINK_HOURS
    )
    result.portal_url = issued.url
    result.portal_application_code = portal[1].code
    logger.info("Datos de demo creados: %s solicitudes", len(result.applications))
    return result
