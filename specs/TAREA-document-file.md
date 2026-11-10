# Tarea: expediente documental (`documents`, paso 10)

## Objetivo
Materializar en cada solicitud la lista concreta de documentos que exigen los requisitos publicados (slots), dejar que el comprador cargue y reemplace archivos desde su portal, analizarlos de forma asíncrona (MIME real, tamaño, antivirus), permitir que el asesor los revise, apruebe, rechace o exonere, y generar de forma asíncrona el paquete ZIP para radicar. Con el expediente real se completa la guarda de `READY_TO_FILE` y la completitud.

Referencias: DER §8 y §12 (puntos 6 y 13), esquema SQL §7 y sus índices, API §5.5, §6, §19, §25, §26, §27.2, §27.3 y §28; REQUERIMIENTOS §4.3, §4.4, §5.6, §8.3, §8.8 ("Documento y observación"), §9, §10.4 (E2E 3, 4, 5, 8 y 14) y §11 (RNF-03, RNF-15, RNF-17 y RNF-19).

Tablas propias (DER_COMPLETO §15, orden 10): `file_objects`, `application_document_slots`, `document_files`, `document_reviews` y `document_package_jobs`.

Incluye los pendientes de pasos anteriores:

- `TAREA-applications.md`, pendiente 3: la parte documental de la guarda `APPLICATION_READY_TO_FILE` reemplaza a `DOCUMENTS_NOT_VERIFIED`; una lista sin requisitos obligatorios no la cumple; los requisitos se recalculan cuando cambia el perfil laboral (API §17.2); en `/completeness`, los documentos cuentan en `percentage` y `ready_to_file` se calcula con el expediente real.
- `TAREA-documents-config.md`, pendientes 1 a 7: formatos y tamaños para el comprador por sus slots, lista vacía, documentos de la solicitud frente a documentos del participante, varios archivos en un slot, huella y firma, grupo alternativo y tipos sin requisito.
- `TAREA-buyer-access.md`, pendiente 4: `document_files.uploaded_by_buyer_session_id` y la carga del comprador, incluido el reemplazo de slots observados después de `FILED`.

## Cuándo se construye
Paso 10 del orden de construcción (DER_COMPLETO §15), después del acceso del comprador (9). Rama `feat/document-file`, creada desde `master` (`6ee1248`).

**Fuera de alcance:**
- Radicación, respuestas del banco y observaciones (`filings`, `filing_document_snapshots`, `filing_responses`, `filing_response_observations`): paso 11. Este paso deja preparados el bloqueo de slots (`locked_at`) y el punto de enganche para saber si un slot tiene una observación abierta.
- Transiciones desde `READY_TO_FILE → FILED` en adelante: paso 11.
- Bitácora de cargas, revisiones y descargas (`activity_logs`, RF-61): paso 12. Mientras tanto, logs estructurados sin PII.
- Notificación al comprador de un rechazo (API §27.2 paso 6), `Idempotency-Key` y outbox: paso 13.
- Auditoría de descargas: paso 14.
- Resumen documental para broker y partner (REQUERIMIENTOS §12, "Durante diseño UX").
- Carga por parte del asesor en nombre del comprador: el esquema exige `uploaded_by_buyer_session_id NOT NULL` y REQUERIMIENTOS §4.4 y §13.4 dicen que el comprador es el único cargador.

---

## Avance

| Parte | Contenido | Estado | Commit |
| ---: | --- | --- | --- |
| 1 | Modelos, migraciones, semillas, `holder_scope` en la API y DER | Hecha | `3d7c1ac` |
| 2 | Infraestructura: almacenamiento, validación de archivos, antivirus y Celery | Hecha | `4e73503` |
| 3 | Materialización y recálculo de slots; lectura interna del expediente | Hecha | (pendiente de commit) |
| 4 | Portal del comprador: slots, carga, reemplazo y análisis asíncrono | Hecha | (pendiente de commit) |
| 5 | Revisión, exoneración y descargas | **Siguiente** | |
| 6 | Guarda de `READY_TO_FILE`, completitud y progreso del comprador | Pendiente | |
| 7 | Paquete ZIP asíncrono, README y documentación | Pendiente | |

Al cerrar la Parte 1: 1192 tests en verde (32 nuevos), 97,95 % de cobertura total, los modelos y la semilla nuevos al 100 % y el esquema OpenAPI sin avisos.

Al cerrar la Parte 2: 1262 tests en verde (70 nuevos), 98,03 % de cobertura total, `storage.py`, `scanning.py`, `file_validation.py` y los comandos al 100 %, y el esquema OpenAPI sin avisos. Además, verificado de punta a punta con SeaweedFS, ClamAV y Celery reales (ver "Decididas en la implementación", Parte 2).

Al cerrar la Parte 3: 1311 tests en verde (49 nuevos), 98,09 % de cobertura total, `slots.py`, `dossier.py`, `dossier_serializers.py` y `dossier_views.py` al 100 %, y el esquema OpenAPI sin avisos.

Al cerrar la Parte 4: 1361 tests en verde (50 nuevos), 98,16 % de cobertura total, `uploads.py`, `scans.py`, `tasks.py`, `buyer_views.py`, `buyer_serializers.py` y `requeue_pending_scans` al 100 %, y el esquema OpenAPI sin avisos. Además, verificado de punta a punta con SeaweedFS y clamd reales (ver "Decididas en la implementación", Parte 4).

Sin cubrir, de antes de este paso: `admin.py` (los `has_*_permission` de `_ReadOnlyAdmin`), el `unseed` de `documents 0002` y cuatro ramas de `services.py` (líneas 87, 261, 288 y 386).

---

## Cómo retomar en una sesión nueva

### Reglas de trabajo (las fija el usuario)
- Antes de programar una parte, confirmar el alcance si surge una ambigüedad nueva. Cada parte es un commit con sus tests.
- **Correr los 5 checks en verde antes de proponer un commit**: `ruff check .`, `ruff format --check .`, `mypy .`, `python manage.py makemigrations --check --dry-run` y `pytest --cov=apps --cov-report=term-missing` (el CI exige `--cov-fail-under=95`).
- Validar también el esquema: `python manage.py spectacular --validate --fail-on-warn --file /tmp/s.yml`, que debe seguir **sin avisos**.
- Todo con anotaciones de tipos. Nada de `type: ignore` ni `noqa` sin justificar.
- **Git solo en modo lectura.** El usuario hace los commits y los pushes.
- Las propuestas de commit van **sin `Co-Authored-By` ni firma**. Mensajes cortos, en inglés, con el estilo `feat(documents): ...`.

### Entorno local
- **No hay entorno Python local.** Todo corre en Docker; si `docker` responde "failed to connect to the docker API", hay que abrir Docker Desktop (`C:\Program Files\Docker\Docker\Docker Desktop.exe`) y esperar a que `docker info` conteste.
- **`.env` y `.env.example` están en la lista de rutas denegadas**: no se leen ni se editan (ni con `cat` ni con la herramienta de lectura). Las variables nuevas se documentan en el README y se le pasan al usuario las líneas para que las copie a los dos archivos. La de la Parte 2 ya se le entregó; **al empezar, confirmar con el usuario que las agregó**, porque sin `DOCUMENT_STORAGE_ACCESS_KEY_ID` y `DOCUMENT_STORAGE_SECRET_ACCESS_KEY` SeaweedFS no arranca y `backend` tampoco (espera a `storage-init`).
- **Checks** en un contenedor efímero con clave ficticia y `--no-deps` (no levanta SeaweedFS ni `storage-init`). PostgreSQL sí tiene que estar arriba (`docker compose up -d postgres`):

  ```bash
  docker compose run --rm --no-deps -e AUTH_JWT_SIGNING_KEY=local-dev-only-not-a-secret backend sh -c '
    ruff check . && ruff format --check . && mypy . &&
    python manage.py makemigrations --check --dry-run &&
    python manage.py spectacular --validate --fail-on-warn --file /tmp/s.yml &&
    pytest --cov=apps --cov-report=term-missing --cov-fail-under=95 -q -p no:cacheprovider'
  ```

  `ruff format <rutas>` dentro del mismo contenedor formatea los archivos tocados (el volumen `.:/app` escribe en el host).
