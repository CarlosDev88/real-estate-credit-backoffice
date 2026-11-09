# Tarea: acceso del comprador (`identity`, paso 9)

## Objetivo
Dar al comprador un acceso sin cuenta ni contraseña: un enlace mágico de un solo uso, ligado a una persona y a una solicitud, que al consumirse abre una sesión temporal y revocable. Durante esa sesión, el comprador consulta su proceso, completa sus datos, los perfiles financieros, el inmueble y la financiación, desiste y acepta los consentimientos. Las referencias son DER §4.9 a §4.12, §7 y §15.6; API §8, §21.1, §26, §27.1 y §28.1; y REQUERIMIENTOS §3, §5.5, §8.6 y §9.

Tablas propias (DER_COMPLETO §15, orden 9): `consent_definitions`, `buyer_access_links`, `buyer_sessions` y `consent_records`.

Incluye los pendientes de pasos anteriores (`TAREA-applications.md`, "Pendientes", punto 1):

- `application_status_history.actor_buyer_session_id`, con FK a `buyer_sessions` (`SET NULL`) y `CHECK (num_nonnulls(actor_user_id, actor_buyer_session_id) <= 1)`.
- El comprador puede desistir, editar el expediente antes de `FILED`, confirmar su perfil (`data_confirmed_at`) y consultar `eligible-bank-products`.
- Decidir si un `PUT` del perfil financiero con cambios reales limpia `data_confirmed_at` (decisión 14).
- Definir quién genera el enlace de invitación (decisión 1).

## Cuándo se construye
Es el paso 9 del orden de construcción (DER_COMPLETO §15) y va después de `applications` (8). Se trabaja en la rama `feat/buyer-access`, creada desde `master` y rebasada sobre el commit de documentación `d19843d`.

**Fuera de alcance:**
- Slots, carga y descarga de documentos (paso 10). La sesión del comprador queda lista para que ese paso la use (`uploaded_by_buyer_session_id`).
- Actividad visible para el comprador (paso 12).
- Notificaciones del comprador (`/buyer/notifications`), `Idempotency-Key` y outbox (paso 13).
- Auditoría (paso 14).
- `/metadata/form-schemas` para el comprador.
- Alta y retiro de participantes por el comprador: siguen siendo solo internos.

---

## Avance

| Parte | Contenido | Estado | Commit |
| ---: | --- | --- | --- |
| 1 | Modelos, migraciones, semillas y configuración | Hecha | `58ea555` |
| 2 | Emisión, listado y revocación de enlaces (interno) | Hecha | `d3e7da7` |
| 3 | Consumo del enlace, sesión del comprador y lectura de su proceso | Hecha | `c7b5e11` |
| 4 | Consentimientos y bloqueo de escrituras por consentimiento pendiente | Hecha | (pendiente de commit) |
| 5 | Actor comprador en `applications`: datos personales, perfiles financieros, ingresos y confirmación | Pendiente | |
| 6 | Inmueble, financiación, `eligible-bank-products`, desistimiento, README y documentación | Pendiente | |

Al cerrar la Parte 1: 1013 tests en verde (25 nuevos), 98 % de cobertura total y el esquema OpenAPI sin avisos. Sin cubrir en código nuevo:
- los `__str__` de los modelos;
- `has_delete_permission` del admin;
- el `unseed` de `identity 0010`.

Al cerrar la Parte 2: 1041 tests en verde (28 nuevos), 98 % de cobertura total (`buyer_access.py`, `buyer_access_serializers.py`, `buyer_access_views.py` y `emails.py` al 100 %) y el esquema OpenAPI sin avisos.

Al cerrar la Parte 3: 1085 tests en verde (44 nuevos), 98 % de cobertura total (los módulos nuevos `buyer_sessions.py`, `buyer_authentication.py`, `buyer_portal*.py` al 100 %) y el esquema OpenAPI sin avisos.

Al cerrar la Parte 4: 1113 tests en verde (28 nuevos), 98 % de cobertura total (`consents.py`, `consent_views.py` y lo modificado del portal al 100 %) y el esquema OpenAPI sin avisos.

---

## Cómo retomar en una sesión nueva

### Reglas de trabajo (las fija el usuario)
- Antes de programar una parte, confirmar el alcance si surge una ambigüedad nueva. Cada parte es un commit con sus tests.
- **Correr los 5 checks en verde antes de proponer un commit**: `ruff check .`, `ruff format --check .`, `mypy .`, `python manage.py makemigrations --check --dry-run` y `pytest --cov=apps --cov-report=term-missing`.
- Validar también el esquema: `python manage.py spectacular --validate --fail-on-warn --file /tmp/s.yml`, que debe seguir **sin avisos**.
- Todo con anotaciones de tipos. Nada de `type: ignore` ni `noqa` sin justificar.
- **Git solo en modo lectura.** El usuario hace los commits y los pushes.
- Las propuestas de commit van **sin `Co-Authored-By` ni firma**. Mensajes cortos, en inglés, con el estilo `feat(buyer-access): ...`.

