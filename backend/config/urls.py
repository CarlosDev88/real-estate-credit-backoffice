"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.views import admin_login, health, ready

api_v1_patterns = [
    path("auth/", include("apps.identity.urls")),
    path("", include("apps.identity.user_urls")),
    path("", include("apps.identity.invitation_urls")),
    path("", include("apps.catalogs.urls")),
    path("", include("apps.partners.urls")),
    path("", include("apps.crm.urls")),
    path("", include("apps.banking.urls")),
    path("", include("apps.documents.urls")),
    path("", include("apps.applications.urls")),
    path("", include("apps.filings.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.identity.buyer_access_urls")),
    path("", include("apps.identity.buyer_portal_urls")),
    path("", include("apps.identity.consent_urls")),
    path("", include("apps.workday.urls")),
    path("", include("apps.tasks.urls")),
    path("", include("apps.activity.urls")),
    path("", include("apps.audit.urls")),
    path("", include("apps.reporting.urls")),
    path("", include("apps.commissions.urls")),
]

urlpatterns = [
    path("api/v1/", include(api_v1_patterns)),
    path("health", health, name="health"),
    path("ready", ready, name="ready"),
]

# `/admin/` solo con `DEBUG` o `ADMIN_ENABLED` (SEC-18), en `ADMIN_URL_PATH`; su login pasa
# por un límite de intentos por IP (va antes que `admin.site.urls` para reemplazarlo).
if settings.DEBUG or settings.ADMIN_ENABLED:
    admin_path = settings.ADMIN_URL_PATH.strip("/") + "/"
    urlpatterns += [
        path(f"{admin_path}login/", admin_login, name="admin-login"),
        path(admin_path, admin.site.urls),
    ]

# El esquema y Swagger solo con `DEBUG` o `API_DOCS_PUBLIC` (SEC-19). El frontend y la
# referencia publicada usan `contracts/openapi.json` del repo.
if settings.DEBUG or settings.API_DOCS_PUBLIC:
    urlpatterns += [
        path("openapi.json", SpectacularAPIView.as_view(), name="openapi-schema"),
        path(
            "docs",
            SpectacularSwaggerView.as_view(url_name="openapi-schema"),
            name="swagger-ui",
        ),
    ]

# Rutas inexistentes y errores fuera de DRF: el formato de error de la API en `/api/`
# (SEC-12). Django solo los usa sin `DEBUG`.
handler404 = "config.views.page_not_found"
handler500 = "config.views.server_error"