- **El CI no tiene Redis, SeaweedFS ni ClamAV.** Los tests usan `config.settings.test`: `DOCUMENT_STORAGE_BACKEND=memory`, `DOCUMENT_SCANNER=fake`, `DOCUMENT_ALLOW_FAKE_SERVICES=True` y `CELERY_TASK_ALWAYS_EAGER=True`.
- **Finales de línea.** El repo es mayoritariamente LF, pero **42 archivos versionados son CRLF**, no solo los obvios: `config/settings/base.py`, `config/settings/test.py`, `docker-compose.yml`, `README.md`, `.env.example`, `tests/conftest.py`, buena parte de `apps/identity/` (por ejemplo `throttling.py`, `permissions.py` y `authentication.py`) y archivos sueltos de `catalogs` y `crm`. `docs/MODELO_DATOS_DER_MVP_CREDITO.md` tiene finales **mezclados** (86 líneas CRLF). **Antes de tocar un archivo existente, mirarlo con `git ls-files --eol <archivo>`** (`i/crlf` = CRLF).
  - En la Parte 4, un `read_text`/`write_bytes` de Python dejó `tests/conftest.py` en LF, y un `sed -i` con una línea agregada por heredoc dejó `apps/identity/throttling.py` en LF. Se restauraron con `sed -i 's/$/\r/'` sobre el archivo entero (solo si quedó sin ningún CR).
  - Los CRLF se editan con la herramienta de edición, que los conserva; nunca con `sed -i`.
  - En el archivo mezclado, la herramienta de edición lo deja todo en LF. Después de editarlo hay que restaurar los CR de las líneas no tocadas (en la Parte 1 se hizo con un script que alinea contra `git show HEAD:<archivo>`).
  - Con Python del host, escribir con `write_bytes` (o `newline="\n"`): `write_text` en Windows convierte LF a CRLF y el diff sale del archivo entero.
  - Comprobación rápida: `tr -cd '\r' < archivo | wc -c` frente a `git show HEAD:archivo | tr -cd '\r' | wc -c`.
- **Shell.** Un heredoc de bash con Python que lleva comillas o barras invertidas puede fallar al interpretarse: escribir el script en el *scratchpad* y correrlo con `python -I`. En `docker run -v` con rutas de Windows, anteponer `MSYS_NO_PATHCONV=1`.
- **Prueba de punta a punta** (sin tocar `.env`): exportar credenciales temporales en el shell (`DOCUMENT_STORAGE_ACCESS_KEY_ID`, `DOCUMENT_STORAGE_SECRET_ACCESS_KEY`), `docker compose --profile async up -d clamav seaweedfs` y correr comandos con `docker compose run --rm --no-deps -e ...` pasando los `DOCUMENT_STORAGE_*` de SeaweedFS (`ENDPOINT_URL=http://seaweedfs:8333`, `PUBLIC_ENDPOINT_URL=http://localhost:8333`, `ADDRESSING_STYLE=path`, `SSE=` vacío) y `DOCUMENT_SCANNER=clamd`. Al terminar: `docker compose --profile async stop seaweedfs clamav`, `rm -f` de los dos y `docker volume rm mvp_credit_seaweedfs_data`. El volumen `mvp_credit_clamav_data` se conserva: guarda las firmas y evita bajarlas otra vez (varios minutos).

### Lo que ya existe y se reutiliza
**De pasos anteriores:**
- `apps/documents/constants.py`: `ALLOWED_MIME_TYPES` (PDF, JPEG, PNG) y `MAX_FILE_SIZE_BYTES` (10 MB).
- `apps/documents/services.py`: `applicable_requirements`, `requirement_applies_to`, `ParticipantCase`, `preview_checklist` (devuelve `ChecklistPreview`) e `is_application_document`, punto de partida de la materialización.
- `apps/applications/services.py`: `documents_verified(application)` (hoy `False`, punto de enganche), `_ready_to_file_problems`, `completeness` → `Completeness`, `lock_for_edit`, `bump_version`, `applications_visible_to`, `Actor = User | BuyerSession` y `DOCUMENTS_NOT_VERIFIED_MESSAGE` (se elimina en la Parte 6).
- `apps/applications/signals.py`: se envían **después del commit**; por eso la sincronización de slots no se cuelga de ellos (decisión 6).
- `apps/applications/concurrency.py`: `expected_version`, `ensure_version` y `with_etag`.
- `apps/identity/buyer_authentication.py`: `BuyerSessionAuthentication`, `IsBuyerSession`, `ApplicationNotClosed` y `ConsentsAccepted`; `buyer_portal_views.BuyerPortalView` como base de las vistas del comprador.
- `apps/identity/throttling.py`: patrón de `AuthRateThrottle` sobre Redis, con tasas en `AUTH_RATE_LIMITS`.
- `apps/identity/buyer_portal.py`: progreso del comprador = ítems de `completeness` sin `bank_evaluation`.

**De la Parte 1 (`3d7c1ac`):**
- Modelos en `apps/documents/models/`: `FileObject`/`ScanStatus`, `ApplicationDocumentSlot`/`SlotStatus`, `DocumentFile`/`DocumentFileStatus`, `DocumentReview`/`ReviewDecision`, `DocumentPackageJob`/`PackageJobStatus` y `HolderScope` (en `DocumentType`).
- Relaciones inversas: `application.document_slots`, `participant.document_slots`, `document_type.slots`, `requirement.slots`, `slot.files`, `file_object.document_file`, `document_file.reviews`, `application.document_package_jobs`, `file_object.package_job`, `user.document_reviews`, `user.document_package_jobs` y `buyer_session.document_files`. `slot.current_file` no tiene relación inversa (`related_name="+"`).
- Migraciones `documents 0003_dossier` y `0004_seed_dossier` (permisos, catálogos `document_rejection_reason` y `document_waiver_reason`, y `holder_scope`).
- Fixtures en `tests/applications/dossier/conftest.py`: `make_file_object`, `make_slot` (titular de `application`, cédula por omisión), `buyer_session`, `make_document_file`, y `make_link`/`make_session` reexportados de `buyer_access`. Tipos `SlotFactory`, `FileObjectFactory` y `DocumentFileFactory`.

**De la Parte 2 (`4e73503`):**
- `apps/documents/storage.py`: `get_storage()` → `ObjectStorage` (`put`, `open`, `delete`, `presigned_url`, `ensure_bucket`, `check`, `provider`, `bucket`, `encryption_key_version`), `new_document_key(application_id)`, `new_package_key(application_id)` y `attachment_disposition`. En tests, `get_storage()` devuelve un `MemoryStorage` compartido por el proceso (`.objects`, `.clear()`); `get_storage.cache_clear()` lo reinicia.
- `apps/documents/file_validation.py`: `inspect_upload(stream, filename=, declared_mime_type=, allowed_mime_types=, max_size_bytes=)` → `InspectedFile`. Deja el flujo al inicio.
- `apps/documents/scanning.py`: `get_scanner()` → `Scanner` (`scan(stream) -> ScanResult`, `ping()`, `name`). `EICAR` es la firma de prueba para los tests.
- `apps/documents/exceptions.py`: `UnsupportedFileType`, `FileTooLarge`, `StorageUnavailable` y `ScannerUnavailable`.
- Comandos `init_document_storage` y `check_document_services`.
- `config/celery.py` (`celery_app` en `config/__init__.py`): las tareas de las Partes 4 y 7 se declaran con `@shared_task` en `apps/documents/tasks.py` y `autodiscover_tasks` las encuentra.

**De la Parte 3:**
- `apps/documents/slots.py`: `sync_slots(locked) -> SlotSync` (`created`, `retired`, `revived`, `updated`, `changed`), `desired_slots`, `merge_requirements` y `SNAPSHOT_FIELDS`. Ya lo llaman los servicios de `applications` (ver "Decididas en la implementación", Parte 3).
- `apps/documents/dossier.py`: `slots_queryset()` (con `set_size` anotado y el orden de presentación), `slots_visible_to(user)`, `application_slots(application, include_retired=)`, `slot_versions(slot)` y `refresh_slots(actor, application)`.
- `apps/documents/dossier_serializers.py`: `slot_label`, `DocumentSlotSerializer`, `DocumentFileSerializer` (con `reviews` e `internal_comment`: solo para uso interno), `FileMetadataSerializer` y `SlotRefreshSerializer`.
- `apps/documents/dossier_views.py`: `DossierView` (`get_application`, `get_slot`), base para las vistas internas de la Parte 5.
- Tests en `tests/applications/dossier/test_slots.py` (helpers `sync`, `requirement`, `set_profile`, `seeded_requirement`, `publish_version`) y `test_slots_api.py` (fixture `dossier`: Bancolombia, titular empleado y un documento de la solicitud; 8 slots).

**De la Parte 4:**
- `apps/documents/uploads.py`: `upload_document(session, slot, Upload(...))`, `upload_block(application, slot)` (el error que impediría cargar, o `None`; lo usa también `can_upload`), `slot_has_open_observation(slot)` (enganche del paso 11, hoy `False`), `buyer_slots(session)` y `UPLOADABLE_STATUSES`.
- `apps/documents/scans.py`: `scan_document_file(file_object_id)` y `SECURITY_REJECTION_MESSAGE`. `apps/documents/tasks.py`: `scan_file_object` (reintentos con `scan_retry_delay`). Comando `requeue_pending_scans`.
- `apps/documents/dossier.py`: `buyer_slot_queryset(session)` y `buyer_versions(slot)`.
- `apps/documents/buyer_serializers.py`: `BuyerDocumentSlotSerializer` (necesita `context["application"]`), `BuyerDocumentFileSerializer`, `BuyerDocumentVersionSerializer` (`context["current_file_id"]`), `BuyerRejectionSerializer`, `version_rejection(version)` y `BuyerDocumentUploadSerializer`.
- `apps/documents/buyer_views.py`: `BuyerDossierView` (`get_slot`, `slot_context`, `slot_response`), base para la descarga del comprador de la Parte 5.
- Errores nuevos en `apps/documents/exceptions.py`: `DocumentLocked`, `DocumentNotRejected`, `DocumentQuotaExceeded`, `PayloadTooLarge` (`413`) y `UploadUnavailable` (`503 SERVICE_UNAVAILABLE`). Throttle `BuyerDocumentUploadRateThrottle` en `apps/identity/throttling.py`.
- Tests: `tests/applications/dossier/test_buyer_dossier_api.py` (helpers `pdf`, `upload`, `memory`, `session_of`, `decide`) y `test_scans.py` (fixture `current_version` y `eager_retries`). `tests/conftest.py` limpia el `MemoryStorage` después de cada test. El `conftest.py` de `dossier` reexporta `portal`, `buyer_client`, `buyer_csrf_client` y `accept_consents`.

