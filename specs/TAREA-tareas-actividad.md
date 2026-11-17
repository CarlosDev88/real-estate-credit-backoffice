# Tarea: "Mi día", tareas y actividad (módulo 12)

## Objetivo
Darle al asesor su bandeja de trabajo y la trazabilidad del expediente:
- **"Mi día"** (RF-21, RF-22, API §15.1): las solicitudes asignadas al asesor, con su siguiente acción, los días en la etapa y segmentos de atención.
- **Tareas manuales** (RF-20, API §15.2): con responsable, fecha, prioridad y estado.
- **Actividad y notas** (API §21.1): la línea de tiempo del expediente y las notas internas. Cierra la brecha "Actividad reciente" de la F1.

## Cuándo y dónde
- **Agente:** backend A, en la carpeta principal (`real-estate-credit-backoffice`), rama `feat/tasks-activity` desde `master` (ya tiene las brechas).
- **En paralelo:**
  - el backend B cierra la radicación (`feat/filings`, PR #19);
  - el front cierra la F1.
- **No toques** `apps/filings`. Si al traer `master` ya existe la app de radicación, agregas al final los suscriptores de sus señales (ver Parte 3).

## Reglas de trabajo
- Git solo en lectura. Carlos hace todos los commits y push, sin `Co-Authored-By` ni firmas.
- **Comunicación por buzón** (`.buzon/PROTOCOLO.md`): reporte completo en `.buzon/reportes/`, `ESTADO.md` al día y en la consola solo una línea.
- **No se presentan dudas.** Lo que esta spec no cubra lo decides tú con la opción más simple, lo anotas en "Precisiones acordadas" y sigues. Solo te detienes si rompe un contrato publicado, cambia el alcance, borra o altera datos existentes, o exige tocar un `.env`.
- **Pruebas** con tu base propia: `docker compose exec -e DATABASE_NAME=mvp_credit_a backend pytest …`.
- Las migraciones se aplican en `:8000` (`migrate`) apenas se crean: el front usa ese backend.
- Al cerrar cada parte: contrato (`--validate --fail-on-warn`) y `schema.d.ts` regenerados (`npx --yes openapi-typescript@7.13.0 ../contracts/openapi.json -o src/lib/api/schema.d.ts`, desde `frontend/`).
- CI en verde y cobertura ≥ 95 %.
- **Toda etiqueta visible sale del backend** (`TextChoices`, catálogo o una constante única, con `ChoiceLabelField`).
- **`ETag`:** si alguna vista nueva envía `ETag` o pide `If-Match`, se declara con `etag_response_headers`.

## Parte 1. "Mi día" (`apps/applications`, o una app nueva `workday` si queda más limpio; anótalo)

### Endpoints
| Método | Ruta | Permiso |
| --- | --- | --- |
| `GET` | `/workday/applications` | `ADMIN` o `ADVISOR` (permiso nuevo `workday.read`) |
| `GET` | `/workday/summary` | el mismo |

### Alcance
- El asesor ve **siempre** sus solicitudes asignadas. Si manda `advisor_id`, la API lo ignora.
- El administrador puede pasar `advisor_id`. Sin él, ve todas las solicitudes no terminales.
- Solo entran solicitudes no terminales.

### Filtros
- `stage` (código de estado), `bank_id`, `purpose`, `search` (código, nombre o documento, igual que el listado), `attention`, `page` y `page_size`.
- Los códigos desconocidos responden `400`, como el listado.

### Segmentos de atención (`attention`)
Configuración fija en el backend, en una constante única con prueba:

| `code` | Etiqueta | Regla |
| --- | --- | --- |
| `REVIEW_DOCUMENTS` | Documentos por revisar | Tiene al menos un slot vigente en `UPLOADED`. |
| `READY_TO_FILE` | Listas para radicar | Estado `READY_TO_FILE`. |
| `FILED` | Radicadas | `FILED` o `FILING_VALIDATION`. |
| `IN_ANALYSIS` | En análisis | `CREDIT_ANALYSIS`. |
| `OBSERVED` | Observadas por el banco | `BANK_OBSERVATION`. |
| `BUYER_INACTIVE` | Comprador sin actividad | La misma regla de `buyer_inactive` del listado. |
| `TASKS_DUE` | Con tareas vencidas o de hoy | Tiene una tarea `PENDING` con `due_at` ≤ fin del día de hoy (Bogotá). |

Un segmento puede compartir solicitudes con otro: no son excluyentes.

### Fila de `/workday/applications`
- `id`, `code`, `client_display_name`, `bank` (`{id, name, short_name}` o `null`) y `bank_product` (`{id, name}` o `null`);
- `status` y `status_label`;
- `next_action` y `next_action_label` (abajo);
- `days_in_stage`: días enteros desde `current_stage_started_at`, según la fecha de Bogotá;
- `attention`: lista de los códigos de segmento que cumple, con su etiqueta;
- `pending_tasks_count` y `updated_at`.
- **Orden por defecto:** primero las que tienen `TASKS_DUE` y después las de más `days_in_stage`. `ordering` admite `days_in_stage`, `updated_at` y `code`.

**Siguiente acción** (constante única por estado, con prueba de que cubre todos los estados no terminales):

| Estado | `next_action` | Etiqueta |
| --- | --- | --- |
| `DRAFT` | `COMPLETE_DRAFT` | Completar el borrador |
| `WAITING_BUYER_DATA` | `FOLLOW_UP_BUYER_DATA` | Hacer seguimiento a los datos del comprador |
| `WAITING_DOCUMENTS` | `FOLLOW_UP_DOCUMENTS` | Hacer seguimiento a los documentos |
| `DOCUMENTS_REVIEW` | `REVIEW_DOCUMENTS` | Revisar documentos |
| `READY_TO_FILE` | `FILE_WITH_BANK` | Radicar en el banco |
| `FILED`, `FILING_VALIDATION`, `CREDIT_ANALYSIS` | `WAIT_BANK_RESPONSE` | Esperar respuesta del banco |
| `BANK_OBSERVATION` | `RESOLVE_OBSERVATIONS` | Resolver las observaciones del banco |
| `APPROVED` | `START_LEGALIZATION` | Iniciar la legalización |
| `LEGALIZATION` | `FOLLOW_UP_LEGALIZATION` | Hacer seguimiento a la legalización |

### `/workday/summary`
- Responde `{ total, segments: [{code, label, count}] }`, en el orden de la tabla.
- Los conteos salen en **una sola consulta** (`aggregate` con `Count(filter=…)`) y aplican los mismos filtros, salvo `attention`.

### Pruebas
- alcance por rol (`advisor_id` ignorado para el asesor);
- cada segmento;
- filtros válidos e inválidos;
- `days_in_stage` con el tiempo congelado;
- cobertura de `next_action`;
- orden;
- consultas constantes con 1 y 25 filas;
- `summary` en una consulta.

**Commit:** `feat(workday): add the advisor workday with attention segments and next actions`

## Parte 2. Tareas manuales (app nueva `apps/tasks`)

### Modelo y catálogo
- **`Task`**, según `tasks` del SQL: `opportunity` o `application` (al menos uno), `assigned_to`, `created_by`, `title` (180), `description`, `priority_item` (catálogo `task_priority`), `status` (`PENDING`, `COMPLETED` o `CANCELLED`), `source` (`MANUAL` o `AUTOMATIC`; en este módulo solo se crean `MANUAL`), `due_at` y `completed_at`.
  - Más `cancel_reason` (texto) y `cancelled_at`, que no están en el SQL: los agregas al SQL y al DER.
  - Con los `CHECK` del SQL.
- **Catálogo `task_priority`** (migración de datos con `reverse`): `LOW` "Baja", `MEDIUM` "Media" y `HIGH` "Alta".
- **Permisos** (migración): `tasks.read`, `tasks.create`, `tasks.update`, `tasks.complete` y `tasks.cancel`, para `ADMIN` y `ADVISOR`.

### Endpoints (API §15.2)
- `GET /tasks`:
  - **Alcance:** el asesor ve las tareas asignadas a él y las de sus solicitudes u oportunidades; el administrador, todas.
  - **Filtros:** `status`, `application_id`, `opportunity_id`, `assigned_to_id` (solo administrador), `due` (`overdue`, `today` o `upcoming`, según la fecha de Bogotá) y `priority`.
  - **Orden:** `due_at`, con los nulos al final.
- `POST /tasks`:
  - `title`, `description`, `application_id` u `opportunity_id`, `assigned_to_id` (por defecto, el actor), `due_at` y `priority_code` (por defecto `MEDIUM`).
  - El padre debe estar dentro del alcance del actor.
  - El responsable debe ser un usuario activo con rol `ADMIN` o `ADVISOR`.
  - Una solicitud terminada responde `409 APPLICATION_CLOSED`.
- `GET /tasks/{id}` y `PATCH /tasks/{id}` (título, descripción, responsable, `due_at` y prioridad). Solo con `PENDING`; si no, `409 TASK_NOT_PENDING` (código nuevo en API §5.5).
- `POST /tasks/{id}/complete` y `POST /tasks/{id}/cancel` (este último con `reason`, obligatorio). Solo desde `PENDING`.
- **Respuesta:**
  - `status_label`, `priority` (`{code, label}`) y `source_label`;
  - `assigned_to` y `created_by` como `{id, name}`;
  - el padre como `{type, id, code}`;
  - `is_overdue`.
- El broker y la constructora no ven tareas: `403`.

### Pruebas
- alcance;
- validaciones del padre y del responsable;
- cada transición y los estados inválidos;
- filtros de `due` con el tiempo congelado;
- solicitud cerrada;
- consultas constantes en la lista.

**Commit:** `feat(tasks): add manual tasks with priority, due dates and scope`

## Parte 3. Actividad y notas (app nueva `apps/activity`)

### Modelo
- **`ActivityLog`**, según `activity_logs` del SQL: `client`, `opportunity` o `application` (al menos uno), `event_type`, `visibility` (`INTERNAL` o `BUYER`), `title`, `message`, `actor_user` o `actor_buyer_session` (como mucho uno) y `metadata` (JSON).
- **Inmutable:** no hay `PATCH` ni `DELETE`.

### Cómo se registra
- Un servicio único `record_activity(...)`, llamado desde **suscriptores de señales** en `apps/activity/receivers.py`, conectados en `ready()`.
- Los servicios de otras apps no importan `activity`.
- Si un evento no tiene señal todavía, se agrega la señal en su app (por ejemplo, `document_uploaded` y `document_reviewed` en `documents/signals.py`) y se emite en su servicio con `transaction.on_commit`.

### Eventos mínimos
`title` es un texto en español armado en el backend, con nombres y etiquetas.

| `event_type` | Origen | Visibilidad | Título (ejemplo) |
| --- | --- | --- | --- |
| `APPLICATION_CREATED` | `application_created` | interna | Solicitud creada desde la oportunidad OPP-000431 |
| `STATUS_CHANGED` | `application_status_changed` | interna y del comprador (dos filas: la del comprador usa la etiqueta pública) | Pasó de Esperando documentos a Revisión documental |
| `ADVISOR_ASSIGNED` | `application_assigned` | interna | Paula Rincón quedó como asesora |
| `PARTICIPANT_ADDED` / `PARTICIPANT_REMOVED` | señales existentes | interna | Se agregó a Daniel Mejía como co-solicitante |
| `DOCUMENT_UPLOADED` | nueva | interna y del comprador | Sofía Herrera cargó el certificado laboral |
| `DOCUMENT_REVIEWED` | nueva | interna; solo los rechazos también para el comprador, con el mensaje al comprador | Paula Rincón rechazó el desprendible de nómina 2 de 3 |
| `BUYER_LINK_SENT` | nueva (al crear el enlace) | interna | Andrés Cárdenas envió el enlace de acceso al comprador |
| `BUYER_SESSION_STARTED` | nueva (al consumirlo) | interna | El comprador entró al portal |
| `CONSENT_RECORDED` | nueva | interna | Sofía Herrera aceptó el tratamiento de datos |
| `TASK_CREATED` / `TASK_COMPLETED` / `TASK_CANCELLED` | señales nuevas de `tasks` | interna | Tarea completada: Revisar extractos |
| `NOTE_ADDED` | notas | interna | Nota de Paula Rincón |
| `FILING_CREATED` / `BANK_RESPONSE_RECORDED` | señales de `filings` (**solo si al traer `master` ya existe la app**) | interna; la respuesta también para el comprador si tiene `public_message` | Radicada en Bancolombia (#1) |

**Lo que nunca va a una fila del comprador:** notas internas, `internal_comment`, comentarios internos de revisión, identidades técnicas, IP ni agente de usuario.

### Endpoints
- `GET /applications/{id}/activity`: actor interno con alcance (el broker solo ve las filas `BUYER`). Paginada y en orden descendente.
  - Filtro `event_type` (lista).
  - Respuesta: `id`, `event_type`, `event_type_label`, `title`, `message`, `actor` (`{name}` o "portal del comprador") y `created_at`.
- `GET /buyer/applications/{id}/activity`: solo las filas `BUYER`, con el actor como "Tú" o "Tu asesor".
- `GET /applications/{id}/notes` y `POST /applications/{id}/notes`:
  - permiso `applications.add_note` (`ADMIN` y asesor asignado; migración);
  - `body` obligatorio, máximo 2000 caracteres;
  - se guarda como `ActivityLog` `NOTE_ADDED`, `INTERNAL`.
- **Backfill:** una migración de datos que crea `STATUS_CHANGED` desde `application_status_history` para las solicitudes existentes, idempotente. Así los datos de demo ya tienen línea de tiempo.

### Pruebas
- cada evento genera su fila con la visibilidad correcta;
- el comprador no ve nada interno;
- el broker solo ve las filas del comprador;
- notas;
- backfill idempotente;
- consultas constantes;
- un error en un suscriptor no rompe la operación original (`on_commit` y log).

**Commit:** `feat(activity): add the application activity timeline and internal notes`

## Cierre
- **Docs:** API §15 y §21.1 según lo implementado; DER, SQL y modelo de datos (`tasks` con su cancelación, `activity_logs`, catálogo y permisos); README del backend (los módulos).
- **`specs/TAREA-frontend-base.md`, "Brechas":** anota que la "Actividad reciente" ya tiene endpoint (`/applications/{id}/activity`) y que "Mi día" tiene API lista para una pantalla futura.
- **`seed_demo_data`:** agrega unas 8 tareas de demo (vencidas, de hoy y futuras) para el asesor e2e y una nota en dos solicitudes, respetando la idempotencia.
- **Trae `master` antes de entregar.** Si la radicación ya se fusionó, conecta sus suscriptores y regenera.
- Entregas el **título y la descripción del PR**, en español, sin firmas.

## Precisiones acordadas
_(las agrega el agente)_

### Parte 1
- **P1.1 Dónde vive.** App nueva `apps/workday`, sin modelos propios: `rules.py` (constantes `AttentionSegment`, `NextAction` y `NEXT_ACTIONS`, y la regla de cada segmento), `services.py` (queryset y resumen), serializers, vistas, rutas y la migración del permiso `workday.read` (`ADMIN` y `ADVISOR`). Así `applications` no crece más y "Mi día" no queda mezclado con el listado.
- **P1.2 El modelo `Task` se adelanta.** El segmento `TASKS_DUE` y `pending_tasks_count` necesitan las tareas, así que en esta parte se crea `apps/tasks` con el modelo `Task` (incluidos `cancel_reason` y `cancelled_at`, con `ck_tasks_cancellation`) y el catálogo `task_priority` (migración con `reverse`). Los permisos, servicios, endpoints y señales de tareas quedan para la Parte 2.
- **P1.3 Reglas en la base de datos.** Cada segmento es una condición de base de datos (`segment_conditions`), anotada como booleano en el queryset. La fila, el filtro `attention` y los conteos del resumen usan exactamente las mismas, sin consultas por fila. `BUYER_INACTIVE` usa `buyer_inactive_condition` (nueva en `applications/services.py`), la misma regla y los mismos campos que `buyer_inactive` del listado.
- **P1.4 Fecha de Bogotá.** "Hoy" y "fin del día" salen de `TIME_ZONE` (`America/Bogota`). `days_in_stage` es `fecha de hoy - fecha de inicio de la etapa`, las dos en Bogotá (`TruncDate` con la zona del proyecto; en PostgreSQL la resta de fechas da un entero). `TASKS_DUE` usa `due_at <= 23:59:59.999999` de hoy en Bogotá, así que también cuenta las vencidas.
- **P1.5 Alcance.** Con el rol `ADMIN` (o superusuario) se ve todo y se acepta `advisor_id`. Cualquier otro actor con `workday.read` ve solo sus asignadas, y su `advisor_id` se ignora sin validarlo (ni siquiera un valor que no es UUID responde `400`). Broker y constructora no tienen el permiso: `403`.
- **P1.6 Filtro `stage`.** Solo admite estados no terminales: un terminal, o un código desconocido, responde `400`, porque nunca hay solicitudes terminales en "Mi día". `purpose` valida contra el catálogo `loan_purpose`, `bank_id` debe ser un UUID y `ordering` solo admite `days_in_stage`, `updated_at` y `code` (con `-`). `search` usa los mismos campos que el listado.
- **P1.7 Orden.** Por omisión: `TASKS_DUE` primero, después más `days_in_stage` y después `code`, para que el orden sea estable. Con `ordering`, el orden indicado reemplaza al de omisión.
- **P1.8 Forma de la fila.** `bank` es `{id, name, short_name}` del banco del producto elegido y `bank_product` es `{id, name}`; los dos son `null` sin producto. `attention` es una lista de `{code, label}` en el orden de la tabla. Las etiquetas de `status`, `next_action` y los segmentos salen de sus `TextChoices`.
- **P1.9 Resumen.** `services.summary` hace un solo `aggregate` con `Count(filter=…)` por segmento; aplica los mismos filtros que la lista (incluida la búsqueda), salvo `attention`. La prueba mide la consulta del servicio, porque la petición suma las de la sesión y los permisos.
- **P1.10 Nombres de enums.** El `code` de los segmentos chocaba con el `code` de `CompletenessItem`, y drf-spectacular renombraba el `CodeEnum` ya publicado. En `ENUM_NAME_OVERRIDES` quedan fijos `CodeEnum` (las opciones, ahora en la constante `COMPLETENESS_ITEM_CODES`), `AttentionSegmentEnum` y `NextActionEnum`. Una prueba nueva (`tests/test_contract_names.py`) protege esos nombres y los de la tarea anterior.
- **P1.11 Pruebas con el tiempo congelado.** El cliente inicia sesión dentro del bloque `freeze_time`: un token emitido con la hora real no vale en otra fecha.
