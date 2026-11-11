"""Límites técnicos de los archivos que puede pedir un tipo documental.

``allowed_mime_types`` de ``document_types`` es una "lista técnica pequeña y cerrada"
(sección 7.10 del modelo de datos): un tipo solo puede elegir valores de
``ALLOWED_MIME_TYPES``. La carga de archivos (paso 10) verificará además el MIME real
detectado, no el que declara el navegador.

``MAX_FILE_SIZE_BYTES`` es el máximo por archivo de la sección 9.3 de los
requerimientos; cada tipo puede fijar un límite menor.
"""

PDF = "application/pdf"
JPEG = "image/jpeg"
PNG = "image/png"

ALLOWED_MIME_TYPES: tuple[str, ...] = (PDF, JPEG, PNG)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
