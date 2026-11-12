# Tarea: radicación manual y respuestas del banco (módulo 11)

## Objetivo
Que el asesor registre la entrega manual del expediente al banco (radicación) y cada respuesta que reciba: recibida, en análisis, devuelta con observaciones, aprobada, rechazada, desembolsada u otra. Cada respuesta mueve la solicitud de estado con trazabilidad. Cubre RF-60 a RF-65, REQ §4.4 y §4.5, y API §20.

La API **no** se comunica con ningún banco: todo se registra a mano.

## Cuándo y dónde
- **Agente:** backend B, en el worktree `wt-back-filings`, rama `feat/filings`, creada desde `master` después del merge del PR #16.
- **En paralelo:** el backend A trabaja en `TAREA-brechas.md`, en la carpeta principal.
  - No toques lo que toca A: catálogos del comprador, `stages` y `advisor` del detalle del comprador, `/auth/me` y el helper de `ETag`.
  - Si necesitas un archivo que A también toca (por ejemplo, `apps/identity/buyer_serializers.py` o el de documentos), haz el cambio mínimo y anótalo en el reporte. El choque se resuelve al traer `master`.
- **Tu código vive en una app nueva, `apps/filings`.** Fuera de ella solo tocas:
  - los puntos de enganche de esta spec;
  - `config/settings` (`INSTALLED_APPS` y `urls`);
  - el modelo `Bank`.

## Cómo corres el backend (importante)
**No uses `docker compose` ni toques los contenedores que están corriendo:** esos montan la carpeta principal, la del backend A, y los usa el front en `:8000`. Tú corres todo en contenedores de un solo uso que montan **tu** worktree y usan **tu propia base de pruebas**:

```
docker run --rm --network mvp_credit_network --env-file C:\Users\ASUS\Documents\programacion\mvp-backoffice\real-estate-credit-backoffice\backend\.env -e DATABASE_HOST=postgres -e DATABASE_NAME=mvp_credit_filings -v C:\Users\ASUS\Documents\programacion\mvp-backoffice\wt-back-filings\backend:/app -v C:\Users\ASUS\Documents\programacion\mvp-backoffice\wt-back-filings\contracts:/contracts -w /app mvp-credit-backend-backend <comando>
```

- `<comando>` es `pytest`, `ruff check .`, `mypy .`, `python manage.py makemigrations --check --dry-run` o el `spectacular` del contrato.
- `DATABASE_NAME=mvp_credit_filings` hace que pytest cree `test_mvp_credit_filings` y no choque con las pruebas del backend A.
- Si el nombre de la imagen no es `mvp-credit-backend-backend`, búscalo con `docker images` y anótalo.
- **El `.env` lo lees solo a través de `--env-file`.** No lo abras ni lo copies.
- **No aplicas migraciones a la base de desarrollo:** tu rama no está en `:8000`. Las migraciones se prueban con pytest. Cuando el PR se fusione, el backend las aplica solo al arrancar.

## Reglas de trabajo
- Git solo en lectura. Carlos hace todos los commits y push, sin `Co-Authored-By` ni firmas.
- **No se presentan dudas.** Lo que esta spec no cubra lo decides tú con la opción más simple, lo anotas en "Precisiones acordadas" y sigues. Solo te detienes si la decisión rompe un contrato ya publicado, cambia el alcance, borra o altera datos existentes, o exige tocar un `.env`.
- Cada parte se hace de corrido. Al cerrarla entregas: verificaciones en verde, la lista corta de decisiones que tomaste y el mensaje de commit. Esperas el "listo" de Carlos.
- **Contrato y tipos del front:** al cerrar cada parte regeneras `contracts/openapi.json` (`--validate --fail-on-warn`, con el contenedor de un solo uso) y los tipos del front, desde `frontend/`:
  ```
  npx --yes openapi-typescript@7.13.0 ../contracts/openapi.json -o src/lib/api/schema.d.ts
  ```