### Próximo paso: Parte 5
- `PATCH /document-slots/{id}/review` según las decisiones 7 y 8 y las acordadas 6 y 8, sobre `DossierView`: bloqueo del slot, `document_file_id` vigente (`409 DOCUMENT_NOT_CURRENT`), aprobar solo `CLEAN` (`409 FILE_NOT_CLEAN`), vigencia (`document_date` corregible, `422 DOCUMENT_EXPIRED`), rechazo con `reason_code` y `buyer_comment`, corrección de una decisión (fila nueva) y exoneración del grupo alternativo.
- Al aprobar o rechazar, la versión deja `IN_REVIEW`; al exonerar, `waiver_reason_item`. Ninguna toca la versión de la solicitud.
- Descargas (decisión 13): `GET /document-files/{id}`, `.../scan-status` y `.../download` (interno, `documents.download`) y `GET /buyer/document-files/{id}/download` (sobre `BuyerDossierView`), con rate limit de 60/h por usuario o sesión y la URL fuera de los logs. Variable nueva `DOCUMENT_DOWNLOAD_URL_SECONDS`: documentarla en el README y pasarle al usuario la línea para `.env.example` y `.env`.
- El rechazo que ve el comprador ya sale de la última revisión (`version_rejection`): no hay que tocar los DTO del comprador.

---

## Decisiones por defecto (confirmadas)

Salen de los documentos o del precedente de los pasos anteriores. El usuario no vetó las 1 a 13, confirmó explícitamente las 14 a 24 antes de la Parte 1 y ajustó la 12 (60 cargas por hora).

1. **Solo el comprador carga** (esquema, REQUERIMIENTOS §4.4 y §13.4). El asesor revisa, exonera y descarga, pero no carga.
2. **Rutas del comprador bajo `/buyer/...`** con DTO propios (precedente de `TAREA-buyer-access.md`, decisión 10). API §19 lista al comprador en las rutas internas: se corrige.

   | Método | Ruta | Actor |
   | --- | --- | --- |
   | `GET` | `/applications/{id}/document-slots` | interno |
   | `POST` | `/applications/{id}/document-slots/refresh` | interno |
   | `GET` | `/document-slots/{slot_id}` | interno |
   | `GET` | `/document-slots/{slot_id}/versions` | interno |
   | `PATCH` | `/document-slots/{slot_id}/review` | interno |
   | `GET` | `/document-files/{file_id}` | interno |
   | `GET` | `/document-files/{file_id}/download` | interno |
   | `GET` | `/document-files/{file_id}/scan-status` | interno |
   | `POST` | `/applications/{id}/document-package-jobs` | interno |
   | `GET` | `/document-package-jobs/{job_id}` | interno |
   | `GET` | `/document-package-jobs/{job_id}/download` | interno |
   | `GET` | `/buyer/applications/{id}/document-slots` | comprador |
   | `GET` | `/buyer/document-slots/{slot_id}` | comprador |
   | `GET` | `/buyer/document-slots/{slot_id}/versions` | comprador |
   | `POST` | `/buyer/document-slots/{slot_id}/uploads` | comprador |
   | `GET` | `/buyer/document-files/{file_id}/download` | comprador |

3. **Mandan los estados del esquema.** Slot: `PENDING`, `UPLOADED`, `APPROVED`, `REJECTED`, `WAIVED` (API decía `MISSING` e `IN_REVIEW`). Análisis: `PENDING`, `CLEAN`, `INFECTED`, `INVALID` (API decía `PENDING_SCAN`). Versión (`document_files.status`):
   - `UPLOADED`: cargada, análisis pendiente;
   - `IN_REVIEW`: análisis `CLEAN`, espera la decisión del asesor;
   - `APPROVED` / `REJECTED`: decisión del asesor; también `REJECTED` cuando el análisis da `INFECTED` o `INVALID` (sin fila en `document_reviews`, porque `reviewer_id` es obligatorio). El slot pasa a `REJECTED` y el comprador ve un mensaje fijo ("El archivo no pasó la validación de seguridad").
   Se corrige API §19 y el catálogo `document_status` no cambia.
4. **Qué puede cargar el comprador antes de `FILED`.** Slots `PENDING`, `UPLOADED` y `REJECTED`. Sobre un slot `APPROVED` o `WAIVED`: `409 DOCUMENT_LOCKED`. Si el asesor quiere un archivo nuevo, primero rechaza la versión aprobada (la revisión admite corregir una decisión anterior). Cada carga crea una versión nueva (`version_number` consecutivo bajo `select_for_update` del slot), mueve `current_file_id` y deja el slot en `UPLOADED`. La versión anterior se conserva con su estado.
5. **Después de `FILED`** (aún inalcanzable hasta el paso 11): solo en un slot `REJECTED` con observación abierta; si no, `409 DOCUMENT_NOT_REJECTED`; un slot con `locked_at` y sin observación, `409 DOCUMENT_LOCKED`. "Observación abierta" es un punto de enganche `slot_has_open_observation(slot)` que **falla cerrado** (devuelve `False`) hasta el paso 11, igual que `documents_verified` en el paso 8. Los tests lo simulan con `monkeypatch`. Con la solicitud terminada, `409 APPLICATION_CLOSED` (permiso `ApplicationNotClosed`). La carga exige los consentimientos (`ConsentsAccepted`).
6. **La sincronización de slots corre en la misma transacción** que el cambio que la provoca, con la solicitud bloqueada. Los servicios de `applications` llaman a un único punto `documents.slots.sync_slots(locked)` después de cambiar producto, finalidad, condición del inmueble, participantes o perfil laboral. No se usa `application_updated`, que sale después del commit.
7. **Grupo alternativo** (pendiente 6). Se evalúa por participante: el grupo queda cumplido con un slot `APPROVED`. Exonerar un slot del grupo exonera todos los slots del grupo de ese participante, con el mismo motivo, en la misma transacción.
8. **Revisión** (`PATCH /document-slots/{slot_id}/review`):
   - `decision`: `APPROVED`, `REJECTED` o `WAIVED`;
   - `APPROVED` y `REJECTED` llevan `document_file_id` y solo valen sobre el archivo vigente del slot (acordada 6); aprobar exige análisis `CLEAN` (`409 FILE_NOT_CLEAN`) y la vigencia de la acordada 8, y rechazar exige `reason_code` y `buyer_comment` (el `CHECK` del esquema);
   - bloquea la fila del slot (`select_for_update`), sin `If-Match`: los documentos no tocan la versión de la solicitud;
   - `WAIVED` exige `is_waivable`, `reason_code` del catálogo de exoneración y el permiso `documents.waive`; no crea fila en `document_reviews` (no hay versión), queda en el slot (`waiver_reason_item_id`);
   - una revisión sobre una versión ya decidida es una corrección: fila nueva en `document_reviews`, nunca se edita la anterior;
   - `internal_comment` nunca sale hacia el comprador.
9. **Catálogos nuevos** (propuesta editable, `is_manageable = true`):
   - `document_rejection_reason` (público): `ILLEGIBLE`, `INCOMPLETE`, `OUTDATED`, `WRONG_DOCUMENT`, `DATA_MISMATCH`, `OTHER`;
   - `document_waiver_reason` (interno): `NOT_APPLICABLE`, `BANK_EXEMPTED`, `REPLACED_BY_OTHER_SUPPORT`, `OTHER`.
10. **Permisos nuevos:**
    - `documents.read` (`ADMIN`, `ADVISOR`): leer slots, versiones, metadatos y estado del análisis;
    - `documents.review` y `documents.waive` (`ADMIN`, `ADVISOR`);
    - `documents.manage_requirements` (`ADMIN`, `ADVISOR`): `refresh`;
    - `documents.download` (`ADMIN`, `ADVISOR`);
    - `filings.prepare` (`ADMIN`, `ADVISOR`): paquetes. Se siembra aquí aunque el módulo `filings` llegue en el paso 11.
    - El asesor siempre dentro de su alcance (asignadas, `404` fuera de él). Broker y partner: `403` en todo.