### Entorno local
Es el mismo de `TAREA-applications.md`: los checks se corren en un contenedor efímero con una clave ficticia, sin leer ni editar `.env`. `config/settings/base.py` usa CRLF, así que se edita con la herramienta de edición, nunca con `sed -i`.

### Lo que ya existe y se reutiliza
- `apps/identity/tokens.py`: `generate_opaque_token()` (256 bits, `token_urlsafe(32)`) y `hash_token()` (SHA-256 en hexadecimal).
- `apps/identity/cookies.py`: el prefijo `__Host-` según `AUTH_COOKIE_SECURE`, `_set_cookie` y `SameSite`.
- `apps/identity/authentication.py`: `enforce_csrf` y el patrón de `CookieJWTAuthentication`, que revalida la sesión en cada petición.
- `apps/identity/throttling.py`: `AuthRateThrottle`, con tasas `"5/15m"` en `AUTH_RATE_LIMITS`, sobre Redis.
- `apps/identity/services.py`: `client_ip(request)` (respeta `NUM_PROXIES`) y `_user_agent_summary(request)`.
- `apps/identity/invitations.py`: el patrón de token de un solo uso (`select_for_update`, estado derivado de las fechas y correo en `on_commit`).
- `apps/applications/services.py`: `applications_visible_to`, `lock_for_edit`, `bump_version`, `put_financial_profile`, los servicios de ingresos, `put_property`, `put_financing`, `eligible_products_queryset`, `preview_products`, `withdraw_application`, `_apply_status_change` y `completeness`.
- `apps/applications/concurrency.py`: `expected_version`, `ensure_version` y `with_etag`.

---

## Decisiones (acordadas con el usuario)

1. **Quién emite el enlace.**
   - `ADMIN` emite en cualquier solicitud;
   - `ADVISOR`, en las que tiene asignadas;
   - `INDEPENDENT_BROKER`, en las de oportunidades que originó; la respuesta no le revela datos del expediente;
   - `CONSTRUCTION_PARTNER` nunca;
   - listar: los mismos tres. Revocar: `ADMIN` y `ADVISOR` dentro de su alcance, y el broker solo los enlaces que él emitió;
   - permisos nuevos: `buyer_access.create`, `buyer_access.read` y `buyer_access.revoke` (`ADMIN`, `ADVISOR` y `INDEPENDENT_BROKER`).
2. **A quién se invita.** Solo al participante `PRIMARY` activo. El sistema toma el `PRIMARY`; ningún `client_id` de la entrada se acepta. Los enlaces por participante son una mejora futura.
3. **Cuándo se puede emitir.** En cualquier estado no terminal, también después de `FILED` (API §27.3 paso 6). En una solicitud terminada, `409 APPLICATION_CLOSED`. Con el canal `EMAIL` y un `PRIMARY` sin correo, `400`.
4. **Rate limits.**
   - Consumo: `5/1h` por IP (manda API §8 y REQUERIMIENTOS §9.3 sobre API §26).
   - Emisión: `3/1h` por emisor + solicitud (manda REQUERIMIENTOS §9.3).
   - Al superarlos: `429 RATE_LIMITED` con `Retry-After`.
5. **Rotación y revocación.**
   - Crear un enlace revoca los `PENDING` anteriores de la misma solicitud, en la misma transacción, y no cierra las sesiones vivas.
   - Consumir un enlace revoca las otras sesiones activas del mismo cliente y solicitud: queda una sola sesión viva.
   - `DELETE /buyer-access-links/{id}`:
     - un enlace `PENDING` se revoca;
     - uno `REVOKED` o `EXPIRED` responde `204`, porque la operación es idempotente;
     - uno `CONSUMED` no puede llevar `revoked_at` (`CHECK` del esquema), así que se revoca la sesión que nació de él (`204`).
   - Cuando la solicitud termina, la sesión sigue viva solo para lectura y toda escritura responde `409 APPLICATION_CLOSED`.
6. **Vencimientos.**
   - `expires_in_hours` es opcional, un entero de 1 a 168, y vale 72 por omisión.
   - La sesión dura 24 h absolutas, sin renovación ni refresh token.
   - Que el comprador pueda pedir un enlace nuevo a su correo registrado es una mejora futura.
