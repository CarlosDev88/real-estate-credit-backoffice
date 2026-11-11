# Tarea: entorno local con 3 contenedores

## Objetivo
El proyecto se entrega para correr en local y **no tiene despliegue**: el alcance llega hasta CI. Con `docker compose up` deben levantar solo tres contenedores:

| Contenedor | Qué hace |
| --- | --- |
| `postgres` | Base de datos. |
| `backend` | API Django. |
| `frontend` | Next.js. Lo agrega `TAREA-frontend-base.md`; esta tarea deja el compose preparado. |

Lo demás (Redis, SeaweedFS, `storage-init`, worker de Celery y ClamAV) no se borra: pasa a un perfil opcional `full`, que muestra la arquitectura asíncrona real con `docker compose --profile full up`.

## Cuándo
- Después del merge del reporte del CI (`TAREA-ci-reporte.md`).
- Rama: `chore/local-simple`, desde `master` al día.
- Puede ir en paralelo con la F0 del frontend. **Regla para no chocar:** el servicio `frontend` del compose lo agrega la F0 recién cuando esta tarea esté fusionada.

## Reglas de trabajo
Las de siempre:
- git solo en lectura; Carlos hace los commits;
- sin `Co-Authored-By`;
- primero las dudas, una por una y con recomendación; las precisiones van al final;
- se trabaja por partes, y el agente espera el "listo" de Carlos entre una y otra;
- el CI sigue en verde y con cobertura ≥ 95 %, el contrato al día y el reporte del PR sin errores.

## Lo que existe hoy (verificado)
- **Compose:** `postgres`, `backend`, `redis`, `seaweedfs` y `storage-init` siempre; `worker` y `clamav` con el perfil `async`. `backend` depende de `redis` y de `storage-init`.
- **Caché:** `CACHES` usa Redis. La usan los límites de consumo, que no pueden vivir en la memoria de un proceso.
- **Celery:** `CELERY_BROKER_URL` apunta a Redis. Las tareas `scan_file_object` y `build_document_package` se encolan con `.delay()` dentro de `transaction.on_commit`.
- **Almacenamiento:** `apps/documents/storage.py` define el protocolo `ObjectStorage` (`put`, `open`, `delete`, `presigned_url`, `ensure_bucket`, `check`) con dos backends: `S3Storage` y `MemoryStorage`. El de memoria es solo para DEBUG y pruebas.
- **Antivirus:** `DOCUMENT_SCANNER=fake` ya existe para desarrollo (requiere DEBUG).
- **Pruebas:** usan `config.settings.test` (caché en memoria y almacenamiento en memoria). El CI no cambia.

## Qué construir

### Parte 1. Almacenamiento en disco
- **Backend nuevo `filesystem`** en `storage.py`, que cumple el protocolo `ObjectStorage`:
  - guarda los objetos bajo `DOCUMENT_STORAGE_ROOT`, por ejemplo `/data/documents`, en un volumen con nombre;
  - `ensure_bucket` crea la carpeta y `check` verifica que se pueda escribir en ella;
  - las claves se validan para que no puedan salir de la carpeta raíz (`..`, rutas absolutas).
- **`presigned_url`:** devuelve una URL firmada hacia un endpoint nuevo del backend, por ejemplo `GET /api/v1/storage/objects/{token}`. El token lleva la clave, el nombre de archivo, el tipo de contenido y la expiración, firmados con `django.core.signing`.
  - El endpoint no pide sesión: la firma es la autorización, igual que una URL prefirmada de S3.
  - Responde el archivo con `Content-Disposition` y `Cache-Control: no-store`.
  - Con el token vencido o alterado responde `403`.
  - La expiración es la misma que hoy (`DOCUMENT_DOWNLOAD_URL_SECONDS`).
- **Solo con DEBUG**, igual que `memory`. Producción usaría S3; el backend en disco es para local.
- **Pruebas:** guardar, leer y borrar; claves inválidas; firma válida, vencida y alterada; descarga con encabezados correctos; que el endpoint no exista sin DEBUG.

