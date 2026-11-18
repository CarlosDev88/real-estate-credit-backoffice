from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.audit.retention import AUDIT_RETENTION_DAYS, purge_audit_events


class Command(BaseCommand):
    help = (
        "Borra los eventos de auditoría más viejos que la retención "
        f"({AUDIT_RETENTION_DAYS} días por omisión). Es la única forma de borrarlos."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--days",
            type=int,
            default=AUDIT_RETENTION_DAYS,
            help=f"Días que se conservan (por omisión, {AUDIT_RETENTION_DAYS}).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        days = options["days"]
        if days < 1:
            raise CommandError("--days debe ser al menos 1.")
        deleted = purge_audit_events(days=days)
        self.stdout.write(f"Eventos de auditoría borrados: {deleted} (más viejos que {days} días)")
