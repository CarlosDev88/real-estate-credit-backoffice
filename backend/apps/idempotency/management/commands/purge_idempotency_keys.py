from typing import Any

from django.core.management.base import BaseCommand

from apps.idempotency.services import purge_expired


class Command(BaseCommand):
    help = (
        "Borra las claves de idempotencia vencidas (24 h). Son datos técnicos: correrlo "
        "periódicamente, por ejemplo una vez al día desde cron."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        deleted = purge_expired()
        self.stdout.write(self.style.SUCCESS(f"Claves de idempotencia borradas: {deleted}."))