7. **Canal de entrega.** Catálogo nuevo `buyer_access_channel` con `COPY_LINK` y `EMAIL`. No es público y no es administrable (`is_manageable = false`), porque el backend decide según el código.
   - `delivery_channel` vale `COPY_LINK` por omisión.
   - Con `EMAIL`, el correo se envía en `on_commit` con `send_mail` hasta que exista la outbox (paso 13).
   - `url` se devuelve en la respuesta `201` en los dos canales y nunca en listados ni logs.
8. **`Idempotency-Key` en la emisión se aplaza al paso 13.** Un reintento crea otro enlace y revoca el anterior, y el rate limit acota el abuso.
9. **Errores del consumo** (todos `401`):
   - `MAGIC_LINK_EXPIRED`, `MAGIC_LINK_CONSUMED` y `MAGIC_LINK_REVOKED`;
   - `MAGIC_LINK_INVALID` (código nuevo) para un token desconocido o mal formado, y para un enlace válido cuya solicitud terminó o cuyo cliente dejó de ser `PRIMARY` activo; en ese caso el enlace no se consume;
   - el consumo bloquea la fila: de dos consumos simultáneos, solo uno gana;
   - el consumo rota el token CSRF y fija la cookie de la sesión.
10. **Rutas del comprador**: todas bajo `/buyer/...`, con DTO exclusivos (manda API §8 sobre §17 y §18). Las rutas internas siguen siendo solo internas.

    | Método | Ruta | Parte |
    | --- | --- | --- |
    | `POST` | `/buyer-access/consume` | 3 |
    | `GET` | `/buyer/session` | 3 |
    | `POST` | `/buyer/session/logout` | 3 |
    | `GET` | `/buyer/processes` | 3 |
    | `GET` | `/buyer/applications/{id}` | 3 |
    | `GET`/`POST` | `/buyer/applications/{id}/consents` | 4 |
    | `GET`/`PATCH` | `/buyer/applications/{id}/profile` | 5 |
    | `GET` | `/buyer/applications/{id}/participants` | 5 |
    | `GET`/`PUT` | `/buyer/participants/{participant_id}/financial-profile` | 5 |
    | `POST` | `/buyer/participants/{participant_id}/financial-profile/confirmation` | 5 |
    | `GET`/`POST` | `/buyer/financial-profiles/{id}/income-sources` | 5 |
    | `PATCH`/`DELETE` | `/buyer/income-sources/{id}` | 5 |
    | `GET`/`PUT` | `/buyer/applications/{id}/property` | 6 |
    | `GET`/`PUT` | `/buyer/applications/{id}/financing` | 6 |
    | `GET` | `/buyer/applications/{id}/eligible-bank-products` | 6 |
    | `POST` | `/buyer/applications/{id}/withdrawals` | 6 |

    Las rutas por participante, perfil o fuente de ingreso solo admiten recursos de la solicitud de la sesión; un id de otra solicitud responde `404`. La forma exacta de estas rutas se fija en la Parte 5.
11. **Alcance de edición del comprador**, antes de `FILED`:
    - datos personales del `PRIMARY` (`PATCH /profile`): `email`, `phone`, `birth_date` y direcciones. Nombres y documento de identidad los corrige el asesor;
    - el perfil financiero y los ingresos del `PRIMARY` y de los co-solicitantes activos;
    - el inmueble;
    - la financiación y el producto;
    - agregar o retirar participantes sigue siendo solo interno.
12. **Error después de `FILED`**: `409 APPLICATION_NOT_EDITABLE`. `DOCUMENT_LOCKED` queda para documentos (paso 10). Se corrige API §8.
13. **Concurrencia del comprador**: las mismas reglas que el backoffice. `ETag` en las respuestas del expediente, `If-Match` obligatorio en `PUT`/`PATCH` (`428` y `409 STALE_VERSION`) y `expected_version` en `withdrawals`.
14. **`data_confirmed_at`.**
    - La confirmación del comprador fija `data_confirmed_at = now`, exige un perfil existente y aumenta la versión.
    - Todo cambio real del perfil o de sus ingresos, sea del asesor o del comprador, la limpia.
    - El `PUT` interno sigue rechazando `data_confirmed_at` en la entrada.
    - No es un ítem de `/completeness` por ahora.
15. **Desistimiento del comprador.**
    - Usa la transición activa `<estado> → WITHDRAWN` sin comprobar rol ni permiso: la autorización es la sesión.
    - El motivo es obligatorio (catálogo `application_withdrawal_reason`), igual que `expected_version`.
    - La respuesta tiene la forma de API §16.3, y el historial lleva `actor_buyer_session`.
    - Se admite también después de `FILED`, y la sesión sigue viva para lectura.
