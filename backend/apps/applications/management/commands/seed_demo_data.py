from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.applications.demo_data import (
    DEMO_PASSWORD,
    demo_data_exists,
    seed_demo_data,
)
from apps.crm.services import ensure_advisor
from apps.identity.models import User
from apps.identity.models.user import UserManager
from config.exceptions import ApiError

EXISTS_MESSAGE = "Los datos de demo ya existen"


class Command(BaseCommand):
    help = (
        "Crea datos de demo para correr en local: usuarios @demo.local, clientes, "
        "oportunidades y unas 30 solicitudes en borrador, esperando al comprador, en "
        "revisión y listas para radicar, con documentos y un enlace del portal. Solo con "
        "DEBUG. Si ya existen, no hace nada. Nunca borra."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--advisor-email",
            help="Correo de un asesor existente que también recibe solicitudes "
            "(por ejemplo, el usuario de las pruebas end-to-end).",
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
        if demo_data_exists():
            self.stdout.write(EXISTS_MESSAGE)
            return

        result = seed_demo_data(extra_advisor=extra_advisor)
        call_command("refresh_application_completeness", stdout=self.stdout)

        self.stdout.write(f"Solicitudes de demo: {len(result.applications)}")
        self.stdout.write(f"Usuarios (contraseña {DEMO_PASSWORD}, solo para local):")
        for user in result.users:
            self.stdout.write(f"  {user.role:<20} {user.email}")
        if extra_advisor is not None:
            self.stdout.write(f"  {'ADVISOR':<20} {extra_advisor.email} (existente)")
        self.stdout.write(f"Portal del comprador ({result.portal_application_code}):")
        self.stdout.write(f"  {result.portal_url}")
