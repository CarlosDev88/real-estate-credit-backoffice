# ADR 0010 · Almacenamiento privado con URL firmadas y antivirus que falla cerrado

- **Estado:** aceptada.
- **Fecha:** módulo 10 (expediente documental) y tarea del modo local simple; registrada el 2026-11-18.
- **Fuentes:** RNF-03, RNF-15, REQ §9.2 y §9.5; Tanda 1 (decisiones 1 y 2) y decisiones 11 y 13 de [`specs/TAREA-document-file.md`](../../specs/TAREA-document-file.md); [`specs/TAREA-local-simple.md`](../../specs/TAREA-local-simple.md); `backend/apps/documents/storage.py`, `file_validation.py`, `scanning.py`, `scans.py`, `downloads.py`.

## Contexto

Los compradores suben cédulas, extractos y certificados. Esos archivos no pueden tener una URL pública permanente, no pueden ser ejecutables disfrazados y no pueden llegar al asesor ni al banco si traen malware.

## Opciones consideradas

1. **Guardar en la base** (BLOB). Infla la base y los respaldos, y la descarga pasa siempre por la API.
2. **Carpeta pública del servidor web.** Rutas adivinables y permanentes.
3. **Almacenamiento de objetos privado (S3 compatible)** con URL prefirmadas de corta duración, validación por bytes y antivirus antes de habilitar el archivo.
4. Para el servidor S3 local: **MinIO** o **SeaweedFS**.

## Decisión

Opción 3 con una interfaz propia (`ObjectStorage`: `put`, `open`, `delete`, `presigned_url`, `ensure_bucket`, `check`) y tres implementaciones: S3 (SeaweedFS en el modo completo, S3 real en producción, cambiando solo variables), **disco** para el modo simple (con URL firmadas por Django en `/api/v1/storage/objects/{token}`) y memoria para las pruebas. Clave del objeto sin el nombre original. Tipo real por firma de bytes con lista cerrada (PDF, JPG, PNG). Antivirus ClamAV (`clamd`, `INSTREAM`) en una tarea después del commit; **si el antivirus falla, el archivo sigue pendiente, nunca limpio**. Nada sin análisis limpio se aprueba ni se descarga. Descargas con URL de 5 minutos, siempre `attachment` y `nosniff`. Se eligió **SeaweedFS** porque la edición comunitaria de MinIO dejó de publicar imágenes.

## Consecuencias

- **A favor:** pasar a S3 real es configuración; un fallo de infraestructura nunca aprueba un archivo; un archivo no se abre como HTML en el origen de la app.
- **En contra:** el modo simple no tiene antivirus real (escáner de prueba que solo detecta la firma EICAR); los servicios falsos **exigen `DEBUG`** y sin él la app no arranca.
- **Cifrado:** SSE-S3 en S3 real; SeaweedFS no lo implementa.
- **Un solo almacenamiento por proceso:** los archivos guardados en un modo no se ven en el otro (`503 DOWNLOAD_UNAVAILABLE`).
- El ZIP del paquete no pasa por el antivirus: se arma con versiones limpias cuyo SHA-256 se verifica.
