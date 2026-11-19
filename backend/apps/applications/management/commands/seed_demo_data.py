from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.applications.demo_data import DEMO_PASSWORD
from apps.applications.demo_seed import DemoReport, run_demo_seed
from apps.crm.services import ensure_advisor
from apps.identity.models import User
from apps.identity.models.user import UserManager
from config.exceptions import ApiError

CREATED = "creados"
EXISTED = "ya existían"


class Command(BaseCommand):
    help = (
        "Crea datos de demo para correr en local: un usuario por rol (@demo.local), "
        "constructoras y proyectos, unas 60 solicitudes de los últimos seis meses en todos "
        "los estados, radicaciones con cada respuesta del banco, comisiones, tareas, notas, "
        "avisos, exportaciones, invitaciones, reglas y auditoría. Solo con DEBUG. Cada "
        "bloque es idempotente: agrega solo lo que falta y se puede correr varias veces. "
        "Nunca borra."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--advisor-email",
            help="Correo de un asesor existente que también recibe solicitudes de la demo "
            "base (por ejemplo, el usuario de las pruebas end-to-end).",
        )
        parser.add_argument(
            "--new-portal-link",
            action="store_true",
            help="Emite un enlace nuevo del portal aunque ya haya uno sin usar (revoca el "
            "anterior).",
        )

    def _extra_advisor(self, email: str | None) -> User | None:
        if not email:
            return None
        user = User.objects.filter(email=UserManager.normalize_email(email)).first()
        if user is None:
            raise CommandError(f"No existe un usuario con el correo {email}.")
        try:
            ensure_advisor(user)
        except ApiError as exc:
            raise CommandError(f"{email} no es un asesor activo.") from exc
        return user

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("seed_demo_data solo corre con DEBUG=True (entorno local).")
        extra_advisor = self._extra_advisor(options.get("advisor_email"))

        report = run_demo_seed(
            extra_advisor=extra_advisor, new_portal_link=bool(options.get("new_portal_link"))
        )
        if any(not block.existed for block in report.blocks):
            call_command("refresh_application_completeness", stdout=self.stdout)
        self._print(report, extra_advisor)

    def _print(self, report: DemoReport, extra_advisor: User | None) -> None:
        write = self.stdout.write
        write("Bloques de la demo:")
        width = max(len(block.name) for block in report.blocks)
        for block in report.blocks:
            state = EXISTED if block.existed else f"{CREATED} ({block.created})"
            write(f"  {block.name:<{width}}  {state}")

        write("")
        write(f"Usuarios por rol (contraseña {DEMO_PASSWORD}, solo para local):")
        role_width = max(len(row.role) for row in report.users)
        email_width = max(len(row.email) for row in report.users)
        for row in report.users:
            write(f"  {row.role:<{role_width}}  {row.email:<{email_width}}  {row.purpose}")
        if extra_advisor is not None:
            write(f"  {'ADVISOR':<{role_width}}  {extra_advisor.email} (existente)")

        write("")
        if not report.portal_application_code:
            write("Portal del comprador: no se encontró la solicitud de la demo.")
        elif report.portal_url:
            write(f"Portal del comprador ({report.portal_application_code}), un solo uso:")
            write(f"  {report.portal_url}")
        else:
            write(
                f"Portal del comprador ({report.portal_application_code}): ya hay un enlace "
                "sin usar. Para emitir otro: seed_demo_data --new-portal-link"
            )
