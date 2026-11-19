# Imagen del backend en dos etapas (SEC-06):
# - `dev`: la que usa el compose (`target: dev`), con el código montado y `runserver`;
# - `production`: gunicorn con `config.settings.production`, sin pruebas ni scripts.
#
# Base fijada por digest: índice multiplataforma de `python:3.11-slim` tomado el
# 2026-11-19 con `docker buildx imagetools inspect python:3.11-slim`. Para actualizarla,
# se repite el comando y se cambia el digest (y se anota la fecha).
FROM python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install pip==26.3 \
    && python -m pip install -r requirements.txt

# /data/documents: almacenamiento en disco del modo local simple. Existe en la imagen con
# dueño `app` para que el volumen con nombre, al crearse, herede ese dueño.
RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir -p /data/documents \
    && chown app:app /app /data/documents

EXPOSE 8000


# --- Desarrollo ---------------------------------------------------------------------
FROM base AS dev

COPY --chown=app:app . ./

USER app

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


# --- Producción ---------------------------------------------------------------------
FROM base AS production

ENV DJANGO_SETTINGS_MODULE=config.settings.production

# Solo lo que corre: sin `tests/`, `scripts/`, `security/` ni el compose.
COPY --chown=app:app manage.py ./
COPY --chown=app:app config ./config
COPY --chown=app:app apps ./apps

USER app

# `check` primero: sin `DEBUG`, una clave débil (SEC-03) u otra configuración insegura es un
# error y el contenedor no arranca. Gunicorn toma `GUNICORN_WORKERS` y demás de su
# configuración (`config/gunicorn.py`).
CMD ["sh", "-c", "python manage.py check && exec gunicorn -c config/gunicorn.py config.wsgi"]
