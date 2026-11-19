"""Configuración de pruebas: rápida, aislada y sin servicios externos salvo PostgreSQL."""

import os

# base.py exige estas variables; en pruebas basta un valor fijo si no vienen del entorno.
os.environ.setdefault("AUTH_JWT_SIGNING_KEY", "test-signing-key-only-for-automated-tests")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-only-for-automated-tests")

from .base import *  # noqa: E402, F403

DEBUG = False

# Hash rápido solo para pruebas; producción usa Argon2id (base.py).
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Caché en memoria por proceso: aísla los límites de consumo entre pruebas.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Los límites generales (SEC-10) ×1000: muchas pruebas pegan a la misma vista con el mismo
# usuario. Solo las pruebas de límites vuelven a las tasas reales (`base.AUTH_RATE_LIMITS`)
# con `override_settings`.
AUTH_RATE_LIMITS = {
    **AUTH_RATE_LIMITS,  # noqa: F405
    "general_read": "600000/1m",
    "general_write": "120000/1m",
    "state_changes": "20000/1m",
}

# Fijas y largas: sin `DEBUG`, el check de SEC-03 (`apps/identity/checks.py`) exige 50
# caracteres en `SECRET_KEY` y 32 bytes en la clave JWT, y las del entorno del CI son cortas.
SECRET_KEY = "test-secret-key-only-for-automated-tests-0123456789-abcdefghij"
AUTH_JWT_SIGNING_KEY = "test-signing-key-only-for-automated-tests-0123456789"
AUTH_JWT_ISSUER = "mvp-credito-api"
AUTH_JWT_AUDIENCE = "mvp-credito-backoffice"
AUTH_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Sin servicios externos: almacenamiento en memoria, antivirus falso (EICAR) y tareas de
# Celery ejecutadas en el mismo proceso.
DOCUMENT_ALLOW_FAKE_SERVICES = True
DOCUMENT_STORAGE_BACKEND = "memory"
DOCUMENT_SCANNER = "fake"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