16. **Consentimientos.**
    - **Semilla.** Dos definiciones v1 con texto **provisional** (REQUERIMIENTOS §12 deja el texto legal pendiente):
      - `DATA_PROCESSING`: tratamiento de los datos personales del titular;
      - `CO_APPLICANT_AUTHORIZATION`: el titular declara que tiene la autorización de los co-solicitantes para compartir sus datos.
    - **Sin CRUD REST de definiciones.** Las versiones nuevas se publican por migración. El admin de Django solo las muestra.
    - **Obligatoriedad.** `DATA_PROCESSING` siempre. `CO_APPLICANT_AUTHORIZATION` solo si la solicitud tiene co-solicitantes activos.
    - **Bloqueo.** Mientras falte aceptar la versión vigente de un consentimiento obligatorio, las escrituras del portal responden `403 CONSENT_REQUIRED`. Las lecturas, la aceptación de consentimientos y el logout siguen permitidos.
    - **Comprador.**
      - `GET /buyer/applications/{id}/consents`: definiciones vigentes (`effective_from <= now`, sin `retired_at`, la versión mayor por código), con `required` y el estado para ese cliente y esa solicitud;
      - `POST` con `{consent_definition_id, action}`: guarda IP, agente y sesión;
      - una versión no vigente responde `422 CONSENT_NOT_EFFECTIVE`;
      - aceptar dos veces la misma versión devuelve el registro existente;
      - `WITHDRAWN` se guarda como fila nueva y vuelve a dejar pendiente el consentimiento.
    - **Interno.** `GET /applications/{id}/consents`, con el permiso `consents.read` (`ADMIN` y `ADVISOR`, este último dentro de su alcance). El broker no lo ve.
17. **Estado público.** Por ahora es igual a `status`, con la etiqueta del catálogo `application_status`, y `next_action` es un texto fijo por estado.

18. **Co-solicitantes.** Son todos los participantes activos que no son el titular, incluidos los deudores solidarios (`CO_APPLICANT` y `SOLIDARY_DEBTOR`). Esto define qué perfiles e ingresos edita el comprador (decisión 11) y cuándo se exige `CO_APPLICANT_AUTHORIZATION` (decisión 16).

---

## Diseño

### Modelos (`apps/identity/models/`)
Son fieles al esquema SQL. Los nombres de restricciones e índices son los del esquema.

- **`ConsentDefinition`** (`consent_definitions`, `models/consent.py`):
  - `code`, `version > 0`, `title`, `body`, `content_hash`, `effective_from` y `retired_at`;
  - `UQ (code, version)` y `CHECK retired_at >= effective_from`;
  - `content_hash` es el SHA-256 del `body` y lo calcula `save()`, nunca la entrada.
- **`BuyerAccessLink`** (`buyer_access_links`, `models/buyer_access.py`):
  - `client`, `application`, `token_hash` (UQ), `created_by`, `delivery_channel_item`, `expires_at`, `consumed_at` y `revoked_at`;
  - `CHECK expires_at > created_at` y `CHECK consumed_at IS NULL OR revoked_at IS NULL`;
  - índice parcial `ix_buyer_access_links_pending`;
  - estado derivado (`PENDING`, `CONSUMED`, `REVOKED` o `EXPIRED`), con `buyer_access_link_status_filter`.
- **`BuyerSession`** (`buyer_sessions`):
  - `access_link` (`OneToOne`, `RESTRICT`), `client`, `application`, `session_token_hash` (UQ), `expires_at`, `revoked_at`, `last_seen_at`, `ip_address` y `user_agent_summary`;
  - `CHECK expires_at > created_at`;
  - `is_active_at()`.
- **`ConsentRecord`** (`consent_records`):
  - `consent_definition`, `client`, `user`, `application`, `action`, `ip_address`, `user_agent_summary` y `buyer_session` (`SET NULL`);
  - los tres `CHECK` del esquema;
  - es inmutable: no tiene `updated_at`.
- **`ApplicationStatusHistory.actor_buyer_session`**, con `CHECK ck_application_status_actor`.

### Migraciones
- `identity 0009`: las cuatro tablas. Depende de `applications 0003`, `crm 0002` y `catalogs 0002`.
- `identity 0010`: semillas (permisos, catálogo y consentimientos).
- `applications 0004`: `actor_buyer_session`. Depende de `identity 0009`.

No hay ciclo: `applications 0001` a `0003` dependen de `identity` hasta la `0008`.

### Sesión del comprador (Parte 3)
- **`BuyerSessionAuthentication`**:
  - lee la cookie `__Host-buyer_session` (`buyer_session` en HTTP local) y busca la sesión por hash;
  - vencida o revocada: `401 SESSION_EXPIRED`;
  - valida CSRF en las escrituras;
  - actualiza `last_seen_at` como máximo una vez por minuto.
  - `request.user` sigue siendo `AnonymousUser`, y la sesión queda en `request.auth`.
  - Solo la usan las vistas `/buyer/*`, que no aceptan el JWT interno. La cookie del comprador nunca autentica un endpoint interno.
