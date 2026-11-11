from .base import *  # noqa: F403

DEBUG = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# En local la API corre por HTTP: sin `Secure` el navegador rechazaría las cookies
# con prefijo `__Host-`, así que se usan los nombres sin prefijo.
AUTH_COOKIE_SECURE = False

# El navegador de Swagger sirve para explorar la API en desarrollo.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}
