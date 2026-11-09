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

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.views import health, ready

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
    path("", include("apps.identity.buyer_access_urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1_patterns)),
    path("health", health, name="health"),
    path("ready", ready, name="ready"),
    path("openapi.json", SpectacularAPIView.as_view(), name="openapi-schema"),
    path(
        "docs",
        SpectacularSwaggerView.as_view(url_name="openapi-schema"),
        name="swagger-ui",
    ),
]