### Parte 2. Caché y tareas sin Redis
- **Caché:** `CACHE_BACKEND=redis|database`. Con `database`, se usa `DatabaseCache`: es compartida entre procesos, así que los límites de consumo siguen funcionando. La tabla se crea con `createcachetable`.
- **Tareas:** `CELERY_TASK_ALWAYS_EAGER=true|false`. Con `true`, `.delay()` ejecuta la tarea en el mismo proceso, después del commit. El análisis antivirus (con el escáner de prueba) y el ZIP del paquete corren dentro de la petición, y eso es aceptable en local.
  - Verificar cómo se comportan en modo inmediato los reintentos de `build_document_package` y de `scan_file_object`: que un fallo no rompa la petición del usuario, y que el trabajo quede en `FAILED` o `PENDING` como hoy.
- Con `REDIS_URL` vacío y el modo inmediato, nada intenta conectarse a Redis.
- **Pruebas:** límites de consumo con `DatabaseCache`, y la carga y el paquete de punta a punta en modo inmediato, con almacenamiento en disco.

### Parte 3. Compose, `.env.example` y README
- **Compose:**
  - Sin perfil: `postgres` y `backend`, más `frontend` cuando lo agregue la F0.
  - Con el perfil `full`: `redis`, `seaweedfs`, `storage-init`, `worker` y `clamav`. El perfil `async` desaparece y se une a `full`.
  - `backend` depende solo de `postgres` por defecto. Para el modo `full`, las dependencias se declaran con `required: false`, o como proponga el agente.
- **Arranque del backend:** que `migrate` y `createcachetable` corran solos al levantar, con un *entrypoint* o un comando previo. El agente propone cómo.
- **Volumen con nombre** para los documentos (`mvp_credit_documents_data`).
- **`.env.example`, dos bloques:**
  - "Local simple" (por defecto): `DOCUMENT_STORAGE_BACKEND=filesystem`, `CACHE_BACKEND=database`, `CELERY_TASK_ALWAYS_EAGER=true`, `DOCUMENT_SCANNER=fake`.
  - "Full" (comentado): S3/SeaweedFS, Redis, `clamd`.
- **README raíz y `backend/README.md`:** cómo levantar el modo simple (3 contenedores), cómo levantar `full` y qué cambia en cada uno.
- **`TAREA-frontend-base.md`:** anotar que la F0 agrega el servicio `frontend` al compose, en el puerto 3000, con `API_ORIGIN=http://backend:8000` para los rewrites.

## Dudas que el agente debe resolver primero
1. ¿URL firmada absoluta o relativa? Con el front en `:3000` y los rewrites de `/api/v1`, una ruta relativa funciona en los dos modos de trabajo.
2. ¿Migraciones automáticas al arrancar o un comando aparte?
3. ¿Qué pasa con los datos que ya están en SeaweedFS en tu máquina? Lo más probable: son de prueba y se descartan. Confirmarlo.

## Fuera de alcance (pendiente aparte)
- **Datos de demo:** un comando que cree usuarios, solicitudes y documentos de ejemplo, para mostrar el proyecto al correrlo en local. Va en una tarea propia, al final.

## Definición de terminado
- `docker compose up -d` desde `backend/` levanta solo `postgres` y `backend`. Se puede cargar un documento como comprador, revisarlo como asesor, descargarlo y generar el ZIP, todo sin Redis ni SeaweedFS.
- `docker compose --profile full up -d` levanta lo de siempre y funciona igual que hoy.
- CI en verde, cobertura ≥ 95 %, contrato al día.

## Precisiones acordadas

### 0. Verificación inicial
- La base local tenía 15 migraciones sin aplicar (`crm`, `banking`, `applications`, `documents` y dos de `identity`). Se aplicaron con `migrate` antes de empezar, sin reiniciar contenedores.
- `CELERY_TASK_ALWAYS_EAGER` hoy no se lee del entorno: solo existe en `config/settings/test.py`.
- `.env.example` no es editable por el agente: en la Parte 3 el agente entrega las líneas exactas y Carlos las aplica.

### 1. URL firmada relativa
- `presigned_url` del backend `filesystem` devuelve una ruta relativa: `/api/v1/storage/objects/<token>`. Funciona con el frontend en `:3000` (rewrites de `/api/v1`) y directo en `:8000`. `DocumentDownload.url` es un `string` sin formato en el contrato, así que la ruta relativa no lo rompe.

