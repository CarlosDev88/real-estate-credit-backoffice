"""Configuración de gunicorn para la imagen ``production`` (``Dockerfile``, SEC-06).

Todo se ajusta con variables de entorno; los valores por defecto sirven para un contenedor
pequeño detrás de un proxy que termina el TLS.
"""

import os

# Dentro del contenedor: lo que se publica lo decide el orquestador o el proxy.
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")  # nosec B104
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
# Reinicia cada worker cada tanto, con algo de azar para que no reinicien todos a la vez.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "100"))

# Sin access log (SEC-15): escribiría la URL con la consulta (búsquedas con documentos o
# nombres) sin pasar por los filtros de `config/log_redaction.py`. Las peticiones con error
# ya quedan en el log de Django, filtrado.
accesslog = None
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
