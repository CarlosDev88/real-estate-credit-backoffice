"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Producción por defecto (SEC-01): `local` fuerza `DEBUG=True`. El compose y el CI fijan
# `DJANGO_SETTINGS_MODULE` en cada servicio; `manage.py` sigue con `local`.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_wsgi_application()
