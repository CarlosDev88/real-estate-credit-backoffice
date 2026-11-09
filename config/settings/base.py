from datetime import timedelta
from pathlib import Path

import environ
from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(DJANGO_DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "apps.identity",
    "apps.catalogs",
    "apps.partners",
    "apps.crm",
    "apps.banking",
    "apps.documents",
    "apps.applications",
]

MIDDLEWARE = [
    "config.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DATABASE_NAME"),
        "USER": env("DATABASE_USER"),
        "PASSWORD": env("DATABASE_PASSWORD"),
        "HOST": env("DATABASE_HOST"),
        "PORT": env("DATABASE_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_USER_MODEL = "identity.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "config.api.StandardResultsSetPagination",
    "PAGE_SIZE": 25,
    # Seguro por defecto: todo endpoint exige sesión salvo que declare lo contrario.
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.identity.authentication.CookieJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "config.exceptions.api_exception_handler",
    # Proxies de confianza delante de la API. Con 0 se ignora X-Forwarded-For.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=0),
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "MVP Crédito API",
    "DESCRIPTION": "API REST para gestión de crédito de vivienda.",
    "VERSION": "1.0.0",
    "OAS_VERSION": "3.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_AUTHENTICATION": [],
    "COMPONENT_SPLIT_REQUEST": True,
    # Nombres estables para enums que se repiten en varios recursos (campo `status`).
    "ENUM_NAME_OVERRIDES": {
        "PartnerStatusEnum": "apps.partners.models.partner.PartnerStatus",
        "ProjectStatusEnum": "apps.catalogs.workflow.ProjectStatus",
        "OpportunityStatusEnum": "apps.catalogs.workflow.OpportunityStatus",
        "ApplicationStatusEnum": "apps.catalogs.workflow.ApplicationStatus",
        # Requisitos documentales (`participant_role`) y participantes (`role`).
        "ParticipantRoleEnum": "apps.documents.models.ParticipantRole",
        "RuleOutcomeEnum": "apps.banking.rule_engine.Outcome",
        "BuyerAccessLinkStatusEnum": "apps.identity.models.BuyerAccessLinkStatus",
    },
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://localhost:3000"])
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = (*default_headers, "x-request-id", "idempotency-key", "if-match")
# `ETag` lleva la versión de la solicitud que el frontend reenvía en `If-Match`.
CORS_EXPOSE_HEADERS = ["X-Request-ID", "Retry-After", "ETag"]

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# CSRF (sección 4 de la API): Next.js lee la cookie `app_csrf` y la reenvía en
# la cabecera `X-CSRFToken` en cada escritura autenticada.
CSRF_COOKIE_NAME = "app_csrf"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = env.bool("AUTH_COOKIE_SECURE", default=True)

# Caché compartida: la usan los límites de consumo, que no pueden vivir en memoria.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_CACHE_URL", default="redis://redis:6379/1"),
        "KEY_PREFIX": "mvp_credit",
        "TIMEOUT": 300,
    }
}

# --- Autenticación interna (secciones 4, 7 y 9.1) ------------------------------------
# Clave dedicada para firmar los JWT; distinta de SECRET_KEY y de alta entropía.
AUTH_JWT_SIGNING_KEY = env("AUTH_JWT_SIGNING_KEY")
AUTH_JWT_ISSUER = env("AUTH_JWT_ISSUER", default="mvp-credito-api")
AUTH_JWT_AUDIENCE = env("AUTH_JWT_AUDIENCE", default="mvp-credito-backoffice")
AUTH_JWT_LEEWAY_SECONDS = 5
AUTH_ACCESS_TOKEN_LIFETIME = timedelta(minutes=env.int("AUTH_ACCESS_TOKEN_MINUTES", default=15))
AUTH_REFRESH_TOKEN_LIFETIME = timedelta(hours=env.int("AUTH_REFRESH_TOKEN_HOURS", default=8))
AUTH_PASSWORD_RESET_TOKEN_LIFETIME = timedelta(
    minutes=env.int("AUTH_PASSWORD_RESET_TOKEN_MINUTES", default=30)
)
AUTH_INVITATION_LIFETIME = timedelta(hours=env.int("AUTH_INVITATION_HOURS", default=72))
# En producción siempre True (HTTPS); habilita el prefijo `__Host-` en las cookies.
AUTH_COOKIE_SECURE = env.bool("AUTH_COOKIE_SECURE", default=True)
AUTH_COOKIE_SAMESITE = "Lax"

# Límites de consumo (sección 26). Formato `<cantidad>/<n><s|m|h|d>`.
AUTH_RATE_LIMITS = {
    "login": "5/15m",
    "password_reset_request": "3/1h",
    "password_reset_confirm": "10/15m",
    "change_password": "5/15m",
    "invitation_accept": "10/15m",
    # Acceso del comprador (API §8 y REQUERIMIENTOS §9.3).
    "buyer_access_consume": "5/1h",
    "buyer_access_issue": "3/1h",
}

# Página del frontend que recibe `?token=` para definir la nueva contraseña.
PASSWORD_RESET_URL = env(
    "PASSWORD_RESET_URL", default="http://localhost:3000/restablecer-contrasena"
)
# Página del frontend que recibe `?token=` para aceptar una invitación interna.
INVITATION_ACCEPT_URL = env(
    "INVITATION_ACCEPT_URL", default="http://localhost:3000/aceptar-invitacion"
)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-responder@localhost")

# --- Acceso passwordless del comprador (API §8 y REQUERIMIENTOS §9.1) ------------------
# Vencimiento del enlace mágico: `expires_in_hours` va de 1 al máximo.
BUYER_ACCESS_LINK_DEFAULT_HOURS = env.int("BUYER_ACCESS_LINK_DEFAULT_HOURS", default=72)
BUYER_ACCESS_LINK_MAX_HOURS = env.int("BUYER_ACCESS_LINK_MAX_HOURS", default=168)
# Duración absoluta de la sesión del comprador; no se renueva con la actividad.
BUYER_SESSION_LIFETIME = timedelta(hours=env.int("BUYER_SESSION_HOURS", default=24))
# Página del portal de compradores que recibe `?token=` y lo consume.
BUYER_ACCESS_URL = env("BUYER_ACCESS_URL", default="http://localhost:3000/acceso")

# --- Metadatos para el frontend (sección 9) ------------------------------------------
# Catálogos grandes que no viajan en /metadata/bootstrap; se piden con
# /metadata/catalogs/{code}.
METADATA_ON_DEMAND_CATALOGS = ["municipality"]
# Configuración pública que el frontend usa para mostrar u ocultar funciones.
PUBLIC_FEATURES = {"manual_filing": True, "buyer_magic_link": True}

CELERY_BROKER_URL = env("REDIS_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TIME_LIMIT = 300

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "config.request_context.RequestIDLogFilter"}},
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)s %(name)s [request_id=%(request_id)s] %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "default",
        }
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
    # Sin handler propio: los logs de Django suben al root y salen una sola vez,
    # con el formato que incluye el request_id.
    "loggers": {"django": {"handlers": [], "propagate": True}},
}