- Cobertura ≥ 95 %. Sigue los patrones que ya existen en `applications` y `documents`:
  - servicios con `select_for_update`;
  - errores `ApiError` con los códigos de API §5.5;
  - `extend_schema` completo;
  - alcance con `applications_visible_to`;
  - permisos sembrados por migración.

## Decisiones de negocio (ya tomadas con Carlos)
1. **Tipos de respuesta:** los del catálogo `filing_response_type` (REQ §4.5): `RECEIVED`, `RETURNED`, `IN_ANALYSIS`, `APPROVED`, `REJECTED` y `OTHER`, **más `DISBURSED` (nuevo)**. La tabla de API §20.2 está desactualizada (usa `UNDER_REVIEW` y estados que no existen): se corrige en la documentación.
2. **Legalización:** el asesor pasa de `APPROVED` a `LEGALIZATION` con una transición manual. El **desembolso** se registra como respuesta `DISBURSED`, con fecha y monto (lo usará el módulo de comisiones).
3. **Devolución:** la solicitud queda en `BANK_OBSERVATION`.
   - Los documentos observados quedan rechazados ("Corrígelo") y el comprador solo puede reemplazar esos.
   - Cuando el asesor los aprueba, marca "Lista para radicar" y crea una nueva radicación.
   - No pasa por `WAITING_DOCUMENTS`.
4. **Evidencia:** cada respuesta admite un archivo opcional (PDF, JPG o PNG). Solo lo ven el administrador y el asesor asignado.

## Parte 1. Modelo, catálogos, permisos y transiciones

### Modelos (`apps/filings`, según `docs/ESQUEMA_POSTGRESQL_MVP_CREDITO.sql`)
- **`Filing`:**
  - `application`, `bank_product`, `package_job` (único), `sequence_number` (único por solicitud, empieza en 1), `channel_item` (catálogo `filing_channel`) y `external_reference` (opcional, 100);
  - `status` (`TextChoices`: `FILED`, `RECEIVED`, `IN_ANALYSIS`, `RETURNED`, `APPROVED`, `REJECTED` y `DISBURSED`; refleja la última respuesta que cambió algo);
  - `filed_by`, `filed_at`, `target_response_at` (nulo) y `comment`;
  - `created_at` y `updated_at`.
- **`FilingDocumentSnapshot`:** `filing`, `document_file`, `file_object`, `sha256` y `document_type_code`, con único `(filing, document_file)`.
- **`FilingResponse`:**
  - `filing`, `response_type_item`, `reason_item` (nulo), `received_at` y `external_reference`;
  - `public_message` e `internal_comment`;
  - `evidence_file_object` (nulo);
  - `approved_amount_cop`, `approved_term_months`, `valid_until` y `disbursed_amount_cop`;
  - `recorded_by`, `corrects_response` (único, nulo) y `created_at`.
  - Con los `CHECK` del SQL.
- **`FilingResponseObservation`:**
  - `filing_response`, `document_slot`, `reason_item` (catálogo `document_rejection_reason`) y `buyer_message`;
  - `resolved_by_file` y `resolved_at`, los dos nulos o los dos llenos;
  - único `(filing_response, document_slot)`.
- **En `Bank`:** `filing_response_days` (`PositiveSmallIntegerField`, nulo). Al FNA se le siembra `7` (REQ, etapas del FNA), buscándolo por `code`. `target_response_at = filed_at + días`, o nulo si el banco no lo tiene.

### Catálogos (migración de datos en `filings`)
- `filing_response_type`: agregar `DISBURSED` "Desembolsada".
- `filing_channel` (nuevo): `BANK_PORTAL` "Portal del banco", `EMAIL` "Correo electrónico" e `IN_PERSON` "Presencial".
- `filing_return_reason` (nuevo): `DOCUMENT_CORRECTION` "Corrección de documentos", `MISSING_INFORMATION` "Información incompleta" y `OTHER` "Otro".
- `filing_rejection_reason` (nuevo): `CREDIT_POLICY` "Políticas del banco", `PAYMENT_CAPACITY` "Capacidad de pago insuficiente", `CREDIT_HISTORY` "Historial crediticio", `PROPERTY` "El inmueble no cumple" y `OTHER` "Otro".
- Cada uno con su `reverse`.

