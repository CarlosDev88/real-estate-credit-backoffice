"""Caché y Celery según el modo local: simple (sin Redis) o ``full``.

Lo usa ``config/settings/base.py``. Vive aparte para poder probarlo sin recargar los
settings.

- Caché: ``CACHE_BACKEND=redis`` (por omisión) o ``database``. Las dos son compartidas
  entre procesos, que es lo que necesitan los límites de consumo; ``database`` usa la
  tabla de ``createcachetable``.
- Celery: con ``CELERY_TASK_ALWAYS_EAGER`` las tareas corren dentro de la petición y el
  broker es uno en memoria aunque haya ``REDIS_URL``: Celery igual pide un productor al
  encolar en modo inmediato, y así nada intenta conectarse a Redis. Sin modo inmediato,
  ``REDIS_URL`` es obligatorio.
"""

from typing import Any

from django.core.exceptions import ImproperlyConfigured

REDIS = "redis"
DATABASE = "database"
CACHE_BACKENDS = (REDIS, DATABASE)
CACHE_TABLE = "django_cache"
# Con host explícito: sin él, kombu avisa "No hostname was supplied" en cada conexión.
MEMORY_BROKER = "memory://localhost/"


def cache_settings(backend: str, redis_url: str) -> dict[str, dict[str, Any]]:
    common: dict[str, Any] = {"KEY_PREFIX": "mvp_credit", "TIMEOUT": 300}
    if backend == REDIS:
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": redis_url,
                **common,
            }
        }
    if backend == DATABASE:
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.db.DatabaseCache",
                "LOCATION": CACHE_TABLE,
                **common,
            }
        }
    raise ImproperlyConfigured(f"CACHE_BACKEND debe ser uno de {CACHE_BACKENDS}.")


def celery_broker_url(redis_url: str, *, always_eager: bool) -> str:
    if always_eager:
        return MEMORY_BROKER
    if not redis_url:
        # Con un broker en memoria ningún worker vería las tareas: quedarían sin correr.
        raise ImproperlyConfigured(
            "Sin REDIS_URL, CELERY_TASK_ALWAYS_EAGER debe ser true (modo local simple)."
        )
    return redis_url


def celery_result_backend(redis_url: str, *, always_eager: bool) -> str | None:
    # En modo inmediato no se guardan resultados.
    return None if always_eager else redis_url
