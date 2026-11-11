from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.documents.exceptions import ScannerUnavailable, StorageUnavailable
from apps.documents.scanning import get_scanner
from apps.documents.storage import get_storage


class Command(BaseCommand):
    help = "Comprueba que respondan el almacenamiento de documentos y el antivirus."

    def handle(self, *args: Any, **options: Any) -> None:
        failures: list[str] = []

        storage = get_storage()
        try:
            storage.check()
            self.stdout.write(f"Almacenamiento ({storage.provider}, {storage.bucket}): OK")
        except StorageUnavailable as exc:
            failures.append(f"Almacenamiento ({storage.provider}, {storage.bucket}): {exc}")

        scanner = get_scanner()
        try:
            scanner.ping()
            self.stdout.write(f"Antivirus ({scanner.name}): OK")
        except ScannerUnavailable as exc:
            failures.append(f"Antivirus ({scanner.name}): {exc}")

        if failures:
            raise CommandError("\n".join(failures))
        self.stdout.write(self.style.SUCCESS("Servicios del expediente disponibles."))