### Permisos (migración)
- `filings.read`: `ADMIN`, `ADVISOR` y `BROKER`.
- `filings.create`, `filings.update` y `filings.record_response`: `ADMIN` y `ADVISOR`.
- Además del permiso, el alcance: el asesor solo actúa sobre las solicitudes asignadas, y el broker solo lee las que originó.

### Transiciones (migración en `filings`, sobre `WorkflowTransition`)
| Código | Origen | Destino | Etiqueta | Cómo se usa |
| --- | --- | --- | --- | --- |
| `FILE` | `READY_TO_FILE` | `FILED` | Radicar | **Solo** desde el servicio de radicación. `available-actions` no la ofrece como botón genérico. |
| `BANK_RECEIVED` | `FILED` | `FILING_VALIDATION` | Recibida por el banco | Solo desde respuestas. |
| `BANK_IN_ANALYSIS_*` | `FILED`, `FILING_VALIDATION` | `CREDIT_ANALYSIS` | En análisis | Solo desde respuestas. |
| `BANK_RETURNED_*` | `FILED`, `FILING_VALIDATION`, `CREDIT_ANALYSIS` | `BANK_OBSERVATION` | Devuelta por el banco | Solo desde respuestas. |
| `BANK_APPROVED_*` | `FILED`, `FILING_VALIDATION`, `CREDIT_ANALYSIS` | `APPROVED` | Aprobada por el banco | Solo desde respuestas. |
| `BANK_REJECTED_*` | `FILED`, `FILING_VALIDATION`, `CREDIT_ANALYSIS`, `BANK_OBSERVATION` | `REJECTED` | Rechazada por el banco | Solo desde respuestas. |
| `BANK_DISBURSED` | `LEGALIZATION` | `DISBURSED` | Desembolsada | Solo desde respuestas. |
| `START_LEGALIZATION` | `APPROVED` | `LEGALIZATION` | Iniciar legalización | Manual (`applications.transition`), por `/status-transitions`. |
| `MARK_READY_TO_REFILE` | `BANK_OBSERVATION` | `READY_TO_FILE` | Lista para radicar de nuevo | Manual, con la guarda de `READY_TO_FILE` más "sin observaciones abiertas". |

- Las transiciones "solo desde el servicio" se marcan de forma que `POST /status-transitions` las rechace (`409`) y `available-actions` no las liste. Usa el mecanismo que ya exista; si no hay, agrega un campo booleano `system_only` a `WorkflowTransition` y anótalo.
- Todo cambio de estado pasa por el servicio de transición que ya existe, para que se guarden el historial y la actividad y se emita `application_status_changed`.

**Pruebas de la Parte 1:**
- Migraciones de ida y vuelta.
- Catálogos y permisos sembrados.
- `START_LEGALIZATION` y `MARK_READY_TO_REFILE` desde `/status-transitions`, con sus guardas.
- Las transiciones de sistema rechazadas por `/status-transitions` y ausentes en `available-actions`.

**Commit:** `feat(filings): add filing models, catalogs, permissions and transitions`

## Parte 2. Radicaciones

| Método | Ruta | Permiso |
| --- | --- | --- |
| `GET` | `/applications/{application_id}/filings` | `filings.read` y alcance |
| `POST` | `/applications/{application_id}/filings` | `filings.create` y asesor asignado (o administrador) |
| `GET` | `/filings/{filing_id}` | `filings.read` y alcance |
| `PATCH` | `/filings/{filing_id}` | `filings.update` y asesor asignado (o administrador) |
| `GET` | `/filings/{filing_id}/document-snapshots` | Administrador o asesor asignado |