- **Alcance.** Cada ruta compara la solicitud con `session.application_id`. Si no coincide, `404`.

### Actor de las mutaciones (Parte 5)
`Actor = User | BuyerSession` en los servicios de `applications` que usa el comprador:
- historial: con un comprador, `actor_user` queda `None` y `actor_buyer_session` queda con la sesión;
- evaluación bancaria: `evaluated_by` queda `None`, porque el esquema solo tiene FK a `users`;
- señales: envían `actor` tal cual.

### Configuración (`config/settings/base.py`)
- `BUYER_ACCESS_LINK_DEFAULT_HOURS` (72), `BUYER_ACCESS_LINK_MAX_HOURS` (168) y `BUYER_SESSION_LIFETIME` (24 h).
- `BUYER_ACCESS_URL`: la página del portal que recibe `?token=`.
- `AUTH_RATE_LIMITS["buyer_access_consume"] = "5/1h"` y `["buyer_access_issue"] = "3/1h"`.

---

## Plan de las partes

### Parte 1. Modelos, migraciones, semillas y configuración
- Los cuatro modelos, sus `CHECK`, UQ e índice parcial, y su admin de solo lectura sin hashes.
- `ApplicationStatusHistory.actor_buyer_session` y su `CHECK`.
- Semillas: los permisos `buyer_access.*` y `consents.read`, el catálogo `buyer_access_channel` y las dos definiciones de consentimiento.
- La configuración de la sección anterior.
- Tests de restricciones, estado derivado y semillas, en `tests/applications/buyer_access/`. Ahí se reutilizan los fixtures de `tests/applications/conftest.py` (solicitud, `PRIMARY` y usuarios).

### Parte 2. Emisión, listado y revocación de enlaces (interno)
- `POST`/`GET /applications/{id}/buyer-access-links` y `DELETE /buyer-access-links/{id}`, con tag `Buyer access`.
- Servicio `issue_access_link` (decisiones 1 a 8).
- Listado paginado sin token, con filtro `status` y el emisor `{id, name}`.
- Tests: el token nunca aparece en el listado ni en los logs; el broker fuera de su alcance recibe `404`; el partner recibe `403`.

### Parte 3. Consumo, sesión y lectura del proceso
- `POST /buyer-access/consume`, `BuyerSessionAuthentication`, cookie y CSRF.
- `GET /buyer/session`, `POST /buyer/session/logout`, `GET /buyer/processes` y `GET /buyer/applications/{id}`. Este último devuelve un DTO del portal con el estado público, el progreso, los participantes, el inmueble y la financiación, sin notas, asesor interno ni evaluaciones.
- Tests de seguridad:
  - enlace vencido, consumido, revocado o de otra solicitud (E2E 20);
  - doble consumo concurrente;
  - sesión revocada o vencida (RNF-11);
  - otro `application_id` responde `404` (E2E 8);
  - escritura sin CSRF responde `403`;
  - la cookie del comprador no abre endpoints internos y el JWT interno no abre `/buyer/*`;
  - `429` y `Retry-After`.

### Parte 4. Consentimientos
- Servicios y endpoints de la decisión 16, para el comprador y para el interno.
- El permiso del portal que aplica `403 CONSENT_REQUIRED` a las escrituras.

### Parte 5. Actor comprador: datos personales, perfiles financieros, ingresos y confirmación
- `Actor` en los servicios de `applications`, sin cambiar el comportamiento interno: la suite actual sigue verde.
- `PATCH /profile`, el perfil financiero y los ingresos del `PRIMARY` y de los co-solicitantes, y la confirmación (decisiones 11 y 14).
- `If-Match`, `ETag` y `409 APPLICATION_NOT_EDITABLE` después de `FILED` (E2E 7).

### Parte 6. Inmueble, financiación, elegibles, desistimiento y cierre
- `GET`/`PUT /buyer/applications/{id}/property` (reutiliza `put_property`).
- `GET`/`PUT /buyer/applications/{id}/financing`, con evaluación automática si cambia el producto y `evaluated_by = None`.
- `GET .../eligible-bank-products`, con un DTO del portal: producto, banco y `eligible`, sin el detalle de las reglas.
- `POST .../withdrawals` (decisión 15).
- README, con la sección "Buyer access" y "Current Status" en el paso 9.
- Documentación: API §5.5 (errores nuevos `MAGIC_LINK_INVALID`, `CONSENT_REQUIRED` y `CONSENT_NOT_EFFECTIVE`), §6, §8, §17, §18, §21.1, §25, §26 y §27.1.

