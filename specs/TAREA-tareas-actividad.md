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

### Agregado 2b (tipo de cada acción disponible)
- **P2b.1 Dónde vive.** `apps/applications/actions.py`: `ActionKind` (`primary`, `secondary`, `destructive`), `ACTION_KIND_BY_TARGET_STATUS` (cubre todos los estados; una prueba lo exige) y `BACKWARD_TRANSITION_CODES` (`RETURN_TO_DOCUMENTS` y `REOPEN_REVIEW`, secundarias aunque su destino esté en el camino principal). Por estado destino y no por código, para que una transición nueva creada desde la administración quede clasificada sin tocar código; las que retroceden son la única excepción por código.
- **P2b.2 Orden.** `services.available_actions` ordena por grupo con un `sorted` estable sobre el orden por código de `available_transitions`, así que el detalle, `/available-actions` y la creación comparten el mismo orden.
- **P2b.3 Contrato.** `kind` es un campo nuevo de `AvailableAction`, con el nombre de enum fijo `AvailableActionKindEnum` (protegido en `tests/test_contract_names.py`). No se agrega `kind_label`.

### Parte 2
- **P2.1 Un solo padre al crear.** `POST /tasks` exige exactamente uno de `application_id` u `opportunity_id` (ninguno o los dos: `400`, error sin campo). Una tarea manual guarda solo ese padre; así `parent` no es ambiguo.
- **P2.2 Padre fuera del alcance.** Responde `400 VALIDATION_ERROR` en `application_id` u `opportunity_id` ("no existe"), como `POST /applications` con una oportunidad ajena. La oportunidad se resuelve con `resolve_visible_opportunity` y la solicitud con `applications_visible_to`.
- **P2.3 Alcance del asesor.** Ve las tareas asignadas a él y las de las solicitudes que tiene asignadas o de las oportunidades que tiene asignadas o capturó (las mismas reglas de visibilidad de CRM). El administrador (o superusuario) ve todas. Cualquier otro actor con `tasks.read` vería solo las asignadas a él. Fuera del alcance: `404`.
- **P2.4 Responsable.** Activo, no borrado y con rol `ADMIN` o `ADVISOR` (o superusuario); si no, `400 VALIDATION_ERROR` en `assigned_to_id` (no un código nuevo). El responsable por omisión es el actor y también se valida.
- **P2.5 `assigned_to_id` en la lista.** Solo para el administrador; para el asesor se ignora sin validarlo, igual que `advisor_id` en "Mi día".
- **P2.6 `due` y `is_overdue`.** Se miden con la fecha de Bogotá y solo aplican a tareas `PENDING` con `due_at`: `overdue` es antes del inicio de hoy, `today` es hoy y `upcoming` es después de hoy. `is_overdue` usa la misma regla que `overdue`, así que una tarea de hoy a las 9:00 no está vencida a las 15:00 (sale en `today`). Coincide con `TASKS_DUE` de "Mi día", que cuenta las vencidas y las de hoy.
- **P2.7 Forma de `parent`.** `{type, type_label, id, code, client_display_name}`. Las oportunidades no tienen código: `code` es nulo y `client_display_name` las identifica. `type` es `APPLICATION` u `OPPORTUNITY`.
- **P2.8 Solicitud terminada.** Solo bloquea la creación (`409 APPLICATION_CLOSED`). Las tareas pendientes de una solicitud que terminó se pueden seguir editando, completando o cancelando, para poder limpiarlas.
- **P2.9 Sin `ETag`.** Las tareas no tienen versión: `PATCH`, `complete` y `cancel` bloquean la fila (`select_for_update`) y validan el estado dentro de la transacción.
- **P2.10 Señales.** `task_created`, `task_completed` (con `actor`) y `task_cancelled` (con `reason` y `actor`) en `apps/tasks/signals.py`, enviadas con `transaction.on_commit`. Las usará la Parte 3.
- **P2.11 Límites de texto.** `description` hasta 4000 caracteres y `reason` de la cancelación hasta 1000 (el modelo usa `TEXT`).
- **P2.12 Nombres de enums.** `TaskStatusEnum`, `TaskSourceEnum` y `TaskParentTypeEnum` quedan fijos en `ENUM_NAME_OVERRIDES` (y en `tests/test_contract_names.py`). Sin eso salían como `SourceEnum` y `TypeEnum`, que la Parte 3 renombraría al agregar otros campos `type` o `source`. `TaskParentType` vive en `apps/tasks/models.py`, junto a los demás.

