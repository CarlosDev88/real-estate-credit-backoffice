import logging
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

CACHE_NAMES = {
    "django.core.cache.backends.db.DatabaseCache": "database",
    "django.core.cache.backends.redis.RedisCache": "redis",
    "django.core.cache.backends.locmem.LocMemCache": "memoria",
}


def local_services_summary() -> str:
    """Una línea con el modo de los servicios: simple (sin Redis ni SeaweedFS) o ``full``."""
    cache_backend = str(settings.CACHES["default"]["BACKEND"])
    cache = CACHE_NAMES.get(cache_backend, cache_backend.rsplit(".", 1)[-1])
    tasks = "inmediatas" if settings.CELERY_TASK_ALWAYS_EAGER else "worker"
    return (
        f"Servicios locales: almacenamiento={settings.DOCUMENT_STORAGE_BACKEND}"
        f" · caché={cache} · tareas={tasks} · antivirus={settings.DOCUMENT_SCANNER}"
    )


class Command(BaseCommand):
    help = (
        "Deja en el log el modo de los servicios (almacenamiento, caché, tareas y antivirus). "
        "docker-compose lo corre al arrancar el backend."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        logger.info(local_services_summary())
