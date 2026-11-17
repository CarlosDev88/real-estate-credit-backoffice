# Tarea: auditoría técnica (módulo 14)

## Objetivo
Una bitácora **inmutable** de lo sensible que pasa en el sistema (API §24.1, REQ §9): quién hizo qué, sobre qué recurso, con qué resultado, desde dónde y con qué `request_id`. Sirve para investigar incidentes y para cumplimiento. **Nunca guarda secretos:** ni contraseñas, ni tokens, ni la cabecera `Authorization`, ni URLs firmadas, ni números de documento completos.

**No es la actividad del módulo 12.** La actividad es la línea de tiempo funcional del expediente, que leen el asesor y el comprador. La auditoría es técnica y solo la lee el administrador.

## Cuándo y dónde
- **Agente:** backend A, en la carpeta principal, rama `feat/audit` desde `master`, después del merge del PR #20 (módulo 12).
- **En paralelo:** el backend B cierra el módulo 13 (notificaciones e `Idempotency-Key`, PR #23).
  - Los dos van a tocar algunas vistas (descargas y POST críticos). Haz cambios mínimos en esas vistas y anótalos: el choque se resuelve al fusionar.
- **Tu código vive en `apps/audit`.** Fuera de ella solo tocas los puntos de enganche de esta spec.

## Reglas de trabajo
- Git solo en lectura. Carlos hace todos los commits y push, sin `Co-Authored-By` ni firmas.
- **Comunicación por buzón:** reporte completo, `ESTADO.md` al día y en la consola una línea.
- **No se presentan dudas.** Lo que no esté cubierto lo decides tú con la opción más simple, lo anotas en "Precisiones acordadas" y sigues.
- **Pruebas con `DATABASE_NAME=mvp_credit_a`.**
  - **Memoria:** el equipo se queda sin memoria con cuatro agentes a la vez. En local corre **solo las pruebas de lo que tocas** (y las de las apps donde enganchas). La suite completa la corre el CI del PR.
  - Si necesitas la suite completa en local, avisa en `ESTADO.md` y espera a que Carlos te dé el visto bueno.
- Contrato (`--validate --fail-on-warn`) y `schema.d.ts` regenerados al cerrar cada parte. Cobertura ≥ 95 % en lo nuevo.

## Parte 1. Modelo, servicio y saneamiento
- **`AuditEvent`**, según el SQL:
  - `actor_user` o `actor_buyer_session` (como mucho uno);
  - `action` (100), `resource_type` (80) y `resource_id` (nulo);
  - `result` (`SUCCESS`, `DENIED` o `FAILED`);
  - `request_id`, `ip_address` y `metadata` (JSON).
- **Inmutable:**
  - el modelo rechaza `save()` sobre una fila que ya existe, y `delete()`;
  - una migración agrega un **trigger de PostgreSQL** que bloquea `UPDATE` sobre `audit_events` (prueba incluida).
- **Servicio único `record_audit(action, resource, result, *, actor=None, metadata=None, request=None)`:**
  - **`request_id`:** sale del contexto que ya pone `RequestIDMiddleware` (`set_request_id`).
  - **IP:** sale de `REMOTE_ADDR`. En local la petición llega por el rewrite de Next, así que se guarda la del proxy. Se anota, y **no** se confía en `X-Forwarded-For` mientras no haya proxy de confianza configurado (constante `AUDIT_TRUST_FORWARDED_FOR = False`).
  - **Si la operación tuvo éxito y se está dentro de una transacción:** se registra con `on_commit`, para no auditar algo que se deshizo.
  - **Si es `DENIED` o `FAILED`:** se registra de inmediato, fuera de la transacción que falla, para que no se pierda con el rollback.
  - **Un error al auditar nunca rompe la operación:** se registra en el log.
- **Saneamiento de `metadata`** (una función única y probada):
  - lista de claves prohibidas (`password`, `token`, `authorization`, `cookie`, `secret`, `signature`, `url` firmada, etc.), que se descartan;
  - números de documento enmascarados (solo los últimos 4);
  - textos largos recortados a 500 caracteres.
  - Una prueba recorre todos los eventos que se generan en la suite de auditoría y falla si aparece algo prohibido.
- **Catálogo de acciones:** `TextChoices` con su etiqueta (por ejemplo, `AUTH_LOGIN`, `AUTH_LOGIN_FAILED`, `DOCUMENT_DOWNLOADED`…), en una constante única.

**Commit:** `feat(audit): add the immutable audit log with request context and sanitized metadata`

## Parte 2. Qué se audita
Por **señales** (las que ya existen y avisan en su docstring que la auditoría se suscribiría) y, donde no hay señal, con **llamadas directas mínimas** en el servicio o la vista.

| Grupo | Acciones |
| --- | --- |
| Autenticación | login correcto y fallido (con el correo enmascarado, sin la contraseña), logout, refresh rechazado, solicitud y uso de restablecimiento de contraseña, bloqueo por límite de consumo |
| Comprador | enlace mágico creado, consumido y fallido (con el código del error), sesión cerrada, consentimiento aceptado o retirado |
| Archivos | descarga de documento, de paquete y de evidencia (quién, qué recurso, **sin** la URL firmada), carga de documento |
| Expediente | transición de estado, reasignación, revisión, exoneración y reapertura de documentos, desistimiento |
| Radicación | radicación creada o corregida, respuesta del banco registrada |
| Configuración | cambios de catálogos, bancos, productos, reglas, requisitos documentales, transiciones, usuarios, roles y estado de usuarios (las señales `*_status_changed` que ya existen) |
| Acceso denegado | todo `403` de la API, por el manejador de excepciones de DRF: `DENIED` con la ruta, el método y el código del error, sin el cuerpo |

- Cada evento lleva en `metadata` solo lo necesario para entenderlo: códigos, ids, de y a qué estado, campos cambiados (**los nombres, no los valores**, cuando son datos personales).
- Las tareas, notas, notificaciones y actividad **no** se auditan aquí (ya tienen su propio registro), salvo que toquen permisos o configuración.

**Pruebas:**
- cada grupo genera su evento con el actor, el resultado y la metadata correctos;
- los fallidos y denegados quedan aunque la operación se deshaga;
- ningún evento tiene datos prohibidos (la prueba de la Parte 1).

**Commit:** `feat(audit): record authentication, access, file, dossier, filing and configuration events`

## Parte 3. Consulta y retención
- **`GET /audit-events`** (permiso nuevo `audit.read`, solo `ADMIN`; migración):
  - paginado, del más nuevo al más viejo;
  - **filtros:** `actor_user_id`, `actor_buyer_session_id`, `action` (lista), `resource_type`, `resource_id`, `result`, `request_id`, `created_from` y `created_to`;
  - códigos desconocidos responden `400`;
  - consultas constantes;
  - índices para los filtros principales (`created_at`, `actor_user`, `resource_type` + `resource_id` y `request_id`).
- **`GET /audit-events/{id}`:** el detalle, con `action_label` y `result_label`. El actor va como `{id, name}` o "Comprador (sesión …)".
- **Retención:** constante `AUDIT_RETENTION_DAYS = 365` y comando `purge_audit_events`, que borra lo más viejo. Es la única forma de borrar: el comando desactiva la protección del modelo de forma explícita; el trigger solo bloquea `UPDATE`. El README lo documenta.
- **Broker, asesor, constructora y comprador:** `403` (y ese `403` también queda auditado).

**Commit:** `feat(audit): add the audit event search API and retention command`

## Cierre
- **Docs:** API §24.1 (endpoints, acciones y qué nunca se guarda), REQ §9 si hace falta alinear, DER, SQL (trigger e índices) y modelo de datos; README del backend.
- **`specs/TAREA-frontend-base.md`, "Brechas":** pantalla de auditoría para el administrador (va con las vistas de administración).
- **Trae `master` antes de entregar.** Si el PR #23 ya se fusionó, revisa los choques en las vistas de descarga y en los POST con idempotencia.
- Entregas el **título y la descripción del PR**, en español, sin firmas.

## Precisiones acordadas
_(las agrega el agente)_

### Parte 1
- **P1.1 `request_id` como texto.** El SQL lo define como `UUID NOT NULL`, pero `RequestIDMiddleware` acepta el identificador que manda el cliente (8 a 64 caracteres, no siempre un UUID). Se guarda como `VARCHAR(64)`. Fuera de una petición (un comando), se genera un UUID nuevo.
- **P1.2 Conexión `audit` para lo fallido dentro de una transacción.** `DATABASES["audit"]` es una copia de `default` (misma base, sin tocar `.env`) con `lock_timeout=2000`. `DENIED` y `FAILED` se escriben por ella si hay una transacción abierta por el código, así que el rollback no los borra. Fuera de una transacción usan la conexión normal. Límite conocido: si el actor se creó dentro de la misma transacción que falla, la llave foránea no lo encuentra y el evento se pierde (queda en el log). Con `lock_timeout`, una espera de bloqueos nunca cuelga la petición.
- **P1.3 Las transacciones de las pruebas no cuentan.** `in_code_transaction` ignora los bloques que abre `TestCase` (`_from_testcase`, que es interno de Django), así que en las pruebas un evento se comporta como en producción: se escribe en el acto si el código no abrió una transacción.
- **P1.4 Éxito.** Fuera de una transacción del código se escribe en el acto; dentro, con `on_commit`.
- **P1.5 IP.** `AuditContextMiddleware` (justo después de `RequestIDMiddleware`) guarda la IP de `REMOTE_ADDR` en un `ContextVar`, para los eventos que llegan por señales sin la petición a mano. Una IP que no es válida queda nula. `AUDIT_TRUST_FORWARDED_FOR = False`: en local se guarda la IP del rewrite de Next.
- **P1.6 Inmutable en tres capas.** `save()` sobre una fila existente y `delete()` lanzan `AuditImmutable`. `QuerySet.update()` siempre la lanza y `QuerySet.delete()` también, salvo dentro de `allow_purge()`, que solo usará la retención. El trigger `trg_audit_events_block_update` bloquea `UPDATE` en la base (no `DELETE`, por la retención).
- **P1.7 Recurso.** `record_audit` recibe un modelo (el tipo es su tabla, por ejemplo `credit_applications`), una tupla `(tipo, id)` o solo el tipo (por ejemplo `auth`). Un id que no es UUID va en `metadata.resource_pk`.
- **P1.8 Actor.** El explícito o, si no lo hay, el de la petición: `request.auth` si es una sesión del comprador, o `request.user` si es un usuario interno.
- **P1.9 Saneamiento.** Se descarta toda clave cuyo nombre contenga `password`, `passwd`, `token`, `authorization`, `cookie`, `secret`, `signature`, `url`, `otp` o `api_key`, a cualquier profundidad. `document_number`, `document` y `tax_id` se enmascaran (`••••5908`). Un texto con una URL con consulta se reemplaza por `[URL omitida]`. Los textos de más de 500 caracteres se recortan, y los valores que no son JSON pasan a texto. `mask_email` (`l•••@example.com`) es para quien llama.
- **P1.10 Escáner.** Un fixture automático de `tests/applications/audit` revisa todos los eventos al terminar cada prueba: claves prohibidas, URL con consulta, textos largos y números de 6 o más dígitos que no son UUID. Si encuentra algo, la prueba falla.
- **P1.11 Índices.** Los tres del SQL (`resource_type` + `resource_id` + `created_at`, `actor_user` + `created_at` y `request_id`), más `created_at` solo, para la lista de la Parte 3.

### Parte 2
- **P2.1 Dos mecanismos.**
  - Las señales que ya existen van a suscriptores en `apps/audit/receivers.py`: `user_logged_in` y `user_logged_out` de Django, el enlace emitido y consumido, el consentimiento, la carga y la revisión de documentos, el cambio de estado y la reasignación, la radicación y la respuesta del banco, y todas las `*_status_changed` de configuración.
  - Lo que no tiene señal se marca en la vista con un atributo de clase: `audit_actions = {método: acción}` para el éxito y `audit_failure_action` para los 4xx. `AuditContextMiddleware` lo registra desde la respuesta de DRF (`apps/audit/hooks.py`).
  - En las vistas solo se agregan 2 o 3 líneas por clase, comentadas "Auditoría (módulo 14)". Así el choque con el PR #23 se resuelve conservando las dos cosas.
- **P2.2 Los `403` y `429` en el middleware, no en el manejador de excepciones.** El middleware ve cada respuesta de DRF con su `code`, así que no hizo falta tocar `config/exceptions.py`. Todo `403` queda como `ACCESS_DENIED` y todo `429` como `AUTH_RATE_LIMITED` (aunque no sea de autenticación: casi todos los límites protegen el login y los enlaces).
- **P2.3 Login fallido por la vista.** `LoginView.audit_failure_action` cubre la contraseña incorrecta, el usuario inactivo y la validación, con el correo enmascarado. No se usa `user_login_failed`, para no registrar dos veces. Un login limitado (`429`) queda como `AUTH_RATE_LIMITED`.
- **P2.4 Qué guarda la metadata de una vista.** Método, ruta, nombre de la vista, argumentos de la ruta y los **nombres** de los campos enviados. Nunca los valores ni la respuesta: la de una descarga trae la URL firmada. Un `email` enviado va enmascarado. En los fallos, además, el estado y el `code` del error.
- **P2.5 Recurso de una vista.** `audit_resource_type` (la tabla) con el `id` de la respuesta o, si no lo trae, el primer argumento de la ruta.
- **P2.6 Cierre de sesión del comprador.** La vista es pública (sin autenticación), así que la llamada directa va en `buyer_sessions.logout_buyer_session`, con la sesión como actor.
- **P2.7 Configuración.** Las altas y ediciones (`POST` y `PATCH`) de catálogos, ítems, transiciones, bancos, productos (y sus finalidades), reglas, tipos documentales, requisitos y usuarios (y sus roles) van por la vista. Las activaciones y desactivaciones con señal van por la señal, y las de ítems y transiciones (que no tienen señal), por la vista. Los cambios de estado de constructoras y proyectos no entran: son de negocio, no de configuración.
- **P2.8 No se auditan** las lecturas sin `audit_actions`, las tareas, las notas, las notificaciones ni la actividad.
- **P2.9 Conexión `audit` en las pruebas.** Un fixture automático del `conftest` raíz cierra la conexión `audit` antes y después de cada prueba. Si queda abierta, una prueba sin base de datos falla al cerrar una respuesta (`close_old_connections`).
- **P2.10 Problema previo, ajeno a la auditoría.** `tests/documents/test_filesystem_storage.py` (2 pruebas) falla si se corre justo después de `tests/documents/test_document_types_api.py`, por la conexión `default` que queda abierta. También falla con el código de `39b35fd` (antes de la auditoría). No lo toqué.

### Parte 3
- **P3.1 Forma del evento.** `{id, created_at, action, action_label, result, result_label, resource_type, resource_id, actor, request_id, ip_address, metadata}`, la misma en la lista y en el detalle. `actor` es `{id, name}`: el usuario interno, o la sesión del comprador con `name` "Comprador (sesión 1a2b3c4d)". Es nulo sin actor (un intento anónimo, un comando) o si el usuario se borró.
- **P3.2 Filtros de fecha.** `created_from` y `created_to` admiten una fecha (`AAAA-MM-DD`, del inicio al fin del día en Bogotá, incluido) o una fecha y hora ISO. Otro valor responde `400`. `action` y `result` validan contra sus `TextChoices` y `action` se puede repetir. `actor_user_id`, `actor_buyer_session_id` y `resource_id` deben ser UUID.
- **P3.3 IP fuera de una petición.** El middleware limpia la IP al terminar, así que un evento registrado fuera de una petición (un comando o una prueba) queda sin IP, en lugar de heredar la de la petición anterior. El `request_id` sí se conserva (lo usan los logs).
- **P3.4 Retención.** `purge_audit_events [--days N]` (por omisión, `AUDIT_RETENTION_DAYS = 365`; `--days` debe ser al menos 1) borra con `allow_purge()`. Es la única forma de borrar.
- **P3.5 Nombres de enums.** `AuditActionEnum` y `AuditResultEnum` quedan fijos. También quedó fijo el `ActionEnum` ya publicado (de los consentimientos, `ACCEPTED`/`WITHDRAWN`): el campo `action` de la auditoría lo habría renombrado a `Action77eEnum`. Una prueba protege los tres nombres.

### Cierre
- **PC.1 Merge con #22 y #23.** Solo `backend/README.md` tuvo conflicto, y lo resolvió Claude. Revisé las vistas mezcladas: las 6 vistas con `@idempotent` (transición, paquete, radicación, respuesta del banco y enlace del comprador) no tienen `audit_actions`, así que una respuesta repetida por idempotencia no se audita dos veces. Esas operaciones se auditan por sus señales, que una repetición no vuelve a emitir. Los 33 atributos `audit_*` siguen en su lugar. El contrato y `schema.d.ts` regenerados coinciden con la mezcla (0 líneas de diferencia).
- **PC.2 Lo nuevo del #23.** No trae una vista de reenvío ni de reintento de correos: los reintentos son el comando `retry_notification_deliveries`. Las lecturas de avisos del comprador no se auditan. No hubo nada que enganchar. Si más adelante hay una vista de reenvío, basta con `audit_actions`.
- **PC.3 REQ §9.5 alineado.** "Acceso a expedientes" quedó como: los accesos denegados (todo `403`) y las acciones sensibles. Las lecturas permitidas no se auditan en el MVP: su trazabilidad funcional es la actividad. En la matriz de REQ, "Notas internas / auditoría" se separó en dos filas; la auditoría técnica es solo del administrador.
- **PC.4 `report_exported` (módulo 15).** No la conecto: la conecta B cuando el #24 esté en `master`. Basta con un suscriptor más en `apps/audit/receivers.py` y la acción en `AuditAction` (por ejemplo, `REPORT_EXPORTED`), con su prueba en `tests/test_contract_names.py`, porque cambia `AuditActionEnum`.
