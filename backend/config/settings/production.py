"""Configuración de producción (SEC-01 y SEC-02 de la auditoría de seguridad).

Es la que usan por defecto ``config/wsgi.py``, ``config/asgi.py`` y ``config/celery.py``
(la imagen ``production`` del ``Dockerfile`` corre gunicorn con ella). ``manage.py`` sigue
con ``local``; el compose y el CI fijan ``DJANGO_SETTINGS_MODULE`` en cada servicio.

Todo lo que no está aquí sale de ``base.py`` y del entorno. Lo de aquí no se puede aflojar
desde el entorno, salvo la redirección a HTTPS (``SECURE_SSL_REDIRECT``), que se apaga
cuando el TLS termina en un proxy que ya redirige.
"""

from .base import *  # noqa: F403
from .base import env

# Fijo: ninguna variable de entorno enciende la depuración en producción.
DEBUG = False

# Correo real (SMTP) desde el entorno.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)

# HTTPS (SEC-02). HSTS empieza en una hora; se sube cuando el dominio esté estable.
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# El TLS termina en el proxy: confía en su `X-Forwarded-Proto` (el proxy debe pisarlo).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
# `/health` y `/ready` los consulta el orquestador por HTTP dentro de la red.
SECURE_REDIRECT_EXEMPT = [r"^health$", r"^ready$"]

# Cookies solo por HTTPS: la de sesión de Django (solo `/admin/`), la de CSRF y las propias
# de autenticación (con prefijo `__Host-`).
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
AUTH_COOKIE_SECURE = True

# Solo JSON: sin el navegador de DRF.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