### Parte 3
- **P3.1 Señales de B copiadas idénticas.** `document_reviewed` (`documents/signals.py` y su envío en `documents/reviews.py`), `buyer_access_consumed` (`identity/signals.py` y `identity/buyer_sessions.py`) son copia byte a byte de `origin/feat/notifications` (PR #23). Al fusionar, `reviews.py` y `buyer_sessions.py` no chocan.
- **P3.2 Señales nuevas mías.** `document_uploaded` va al principio de `documents/signals.py`, lejos de las líneas de B, para que git una sin conflicto. `buyer_access_link_issued` y `consent_recorded` van a continuación de `buyer_access_consumed` en `identity/signals.py`: como B también crea ese archivo, al fusionar habrá un conflicto de "los dos lo agregaron" que se resuelve dejando el de esta rama (es el de B más dos líneas). Las tres se envían con `transaction.on_commit`.
- **P3.3 Quién ve qué.** El administrador y el asesor ven solo las filas `INTERNAL`; el broker (en las que originó) y el comprador, solo las `BUYER`. Todo evento que ve el comprador deja también su fila interna, así que el backoffice no pierde nada y no ve duplicados.
- **P3.4 Permisos.** `/activity` usa `applications.read` con el alcance de la solicitud (el broker lo tiene; la constructora no: `403`). Las notas usan `applications.add_note` para leer y para escribir.
- **P3.5 Actor.** `{name}` o nulo. En el backoffice, una fila del comprador sale como "Portal del comprador"; en `/buyer/...`, "Tú" (sesión del comprador) o "Tu asesor" (usuario interno). Nunca se expone el id de la sesión, la IP ni el agente de usuario.
- **P3.6 Títulos.** Las oportunidades no tienen código, así que `APPLICATION_CREATED` dice "Solicitud SOL-000123 creada". `ADVISOR_ASSIGNED` dice "X quedó como responsable" (sin suponer el género). Los documentos van entre comillas angulares con su número si el slot pide varios ("«Desprendible de nómina» 2 de 3") y el nombre del participante si no es el titular. El rechazo para el comprador dice "Tu asesor rechazó…", con el `buyer_comment`.
- **P3.7 Mensajes.** La fila interna de un cambio de estado lleva el comentario de la transición; la del comprador va sin mensaje. Una revisión interna lleva el `internal_comment` (o el `buyer_comment`). Una respuesta del banco interna lleva el `internal_comment` (o el `public_message`); la del comprador, solo el `public_message`.
- **P3.8 Errores en suscriptores.** Cada suscriptor corre en su propio punto de guardado (`transaction.atomic`) dentro de `never_raises`: un error, incluso de base de datos, se registra con `logger.exception` y no rompe la operación ni la transacción de afuera.
- **P3.9 `created_at` con `default`.** `ActivityLog.created_at` usa `default=timezone.now` (no `auto_now_add`) para que el backfill conserve la fecha del historial. `message` es texto vacío cuando no hay detalle (en el SQL es nulable).
- **P3.10 Backfill.** La fila del historial sin `from_status` da `APPLICATION_CREATED`; cada cambio da sus dos `STATUS_CHANGED`, con el actor y la fecha del historial. Idempotente por `metadata.status_history_id`, que también guardan las filas creadas en vivo (el suscriptor busca la fila del historial), así que el backfill nunca duplica lo que ya registró un suscriptor. Deshacer la migración no borra nada.
- **P3.11 Notas en una solicitud terminada.** Se admiten: una nota de cierre es útil.
- **P3.12 Filtro `event_type`.** Se repite el parámetro (`?event_type=A&event_type=B`); un código desconocido responde `400`.
- **P3.13 Nombre del enum.** `ActivityEventTypeEnum` queda fijo en `ENUM_NAME_OVERRIDES` y en `tests/test_contract_names.py` (sin eso salía `EventTypeEnum`).

### Cierre
- **PC.1 Demo.** `apps/tasks/demo_data.py` (8 tareas: 2 vencidas, 2 de hoy, 3 próximas y 1 sin fecha) y `apps/activity/demo_data.py` (2 notas), llamados al final de `seed_demo_data` para el asesor de `--advisor-email` o, sin él, para la primera asesora. Pasan por los servicios, así que también dejan su actividad. La idempotencia es la del comando: si ya hay datos de demo, no hace nada.
- **PC.2 Falla intermitente de `test_seed_creates_the_demo_data`.** La causa es el reloj, pero no basta con repetir la prueba. `latest_evaluation` elegía la última evaluación bancaria por `created_at`; la demo guarda una al pasar a `READY_TO_FILE` y otra al final, con la versión nueva. Si el reloj de la VM retrocede entre las dos, la vieja (no vigente) pasaba por la última y la completitud quedaba en 90. Ahora ordena por `application_version` y después por `created_at`, que es lo correcto también en producción ante un ajuste del reloj. Prueba nueva: `test_latest_follows_the_version_even_if_the_clock_went_back`, que falla con el orden anterior.