11. **Límites de la carga:**
    - MIME real por firma de bytes (`%PDF-`, `FF D8 FF`, `89 50 4E 47 0D 0A 1A 0A`), sin `libmagic`: la lista es cerrada. Debe estar en `allowed_mime_types` del tipo y coincidir con la extensión; doble extensión, extensión ejecutable o MIME declarado incoherente: `422 UNSUPPORTED_FILE_TYPE` (código nuevo);
    - tamaño: vacío `400`; mayor que `max_size_bytes` del tipo, `422 FILE_TOO_LARGE` (código nuevo); un cuerpo mayor que el límite global (10 MB + margen del multipart) se corta antes de leerlo con `413`;
    - nombre: se quita la ruta y los caracteres de control, se normaliza a NFC y se corta a 255;
    - cuota por solicitud: 20 versiones por slot y 200 MB por solicitud (`DOCUMENT_UPLOAD_MAX_VERSIONS_PER_SLOT`, `DOCUMENT_UPLOAD_QUOTA_BYTES`), `409 DOCUMENT_QUOTA_EXCEEDED` (código nuevo);
    - `document_date` opcional en la carga (fecha de expedición o periodo); el asesor puede corregirla al aprobar.
12. **Rate limits.** Carga: **60/h** por sesión + solicitud (lo fijó el usuario al confirmar las decisiones; API §26 sugería 30/h y REQUERIMIENTOS §9.3, 30/min). Descargas: 60/h por usuario o sesión.
13. **Descarga por URL firmada** (API §19, RNF-03): `GET .../download` responde `200 {url, expires_at}` con una URL prefirmada de 5 minutos (`DOCUMENT_DOWNLOAD_URL_SECONDS`), `Content-Disposition: attachment` y el `Content-Type` detectado. Solo archivos `CLEAN`; `PENDING`, `INFECTED` o `INVALID`: `409 FILE_NOT_CLEAN`. La URL nunca va a logs.
14. **`Idempotency-Key` del paquete se aplaza al paso 13** (precedente de las decisiones 2 y 8 de pasos anteriores). Mientras tanto, si ya hay un trabajo `PENDING`, `RUNNING` o `COMPLETED` no vencido con la misma huella documental (decisión 23), el `POST` lo devuelve con `200` en lugar de crear otro (`201`).
15. **Paquete:**
    - precondición: `documents_verified` (Parte 6), evaluada con los slots bloqueados; si no, `422 APPLICATION_NOT_READY` con los mismos `details` de la guarda, incluido `DOCUMENT_EXPIRED`. API §19.2 dice `409`, pero el código ya es `422` desde el paso 8: se corrige la API;
    - **el contenido se fija al crear el trabajo**, no cuando corre el worker: el `POST` guarda en `manifest` la lista de versiones (ids y SHA-256) y la huella, y el worker empaqueta exactamente esa lista. Una carga posterior no se cuela en el ZIP;
    - `application_version` (obligatoria en el esquema) guarda la versión de la solicitud al pedir el paquete, como dato informativo;
    - se admite en cualquier estado no terminal; el paso 11 exigirá que el paquete corresponda a la versión actual al radicar;
    - contenido: la versión vigente aprobada de cada slot vigente (las exoneradas no llevan archivo), en carpetas por participante, más `manifest.json` con ids, tipo, participante, versión, nombre, tamaño y SHA-256. El mismo manifiesto queda en `document_package_jobs.manifest`;
    - antes de empaquetar se verifica el SHA-256 de cada objeto; si no coincide, `FAILED` con `error_code = CHECKSUM_MISMATCH`;
    - vence a los 7 días (`DOCUMENT_PACKAGE_TTL_DAYS`); el estado `EXPIRED` se deriva al leer y un comando `expire_document_packages` lo persiste y borra el objeto.
16. **Pendientes de configuración que quedan igual:**
    - huella y firma física de `IDENTITY_DOCUMENT` (pendiente 5): se aplaza al paso 11, porque es una condición de la entrega física al banco;
    - `CO_APPLICANT_INCOME_SUPPORT` y `EXTERNAL_APPROVAL_LETTER` (pendiente 7): siguen sin requisito y no generan slots.
17. **Un tipo repetido para el mismo titular.** Si dos requisitos vigentes piden el mismo tipo para el mismo titular (por ejemplo, uno general y uno del producto), se crea un solo juego de slots con la combinación más estricta: obligatorio si alguno lo es, el mayor `minimum_files`, la menor `validity_days` y exonerable solo si ambos lo son. `requirement_id` apunta al más estricto.
18. **Reglas de `holder_scope`** (complementan la decisión acordada 4):
    - un requisito sobre un tipo `APPLICATION` no puede llevar `participant_role` ni `employment_profile_code` (`400`);
    - el tipo no puede cambiar de `holder_scope` mientras tenga requisitos `DRAFT` o `ACTIVE` (`400` en `holder_scope`, igual que el cambio de `is_repeatable`; ver "Decididas en la implementación", Parte 1);
    - los slots ya creados conservan su titular;
    - `POST /document-requirements/preview` agrega `application_requirements`: los de la solicitud, fuera de la lista por participante.
19. **`EXTERNAL_APPROVAL_LETTER` también es `APPLICATION`**: es de la solicitud, no de una persona, aunque hoy no tenga requisito.
20. **Unicidad de los slots.** Índice único parcial sobre (`application`, `participant`, `document_type`, `slot_index`) con `NULLS NOT DISTINCT`, limitado a los slots vigentes (`WHERE retired_at IS NULL`, acordada 5). Reemplaza la "UQ funcional según tipo/participante/periodo" que el DER deja abierta.
21. **Errores nuevos** (API §5.5): `UNSUPPORTED_FILE_TYPE`, `FILE_TOO_LARGE` y `DOCUMENT_QUOTA_EXCEEDED` (decisión 11), `DOCUMENT_NOT_CURRENT` (`409`, acordada 6) y `DOCUMENT_EXPIRED` (`422` al aprobar un documento vencido, acordada 8). Ya existían en la API y se implementan: `DOCUMENT_LOCKED`, `DOCUMENT_NOT_REJECTED` y `FILE_NOT_CLEAN`. `DOCUMENTS_NOT_VERIFIED` se reemplaza en los `details` de `APPLICATION_NOT_READY` por `DOCUMENT_PENDING` (uno por slot o grupo sin cumplir, con `resource_id` = slot y el participante en el mensaje), `DOCUMENT_EXPIRED` y `DOCUMENTS_NOT_CONFIGURED` (lista sin obligatorios).
22. **Orden de los bloqueos.** Siempre solicitud y después slots, ordenados por id, para no crear interbloqueos: la carga bloquea la solicitud (cuota) y el slot; la revisión, el slot; la guarda y el paquete, la solicitud y todos sus slots vigentes.
23. **Huella documental.** SHA-256 de la lista, ordenada por `slot_id`, de los slots vigentes con `(slot_id, status, current_file_id, sha256 del archivo vigente, waiver_reason_item_id, expires_at)`. Un único servicio, `dossier_fingerprint(application)`, la calcula para el paquete, el paso 11 y los tests.
24. **Lista sin obligatorios en la completitud.** `documents_percentage = 0` con el mensaje de `DOCUMENTS_NOT_CONFIGURED`: no puede llegar a 100 si no hay nada que cumplir.

---

## Preguntas abiertas

No quedan. Las dos tandas y la precisión de SeaweedFS están en "Decisiones (acordadas con el usuario)". Las ambigüedades nuevas que surjan al programar se consultan antes de la parte correspondiente.

---

## Plan de las partes

### Parte 1. Modelos, migraciones, semillas y configuración (hecha)
- Modelos fieles al esquema en `apps/documents/models/` (`file_object.py`, `slot.py`, `document_file.py`, `review.py`, `package_job.py`), con los `CHECK`, UQ e índices del esquema (`ix_file_objects_scan_queue`, `ix_document_slots_*`, `ix_document_files_versions`, `ix_document_reviews_latest`, `ix_document_package_jobs_*`). Los nombres se acortan a 30 caracteres si hace falta, como `ix_doc_requirements_active`.
- `current_file_id`: FK diferible (`DEFERRABLE INITIALLY DEFERRED`, `SET NULL`) con la operación de migración que corresponda.
- Columnas fuera del DER: `application_document_slots.slot_index` (acordada 3), `document_types.holder_scope` (acordada 4) y `application_document_slots.retired_at` (acordada 5). `documents 0003` agrega `holder_scope` con `PARTICIPANT` por omisión y lo siembra.
- Validaciones de `holder_scope` en la API de tipos y requisitos, y `application_requirements` en el preview (decisión 18).
- Semillas: permisos (decisión 10), catálogos (decisión 9) y `holder_scope = APPLICATION` en los tipos de la acordada 4.
- Configuración: se movió a la parte que la usa (ver "Decididas en la implementación", Parte 1).
- DER y esquema SQL: las tres columnas nuevas y el índice único parcial, marcados como desvío (acordadas 3, 4 y 5). `ix_document_slots_pending` y `ix_document_slots_application_status` agregan `retired_at IS NULL`.
- Admin de solo lectura sin `object_key`.
- Tests de restricciones y semillas en `tests/applications/dossier/`.