---

## Decididas en la implementación

### Parte 1
- **Migraciones:**
  - `identity 0009_buyer_access_and_consents`: las cuatro tablas;
  - `identity 0010_seed_buyer_access`: permisos, canal y consentimientos;
  - `applications 0004_status_history_buyer_actor`: la columna y el `CHECK ck_application_status_actor`.
- **Huella del consentimiento.** `content_hash` es el SHA-256 de `body`. Lo calcula `ConsentDefinition.save()` (también con `update_fields=["body"]`) e ignora cualquier valor recibido. La migración lo calcula con `hashlib`, porque el modelo histórico no tiene ese `save()`. `consent_content_hash(body)` es la función pública.
- **Vigencia de la semilla.** Las dos definiciones v1 rigen desde el 2026-01-01 00:00, hora de Bogotá. El texto empieza con "TEXTO PROVISIONAL, PENDIENTE DE VALIDACIÓN LEGAL." para que nadie lo tome por definitivo.
- **Índices que el esquema no trae:**
  - `ix_buyer_sessions_open (application, client) WHERE revoked_at IS NULL`, para revocar las otras sesiones vivas al consumir un enlace (decisión 5);
  - `ix_consent_records_subject (application, client, consent_definition, created_at DESC)`, para la última acción de cada consentimiento (decisión 16).
- **`user_agent_summary`** es `VARCHAR(255)` con cadena vacía por omisión, igual que en `auth_sessions`. El esquema lo deja nulo.
- **Admin.** Los cuatro modelos son de solo consulta: no se crean, editan ni borran (`ImmutableAdmin`). Los hashes del enlace y de la sesión no se muestran.
- **Relaciones inversas:**
  - `client.buyer_access_links`, `client.buyer_sessions` y `client.consent_records`;
  - `application.buyer_access_links`, `application.buyer_sessions` y `application.consent_records`;
  - `link.session`;
  - `user.buyer_access_links_created`.
- **Variables de entorno nuevas** (todas con valor por omisión): `BUYER_ACCESS_LINK_DEFAULT_HOURS`, `BUYER_ACCESS_LINK_MAX_HOURS`, `BUYER_SESSION_HOURS` y `BUYER_ACCESS_URL` (por omisión, `http://localhost:3000/acceso`).
- **Tests.** Están en `tests/applications/buyer_access/` (`test_models.py` y `test_seed.py`). Su `conftest.py` agrega `make_link` y `make_session`, que crean filas directamente en la base.

### Parte 2
- **Archivos:**
  - `apps/identity/buyer_access.py` (servicios), separado de `services.py` porque depende de `applications`;
  - `buyer_access_serializers.py`, `buyer_access_views.py` y `buyer_access_urls.py`, incluidos en `config/urls.py`;
  - tag `Buyer access`.
- **Servicios:**
  - `links_queryset()` y `links_visible_to(user)`, con el mismo alcance que `applications_visible_to`;
  - `default_channel()` (`COPY_LINK`);
  - `issue_access_link(actor, application, channel=, expires_in_hours=)` → `IssuedLink(link, url)`;
  - `ensure_can_revoke` y `revoke_access_link`;
  - constantes `CHANNEL_CATALOG`, `COPY_LINK` y `EMAIL`.
- **Emisión:**
  - bloquea la fila de la solicitud (`select_for_update`), para que dos emisiones simultáneas no dejen dos enlaces pendientes;
  - revoca los `PENDING` en la misma transacción. Los vencidos quedan como `EXPIRED`;
  - el titular se toma del participante `PRIMARY` activo;
  - la entrada es estricta, así que un `client_id` responde `400` (campo no permitido);
  - `expires_in_hours` acepta de 1 a `BUYER_ACCESS_LINK_MAX_HOURS`.
  - Orden de las comprobaciones: alcance (`404`), cuerpo (`400`), solicitud terminada (`409 APPLICATION_CLOSED`) y canal `EMAIL` sin correo (`400` en `delivery_channel`).
- **Respuesta.** Los mismos campos que el listado más `url`, que solo está en el `201`:
  - `id`, `application_id`, `client_id` y `status`;
  - `delivery_channel` `{code, label}` y `created_by` `{id, name}`;
  - las fechas;
  - `session`: `{id, created_at, expires_at, revoked_at, last_seen_at, is_active}` o `null`.
