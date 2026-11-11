FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . ./

# /data/documents: almacenamiento en disco del modo local simple. Existe en la imagen con
# dueño `app` para que el volumen con nombre, al crearse, herede ese dueño.
RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir -p /data/documents \
    && chown -R app:app /app /data/documents

USER app

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