**Cuerpo del `POST`:** `bank_product_id`, `package_job_id`, `channel_code`, `external_reference` (opcional), `filed_at` (no futura), `comment` (opcional) y `expected_version`.
- Va `expected_version` en el cuerpo, como `/status-transitions`, en lugar de `If-Match`. Se corrige API §20.1.
- `Idempotency-Key` queda pendiente, como en el resto (API §6): la idempotencia natural es `package_job` único.

**Precondiciones**, cada una con su error (usa los códigos de API §5.5; si falta alguno, lo agregas allí):
- la solicitud está en `READY_TO_FILE`;
- `bank_product_id` es el producto de la financiación;
- todos los documentos obligatorios están `APPROVED` o `WAIVED`;
- la evaluación bancaria no tiene bloqueos;
- el paquete es de esta solicitud, está completo y **su huella documental es la vigente** (la que ya calcula `documents/packages.py`);
- el paquete no se usó en otra radicación;
- `expected_version` coincide.

**Efectos, en una transacción:**
- crea la radicación con el `sequence_number` siguiente y `target_response_at`;
- guarda un snapshot por cada versión de archivo del manifiesto del paquete;
- transiciona con `FILE`;
- emite la señal nueva `filing_created`.

**`PATCH`:** solo `external_reference` y `comment`. No cambia evidencias ni snapshots.

**Respuesta:**
- `id`, `sequence_number`, `status` y `status_label`;
- `bank_product`, `channel` (`{code, label}`) y `external_reference`;
- `filed_by` (`{id, name}`), `filed_at` y `target_response_at`;
- `comment` (no lo ve el broker);
- `responses_count`;
- `application_status` y `application_status_label`.

El broker no ve `comment`.

**Pruebas de la Parte 2:**
- cada precondición;
- alcance por rol;
- `sequence_number` 1 y 2 (después de una devolución);
- snapshots iguales al manifiesto;
- número de consultas fijo en la lista.

**Commit:** `feat(filings): register manual filings with document snapshots`

## Parte 3. Respuestas del banco

| Método | Ruta | Permiso |
| --- | --- | --- |
| `GET` | `/filings/{filing_id}/responses` | `filings.read` y alcance |
| `POST` | `/filings/{filing_id}/responses` | `filings.record_response` y asesor asignado (o administrador) |
| `GET` | `/filing-responses/{response_id}` | `filings.read` y alcance |
| `POST` | `/filing-responses/{response_id}/evidence` | Quien la registró o un administrador; una sola vez |
| `GET` | `/filing-responses/{response_id}/evidence/download` | Administrador o asesor asignado |

**Cuerpo del `POST /responses`:**
- `response_type`, `received_at` (no futura y ≥ `filed_at`), `external_reference`, `reason_code`, `public_message` e `internal_comment`;
- `observations: [{document_slot_id, reason_code, message}]`;
- `approved_amount_cop`, `approved_term_months`, `valid_until` y `disbursed_amount_cop`;
- `corrects_response_id` y `expected_version`.

**Reglas por tipo:**
| Tipo | Estados de la solicitud admitidos | Obligatorio | Efecto |
| --- | --- | --- | --- |
| `RECEIVED` | `FILED`, `FILING_VALIDATION` | — | `FILED` → `FILING_VALIDATION` (si ya está ahí, no cambia). |
| `IN_ANALYSIS` | `FILED`, `FILING_VALIDATION` | — | → `CREDIT_ANALYSIS`. |
| `RETURNED` | `FILED`, `FILING_VALIDATION`, `CREDIT_ANALYSIS` | `reason_code` (`filing_return_reason`), `public_message` y ≥ 1 observación | → `BANK_OBSERVATION`, más las observaciones (abajo). |
| `APPROVED` | `FILED`, `FILING_VALIDATION`, `CREDIT_ANALYSIS` | `approved_amount_cop`, `approved_term_months` y `public_message` | → `APPROVED`. `valid_until` es opcional. |
| `REJECTED` | `FILED`, `FILING_VALIDATION`, `CREDIT_ANALYSIS`, `BANK_OBSERVATION` | `reason_code` (`filing_rejection_reason`) y `public_message` | → `REJECTED`. |
| `DISBURSED` | `LEGALIZATION` | `disbursed_amount_cop` | → `DISBURSED`. |
| `OTHER` | cualquiera no terminal | `internal_comment` | No cambia el estado. |