### Parte 2. Infraestructura (hecha)
- `config/celery.py` y su carga en `config/__init__.py`.
- `apps/documents/storage.py`: interfaz, adaptador S3 y fake en memoria.
- `apps/documents/file_validation.py`: firma de bytes, extensión, nombre y tamaño.
- `apps/documents/scanning.py`: cliente `clamd` (`INSTREAM`) y escáner fake.
- `docker-compose.yml`: `seaweedfs` y `storage-init` (creación del bucket privado al arrancar) en el perfil por omisión, y `clamav` en el perfil `async`, junto al `worker`. Sin tocar `.env`.
- Variables de la acordada 1, con valores de SeaweedFS local: las líneas para que el usuario las copie a `.env.example` y a `.env`.
- README: cómo levantar el perfil `async` (`docker compose --profile async up`) y cómo comprobar SeaweedFS y ClamAV.
- Tests unitarios con dobles: socket fake para `clamd` y cliente `boto3` sustituido. Sin servicios reales en el CI.

### Parte 3. Slots: materialización, recálculo y lectura interna
- `documents/slots.py`: `sync_slots(locked)` a partir de `applicable_requirements` y los participantes activos (rol y perfil laboral), con `bulk_create`; un slot por archivo (`slot_index`), un slot de solicitud para los tipos `APPLICATION`, y retiro, reactivación y actualización del snapshot de la acordada 5.
- Llamadas desde los servicios de `applications` (decisión 6): creación, `PATCH` de producto o finalidad, financiación, inmueble (condición), alta y retiro de participantes y perfil financiero.
- `POST /applications/{id}/document-slots/refresh`: solo antes de `FILED` (`409 APPLICATION_NOT_EDITABLE`); responde la lista con lo creado, retirado y reactivado.
- `GET /applications/{id}/document-slots` (filtros `status`, `participant_id`, `document_type_code`, `required`), `GET /document-slots/{id}` y `GET /document-slots/{id}/versions`.
- Matriz de permisos: admin, asesor asignado y no asignado, broker y partner.

### Parte 4. Portal del comprador: carga y análisis
- `GET /buyer/applications/{id}/document-slots`, `GET /buyer/document-slots/{id}` y `.../versions`, con `allowed_mime_types`, `max_size_bytes`, `minimum_files`, `buyer_comment` y motivo del último rechazo, sin `internal_comment` ni revisor (pendiente 1 de la configuración).
- `POST /buyer/document-slots/{id}/uploads` (`multipart/form-data`): validación, hash, almacenamiento, `file_objects` `PENDING`, versión nueva, slot `UPLOADED`, encolado del análisis en `on_commit` (decisiones 4, 5, 11 y 12).
- Tarea `scan_file_object`: `CLEAN` → versión `IN_REVIEW`; `INFECTED`/`INVALID` → versión y slot `REJECTED` (decisión 3).
- Tests: otro expediente `404`, sin CSRF `403`, sin consentimiento `403 CONSENT_REQUIRED`, slot aprobado `409 DOCUMENT_LOCKED`, después de `FILED` con y sin observación, cuota, `429`, dos cargas simultáneas en el mismo slot (consecutivo único).

### Parte 5. Revisión, exoneración y descargas
- `PATCH /document-slots/{id}/review` (decisiones 7 y 8) sobre un `document_file_id` concreto (acordada 6), con `document_date` corregible y la vigencia de la acordada 8.
- `GET /document-files/{id}`, `.../scan-status` y `.../download` (interno), y `GET /buyer/document-files/{id}/download` (decisión 13).
- Tests: aprobar sin `CLEAN`, aprobar un archivo que ya no es el vigente (`409 DOCUMENT_NOT_CURRENT`), aprobar sin `document_date` o vencido, rechazar sin comentario, exonerar no exonerable, exoneración del grupo, corrección de una decisión, descarga de un archivo infectado, la URL no aparece en logs.

### Parte 6. Guarda, completitud y progreso
- `documents_verified` y los `details` de la decisión 21 en `_ready_to_file_problems`, evaluados dentro de la transacción de la transición con los slots bloqueados (acordada 6); se elimina `DOCUMENTS_NOT_VERIFIED_MESSAGE`.
- `dossier_fingerprint` (decisión 23).
- Lista sin obligatorios: `DOCUMENTS_NOT_CONFIGURED` (pendiente 2).
- Vigencia de la acordada 8: antes de `FILED`, un aprobado vencido cuenta como no cumplido.
- `/completeness` y progreso del comprador (`buyer_portal.py`) según la acordada 7.
- Se reemplazan los `monkeypatch` de `documents_verified` de los tests del paso 8 por expedientes reales.

### Parte 7. Paquete, README y documentación
- `POST /applications/{id}/document-package-jobs`, `GET /document-package-jobs/{id}` y `.../download` (decisiones 14 y 15).
- Tarea `build_document_package`: empaqueta las versiones del `manifest` fijado en el `POST` (decisión 15), `RUNNING`, ZIP en streaming hacia el almacenamiento, `COMPLETED` o `FAILED` con `error_code`; reintentable.
- Comando `expire_document_packages`.
- README: sección "Document Dossier", servicios `seaweedfs`/`clamav`/`worker` y "Current Status" en el paso 10.
- Documentación: API §5.5, §6, §8, §16.3 (guarda), completitud, §19, §23.4 (`holder_scope` y `application_requirements` del preview, Parte 1), §25, §26 y §27.2; DER §7.10 y §8.2 y esquema SQL (si no se hicieron en la Parte 1); `TAREA-applications.md` y `TAREA-documents-config.md` marcan sus pendientes como hechos.

---

## Decisiones (acordadas con el usuario)

### Tanda 1

1. **Almacenamiento: S3 compatible, con SeaweedFS en local** (era MinIO; ver la precisión del cierre de la lista).
   - Interfaz propia (`put`, `open`, `delete`, `presigned_url`) con un adaptador S3 y un fake en memoria para tests y CI. El adaptador usa `boto3` directo (ver "Decididas en la implementación", Parte 2).
   - SeaweedFS en `docker-compose` para desarrollo.
   - Un bucket privado con prefijos `documents/` y `packages/`. `object_key` = `documents/<application_id>/<uuid>`, sin el nombre original. Cifrado SSE del proveedor (`encryption_key_version = "SSE-S3"`).
   - Descarga por URL prefirmada de 5 minutos (decisión 13).
   - **Pasar a S3 real es solo cambiar variables de entorno**: endpoint, región, bucket, credenciales, estilo de direccionamiento y URL pública para las prefirmadas (en local, el host que ve el navegador no es el del contenedor). Se le entregan al usuario las líneas para `.env.example` y `.env`.
   - **Precisión de la Parte 2: MinIO se descartó.** Su edición comunitaria ya no publica imágenes (`minio/minio` y `quay.io/minio/minio` responden "repository does not exist"). El usuario eligió **SeaweedFS** (`chrislusf/seaweedfs:3.85`, `weed server -s3`), con el bucket creado por un servicio de inicialización. El adaptador S3 no cambia.
   - **El cifrado SSE solo aplica en S3 real.** SeaweedFS no lo implementa: en local `DOCUMENT_STORAGE_SSE` va vacío y `encryption_key_version` queda nulo.
2. **Antivirus: ClamAV, con Celery.**
   - `clamd` por TCP con `INSTREAM`, cliente propio sin dependencias, en un servicio `clamav` del perfil `async`.
   - `config/celery.py` nuevo; el análisis y el ZIP se encolan con `transaction.on_commit(task.delay)`. Tareas idempotentes: no hacen nada si el estado ya no es `PENDING`. Comando `requeue_pending_scans` para los que queden colgados. Tests con `CELERY_TASK_ALWAYS_EAGER`.
   - Escáner fake (`CLEAN`, salvo la firma EICAR) **solo con `DEBUG` o en tests**; fuera de eso, la configuración falla al arrancar.
   - **Si `clamd` falla, el archivo sigue `PENDING`, nunca `CLEAN`**: reintento con espera creciente y, al agotarlo, queda para `requeue_pending_scans`.
   - El README explica cómo levantar el perfil `async`.
3. **Varios archivos por requisito: un slot por archivo.**
   - Columna nueva `application_document_slots.slot_index SMALLINT NOT NULL DEFAULT 1 CHECK (slot_index > 0)`, de 1 a `minimum_files`.
   - Cada slot se carga y se revisa por separado. La etiqueta se calcula: "Desprendible de nómina 2 de 3" (con `minimum_files = 1`, solo el nombre del tipo).
   - El snapshot `minimum_files` conserva el valor del requisito en cada slot del juego.
   - **Desvío del DER**: se anota y se actualizan `docs/MODELO_DATOS_DER_MVP_CREDITO.md` §8.2 y `docs/ESQUEMA_POSTGRESQL_MVP_CREDITO.sql`.
