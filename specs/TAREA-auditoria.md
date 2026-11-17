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