- **Solo se registra contra la última radicación** de la solicitud. Una más vieja responde `409`.
- **Cada respuesta es inmutable.** `corrects_response_id` solo se acepta si la respuesta corregida es la última de esa radicación, del mismo tipo, y es de tipo `RECEIVED`, `IN_ANALYSIS` u `OTHER`; corregir no cambia el estado. Las demás correcciones quedan fuera del MVP (`409`).
- **Observaciones de una devolución**, por cada slot observado (de esta solicitud y con una versión vigente):
  - crea `FilingResponseObservation`;
  - registra una **revisión de rechazo** sobre la versión vigente del slot, con el servicio de revisiones que ya existe (`documents/reviews.py`): motivo `reason_code` (catálogo `document_rejection_reason`) y comentario al comprador `message`. Así el slot queda `REJECTED` y el comprador lo ve como "Corrígelo" con el mensaje.
- **`documents/uploads.slot_has_open_observation(slot)`** (ya existe y hoy devuelve `False`) pasa a devolver `True` si el slot tiene una observación sin resolver. Así, después de `FILED`, el comprador solo puede reemplazar los slots observados.
- **Resolución:** cuando el asesor **aprueba** una versión nueva de un slot observado, la observación abierta se marca resuelta (`resolved_by_file` y `resolved_at`). El enganche va en el servicio de aprobación de `reviews.py`.
- **`MARK_READY_TO_REFILE`** exige que no quede ninguna observación abierta en la solicitud.
- La radicación actualiza su `status` al tipo de la respuesta (salvo `OTHER`).
- Todo en una transacción, que termina con la señal nueva `filing_response_recorded` (la usarán notificaciones, módulo 13, y tareas, módulo 12).
- **Evidencia:**
  - `POST` multipart con `file`;
  - valida tipo (PDF, JPG o PNG) y tamaño con `documents/file_validation.py`;
  - guarda en el almacenamiento configurado como un `FileObject` y pasa por el mismo análisis antivirus que los documentos;
  - la descarga reutiliza `documents/downloads.py` (URL firmada) y solo se entrega si el análisis la dejó limpia.

**Lo que ve cada actor de una respuesta:**
- **Administrador y asesor:** todo.
- **Broker:** `response_type` con su etiqueta, `received_at` y `public_message`. No ve `internal_comment`, ni evidencia, ni montos.
- **Comprador:** en `BuyerApplicationDetail`, un campo nuevo `latest_bank_update`, nulo si no hay. Es la última respuesta con `public_message`, como `{response_type, response_type_label, received_at, public_message}`. Nunca `internal_comment` (REQ §4.5).

**Pruebas de la Parte 3:**
- cada tipo, con estados válidos e inválidos;
- campos obligatorios;
- devolución completa: observaciones, slots rechazados, carga del comprador permitida solo en los observados, aprobación que resuelve la observación, `MARK_READY_TO_REFILE` y segunda radicación;
- legalización y desembolso;
- corrección permitida y no permitida;
- evidencia: carga, tipo inválido, segunda carga rechazada y descarga por rol;
- lo que ve el broker y lo que ve el comprador.

**Commit:** `feat(filings): record bank responses with observations, evidence and status changes`

## Cierre
- **Docs:**
  - API §20 reescrita según esta spec: tipos reales, `expected_version`, evidencia y lo que ve cada actor;
  - API §27.3 alineada;
  - DER, SQL y modelo de datos (`filing_response_days`, `system_only` si lo agregaste y los catálogos nuevos);
  - README del backend: el módulo en la lista.
- **Trae `master` antes de entregar.** Carlos hace el merge en tu worktree.
  - Si hay conflictos, los resuelves en los archivos uniendo las dos versiones (sin correr git).
  - Si el conflicto es de migraciones de una misma app, generas `makemigrations --merge`.
  - Después regeneras el contrato y los tipos del front.