4. **Titular del documento: `document_types.holder_scope`.**
   - `PARTICIPANT` | `APPLICATION`, `PARTICIPANT` por omisión, editable por el admin (`PATCH /document-types/{id}`).
   - Un requisito de un tipo `APPLICATION` crea slots con `participant_id` nulo, una sola vez por solicitud.
   - Semilla `APPLICATION`: `PROPERTY_ANALYSIS_DOCUMENTS`, `PROPERTY_OWNERSHIP_DOCUMENT`, `REMODELING_BUDGET`, `TITLE_STUDY_DOCUMENTS`, `DEED_SIGNATURE_DOCUMENTS` y `REGISTRATION_DOCUMENTS` (inmueble y legalización), más `EXTERNAL_APPROVAL_LETTER` (decisión 19).
   - **Desvío del DER**: se actualizan §7.10 y el esquema SQL.

### Tanda 2

5. **Recálculo del checklist.**
   - Automático, en la misma transacción que el cambio que lo provoca (decisión 6), y manual con `POST /applications/{id}/document-slots/refresh`. Los dos, **solo antes de `FILED`**.
   - Un slot que deja de aplicar se retira con una columna nueva `retired_at TIMESTAMPTZ`: no se borra y conserva sus versiones. Si vuelve a aplicar, revive (`retired_at = NULL`) con su historial.
   - Un slot vigente sin versiones se actualiza al requisito nuevo (`requirement_id`, `requirement_version` y snapshot). Uno con versiones conserva su snapshot.
   - Si baja `minimum_files` (3 → 2), se retira el slot sobrante de mayor `slot_index`.
   - Los slots retirados no cuentan en la guarda, la completitud ni el paquete, y el comprador no los ve ni carga en ellos (`404`).
   - **Desvío del DER**: se anota en §8.2 y en el esquema SQL.
6. **Los documentos no tocan `credit_applications.version`.**
   - Carga, análisis, revisión, exoneración y recálculo no la aumentan ni exigen `If-Match`.
   - El paquete guarda una **huella del expediente documental** (decisión 23): el hash de los slots vigentes y sus versiones actuales. El paso 11 la compara al radicar.
   - La revisión apunta a un `document_file_id` concreto. Si ya no es el archivo vigente del slot (el comprador cargó otro mientras tanto): `409 DOCUMENT_NOT_CURRENT`.
   - La guarda de `READY_TO_FILE` evalúa los documentos dentro de la misma transacción, con los slots bloqueados (decisión 22).
7. **Completitud.**
   - `percentage` = promedio, entero hacia abajo, de `data_percentage` (los ítems de datos de hoy) y `documents_percentage` (obligatorios cumplidos / obligatorios). Cumplido = `APPROVED` no vencido o `WAIVED`; un grupo alternativo cuenta como uno.
   - La respuesta trae `percentage`, `data_percentage` y `documents_percentage` por separado.
   - `documents` lleva `verified`, `required_total`, `completed_total`, `message` y el detalle por slot: `slot_id`, `participant_id`, tipo, etiqueta, `status`, `alternative_group_code`, `expires_at` y `complete`.
   - `ready_to_file` se calcula con el expediente real (producto, evaluación y `documents_verified`).
   - El progreso del comprador usa la misma regla, sin `bank_evaluation` en la parte de datos.
8. **Vigencia.**
   - Aprobar un slot con `validity_days` exige `document_date`: lo da el comprador en la carga o lo corrige el asesor al aprobar. No puede ser futura (`400`).
   - `expires_at = document_date + validity_days`, guardada en la versión.
   - No se aprueba un documento ya vencido: `422 DOCUMENT_EXPIRED`.
   - Antes de `FILED`, un aprobado que venció cuenta como no cumplido en el checklist y en la completitud, y la guarda de `READY_TO_FILE` y el paquete fallan con `DOCUMENT_EXPIRED` en `details`.
   - Después de `FILED`, la vigencia no bloquea nada.

## Decididas en la implementación

### Parte 1
- **Migraciones:**
  - `documents 0003_dossier`: `document_types.holder_scope` y las cinco tablas. Depende de `applications 0004` e `identity 0010`;
  - `documents 0004_seed_dossier`: permisos, los dos catálogos y `holder_scope = APPLICATION` en siete tipos.
- **Modelos** (`apps/documents/models/`): `FileObject` y `ScanStatus` (`file_object.py`), `ApplicationDocumentSlot` y `SlotStatus` (`slot.py`), `DocumentFile` y `DocumentFileStatus` (`document_file.py`), `DocumentReview` y `ReviewDecision` (`review.py`), `DocumentPackageJob` y `PackageJobStatus` (`package_job.py`), y `HolderScope` en `document_type.py`.
- **`current_file`** es un `OneToOneField` (la columna es `UNIQUE` en el esquema) con `SET_NULL`. Django crea las FK de PostgreSQL como `DEFERRABLE INITIALLY DEFERRED`, que es lo que pide el esquema; un test lo verifica en `pg_constraint`. Igual que el resto del proyecto, `RESTRICT` y `SET_NULL` los aplica el ORM, no la base.
- **Nombres acortados** a 30 caracteres, solo en los índices: `ix_doc_slots_app_status`, `ix_doc_slots_pending`, `ix_doc_package_jobs_app` e `ix_doc_package_jobs_queue`. Las restricciones conservan el nombre del esquema; la única nueva es `ck_document_slots_req_version`, para el `CHECK` en línea de `requirement_version`.
- **Restricciones que no están en el esquema original:**
  - `uq_document_slots_active` (decisión 20);
  - `ck_document_slots_index` (`slot_index` entre 1 y `minimum_files`);
  - `ck_document_files_expiry` (`expires_at` nulo o posterior a `document_date`);
  - los dos índices de slots se limitan a `retired_at IS NULL`.
  Quedan anotadas en el DER y en el esquema SQL.
- **Sin índice por `sha256`.** DER §8.1 lo menciona, pero el esquema SQL no lo trae y ninguna consulta lo usa todavía.
- **Cambio de `holder_scope` con requisitos vivos: `400`, no `409`.** La decisión 18 decía "`409`, como el cambio de `is_repeatable`", pero ese cambio responde `400 VALIDATION_ERROR` en el campo. Se siguió el precedente: `400` en `holder_scope`. Repetir el valor actual no es un cambio.
- **`holder_scope` en la API:**
  - `GET`/`POST`/`PATCH /document-types` exponen y aceptan `holder_scope`, con `PARTICIPANT` por omisión;
  - un requisito de un tipo `APPLICATION` con `participant_role` o `employment_profile_code` responde `400` en esos campos, tanto al crearlo como al crear un borrador nuevo desde una versión inactiva (el tipo pudo cambiar de titular mientras tanto);
  - `preview_checklist` devuelve `ChecklistPreview(participants, application_requirements)`, y la respuesta agrega `application_requirements`. Los documentos de la solicitud no se repiten en la lista de cada participante. Sigue siendo una sola consulta.
- **Admin.** Los cinco modelos son de solo consulta. `FileObject` no muestra `object_key`.
- **Configuración.** No se agregó ninguna en esta parte. Las variables de almacenamiento, antivirus y Celery van en la Parte 2; cuotas, límites y vencimientos, en las partes que las usan (4, 5 y 7). Así no queda configuración sin uso.
- **Tests:**
  - están en `tests/applications/dossier/` (no en `tests/documents/`) para heredar la solicitud, el titular y los usuarios. Su `conftest.py` importa `make_link` y `make_session` de `buyer_access` y agrega `make_file_object`, `make_slot`, `buyer_session` y `make_document_file`;
  - `test_seed.py` cubre también `unseed` y que `seed` sea idempotente, llamando a las funciones de la migración con el registro de apps;
  - `tests/catalogs/test_workflow.py` creaba a mano un permiso de prueba `documents.review`, que ahora viene sembrado. Se renombró a `workflow_test.review`, porque ese test prueba el motor genérico.

### Parte 2
- **Archivos:**
  - `config/celery.py` y su carga en `config/__init__.py` (`celery_app`). Serialización solo JSON: las tareas reciben ids, nunca archivos ni datos personales;
  - `apps/documents/storage.py`: `ObjectStorage` (`put`, `open`, `delete`, `presigned_url`, `ensure_bucket` y `check`), `S3Storage`, `MemoryStorage`, `get_storage()` (una vez por proceso, con `lru_cache`), `new_document_key`, `new_package_key` y `attachment_disposition`;
  - `apps/documents/file_validation.py`: `inspect_upload` → `InspectedFile(filename, mime_type, size_bytes, sha256)`, `sanitize_filename` y `detect_mime_type`;
  - `apps/documents/scanning.py`: `ClamdScanner`, `FakeScanner`, `ScanResult`, `parse_clamd_reply` y `get_scanner()`;
  - errores `UnsupportedFileType` y `FileTooLarge` (`422`), y `StorageUnavailable` y `ScannerUnavailable`, que no son errores de la API: quien los captura decide si responde `503` o reintenta;
  - comandos `init_document_storage` (crea el bucket si no existe; lo usa `storage-init`) y `check_document_services` (comprueba almacenamiento y antivirus).