### 2. Migraciones al arrancar
- Van en el `command` del servicio `backend` (no en un `ENTRYPOINT`, que correría también en `worker` y `storage-init`): `migrate --noinput && createcachetable && exec runserver 0.0.0.0:8000`. Ambos comandos se pueden repetir sin efecto; si una migración falla, el backend no arranca.

### 3. Datos de SeaweedFS
- No hay nada que migrar: el bucket tiene 0 objetos y la base 0 `file_objects`. El volumen `mvp_credit_seaweedfs_data` se conserva para el modo `full`.
- Hay un solo almacenamiento activo por proceso: los archivos de un modo no se ven desde el otro, y una descarga cruzada responde `503 DOWNLOAD_UNAVAILABLE`. Se documenta en el README. Leer cada archivo según su `storage_provider` queda fuera de esta tarea.

### 4. Endpoint de descarga
- La ruta `GET /api/v1/storage/objects/{token}` siempre está registrada, pero queda fuera del esquema OpenAPI (`exclude=True`). Responde 404 salvo que el backend sea `filesystem` y se admitan servicios falsos (`fake_services_allowed()`: DEBUG o `DOCUMENT_ALLOW_FAKE_SERVICES` en pruebas); el 404 no depende del token.
- Con el modo activo: token vencido o alterado → `403`; token válido de un objeto que ya no existe → `404`.
- `DOCUMENT_STORAGE_BACKEND=filesystem` sin DEBUG impide arrancar, igual que `memory`.
- Sin autenticación ni CSRF: la firma (`django.core.signing`, con sal propia y la expiración dentro del token) es la credencial. Sin límite de consumo propio: emitir el enlace ya está limitado (`document_download`). La URL no va a los logs.
- La respuesta es un `FileResponse` con el `Content-Type` firmado, `Content-Disposition: attachment` siempre (nunca `inline`, con el `attachment_disposition` de hoy), `Cache-Control: no-store` y `X-Content-Type-Options: nosniff`. Un test verifica los encabezados.

### 5. Modo inmediato
- `CELERY_TASK_ALWAYS_EAGER` se lee del entorno (`false` por defecto). `CELERY_TASK_EAGER_PROPAGATES = False` fijo en `base.py`; `test.py` mantiene `True`.
- En modo inmediato Celery ignora el `countdown` de `retry()`: los reintentos corren seguidos dentro de la petición. Se acepta: el estado final es el de hoy (`PENDING` para el análisis, `FAILED` con `STORAGE_UNAVAILABLE` para el paquete). Las tareas no cambian.
- Un fallo de la tarea en modo inmediato nunca llega a la petición del usuario: queda en el log con `logger.exception` y el id del archivo o del paquete.
- En modo inmediato, Celery igual pide un productor al broker al encolar (`producer_or_acquire`). Por eso, con `CELERY_TASK_ALWAYS_EAGER=true` el broker es siempre `memory://localhost/` y no se guardan resultados, aunque haya `REDIS_URL`. Sin modo inmediato, `REDIS_URL` vacío impide arrancar: ningún worker vería las tareas. Verificado en un proceso real: 0 conexiones al puerto 6379.
- Aviso en `.env.example` y en el README: el modo inmediato es para `DOCUMENT_SCANNER=fake`; con `clamd` caído, una carga puede esperar varios minutos.
- Pruebas, con almacenamiento que falla y `propagates=False`: la carga responde lo de siempre y el archivo queda `PENDING`; el paquete responde lo de siempre y queda `FAILED`; un error inesperado de la tarea no convierte la respuesta en 500.

### 6. Paso al modo `full`
- `.env` decide la configuración y el perfil decide los contenedores: pasar a `full` es cambiar de bloque en `.env` y usar `docker compose --profile full up -d`.
- Al arrancar, el backend escribe en el log una línea con el modo: `Servicios locales: almacenamiento=… · caché=… · tareas=… · antivirus=…`.
- `backend` depende de `postgres` (healthy) y de `redis` y `storage-init` con `required: false`.
- El README explica los dos pasos de cada modo y cómo confirmar con `check_document_services`.