- **Datos de demo:** cuando traigas `master`, ya tendrá el comando `seed_demo_data` (lo hace el backend A). Agrégale tres solicitudes radicadas, creadas con tus servicios: una en `CREDIT_ANALYSIS`, una en `BANK_OBSERVATION` con un documento observado y una en `APPROVED`. Respeta la idempotencia del comando y suma sus pruebas.
- Todo en verde. Entregas el **título y la descripción del PR**, en español, sin firmas.

## Precisiones acordadas
_(las agrega el agente)_

### Entorno
- La imagen es `mvp-credit-backend-backend`, como dice la spec. `makemigrations` avisa que la base `mvp_credit_filings` no existe; no afecta (pytest usa `test_mvp_credit_filings`).

### Parte 1
1. **`system_only`.** No había un mecanismo para las transiciones de sistema: se agrega `WorkflowTransition.system_only` (`catalogs/0003`, con `db_default=False`). `available_transitions` y `resolve_transition` solo ven las manuales por omisión, así que `POST /status-transitions` responde `409 INVALID_STATE_TRANSITION` y `available-actions` no las lista. Los servicios de `filings` las resuelven con `system_only=True`, que **sigue exigiendo rol y permiso**. `GET /workflow-transitions` muestra `system_only` (solo lectura); el campo no se crea ni se edita por la API.
2. **Permisos de las transiciones.** `FILE` exige `filings.create`; las `BANK_*`, `filings.record_response`; `START_LEGALIZATION` y `MARK_READY_TO_REFILE`, `applications.transition`. Todas con los roles `ADMIN` y `ADVISOR`.
3. **Guarda de `MARK_READY_TO_REFILE`.** Es una guarda nueva, `APPLICATION_READY_TO_REFILE`, registrada en `TRANSITION_GUARDS`. Evalúa la misma regla que `APPLICATION_READY_TO_FILE` y agrega un `BANK_OBSERVATION_OPEN` por cada slot con una observación abierta en los `details` del `422 APPLICATION_NOT_READY`. Queda en API §5.5. Las observaciones abiertas se consultan en `apps/filings/observations.py`, que solo importa modelos, para que `applications.services` lo use sin ciclos.
4. **Catálogos.** `filing_channel`, `filing_return_reason` y `filing_rejection_reason` son internos (`is_public=False`) y administrables, como los demás motivos. `filing_response_type` sigue sin ser administrable. Agregarle `DISBURSED`, o quitárselo en el `reverse`, sube su `version`, para que se invalide la caché del catálogo.
5. **`Bank.filing_response_days`.** Solo existe en el modelo; la API de bancos no lo expone, porque la spec limita el cambio al modelo. Al FNA se le siembra `7` en `banking/0005` (`AddField` y `RunPython` reversible, buscando el banco por `code`).
6. **Modelos según el SQL.**
   - Los textos opcionales son `null=True`, como en el esquema.
   - Además de lo que pide el SQL, se agregan `ck_filings_status` (como en los demás modelos con estado) y `ck_filings_sequence`, que en el SQL es un `CHECK` de columna.
   - `evidence_file_object` es una FK, como en el SQL; que se cargue una sola vez lo controla el servicio (Parte 3).
   - Se incluyen la única parcial `uq_filings_external_reference` y los índices del SQL.
7. **Pruebas.** Viven en `tests/applications/filings/`, como `dossier`, para heredar las fixtures de la solicitud. `tests/applications/test_seed.py` deja fuera las transiciones que siembra `filings`, porque ahora las prueba `tests/applications/filings/test_seed.py`.
8. **Ida y vuelta.**
   - En pytest: `seed`/`unseed` de `filings/0002` y de `banking/0005`.
   - A mano, en una base propia `mvp_credit_filings` (creada y borrada en el contenedor de un solo uso, nunca la de desarrollo): `migrate`, luego `migrate filings zero`, `banking 0004` y `catalogs 0002`, y otra vez `migrate`.