- **`boto3` directo, no `django-storages`.** El acuerdo decía "django-storages/boto3". La interfaz propia necesita dos clientes (uno interno para leer y escribir, y otro que firma con el host que ve el navegador), `ResponseContentDisposition` en la URL prefirmada y errores propios. Con `boto3` directo eso es más corto y claro. `django-storages[s3]` sigue en `requirements.txt` porque trae `boto3`.
- **Dos endpoints.** `DOCUMENT_STORAGE_ENDPOINT_URL` (el backend llega a `seaweedfs:8333`) y `DOCUMENT_STORAGE_PUBLIC_ENDPOINT_URL` (la URL prefirmada se firma para `localhost:8333`, que es lo que ve el navegador). En S3 real los dos van vacíos.
- **`Content-Disposition`** de la descarga: `attachment`, con nombre ASCII de respaldo y `filename*` en UTF-8 (RFC 6266).
- **Validación de archivos:**
  - extensiones ejecutables o interpretables por el navegador (`exe`, `js`, `html`, `svg`, etc.) en cualquier parte del nombre: `422 UNSUPPORTED_FILE_TYPE` (`BLOCKED_EXTENSION`), antes de leer el contenido;
  - doble extensión: una extensión conocida antes de la última (`foto.png.pdf`). Un punto cualquiera no basta (`certificado.v2.pdf` es válido);
  - cada rechazo trae un `details[0].code` concreto: `BLOCKED_EXTENSION`, `UNKNOWN_CONTENT`, `TYPE_NOT_ALLOWED`, `EXTENSION_MISMATCH`, `DOUBLE_EXTENSION`, `DECLARED_TYPE_MISMATCH` o `FILE_TOO_LARGE`, siempre con `field = file`;
  - el MIME declarado admite alias (`image/jpg`, `image/pjpeg`, `application/x-pdf`, `image/x-png`) y valores que no informan nada (vacío, `application/octet-stream`);
  - el nombre conserva los espacios colapsados, pierde los caracteres de control y de formato (por ejemplo, el espacio de ancho cero) y se corta a 255 conservando la extensión.
- **Antivirus:**
  - el cliente lee la respuesta hasta el `\0` de los comandos con prefijo `z`. `stream: OK` → `CLEAN`; `stream: <firma> FOUND` → `INFECTED` con la firma; cualquier otra respuesta (incluido el límite de tamaño de clamd o una conexión cerrada sin respuesta) → `ScannerUnavailable`. El archivo sigue `PENDING`;
  - el reintento con espera creciente es de la tarea de análisis (Parte 4).
- **Falla al arrancar.** `DocumentsConfig.ready()` valida la configuración: `DOCUMENT_STORAGE_BACKEND=memory` o `DOCUMENT_SCANNER=fake` sin `DEBUG` ni `DOCUMENT_ALLOW_FAKE_SERVICES` (solo `config.settings.test` lo activa) lanzan `ImproperlyConfigured`. También un valor desconocido. Se hace en `ready()` y no en un *system check*, porque gunicorn y Celery no ejecutan los checks.
- **Configuración** (`base.py`): `DOCUMENT_STORAGE_*`, `DOCUMENT_SCANNER`, `CLAMD_*` y `DOCUMENT_ALLOW_FAKE_SERVICES`. Por omisión, S3 con `AES256` y `clamd`: lo seguro es lo que no requiere variables. `test.py` usa `memory`, `fake` y `CELERY_TASK_ALWAYS_EAGER`.
- **docker-compose:**
  - `seaweedfs` y `storage-init` van en el perfil por omisión, no en `async` como decía el plan: la API guarda las cargas sin el worker. `backend` y `worker` esperan a que `storage-init` termine bien;
  - SeaweedFS arranca con una sola identidad, cuyas credenciales salen del `.env`, y el acceso anónimo queda denegado (`403`). Sin credenciales, no arranca y lo explica en el log;
  - healthcheck con `nc -z 127.0.0.1 8333`: dentro del contenedor, `localhost` resuelve a IPv6 y SeaweedFS solo escucha en IPv4;
  - `clamav` (`clamav/clamav:1.4.3`, perfil `async`) guarda las firmas en el volumen `mvp_credit_clamav_data`. El `worker` no espera a que esté sano, porque la primera descarga tarda minutos y mientras tanto el análisis reintenta.
- **Verificado de punta a punta** con el stack real y credenciales temporales (sin tocar `.env`):
  - `storage-init` crea el bucket y la segunda vez dice que ya existía;
  - carga, lectura y URL prefirmada descargada desde el host con `Content-Disposition` y `Content-Type` correctos;
  - sin firma: `403`;
  - `clamd` real: `PING`, un PDF de 300 KB limpio y EICAR `INFECTED`;
  - el worker de Celery se conecta a Redis y queda listo;
  - `check_document_services` en verde.
- **Tests** (`tests/documents/`): `test_file_validation.py`, `test_storage.py` (cliente `boto3` sustituido con `MagicMock`; la URL prefirmada se firma con un cliente real, sin red), `test_scanning.py` (un `clamd` falso sobre TCP real en un hilo) y `test_services_commands.py`.

### Parte 3
- **Archivos:** `apps/documents/slots.py` (sincronización), `dossier.py` (lectura y `refresh`), `dossier_serializers.py` y `dossier_views.py`, con las cuatro rutas en `apps/documents/urls.py`. `dossier.py` va aparte de `slots.py` porque usa `applications.services` (alcance y `lock_for_edit`), que a su vez importa `sync_slots`: así no hay importación circular.
- **Cuándo se llama `sync_slots`** (siempre dentro de la transacción, después de `bump_version`):
  - `create_application`: siempre, sobre la solicitud recién creada (sin bloquearla: nadie más la ve todavía);
  - `update_application`: siempre que haya un cambio real (producto o finalidad);
  - `put_financing`: solo si cambia el producto (pasar a `OWN_FUNDS` o `EXTERNAL_CREDIT` lo limpia y retira el checklist del banco);
  - `put_property`: al crear el inmueble o si cambia `condition_item`;
  - `add_participant` y `remove_participant`: siempre; `update_participant`: solo si cambia el rol;
  - `put_financial_profile`: al crear el perfil o si cambia `employment_profile_item`.
  Si el cambio falla (por ejemplo, `409 STALE_VERSION`), la transacción revierte también los slots.
- **Configuración que deja de aplicar.** El recálculo usa lo publicado en ese momento: un requisito desactivado o vencido, o un tipo inactivo, deja de aplicar y su slot se retira en el siguiente recálculo (no en el momento de desactivarlo). Es la lectura directa de la acordada 5 ("un slot que deja de aplicar se retira"); los slots retirados conservan su historial.
- **Sin historial** = slot `PENDING` y sin versiones. Un slot exonerado (`WAIVED`) cuenta como con historial y conserva su snapshot: si no, el requisito nuevo podría dejarlo no exonerable y romper `ck_document_slots_waiver`.
- **Tipo repetido (decisión 17).** El más estricto se elige por: obligatorio, mayor `minimum_files`, con vigencia antes que sin ella, menor vigencia, no exonerable y, para desempatar, menor `sort_order` e id. El slot toma su `requirement_id`, `requirement_version` y `sort_order`. `alternative_group_code`: el del más estricto solo si todos los requisitos del tipo están en un grupo; uno fuera de grupo exige el documento por sí mismo.
- **Vigencia del snapshot:** `effective_validity_days` (la del requisito o, si está vacía, la sugerida por el tipo).
- **Revivir.** Si hay varios retirados en la misma posición (titular, tipo e índice), revive el que tiene historial y, si no, el retirado más reciente. Uno sin historial toma el requisito vigente al revivir.
- **Bloqueos.** `sync_slots` bloquea los slots de la solicitud (`select_for_update`, ordenados por id) después de la solicitud (decisión 22). Escribe primero los retiros y después los revividos, actualizados (`bulk_update`) y nuevos (`bulk_create`), para no chocar con `uq_document_slots_active`.
- **Etiqueta.** "Nombre n de m", donde m son los slots vigentes del mismo juego (subconsulta `set_size`, que compara el participante con `COALESCE` para incluir los de la solicitud); con m = 1, solo el nombre. Un slot retirado usa su `minimum_files`. Así, si `minimum_files` sube de 2 a 3, los slots con historial (snapshot 2) y el nuevo se muestran "1 de 3", "2 de 3" y "3 de 3".
- **Lectura interna:**
  - `GET /applications/{id}/document-slots` pagina como el resto de listas y filtra por `status`, `participant_id`, `document_type_code`, `required` e `include_retired` (agregado, igual que `include_inactive` en participantes). Orden: los documentos de la solicitud primero, después cada participante en el orden en que entró, y dentro de cada uno `sort_order`, código del tipo y `slot_index`;
  - el slot trae el tipo con `holder_scope`, `allowed_mime_types` y `max_size_bytes`, el participante (`id`, `role`, `client_id`, `full_name`, `is_active`), el resumen de la versión vigente con su `scan_status`, `waiver_reason`, `is_retired` y `retired_at`;
  - `GET /document-slots/{id}` incluye los retirados; `.../versions` pagina, de la más reciente a la primera, con `is_current`, los metadatos del archivo (nunca `object_key` ni el bucket) y todas sus revisiones, incluido `internal_comment`;
  - sin `ETag`: los documentos no tocan la versión de la solicitud (acordada 6).
