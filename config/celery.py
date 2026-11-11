"""Aplicación de Celery: análisis antivirus y paquetes documentales (API §28.3).

Las tareas se encolan con ``transaction.on_commit`` para no correr sobre datos que aún
no se confirmaron, solo reciben ids y son idempotentes. El worker se levanta con el
perfil ``async`` de docker-compose. En las pruebas corren en el mismo proceso
(``CELERY_TASK_ALWAYS_EAGER``).
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
