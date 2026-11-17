# Tarea: notificaciones del comprador e idempotencia (módulo 13)

## Objetivo
- **Notificaciones del comprador** (RF-64, RF-65, RF-73, REQ §4.5, API §21.2): cada evento importante de su solicitud le crea un aviso en el portal y le envía un correo transaccional. El aviso en el portal es la fuente de verdad: si el correo falla, no se revierte nada.
- **`Idempotency-Key`** (API §6): tabla `idempotency_keys` y su soporte en los `POST` críticos.

## Cuándo y dónde
- **Agente:** backend B, en el worktree `wt-back-notifications`, rama `feat/notifications`, desde `master` (ya tiene la radicación #19 y la F1 #17).
- **En paralelo:**
  - el backend A hace el módulo 12 en la carpeta principal (apps `workday`, `tasks` y, después, `activity`);
  - el front hace la F2 (portal).
- **Tu código vive en una app nueva, `apps/notifications`** (y `apps/idempotency`, si queda más limpio; anótalo). Fuera de ellas solo tocas los puntos de esta spec, `INSTALLED_APPS` y `config/urls.py`.
- **Coordinación con A:** él va a crear, en su Parte 3, las señales `document_uploaded` y `document_reviewed` en `documents/signals.py`. **Tú necesitas `document_reviewed`.**
  - Si al empezar no existe en `master`, créala tú en `documents/signals.py`, con argumentos `slot`, `document_file`, `review` y `actor`, y emítela en `documents/reviews.py` después del commit (`transaction.on_commit`).
  - Anótalo en el reporte: A la reutilizará al traer `master`.

## Cómo corres el backend
Igual que en la radicación: **nada de `docker compose`**, solo contenedores de un solo uso con tu worktree y tu base de pruebas:

```
docker run --rm --network mvp_credit_network --env-file C:\Users\ASUS\Documents\programacion\mvp-backoffice\real-estate-credit-backoffice\backend\.env -e DATABASE_HOST=postgres -e DATABASE_NAME=mvp_credit_b -v C:\Users\ASUS\Documents\programacion\mvp-backoffice\wt-back-notifications\backend:/app -v C:\Users\ASUS\Documents\programacion\mvp-backoffice\wt-back-notifications\contracts:/contracts -w /app mvp-credit-backend-backend <comando>
```

- El `.env` solo entra por `--env-file`: no lo abras.
- No apliques migraciones a la base de `:8000`. Se aplican solas cuando el PR se fusiona.

## Reglas de trabajo
- Git solo en lectura. Carlos hace todos los commits y push, sin `Co-Authored-By` ni firmas.
- **Comunicación por buzón** (`.buzon/PROTOCOLO.md`): reporte completo en `.buzon/reportes/`, `ESTADO.md` al día y en la consola una línea.
- **No se presentan dudas.** Lo que no esté cubierto lo decides tú con la opción más simple, lo anotas en "Precisiones acordadas" y sigues. Solo te detienes si rompe un contrato publicado, cambia el alcance, borra o altera datos existentes, o exige tocar un `.env`.
- **Al cerrar cada parte:** contrato (`--validate --fail-on-warn`) y `schema.d.ts` regenerados (`npx --yes openapi-typescript@7.13.0 ../contracts/openapi.json -o src/lib/api/schema.d.ts`, desde `frontend/`).
- Cobertura ≥ 95 %. Etiquetas con `ChoiceLabelField`. Un `ETag` nuevo se declara con `etag_response_headers`.

## Parte 1. Modelo, eventos y aviso en el portal

### Modelos (según el SQL)
- **`Notification`:**
  - `client` (destinatario comprador) o `user` (interno), exactamente uno;
  - `application`, `notification_type`, `title` (180), `message` (texto público), `read_at` y `deduplication_key` (único).
  - En este módulo solo se crean notificaciones para el comprador (`client`). Las internas quedan para después y se anotan como brecha.
- **`NotificationDelivery`:**
  - `notification`, `channel` (`EMAIL` o `PORTAL`), `destination`, `status` (`PENDING`, `SENT` o `FAILED`), `attempt_count`, `next_attempt_at`, `sent_at`, `provider_message_id` y `last_error_code`;
  - con los `CHECK` del SQL.
- **Tipo de notificación:** `TextChoices` con su etiqueta y una plantilla de título y mensaje en una constante única.

### Eventos (suscriptores en `apps/notifications/receivers.py`, conectados en `ready()`)
| `notification_type` | Señal | Cuándo | Título (ejemplo) | Mensaje |
| --- | --- | --- | --- | --- |
| `ACCESS_GRANTED` | `consume` del enlace (señal nueva en `identity`, o en el servicio con `on_commit`) | El comprador entra por primera vez con un enlace | Bienvenido a tu portal | Siguiente paso según `next_action` |
| `DOCUMENT_REJECTED` | `document_reviewed` con decisión de rechazo | Cada rechazo | Debes corregir: <documento> | El mensaje al comprador de la revisión |
| `READY_TO_FILE` | `application_status_changed` → `READY_TO_FILE` | — | Tu expediente está completo | Texto fijo |
| `FILED` | `filing_created` | — | Radicamos tu solicitud en <banco> | Texto fijo con la fecha |
| `BANK_RETURNED` | `filing_response_recorded` con `RETURNED` | — | El banco pidió correcciones | `public_message` |
| `BANK_APPROVED` | … `APPROVED` | — | ¡Tu crédito fue aprobado! | `public_message` |
| `BANK_REJECTED` | … `REJECTED` | — | El banco rechazó tu solicitud | `public_message` |
| `DISBURSED` | … `DISBURSED` | — | Se desembolsó tu crédito | Texto fijo con la fecha |

- **Destinatario:** el titular activo de la solicitud (`PRIMARY`).
- **`deduplication_key`:** tipo más el id del objeto que la origina (por ejemplo, `BANK_APPROVED:<response_id>` o `DOCUMENT_REJECTED:<review_id>`). Un evento repetido no duplica nada: `get_or_create`.
- **Las señales llegan después del commit del dominio:** el suscriptor crea la notificación en su propia transacción. Un error se registra en el log y **nunca** rompe la operación original.
- **Nunca** van en el texto notas internas, `internal_comment`, números de identificación completos ni montos de ingresos. El monto aprobado sí puede ir en la aprobación (es del comprador).
- Al crear la notificación se crean sus dos entregas: `PORTAL` (`SENT` de inmediato) y `EMAIL` (`PENDING`; ver Parte 2).

### Endpoints del comprador (API §21.2)
- `GET /buyer/notifications`:
  - solo las de su cliente y su solicitud de la sesión;
  - paginadas, de la más nueva a la más vieja;
  - filtro `unread=true`;
  - campos: `id`, `notification_type`, `notification_type_label`, `title`, `message`, `created_at` y `read_at`.
- `GET /buyer/notifications/unread-count`: `{count}`, para el número de la navegación.
- `PATCH /buyer/notifications/{id}/read`: idempotente.
- `POST /buyer/notifications/read-all`: responde el número marcado.
- Requieren la sesión del comprador. Una notificación de otro cliente responde `404`. Un `CONSENT_REQUIRED` **no** bloquea leer ni marcar como leídas.

### Endpoint interno
- `GET /applications/{id}/notifications`, para el administrador y el asesor asignado. Muestra cada notificación con sus entregas (canal, estado, intentos y último error), para que el asesor sepa si el correo salió (REQ, E2E 18).

### Pruebas
- cada evento crea su notificación una sola vez (deduplicación);
- el texto no filtra datos internos;
- el alcance del comprador;
- marcar leída y todas leídas;
- conteo de no leídas;
- un error en el suscriptor no rompe la operación;
- el endpoint interno con sus entregas.

**Commit:** `feat(notifications): add buyer notifications for application and bank events`

## Parte 2. Correo transaccional con reintentos
- **Tarea Celery `deliver_notification_email(delivery_id)`**, encolada con `on_commit` al crear la notificación. En el modo local corre en el mismo proceso, y con `EMAIL_BACKEND` de consola el correo sale por el log.
- **Destino:** el correo del cliente. Sin correo, la entrega queda `FAILED` con `last_error_code="NO_DESTINATION"`, sin reintentos.
- **Reintentos:** hasta 5, con espera exponencial (1, 5, 15, 60 y 240 minutos), guardando `attempt_count`, `next_attempt_at` y `last_error_code`. Después del último, `FAILED`.
- **Comando `retry_notification_deliveries`:** reencola las `PENDING` vencidas (para el modo local sin beat). El README dice que en un entorno real correría periódicamente.
- **Contenido** (REQ §9.2):
  - asunto con el título, el mensaje público y una línea "Entra a tu portal con el enlace que te envió tu asesor; si se venció, pídele uno nuevo";
  - **sin** enlace mágico (los enlaces los emite el asesor), sin adjuntos, sin notas internas y sin datos financieros sensibles;
  - texto plano y HTML simple, con plantillas en `apps/notifications/templates/`.
- **Pruebas:** envío correcto (`locmem`), sin destino, fallo con reintento y paso a `FAILED` al agotar intentos, comando de reintento y contenido sin datos prohibidos.

**Commit:** `feat(notifications): deliver buyer notifications by email with retries`

## Parte 3. `Idempotency-Key`
- **Modelo `IdempotencyKey`** según el SQL: actor (`user` o `buyer_session`), `key` (100), `method`, `route_fingerprint`, `request_hash`, la respuesta guardada (código, cuerpo y cabeceras relevantes) y `expires_at` (24 h).
- **Un decorador o mixin único** para las vistas: `POST` de radicación, respuesta bancaria, transición de estado, paquete para radicar y enlace mágico (API §6).
- **Comportamiento:**
  - **Opcional por ahora:** sin cabecera, la vista funciona como hoy. Así no se rompe el front, que todavía no la envía. Se anota en "Brechas" para que el front la mande.
  - **Con cabecera:**
    - misma clave y mismo cuerpo: se devuelve la respuesta original, con el mismo código;
    - misma clave y cuerpo distinto: `422 IDEMPOTENCY_CONFLICT`;
    - dos peticiones simultáneas con la misma clave: la segunda espera el bloqueo de la fila o responde `409 IDEMPOTENCY_IN_PROGRESS`; elige lo más simple y anótalo.
  - Solo se guardan las respuestas `2xx`.
- **Comando `purge_idempotency_keys`:** borra las vencidas (son datos técnicos). El README lo documenta.
- **Contrato:** cabecera `Idempotency-Key` opcional, declarada en esas cinco operaciones, con los errores nuevos.
- **Pruebas:**
  - repetición con la misma respuesta;
  - conflicto;
  - sin cabecera, igual que hoy;
  - clave de otro actor, independiente;
  - vencimiento;
  - las cinco vistas.

**Commit:** `feat(api): support Idempotency-Key on critical POST operations`

## Cierre
- **Docs:** API §6 (idempotencia implementada y opcional), §21.2 (notificaciones, el conteo y el endpoint interno) y §5.5 (errores nuevos); DER, SQL y modelo de datos; README del backend (correo, reintentos y comandos).
- **`specs/TAREA-frontend-base.md`, "Brechas":**
  - "Avisos" del portal: ya hay API;
  - el front debe enviar `Idempotency-Key` en esas cinco operaciones;
  - las notificaciones internas (campana del backoffice), pendientes.
- **`seed_demo_data`:** como las señales disparan las notificaciones, una base nueva ya las tendrá. Verifica que la demo cree al menos los avisos de las solicitudes radicadas y de los rechazos, sin duplicar en la segunda corrida.
- **Trae `master` antes de entregar.** Carlos hace el merge; tú resuelves los conflictos (sin git), regeneras y verificas.
- Entregas el **título y la descripción del PR**, en español, sin firmas.

## Precisiones acordadas

### Parte 1
1. **App única `apps/notifications`** para esta parte (modelos, plantillas, suscriptores, vistas). La idempotencia se decide en la Parte 3.
2. **`document_reviewed` la creé yo** en `documents/signals.py` (no estaba en `master`), con `slot`, `document_file`, `review` y `actor`. Se emite **una vez por cada fila de `document_reviews`** (aprobar y rechazar dejan una; exonerar y reabrir, una por slot afectado), con `transaction.on_commit`. Una revisión dentro de otra operación (las observaciones de una devolución del banco) se emite cuando esa operación confirma. El backend A la reutiliza al traer `master`.
3. **Señal nueva `buyer_access_consumed`** en `apps/identity/signals.py` (archivo nuevo), con `link` y `session`, enviada después de la transacción del consumo, como las demás señales del dominio.
4. **`ACCESS_GRANTED` se crea una sola vez por solicitud y comprador:** `deduplication_key = ACCESS_GRANTED:<solicitud>:<cliente>`. Los consumos siguientes (enlaces nuevos) no la repiten. Mensaje: el `next_action` del estado actual.
5. **`READY_TO_FILE` usa la versión de la solicitud:** `READY_TO_FILE:<solicitud>:<versión>`. Si vuelve a quedar lista (re-radicación después de una devolución), avisa otra vez; el mismo evento repetido no.
6. **Una devolución del banco avisa dos cosas:** `BANK_RETURNED` con el `public_message` y un `DOCUMENT_REJECTED` por cada documento observado (cada observación rechaza la versión con `review_slot`, con el mensaje de la observación). Así el comprador sabe qué documento corregir. La nota interna ("Observación del banco en la radicación #N") nunca sale.
7. **Correcciones de respuestas del banco:** solo `RECEIVED`, `IN_ANALYSIS` y `OTHER` se corrigen, y ninguna avisa; no hace falta tratarlas aparte.
8. **Título de `DOCUMENT_REJECTED`:** el nombre del tipo documental; si el documento es de otro participante (co-solicitante), se agrega "de <nombre completo>". Cualquier título se corta a 180 caracteres con "…".
9. **Textos:** `BANK_APPROVED` = `public_message` + "Monto aprobado: $294.000.000 a 240 meses." `DISBURSED` = texto fijo con la fecha, sin monto. `FILED` usa el nombre del banco y la fecha de radicación. Fechas como "17 de noviembre de 2026" en la hora local. Todos los textos viven en `apps/notifications/messages.py` (`MESSAGES`).
10. **Entregas:** `PORTAL` nace `SENT` con `attempt_count = 1` y `sent_at`. `EMAIL` nace `PENDING` con `destination` = el correo del cliente (o nulo si no tiene) y `next_attempt_at` = ahora. **Desvío del SQL:** `UNIQUE (notification_id, channel)` (`uq_notification_deliveries_channel`), para que reintentar nunca duplique una entrega. El índice de la cola se llama `ix_notification_delivery_queue` (Django admite 30 caracteres; en el SQL, `ix_notification_deliveries_queue`).
11. **`notification_type` sin `CHECK`**, como en el SQL: los tipos internos llegarán después. El modelo sí tiene `choices` (`NotificationType`).
12. **Suscriptores:** `never_raises` registra el error en el log y no lo propaga; cada notificación se crea en su propio `transaction.atomic()` (un savepoint si quien emite sigue dentro de otra transacción). Sin titular activo (`PRIMARY`), no se crea nada y queda un `warning`.
13. **Portal:** las cuatro vistas usan solo `IsBuyerSession`: ni `CONSENT_REQUIRED` ni una solicitud terminada impiden leer o marcar (marcar no cambia el expediente). Las escrituras exigen CSRF, como el resto del portal, y las respuestas llevan `Cache-Control: no-store`.
14. **Respuestas:** `PATCH /read` responde la notificación (`200`, sin cuerpo de entrada). `POST /read-all` y `GET /unread-count` responden `{count}` (en `read-all`, cuántas estaban sin leer y se marcaron). `unread` es booleano; un valor inválido responde `400 VALIDATION_ERROR`.
15. **Endpoint interno:** permiso nuevo `notifications.read` (`ADMIN`, `ADVISOR`) sembrado por migración, y el alcance de la solicitud: el asesor no asignado recibe `404`, el broker `403`. Cada entrega muestra `channel`, `status` (con etiquetas), `destination`, `attempt_count`, `next_attempt_at`, `sent_at` y `last_error_code`.
16. **Brecha:** las notificaciones internas (`user`) no se crean en este paso.

### Parte 2
1. **Un intento por ejecución, hasta 6 en total:** el primero, más 5 reintentos que esperan 1, 5, 15, 60 y 240 minutos después de cada fallo. Si falla el sexto, la entrega queda `FAILED` con `next_attempt_at` nulo.
2. **La tarea no usa `self.retry` de Celery:** en el modo inmediato correría en el acto, sin esperar. Con worker, la tarea se vuelve a encolar con `apply_async(countdown=…)`. En el modo inmediato no se reencola: la retoma `retry_notification_deliveries` cuando vence `next_attempt_at`.
3. **Idempotente:** la tarea bloquea la fila (`select_for_update`) y no hace nada si la entrega no es `EMAIL`, no está `PENDING` o su `next_attempt_at` aún no llega. Así, un ETA repetido de Redis o el comando junto con un reintento programado nunca envían dos veces.
4. **`NO_DESTINATION`** no cuenta como intento (`attempt_count` sigue en 0) y no se reintenta.
5. **`last_error_code`:** `SMTP_ERROR` (`smtplib.SMTPException`), `CONNECTION_ERROR` (`OSError`) o `SEND_FAILED` (cualquier otro). El log registra la clase del error, nunca el correo del destinatario.
6. **`provider_message_id`** es el `Message-ID` que genera el backend (`make_msgid`): no hay proveedor externo.
7. **Encolado:** `on_commit` al crear la notificación. Si el broker no responde (`OperationalError`), queda un `warning` y la entrega sigue `PENDING` para el comando. La operación que avisó no se entera.
8. **Contenido:** saludo con los nombres del cliente, el título, el mensaje, la línea del portal y "Este es un mensaje automático; no lo respondas". El HTML escapa el texto (`linebreaksbr` para los saltos de línea).
9. **El comando no tiene opciones:** reencola todas las `EMAIL` `PENDING` con `next_attempt_at` vencido o nulo, de la más antigua a la más nueva.
10. **README:** la sección "Buyer Notifications" ya documenta los endpoints, el correo, los reintentos y el comando. En el cierre se agrega la idempotencia.

### Parte 3
1. **App propia `apps/idempotency`** (modelo, servicio, decorador `@idempotent` y comando): es infraestructura de la API, no de las notificaciones.
2. **Concurrencia: `409 IDEMPOTENCY_IN_PROGRESS`, sin esperar.** La primera petición reserva la clave en su propia transacción (`response_status` nulo) antes de correr la vista. Una segunda petición que la encuentra, o que choca con la restricción única al insertarla, responde `409`. No se retiene ninguna transacción mientras corre la vista, porque los servicios abren las suyas.
3. **Se libera la clave** si la vista lanza un error o responde algo distinto de `2xx`: el cliente puede reintentar con la misma clave, aunque cambie el cuerpo. Si el proceso muere a mitad, la clave queda "en curso" hasta que vence (24 h). Lo anoto como límite conocido.
4. **Huella del cuerpo:** SHA-256 del JSON canónico (claves ordenadas, sin espacios). Reordenar el cuerpo no es un conflicto. La ruta (`route_fingerprint`) es `request.path`, con sus ids.
5. **Respuesta repetida:** el mismo código, el mismo JSON y las cabeceras `ETag` y `Location`, si estaban. **Desvío del SQL:** la columna `response_headers` (JSONB) guarda esas cabeceras. `resource_id` es el `id` de la respuesta, si es un UUID.
6. **Enlace mágico:** su respuesta lleva el token en claro, que nunca se guarda (solo su hash). Por eso, con `store_response=False`, la clave guarda el código y el id, pero no el cuerpo. Repetir la clave no crea otro enlace y responde **`409 IDEMPOTENCY_REPLAY_UNAVAILABLE`** (error nuevo). Es la única excepción a "devuelve la respuesta original".
7. **Clave mal formada** (vacía, con espacios, con caracteres no ASCII o de más de 100 caracteres): `400 VALIDATION_ERROR` con `field = "Idempotency-Key"`.
8. **Desvío del SQL (y corrección del SQL):** las restricciones únicas son **parciales** (`WHERE user_id IS NOT NULL` y `WHERE buyer_session_id IS NOT NULL`) en lugar de `UNIQUE NULLS NOT DISTINCT`. Con `NULLS NOT DISTINCT`, dos usuarios internos con la misma clave (ambos con `buyer_session_id` nulo) chocaban en la restricción del comprador. Lo detectó la prueba "clave de otro actor"; en el cierre se corrige el SQL.
9. **Solo con actor:** sin usuario autenticado ni sesión del comprador, la cabecera se ignora. Las cinco vistas exigen usuario, así que en la práctica no pasa.
10. **El límite de consumo** (3 enlaces por hora) se aplica antes que la idempotencia: un reintento también cuenta.
11. **`purge_idempotency_keys`** borra las vencidas (`expires_at <= now`) y no tiene opciones. Hay un índice `ix_idempotency_keys_expires`.
12. **Contrato:** cabecera `Idempotency-Key` opcional en las cinco operaciones. Se agregan `400`, `409 IDEMPOTENCY_IN_PROGRESS` y `422 IDEMPOTENCY_CONFLICT` a sus respuestas (con un solo helper, `idempotency_responses`), y en el enlace mágico, también `IDEMPOTENCY_REPLAY_UNAVAILABLE`. Solo son cambios aditivos.