- **Correo** (`emails.send_buyer_access_email`). Saludo con el nombre, el enlace, el aviso de uso único y las horas de vigencia. No lleva código de solicitud, documento ni datos financieros (REQUERIMIENTOS §9.2). Sale en `on_commit`.
- **Logs.** Solo el id del enlace, el código de la solicitud, el actor y el canal. Un test verifica que ni el token ni su hash aparecen en los logs.
- **Rate limit.** `BuyerAccessIssueRateThrottle` cuenta solo los `POST`, con clave hash(usuario + `application_id`). Se aplica después de los permisos, así que el partner recibe `403` y no `429`. Cuenta también los intentos fallidos.
- **Revocación.**
  - Un enlace fuera del alcance responde `404`.
  - El broker (`scope.is_restricted`) que revoca un enlace emitido por otro recibe `403`, porque ese enlace sí aparece en su listado.
  - Un enlace consumido conserva el estado `CONSUMED`, y lo que se revoca es su sesión.
- **Listado.** `?status=` acepta `PENDING`, `CONSUMED`, `REVOKED` o `EXPIRED`; otro valor responde `400`. Orden `-created_at`, paginado (`items`).
- **OpenAPI.** `BuyerAccessLinkStatusEnum` se agregó a `ENUM_NAME_OVERRIDES` para evitar la colisión de nombres de los campos `status`.

### Parte 3
- **Archivos:**
  - `buyer_sessions.py` (servicios): `consume_access_link`, `find_active_session`, `touch_session`, `logout_buyer_session` e `is_active_primary`;
  - `buyer_authentication.py`: `BuyerSessionAuthentication` e `IsBuyerSession`. Está separado de `authentication.py` porque depende de `applications`, y DRF importa `authentication.py` al cargar su configuración;
  - `buyer_portal.py` (lecturas), `buyer_portal_serializers.py`, `buyer_portal_views.py` y `buyer_portal_urls.py`, con tag `Buyer portal`;
  - `cookies.py`: `buyer_session_cookie_name()`, `set_buyer_session_cookie` y `clear_buyer_session_cookie`;
  - `services._user_agent_summary` pasó a ser público (`user_agent_summary`).
