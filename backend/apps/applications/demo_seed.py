"""Orden de los bloques de ``seed_demo_data`` (TAREA-brechas-3-demo, parte 2).

Cada bloque es idempotente por su cuenta: tiene su propia marca (un código, un correo, un
prefijo de documento o un nombre fijo) y, si ya existe, no hace nada. Así, en una base con
la demo de una versión anterior, el comando agrega solo lo que falta, y correrlo dos veces
seguidas no duplica nada. Nunca borra.

Los bloques van en orden de dependencia: usuarios → constructoras → bancos → planes →
demo base → historia de seis meses → oportunidades → comisiones → tareas → notas →
avisos → exportaciones → invitaciones → reglas → auditoría → enlace del portal. Las reglas
van casi al final para no cambiar la evaluación bancaria de las solicitudes sembradas.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from unittest import mock

from django.utils import timezone

from apps.applications.demo_data import (
    DEMO_DOCUMENT_PREFIX,
    DEMO_USERS,
    DemoUser,
    _ensure_leasing_products,
    demo_advisors,
    demo_data_exists,
    ensure_demo_users,
    issue_portal_link,
    pending_portal_link,
    portal_application,
    seed_base_demo,
)
from apps.applications.demo_history import HISTORY_DOCUMENT_PREFIX, history_exists, seed_history
from apps.applications.models import CreditApplication
from apps.banking.models import BankProduct
from apps.identity.models import RoleCode, User

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BlockResult:
    name: str
    created: int

    @property
    def existed(self) -> bool:
        return self.created == 0


@dataclass(frozen=True)
class DemoUserRow:
    role: str
    email: str
    purpose: str


@dataclass
class DemoReport:
    blocks: list[BlockResult] = field(default_factory=list)
    users: list[DemoUserRow] = field(default_factory=list)
    portal_url: str = ""
    portal_application_code: str = ""
    # Ya había un enlace sin usar: no se emite otro (el token solo se ve al emitirlo).
    portal_link_pending: bool = False


PURPOSES = {
    DEMO_USERS[0].email: "Ve todo: administración, reportes, comisiones y auditoría.",
    DEMO_USERS[1].email: "Asesora con cartera: Mi día, solicitudes, tareas y radicaciones.",
    DEMO_USERS[2].email: "El otro asesor; sin teléfono (el portal no muestra WhatsApp).",
    DEMO_USERS[3].email: "Sus prospectos, el resumen de sus solicitudes y sus comisiones.",
}


def _demo_applications() -> list[CreditApplication]:
    return list(
        CreditApplication.objects.filter(
            opportunity__client__document_number__regex=(
                rf"^({DEMO_DOCUMENT_PREFIX}|{HISTORY_DOCUMENT_PREFIX})"
            )
        ).order_by("created_at")
    )


def _history_applications() -> list[CreditApplication]:
    return list(
        CreditApplication.objects.filter(
            opportunity__client__document_number__startswith=HISTORY_DOCUMENT_PREFIX
        ).order_by("created_at")
    )


@contextmanager
def monotonic_now() -> Iterator[None]:
    """``timezone.now`` sin saltos mientras se siembra: la hora de pared del inicio más el
    tiempo transcurrido de ``time.monotonic``.

    En Docker Desktop el reloj de la máquina virtual salta unos segundos hacia atrás y
    hacia adelante; dos filas creadas una tras otra podrían quedar con las fechas al revés,
    y ``backdate`` ordena el historial por fecha real. Nadie en el proyecto importa ``now``
    directamente ni usa fechas por defecto de la base, así que basta con este reemplazo.
    """
    wall, start = timezone.now(), time.monotonic()

    def now() -> datetime:
        return wall + timedelta(seconds=time.monotonic() - start)

    with mock.patch("django.utils.timezone.now", new=now):
        yield


def run_demo_seed(
    *, extra_advisor: User | None = None, new_portal_link: bool = False
) -> DemoReport:
    """Corre los bloques en orden, con un reloj sin saltos (``monotonic_now``). Quien
    llama comprueba ``DEBUG``."""
    with monotonic_now():
        return _run(extra_advisor=extra_advisor, new_portal_link=new_portal_link)


def _run(*, extra_advisor: User | None, new_portal_link: bool) -> DemoReport:
    # Imports locales: estos módulos dependen de `applications`.
    from apps.activity.demo_data import seed_team_notes, team_notes_exist
    from apps.audit.demo_data import audit_exists, seed_audit
    from apps.banking.demo_data import rules_exist, seed_bank_settings, seed_rules
    from apps.commissions.demo_data import (
        commission_states_exist,
        seed_commission_states,
        seed_plans,
    )
    from apps.crm.demo_data import opportunities_exist, seed_opportunities
    from apps.identity.demo_data import (
        INACTIVE_EMAIL,
        ensure_inactive_user,
        seed_invitations,
    )
    from apps.notifications.demo_data import (
        notification_states_exist,
        seed_notification_states,
    )
    from apps.partners.demo_data import (
        PARTNER_EMAIL,
        main_project,
        partners_exist,
        seed_partners,
    )
    from apps.reporting.demo_data import exports_exist, seed_exports
    from apps.tasks.demo_data import seed_team_tasks, team_tasks_exist

    report = DemoReport()
    blocks = report.blocks

    users, created = ensure_demo_users()
    admin = users[DEMO_USERS[0].email]
    advisors = demo_advisors(users)
    broker = users[DEMO_USERS[3].email]
    _, inactive_created = ensure_inactive_user(admin)
    blocks.append(BlockResult("Usuarios", created + int(inactive_created)))

    partners_created = 0
    if not partners_exist():
        result = seed_partners(admin)
        partners_created = 2 + len(result.projects)
    blocks.append(BlockResult("Constructoras, proyectos y membresías", partners_created))
    project = main_project()

    products_before = BankProduct.objects.count()
    _ensure_leasing_products()
    settings_changes = seed_bank_settings(admin)
    blocks.append(
        BlockResult(
            "Bancos y productos", BankProduct.objects.count() - products_before + settings_changes
        )
    )
    blocks.append(BlockResult("Planes de comisión", len(seed_plans(admin))))

    base_created = 0
    if not demo_data_exists():
        base_created = len(seed_base_demo(users=users, extra_advisor=extra_advisor).applications)
    blocks.append(BlockResult("Demo base (pestañas y radicadas)", base_created))

    history_created = 0
    if not history_exists():
        history = seed_history(
            advisors=advisors,
            admin=admin,
            broker=broker,
            project=project,
            first_index=len(_demo_applications()),
        )
        history_created = len(history.applications)
    blocks.append(BlockResult("Historia de seis meses", history_created))

    opportunities_created = 0
    if not opportunities_exist():
        opportunities_created = len(
            seed_opportunities(advisors=advisors, admin=admin, broker=broker, project=project)
        )
    blocks.append(BlockResult("Oportunidades en todos los estados", opportunities_created))

    commissions_created = 0
    if not commission_states_exist():
        commissions_created = seed_commission_states(admin, _history_applications())
    blocks.append(BlockResult("Comisiones (pagos, anulación, revisión)", commissions_created))

    tasks_created = 0
    if not team_tasks_exist(advisors):
        tasks_created = len(seed_team_tasks(advisors, _demo_applications()))
    blocks.append(BlockResult("Tareas de los asesores", tasks_created))

    notes_created = 0
    if not team_notes_exist():
        notes_created = len(seed_team_notes(advisors, _history_applications()))
    blocks.append(BlockResult("Notas de los asesores", notes_created))

    notifications_created = 0
    if not notification_states_exist():
        notifications_created = seed_notification_states(HISTORY_DOCUMENT_PREFIX)
    blocks.append(BlockResult("Avisos leídos y correos fallidos", notifications_created))

    exports_created = 0
    if not exports_exist(admin):
        exports_created = len(seed_exports(admin))
    blocks.append(BlockResult("Exportaciones de reportes", exports_created))

    blocks.append(BlockResult("Invitaciones", seed_invitations(admin)))

    rules_created = 0
    if not rules_exist():
        rules_created = len(seed_rules(admin))
    blocks.append(BlockResult("Reglas bancarias y versiones", rules_created))

    partner_user = User.objects.filter(email=PARTNER_EMAIL).first()
    audit_created = 0
    if not audit_exists():
        audit_created = seed_audit(
            admin=admin, advisors=advisors, broker=broker, partner_user=partner_user
        )
    blocks.append(BlockResult("Auditoría", audit_created))

    _portal(report, new_portal_link=new_portal_link)

    report.users = [
        DemoUserRow(str(spec.role), spec.email, PURPOSES[spec.email]) for spec in DEMO_USERS
    ]
    if partner_user is not None:
        report.users.append(
            DemoUserRow(
                RoleCode.CONSTRUCTION_PARTNER, PARTNER_EMAIL, "Su constructora y sus proyectos."
            )
        )
    report.users.append(
        DemoUserRow(f"{RoleCode.ADVISOR} (inactivo)", INACTIVE_EMAIL, "No puede entrar.")
    )
    logger.info("Demo: %s", ", ".join(f"{b.name}={b.created}" for b in blocks))
    return report


def _portal(report: DemoReport, *, new_portal_link: bool) -> None:
    """Enlace del portal: se emite si no hay uno sin usar (o si se pide uno nuevo).

    Va al final para que ninguna otra emisión lo revoque. El token solo se conoce al
    emitirlo: si ya hay uno sin usar y no se pide otro, no se emite (así la segunda
    corrida no cambia nada) y la salida lo dice.
    """
    application = portal_application()
    if application is None:
        report.blocks.append(BlockResult("Enlace del portal", 0))
        return
    report.portal_application_code = application.code
    if pending_portal_link(application) is not None and not new_portal_link:
        report.portal_link_pending = True
        report.blocks.append(BlockResult("Enlace del portal", 0))
        return
    report.portal_url = issue_portal_link(application)
    report.blocks.append(BlockResult("Enlace del portal", 1))


__all__ = ["BlockResult", "DemoReport", "DemoUser", "run_demo_seed"]
