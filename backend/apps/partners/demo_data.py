"""Constructoras, proyectos y membresías de demo (``seed_demo_data``, TAREA-brechas-3-demo).

- **Constructora Andina de Demo** (activa) con su usuaria ``constructora@demo.local``
  (``CONSTRUCTION_PARTNER``) y proyectos en cada estado: activo (dos), en validación,
  borrador, rechazado (devuelto a borrador con motivo) y archivado.
- **Inmobiliaria del Valle de Demo** (inactiva) con una membresía inactiva.

Todo pasa por los servicios. Marca del bloque: el NIT de la primera constructora; si
existe, el bloque no hace nada.
"""

from dataclasses import dataclass, field
from datetime import date

from django.db import transaction

from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import ProjectStatus
from apps.identity.models import Role, RoleCode, User
from apps.identity.users import create_user
from apps.partners import services
from apps.partners.models import Partner, PartnerMembership, PartnerStatus, Project
from apps.partners.validators import nit_check_digit

DEMO_PASSWORD = "DemoUmbral2026!"


def _nit(number: str) -> str:
    return f"{number}-{nit_check_digit(number)}"


PARTNER_TAX_ID = _nit("901555100")
OTHER_PARTNER_TAX_ID = _nit("901555200")
PARTNER_EMAIL = "constructora@demo.local"
FORMER_MEMBER_EMAIL = "constructora.anterior@demo.local"
# El proyecto activo al que llegan oportunidades de la historia de demo.
MAIN_PROJECT = "Torres del Parque"

# (nombre, código, municipio, estado final, pasos) — pasos: "submit", "approve",
# "approve_draft", "reject", "archive".
PROJECTS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (MAIN_PROJECT, "TDP", "11001", ("submit", "approve")),
    ("Portal de la 80", "P80", "05001", ("approve_draft",)),
    ("Altos de la Sabana", "ADS", "25754", ("submit",)),
    ("Mirador del Río", "MDR", "76001", ()),
    ("Reserva Campestre", "RCA", "05615", ("submit", "reject")),
    ("Bosques de Niza", "BDN", "11001", ("approve_draft", "archive")),
)


@dataclass
class PartnersResult:
    partner: Partner | None = None
    partner_user: User | None = None
    projects: list[Project] = field(default_factory=list)


def partners_exist() -> bool:
    return Partner.objects.filter(tax_id=PARTNER_TAX_ID).exists()


def main_project() -> Project | None:
    return Project.objects.filter(
        partner__tax_id=PARTNER_TAX_ID, name=MAIN_PROJECT, status=ProjectStatus.ACTIVE
    ).first()


def _city(code: str) -> CatalogItem:
    item = CatalogItem.objects.filter(catalog__code="municipality", code=code).first()
    return item or CatalogItem.objects.get(catalog__code="municipality", code="11001")


def _partner_user(admin: User, partner: Partner, email: str, first: str, last: str) -> User:
    user, _ = create_user(
        actor=admin,
        email=email,
        first_name=first,
        last_name=last,
        phone="+573005550110",
        roles=[Role.objects.get(code=RoleCode.CONSTRUCTION_PARTNER)],
        partner=partner,
        send_invitation=False,
    )
    user.set_password(DEMO_PASSWORD)
    user.save(update_fields=["password", "updated_at"])
    return user


def _project(
    partner_user: User, admin: User, spec: tuple[str, str, str, tuple[str, ...]]
) -> Project:
    name, code, city, steps = spec
    project = services.create_project(
        partner_user,
        {
            "name": name,
            "code": code,
            "city_item": _city(city),
            "address": f"Calle {len(name) * 3} # {len(code) * 7}-20",
            "description": f"Proyecto de vivienda {name} (demo).",
            "estimated_delivery_date": date(2027, 6, 30),
        },
    )
    for step in steps:
        if step == "submit":
            project = services.transition_project(
                partner_user, project, to_status=ProjectStatus.PENDING_REVIEW
            )
        elif step in ("approve", "approve_draft"):
            project = services.transition_project(admin, project, to_status=ProjectStatus.ACTIVE)
        elif step == "reject":
            project = services.transition_project(
                admin,
                project,
                to_status=ProjectStatus.DRAFT,
                reason="Falta la licencia de construcción.",
            )
        elif step == "archive":
            project = services.transition_project(
                admin, project, to_status=ProjectStatus.ARCHIVED, reason="Proyecto vendido."
            )
    return project


def seed_partners(admin: User) -> PartnersResult:
    """Crea las constructoras, sus usuarios y los proyectos. Quien llama comprueba
    ``partners_exist``."""
    with transaction.atomic():
        partner = services.create_partner(
            {
                "legal_name": "Constructora Andina de Demo S.A.S.",
                "trade_name": "Andina Demo",
                "tax_id": PARTNER_TAX_ID,
                "contact_name": "Paola Restrepo",
                "contact_email": "contacto@andina.demo.local",
                "contact_phone": "+576015550120",
            }
        )
        partner_user = _partner_user(admin, partner, PARTNER_EMAIL, "Paola", "Restrepo")
        PartnerMembership.objects.filter(user=partner_user).update(job_title="Gerente comercial")

        other = services.create_partner(
            {
                "legal_name": "Inmobiliaria del Valle de Demo S.A.S.",
                "trade_name": "Valle Demo",
                "tax_id": OTHER_PARTNER_TAX_ID,
                "contact_name": "Hernán Zapata",
                "contact_email": "contacto@valle.demo.local",
                "contact_phone": "+576025550130",
            }
        )
        former = _partner_user(admin, other, FORMER_MEMBER_EMAIL, "Hernán", "Zapata")
        membership = PartnerMembership.objects.get(user=former)
        services.update_membership(
            membership, {"status": PartnerStatus.INACTIVE, "job_title": "Director de ventas"}
        )
        services.set_partner_status(
            other, active=False, actor=admin, reason="La constructora pausó sus proyectos."
        )

    result = PartnersResult(partner=partner, partner_user=partner_user)
    for spec in PROJECTS:
        result.projects.append(_project(partner_user, admin, spec))
    return result