- **`POST .../document-slots/refresh`**: `documents.manage_requirements`, sin cuerpo ni `If-Match`, `409 APPLICATION_NOT_EDITABLE` desde `FILED`. Responde `200` con `created`, `retired`, `revived` y `updated` (ids) y `slots`, la lista vigente completa sin paginar.
- **Permisos:** `HasPermissionCode` resuelve el `403` de broker y partner antes de buscar la solicitud; el asesor no asignado recibe `404`.
- **Esquema OpenAPI:** `DocumentSlotStatusEnum` y `DocumentFileStatusEnum` en `ENUM_NAME_OVERRIDES`, porque los dos `status` nuevos chocaban de nombre.
- **`label` y mypy.** El campo `label` del serializer choca con el atributo `Field.label` de los stubs de DRF; lleva el mismo `type: ignore[assignment]` justificado que `CatalogItemRefSerializer`.
- **Tests** (`tests/applications/dossier/`): `test_slots.py` (reglas de la sincronización y llamadas desde los servicios, con un espía sobre `services.sync_slots` para las ramas que no deben recalcular) y `test_slots_api.py` (matriz de permisos con admin, asesor asignado y no asignado, broker, partner y anónimo; lista, filtros, detalle, versiones y `refresh`).

### Parte 4
- **Archivos:** `apps/documents/uploads.py` (carga), `scans.py` (efecto del análisis), `tasks.py` (Celery), `buyer_serializers.py`, `buyer_views.py` y el comando `requeue_pending_scans`, con las cuatro rutas `/buyer/...` en `apps/documents/urls.py`. Las vistas del comprador viven en `documents` (no en `identity`), sobre `BuyerPortalView`.
- **Orden de la carga:**
  1. sin bloqueos: el slot (`404` si es de otra solicitud o está retirado), las reglas de carga, la validación del archivo (`inspect_upload` con `allowed_mime_types` y `max_size_bytes` **del tipo documental vigente**: el slot no copia formatos ni tamaño) y la cuota;
  2. `put` en el almacenamiento, fuera de la transacción, para no retener bloqueos durante la red. Si falla: `503 SERVICE_UNAVAILABLE` (código nuevo);
  3. transacción: bloquea la solicitud y el slot (decisión 22), repite reglas y cuota, crea `file_objects` (`PENDING`), la versión (`MAX(version_number) + 1`) y mueve `current_file`; el análisis se encola en `on_commit`;
  4. si la transacción falla, se borra el objeto; si tampoco se puede borrar, queda un aviso en el log ("objeto huérfano").
- **`413 PAYLOAD_TOO_LARGE`** (código nuevo). Se comprueba `Content-Length` en `initial()` de la vista, **antes de autenticar**: la validación CSRF de Django lee `request.POST`, y eso ya procesaría el multipart entero. Límite fijo `DOCUMENT_UPLOAD_MAX_REQUEST_BYTES` = 10 MB + 512 KB (sin variable de entorno). Sin `Content-Length` válido, decide el parser (`400`).
- **Reglas de carga** (`upload_block`), en este orden: solicitud terminada `409 APPLICATION_CLOSED`; antes de `FILED`, `PENDING`/`UPLOADED`/`REJECTED` se cargan y `APPROVED`/`WAIVED` dan `409 DOCUMENT_LOCKED`; después de `FILED`, `REJECTED` con observación abierta se carga, `locked_at` sin observación da `DOCUMENT_LOCKED` y el resto `DOCUMENT_NOT_REJECTED`. `slot_has_open_observation` se llama por el módulo (`uploads.slot_has_open_observation`) para que los tests la sustituyan.
- **Cuota:** cuenta todas las versiones guardadas, también las rechazadas o infectadas. `details[0].code` dice cuál se superó: `VERSIONS_PER_SLOT` o `APPLICATION_BYTES`.
- **`document_date`** es opcional y no puede ser futura (`timezone.localdate()`). Si el slot tiene vigencia, `expires_at` se calcula ya en la carga (el asesor podrá corregir la fecha al aprobar, Parte 5). Un documento ya vencido se acepta en la carga: lo frena la aprobación (`422 DOCUMENT_EXPIRED`).
- **Respuesta de la carga:** `201` con el slot del comprador (no la versión), releído después del commit.
- **Límite de consumo:** `buyer_document_upload` = `60/1h` en `AUTH_RATE_LIMITS`, por sesión + solicitud, solo `POST`. DRF lo evalúa después de los permisos: un `403`/`409` por permiso no consume el límite; una validación fallida, sí.
- **Análisis** (`scan_document_file`):
  - relee el objeto del almacenamiento y compara el SHA-256: si no coincide, `INVALID`. Si coincide, `clamd` decide `CLEAN` o `INFECTED`;
  - bloquea el slot y después el `file_object`; si ya no está `PENDING`, no hace nada (dos tareas para el mismo archivo);
  - `CLEAN` solo mueve la versión de `UPLOADED` a `IN_REVIEW`; `INFECTED`/`INVALID` la rechazan y rechazan el slot **solo si sigue siendo la vigente** (una versión vieja que resulta infectada no toca el slot);
  - el objeto infectado **no se borra** (queda como evidencia); la descarga lo frenará con `FILE_NOT_CLEAN` (Parte 5). El log lleva la firma detectada y los ids, nunca el nombre del archivo.
- **Tarea `scan_file_object`:** 8 reintentos con espera de 30 s duplicada hasta un tope de 15 min (≈ 1 h 15 min en total). Al agotarlos devuelve `PENDING` sin lanzar error. Si el broker no responde al encolar (`kombu.exceptions.OperationalError`), la carga igual responde `201` y el archivo queda `PENDING`.
- **`requeue_pending_scans`:** vuelve a encolar los archivos de versiones que siguen `PENDING` con más de 15 minutos (`--older-than-minutes`). Hay que programarlo (cron o similar) al desplegar.
- **DTO del comprador:** ve todos los slots vigentes de la solicitud, también los de los co-solicitantes (es el único que carga). Lleva `label`, participante (`id`, `role`, `full_name`), tipo (`code`, `name`, `description`, `holder_scope`), formatos, tamaño máximo, `can_upload`, la versión vigente y `rejection` (`reason`, `buyer_comment`, `rejected_at`): el mensaje fijo de seguridad si lo rechazó el análisis, o la última revisión si es un rechazo del asesor. Sin `internal_comment`, revisor, requisito, SHA-256 ni estado técnico del análisis (`UPLOADED` ya significa "en análisis"). Las listas paginan.
- **Tests:**
  - con `CELERY_TASK_EAGER_PROPAGATES` un `Retry` se propaga en lugar de reaplicar la tarea. Los tests del reintento lo desactivan con `monkeypatch.setitem(celery_app.conf, "CELERY_TASK_EAGER_PROPAGATES", False)`: la app lee la clave **con el prefijo** de Django (`namespace="CELERY"`), la clave sin prefijo no tiene efecto;
  - la carga concurrente usa `django_db(transaction=True, serialized_rollback=True)` con dos hilos y una barrera; `serialized_rollback` restaura los datos sembrados por las migraciones para los tests siguientes.
- **Verificado de punta a punta** con SeaweedFS y `clamd` reales, sin tocar `.env`: carga de un PDF de 100 KB por el portal → objeto en SeaweedFS, `clamd` `CLEAN`, versión `IN_REVIEW`; EICAR guardado en SeaweedFS → `INFECTED` y slot `REJECTED`. Cómo se hizo:
  - **no se usó el servicio `seaweedfs` del compose:** el volumen `mvp_credit_seaweedfs_data` existía (en la Parte 2 se había borrado), así que podía tener datos del usuario. Se levantó un contenedor aparte, `e2e-seaweedfs`, en `mvp_credit_network`, sin volumen ni puerto en el host y con credenciales temporales; `clamav` sí fue el del perfil `async`. Al terminar se borraron los dos contenedores; los volúmenes quedaron como estaban;
  - el test temporal vive fuera del repositorio, montado en `/e2e` con su propio `conftest.py` que importa los fixtures del proyecto, y se corre con `python -m pytest -c /app/pytest.ini /e2e/...`. Con `-p tests.conftest` no funciona: los plugins se cargan antes de `django.setup()`.

## Pendientes para pasos posteriores

1. **Paso 11.** Implementar `slot_has_open_observation`, fijar `locked_at` al radicar, exigir que la huella documental del paquete coincida con la actual (`dossier_fingerprint`, acordada 6) y la huella y firma de `IDENTITY_DOCUMENT`.
2. **Paso 12.** Actividad de cargas, revisiones y descargas (RF-61), con la visible para el comprador.
3. **Paso 13.** `Idempotency-Key` en `POST /document-package-jobs`; notificación al comprador de un rechazo; aviso al comprador cuando un documento aprobado esté por vencer (acordada 8).
4. **Paso 14.** Auditoría de descargas.
5. **Despliegue.** Programar `requeue_pending_scans` (cron o Celery beat) y decidir cuánto tiempo se conservan los objetos infectados (hoy no se borran).