- **Consumo** (`POST /buyer-access/consume`, público y sin autenticación, así una cookie vencida no lo bloquea):
  - el token debe cumplir `[A-Za-z0-9_-]{16,128}`; si no, `401 MAGIC_LINK_INVALID` sin consultar la base. Sin `token`, vacío o con campos de más: `400`;
  - `select_for_update` sobre el enlace. Orden: inexistente (`INVALID`), `CONSUMED`, `REVOKED`, `EXPIRED`, y después solicitud terminada o cliente que ya no es `PRIMARY` activo (`INVALID`, sin consumir);
  - abre la sesión con `last_seen_at = now`, la IP (`client_ip`) y el agente; revoca las otras sesiones abiertas del cliente en la solicitud;
  - fija `__Host-buyer_session` (`HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, 24 h) y rota el token CSRF;
  - respuesta de API §8 (`buyer.display_name`, `application`, `session_expires_at`); `application` agrega `public_status_label`, `is_editable` e `is_closed`.
  - Rate limit `BuyerAccessConsumeRateThrottle`: 5/h por IP, cuenta todos los intentos.
- **Sesión** (`BuyerSessionAuthentication`):
  - sin cookie: `401 NOT_AUTHENTICATED`;
  - cookie mal formada o desconocida, sesión vencida o revocada, o cliente que dejó de ser `PRIMARY` activo: `401 SESSION_EXPIRED` (`BuyerSessionExpired`, con un mensaje para el comprador), y la respuesta borra la cookie;
  - CSRF en las escrituras; `last_seen_at` se escribe como máximo una vez por minuto;
  - revocar desde el backoffice el enlace consumido corta la sesión en la petición siguiente.
- **Logout** (`POST /buyer/session/logout`): público con CSRF, como el logout interno. Revoca la sesión de la cookie si sigue abierta, borra la cookie y responde siempre `204`. No pasa por el bloqueo de consentimientos (Parte 4).
- **Cabeceras.** Todas las respuestas `/buyer/*` y la del consumo llevan `Cache-Control: no-store`.
- **DTO del portal:**
  - `GET /buyer/session`: `session {id, created_at, expires_at}`, `buyer {display_name}` y `application {id, code, public_status, public_status_label, is_editable, is_closed}`;
  - `GET /buyer/processes`: lista paginada con la única solicitud de la sesión, con `purpose`, `next_action`, `progress_percentage` y las fechas;
  - `GET /buyer/applications/{id}`: lo anterior más `version` (también en `ETag`), `progress {percentage, items}`, `participants` activos (`id`, `role`, `full_name`, `contributes_income`), `property` y `financing`, o `null` si faltan;
  - sin documento de identidad, notas, `ownership_notes`, asesor, origen ni evaluaciones.
- **Progreso del comprador.** Son los ítems de `completeness` sin `bank_evaluation`, que es interno, con su propio porcentaje. Por eso puede diferir del `/completeness` interno.
- **Estado público.** `public_status_label` sale del catálogo `application_status` y, si falta el ítem, de la etiqueta del backend. `NEXT_ACTIONS` cubre todos los estados (hay un test que lo verifica).
- **Concurrencia del consumo.** El test verifica que la consulta del enlace lleva `FOR UPDATE`. Así, el segundo consumo simultáneo espera al primero y recibe `MAGIC_LINK_CONSUMED`.

### Parte 4
- **Archivos:**
  - `consents.py` (servicios): `effective_definitions`, `required_codes`, `has_co_applicants`, `consent_states`, `missing_consents`, `ensure_consents_accepted`, `record_consent` y `application_consent_records`; `ConsentStatus` (`PENDING`, `ACCEPTED`, `WITHDRAWN`);
  - `consent_views.py` y `consent_urls.py`: el endpoint interno, con tag `Consents`;
  - `buyer_authentication.ConsentsAccepted`: el permiso del bloqueo;
  - `BuyerConsentsView` en `buyer_portal_views.py`.
- **Vigencia.** Una definición rige si `effective_from <= now` y `retired_at` es nulo o futuro. De cada código se toma la versión mayor vigente: una versión futura no reemplaza a la actual hasta su fecha.
- **Estado** para el cliente y la solicitud de la sesión: la última acción sobre esa versión exacta. Aceptar la v1 no cuenta para la v2, y el registro de otra solicitud tampoco cuenta.
- **Acciones** (`POST /buyer/applications/{id}/consents`, `{consent_definition_id, action}`):
  - repetir la última acción devuelve el registro existente con `200`; una fila nueva responde `201`;
  - retirar sin ninguna acción previa: `409 CONSENT_NOT_ACCEPTED` (código nuevo);
  - una versión futura, retirada o reemplazada: `422 CONSENT_NOT_EFFECTIVE`;
  - una definición inexistente: `400` en `consent_definition_id`;
  - con la solicitud terminada: `409 APPLICATION_CLOSED`. Después de `FILED` sí se permite;
  - bloquea la fila de la sesión (`select_for_update`), así que dos aceptaciones simultáneas no dejan dos filas;
  - el registro guarda cliente, solicitud, sesión, IP y agente. No toca la versión de la solicitud.
- **Listado del comprador.** `{items, pending_required}`. Cada ítem trae `id`, `code`, `version`, `title`, `body`, `content_hash`, `effective_from`, `required`, `status` y `accepted_at`.
- **Bloqueo.** `ConsentsAccepted` va en los permisos por omisión de `BuyerPortalView`, después de `IsBuyerSession`:
  - solo actúa en métodos no seguros;
  - responde `403 CONSENT_REQUIRED` con un `details` por consentimiento pendiente (`code` = código de la definición, `resource_id` = su id);
  - `BuyerConsentsView` lo omite, y el logout es público;
  - como CSRF se valida en la autenticación, una escritura sin token responde `403 CSRF_FAILED` antes que `CONSENT_REQUIRED`.
- **`GET /buyer/session`** agrega `pending_consents`, la lista de códigos de los consentimientos que faltan.
- **Interno** (`GET /applications/{id}/consents`, `consents.read`): lista paginada, de la más reciente a la más antigua. Cada evidencia trae `consent_definition {id, code, version, title, content_hash}`, `client {id, full_name}`, `user`, `action`, `ip_address`, `user_agent_summary`, `buyer_session_id` y `created_at`. Fuera del alcance responde `404`; el broker y el partner reciben `403`.
- **Tests.** Los helpers `consume` y `pending_token` y los fixtures `buyer_client` y `buyer_csrf_client` pasaron al `conftest.py` de `buyer_access`.
- **mypy.** El campo `required` del DTO choca con `Field.required`. Lleva un `type: ignore[assignment]` justificado, igual que `label` en `CatalogItemRefSerializer`.

## Pendientes para pasos posteriores

1. **Mejora futura: enlaces por participante.** Cada co-solicitante recibe su propio enlace, limitado a sus datos (decisión 2).
2. **Mejora futura: autoservicio del enlace.** El comprador pide un enlace nuevo a su correo registrado, con respuesta uniforme y rate limit (decisión 6).
3. **Paso 13.** `Idempotency-Key` en `POST /applications/{id}/buyer-access-links`. Envío del correo del enlace por la outbox.
4. **Paso 10.** Usar `buyer_sessions` en `document_files.uploaded_by_buyer_session_id`, y la carga del comprador después de `FILED` solo en los slots observados.
5. **Paso 12.** Mostrar al comprador la actividad con `visibility = BUYER` y registrar `actor_buyer_session_id` en `activity_logs`.
