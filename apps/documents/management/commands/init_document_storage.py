from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.documents.exceptions import StorageUnavailable
from apps.documents.storage import get_storage


class Command(BaseCommand):
    help = (
        "Crea el bucket privado del expediente si no existe. Lo usa el servicio "
        "storage-init de docker-compose; en S3 real el bucket lo aprovisiona la "
        "infraestructura."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        storage = get_storage()
        try:
            created = storage.ensure_bucket()
        except StorageUnavailable as exc:
            raise CommandError(f"No se pudo preparar el bucket {storage.bucket}: {exc}") from exc
        action = "creado" if created else "ya existía"
        self.stdout.write(self.style.SUCCESS(f"Bucket {storage.bucket}: {action}."))
