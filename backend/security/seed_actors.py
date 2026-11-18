"""Actores extra para la auditoría de seguridad (``specs/TAREA-seguridad.md``, §3.5).

Completa los datos de ``seed_demo_data`` con los actores que faltan para la matriz de
acceso, todos con la contraseña de demo:

- ``broker.b@demo.local``: segundo broker, con una oportunidad propia.
- ``constructora@demo.local``: ``CONSTRUCTION_PARTNER``, miembro de una constructora con
  un proyecto activo.
- Un segundo comprador con su solicitud asignada a ``asesor.andres@demo.local`` (en
  ``WAITING_DOCUMENTS``, con un documento cargado), para probar comprador A contra B.

Uso (después de ``seed_demo_data``, con ``DEBUG=True``)::

    python manage.py shell -c "exec(open('security/seed_actors.py').read())"

- Solo con ``DEBUG``, igual que ``seed_demo_data``.
- Idempotente: si el cliente del segundo comprador ya existe, no crea nada.
- Imprime solo correos y códigos de solicitud. Nunca tokens ni URL.
"""

from typing import Any

from django.conf import settings
from django.db import transaction

from apps.applications.demo_data import (
    DEMO_EMAIL_DOMAIN,
    DEMO_PASSWORD,
    DEMO_USERS,
    SOME_DOCUMENTS,
    WD,
    DemoCase,
    _build_case,
    _item,
    _Names,
)
from apps.catalogs.workflow import ProjectStatus
from apps.crm.services import assign_advisor, create_client, create_opportunity
from apps.identity.models import Role, RoleCode, User
from apps.identity.users import create_user
from apps.partners.models import Partner, Project
from apps.partners.services import create_partner, create_project, transition_project
from apps.partners.validators import nit_check_digit

# Marca de los clientes de los actores extra: distinta de la de la demo (``9900``).
SECURITY_DOCUMENT_PREFIX = "9901"
BROKER_B_EMAIL = f"broker.b@{DEMO_EMAIL_DOMAIN}"
PARTNER_EMAIL = f"constructora@{DEMO_EMAIL_DOMAIN}"
PARTNER_NIT_NUMBER = "990100001"
PROJECT_NAME = "Torres de Auditoría"
BUYER_B_CASE = DemoCase(
    WD, "PURCHASE_NEW", "BANCOLOMBIA_MORTGAGE", "EMPLOYEE", documents=SOME_DOCUMENTS
)


class _SecurityNames(_Names):
    """Como los nombres de la demo, con otro prefijo de documento y otro correo."""

    def next(self) -> dict[str, Any]:
        data = super().next()
        data["document_number"] = f"{SECURITY_DOCUMENT_PREFIX}{self.number:06d}"
        data["email"] = f"comprador.seg.{self.number}@{DEMO_EMAIL_DOMAIN}"
        data["phone"] = f"+57302555{self.number:04d}"
        return data


def _user(email: str) -> User:
    return User.objects.get(email=email)


def _ensure_internal_user(
    *, admin: User, email: str, first_name: str, last_name: str, role: str, partner: Partner | None
) -> User:
    existing = User.objects.filter(email=email).first()
    if existing is not None:
        return existing
    user, _ = create_user(
        actor=admin,
        email=email,
        first_name=first_name,
        last_name=last_name,
        phone="",
        roles=[Role.objects.get(code=role)],
        partner=partner,
        send_invitation=False,
    )
    user.set_password(DEMO_PASSWORD)
    user.save(update_fields=["password", "updated_at"])
    return user


def _ensure_partner() -> Partner:
    tax_id = f"{PARTNER_NIT_NUMBER}-{nit_check_digit(PARTNER_NIT_NUMBER)}"
    existing = Partner.objects.filter(tax_id=tax_id).first()
    if existing is not None:
        return existing
    return create_partner(
        {
            "legal_name": "Constructora Auditoría S.A.S.",
            "trade_name": "Constructora Auditoría",
            "tax_id": tax_id,
            "contact_name": "Contacto de auditoría",
            "contact_email": PARTNER_EMAIL,
        }
    )


def _ensure_active_project(admin: User, partner: Partner) -> Project:
    project = Project.objects.filter(partner=partner, name=PROJECT_NAME).first()
    if project is None:
        project = create_project(
            admin,
            {
                "partner_id": partner.pk,
                "name": PROJECT_NAME,
                "city_item": _item("municipality", "11001"),
                "address": "Calle 100 # 10-10",
            },
        )
    if project.status == ProjectStatus.DRAFT:
        project = transition_project(admin, project, to_status=ProjectStatus.PENDING_REVIEW)
    if project.status == ProjectStatus.PENDING_REVIEW:
        project = transition_project(admin, project, to_status=ProjectStatus.ACTIVE)
    return project


def seed_security_actors() -> list[str]:
    if not settings.DEBUG:
        raise RuntimeError("seed_actors solo corre con DEBUG=True (entorno local).")
    admin = _user(DEMO_USERS[0].email)
    andres = _user(DEMO_USERS[2].email)
    broker_a = _user(DEMO_USERS[3].email)
    lines: list[str] = []

    with transaction.atomic():
        partner = _ensure_partner()
        project = _ensure_active_project(admin, partner)
        _ensure_internal_user(
            admin=admin,
            email=PARTNER_EMAIL,
            first_name="Clara",
            last_name="Constructora",
            role=RoleCode.CONSTRUCTION_PARTNER,
            partner=partner,
        )
        broker_b = _ensure_internal_user(
            admin=admin,
            email=BROKER_B_EMAIL,
            first_name="Bruno",
            last_name="Segundo",
            role=RoleCode.INDEPENDENT_BROKER,
            partner=None,
        )
    lines.append(f"CONSTRUCTION_PARTNER {PARTNER_EMAIL} (proyecto activo: {project.name})")
    lines.append(f"INDEPENDENT_BROKER   {BROKER_B_EMAIL}")

    from apps.crm.models import Client

    if Client.objects.filter(document_number__startswith=SECURITY_DOCUMENT_PREFIX).exists():
        lines.append("Clientes de auditoría ya existen: no se crean de nuevo.")
        return lines

    names = _SecurityNames()
    # Oportunidad propia del broker B, asignada a Andrés.
    client_b = create_client(broker_b, names.next())
    opportunity_b = create_opportunity(
        broker_b, client=client_b, project=None, origin_item=_item("lead_origin", "BROKER")
    )
    assign_advisor(admin, opportunity_b, advisor=andres)
    lines.append(f"Oportunidad del broker B para el cliente {client_b.document_number}")

    # Segundo comprador: solicitud asignada a Andrés, con un documento cargado.
    application = _build_case(
        BUYER_B_CASE, 900, advisor=andres, admin=admin, broker=broker_a, names=names
    )
    lines.append(f"Comprador B: solicitud {application.code} (asesor {andres.email})")
    return lines


for _line in seed_security_actors():
    print(_line)
