# TAREA — Auditoría de seguridad, Fase B: corregir los hallazgos

> Spec cerrada. Todas las decisiones están tomadas. **No preguntes:** si algo no cuadra con el código, decide lo más simple, anótalo en "Precisiones acordadas" (al final) y en el reporte, y sigue.

## 0. Contexto
- La Fase A (PR #32, ya en `master`) dejó 20 hallazgos (0 críticos, 0 altos, 5 medios, 10 bajos, 5 informativos), con su ficha en `docs/seguridad/hallazgos.md`, el informe público `docs/SEGURIDAD.md` y pruebas en `backend/tests/security/` (las brechas abiertas son `xfail(strict=True, reason="SEC-NN")` y los CVE de DRF están en `backend/security/pip-audit-ignore.txt`).
- **Esta tarea corrige 19 y deja 1 aceptado (SEC-16).** Cada ficha de `hallazgos.md` ya trae "Dónde", "Cómo reproducirlo" y "Corrección sugerida": úsalas. Aquí solo va lo decidido encima de eso.
- **Regla de cierre de cada hallazgo** (pedido de Carlos, no negociable): la ficha en `docs/seguridad/hallazgos.md` y en `docs/SEGURIDAD.md` gana una sección **"Cómo se solucionó"** con:
  1. **Causa** en una línea.
  2. **Cambio** con la ruta de cada archivo tocado.
  3. **Verificación**: la prueba que lo cubre (ruta y nombre) y, si aplica, el comando contra el servidor 8010 con el resultado antes y después.
  4. **PR**: "Fase B (este PR)". Carlos pone el número al abrirlo.
  5. **Estado**: `corregido` o `aceptado` (con el motivo).

## 1. Dónde y cómo
- **Worktree:** `C:\Users\ASUS\Documents\programacion\mvp-backoffice\wt-security-b`, rama `fix/security-phase-b`, desde `origin/master`. Copia de esta spec en `specs/TAREA-seguridad-fase-b.md`.
- **Agente:** "seguridad-b". **Buzón** `.buzon/` como siempre.
- **En paralelo** trabaja otro agente de backend con `specs/TAREA-brechas-3-demo.md` (rama `feat/backend-gaps-3`). Los dos tocan `contracts/openapi.json`, `frontend/src/lib/api/schema.d.ts` y `backend/tests/security/access_matrix.py`: **no los edites a mano para "arreglar" lo del otro**. El que entre segundo trae `master` (lo hace Carlos) y regenera esos archivos.

### Reglas
1. **Git solo lectura** (nada de commit, add, mv, restore, fetch, push). Carlos hace los commits.
2. **No leas ni edites `.env*`.** Si una corrección necesita un valor nuevo en `.env`, escríbelo en el reporte (nombre y para qué, nunca el valor): lo pone el orquestador.
3. Nada secreto en reportes, docs, logs ni pruebas. La única contraseña que puede aparecer es la de demo (`DemoUmbral2026!`).
4. **Pruebas acotadas** en local (`tests/security/` y lo que toques); la suite completa la corre el CI. Siempre `ruff`, `mypy .`, `makemigrations --check`, `spectacular --validate --fail-on-warn` y, si cambia el contrato, regenera `schema.d.ts` (`npx --yes openapi-typescript@7.13.0 ../contracts/openapi.json -o src/lib/api/schema.d.ts` en `frontend/`).
5. **Al quitar un `xfail`**: la prueba pasa a ser normal y verde. Nunca borres una prueba de seguridad para que el CI pase.
6. **Endpoint nuevo** (no debería haber): su fila en `backend/tests/security/access_matrix.py` y `python security/render_matrix.py`. **Operación idempotente nueva:** a la lista de `tests/applications/idempotency/test_idempotency.py`.
7. Los fronts usan la API todo el tiempo: **ningún cambio rompe la forma de una respuesta 2xx**. Lo que cambia es solo de errores, cabeceras o configuración.

### Preparación
Variables como en la Fase A (`WT` = la carpeta de arriba, `ENV` = `real-estate-credit-backoffice\backend\.env`, `IMG = mvp-credit-backend-backend`, `NET = mvp_credit_network`).
1. **Base propia** `mvp_credit_secb` (no toques `mvp_credit`, `mvp_credit_a`, `mvp_credit_b`, `mvp_credit_sec`); `migrate`, `createcachetable` y `seed_demo_data`.
2. **Servidor propio en el 8010**, contenedor `mvp-secb-api` (si existe `mvp-sec-api` de la Fase A, bórralo con `docker rm -f mvp-sec-api`). Y otro **sin `DEBUG` en el 8011** (`mvp-secb-api-nodebug`) solo cuando una verificación lo pida.
3. Los scripts de la Fase A siguen en `C:\Users\ASUS\Documents\programacion\mvp-backoffice\_security-work\scripts\` (`rate_limits.py`, `errors.py`, `headers.sh`, `admin_login.py`, `timing.py`…). Úsalos para el "antes y después". Los crudos nuevos van ahí mismo, nunca al repo.

## 2. Parte 1 — Autenticación y límites (los 4 medios que faltan)
1. **SEC-04, DRF:** `djangorestframework>=3.18.2,<3.19` y `djangorestframework-stubs` compatible en `requirements*.txt`. Borra las dos líneas `# SEC-04` de `pip-audit-ignore.txt`. Verificación: el cuerpo bz2 de 101 bytes de la ficha ya no llega al serializer (esperado: `415` o `400` sin expandir). Si la versión nueva rompe algo de la suite, lo arreglas en el código, no fijando la versión vieja.
2. **SEC-09, login y recuperación:** a los throttles actuales (IP + correo, se quedan) súmales, con la misma caché:
   - **por IP sobre todos los correos:** login `20/15m`, recuperación `10/1h`;
   - **por correo sobre todas las IP:** login `10/15m`, recuperación `5/1h`.
   Tasas en `AUTH_RATE_LIMITS` (afectadas por `AUTH_RATE_LIMIT_MULTIPLIER` como las demás). El `429` sigue igual para un correo que existe y uno que no. **Sin demora progresiva con `sleep`** (bloquea workers): el límite por cuenta es el control "progresivo"; anótalo en "Cómo se solucionó" como decisión. Pruebas en `tests/security/` para los tres casos de la ficha (rociado, una cuenta desde varias IP, recuperación a muchos correos).
3. **SEC-10, límites generales por usuario** (REQ §9.3 / API §26): `DEFAULT_THROTTLE_CLASSES` con
   - lecturas (`GET`, `HEAD`) `600/1m` y escrituras `120/1m`, por usuario interno o por `buyer_session`; sin sesión, por IP;
   - un `ScopedRateThrottle` de `20/1m` en cambios de estado (`status-transitions`), radicaciones (`filings`) y desistimientos (`withdrawals`).
   Tasas en `AUTH_RATE_LIMITS` (con el multiplicador). Las vistas que ya tienen throttles propios los conservan **además** de los generales. Pruebas: una lectura, una escritura y un cambio de estado que llegan al límite y responden `429` con `Retry-After` y el texto en español.
   - Ojo con la suite: si muchas pruebas pegan a la misma vista, el límite puede saltar en el CI. Solución decidida: `config/settings/test.py` sube las tasas generales (p. ej. ×1000) y **solo las pruebas de límites** las bajan con `override_settings`.
4. **SEC-14, recuperación de contraseña:** el correo sale por la cola (Celery, como `apps/notifications`), después del commit, y un fallo del envío se registra en el log y nunca llega a la respuesta. La respuesta es la misma (`202`) y tarda lo mismo exista o no el correo. Quita el `xfail` de `test_reset_request_answers_the_same_when_the_mail_fails`. Si las invitaciones envían igual (síncrono), aplícales lo mismo y anótalo.

**Commit:** `fix(security): add account and IP limits, per-user throttles, queue reset emails and upgrade DRF`

## 3. Parte 2 — Respuestas HTTP y exposición
1. **SEC-08:** middleware que pone `Cache-Control: no-store` y agrega `Cookie` a `Vary` en toda respuesta de `/api/v1/` que no traiga ya un `Cache-Control` propio (los catálogos con ETag conservan `private, no-cache`; las descargas, el suyo). Prueba en un listado, un detalle, `/auth/me` y el CSV de reportes.
2. **SEC-07:** `REST_FRAMEWORK["DEFAULT_METADATA_CLASS"] = None`. Prueba que recorre **todas** las rutas del contrato con `OPTIONS` (con y sin sesión) y exige que ninguna dé 5xx; otra que confirma que el *preflight* de CORS (con `Origin` y `Access-Control-Request-Method`) sigue respondiendo bien desde `localhost:3000`.
3. **SEC-11:** `RequestDataTooBig` → `413 PAYLOAD_TOO_LARGE` con el formato de error de la API, en `config/exceptions.py`. Prueba con 3 MB en el login (sin sesión) y en `POST /clients`.
4. **SEC-12:** `handler404` y `handler500` en `config/urls.py`: JSON con `build_error_body` cuando la ruta empieza por `/api/`; fuera de `/api/`, lo de Django. Prueba: `/api/v1/no-existe` y `/api/v1/applications/abc` → `404` JSON con `request_id`.
5. **SEC-15:** el filtro de `config/log_redaction.py` reemplaza por `***` el valor de `search`, `email`, `document_number` (y `q` si existe) en la consulta de cualquier mensaje de log. Quita el `xfail` de `test_search_terms_are_not_written_to_the_access_log`.
6. **SEC-17:** `max_length=4000` en los dos `operational_notes` de `apps/banking/serializers.py`. Quita el `xfail`.
7. **SEC-18:** `/admin/` solo si `DEBUG` o `ADMIN_ENABLED=True` (setting nuevo, por defecto `False`); ruta configurable con `ADMIN_URL_PATH` (por defecto `admin/`). Si se publica sin `DEBUG`, su login pasa por un throttle por IP (`10/15m`). Quita el `xfail` (ajusta la prueba para cubrir los dos casos: con admin apagado → `404`; encendido → `429` al pasar el límite).
8. **SEC-19:** `/openapi.json` y `/docs` solo con `DEBUG` (o `API_DOCS_PUBLIC=True`, por defecto `False`). El frontend y la referencia publicada en GitHub Pages usan `contracts/openapi.json` del repo, así que no se rompe nada. Quita el `xfail`.

**Commit:** `fix(security): harden API responses, error formats, logs, admin and schema exposure`

## 4. Parte 3 — Configuración, despliegue e inventario
1. **SEC-01 + SEC-02:** `config/settings/production.py`: `from .base import *`, `DEBUG = False` fijo, SMTP real desde el entorno, `SECURE_HSTS_SECONDS` (3600), `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`, `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, `SECURE_SSL_REDIRECT` desde el entorno (por defecto `True`), `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, `AUTH_COOKIE_SECURE = True`, sin navegador de DRF.
   - `wsgi.py`, `asgi.py` y `celery.py` usan `production` por defecto; `manage.py` sigue con `local`.
   - **Importante:** el compose y el CI deben fijar `DJANGO_SETTINGS_MODULE` en **todos** sus servicios (backend, worker, beat, lo que haya), para que el entorno local siga en `local` y el CI en `test`. Verifica que `docker compose --profile full up` sigue levantando todo.
   - Verificación: `python manage.py check --deploy --settings=config.settings.production` (con variables de ejemplo, no las del `.env`) sin `W004`, `W008`, `W012`, `W016`, `W018`. Pega la salida en el reporte.
2. **SEC-03:** *system check* propio que falla (error, no aviso) si `len(AUTH_JWT_SIGNING_KEY.encode()) < 32` o si `SECRET_KEY` tiene menos de 50 caracteres o menos de 5 caracteres distintos, **salvo con `DEBUG`** (con `DEBUG`, aviso). Pruebas de los dos casos. **Regenerar las claves locales lo hace el orquestador en el `.env`**: deja en el reporte el comando para generarlas (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).
3. **SEC-05:** en `backend/docker-compose.yml`, todos los puertos publicados con `127.0.0.1:` delante. Los contenedores siguen hablando entre sí por la red del compose.
4. **SEC-06:** `backend/Dockerfile` en dos etapas:
   - base con `python:3.11-slim@sha256:<digest>` (saca el digest con `docker buildx imagetools inspect python:3.11-slim` y anota la fecha) y `pip==<versión>` fija;
   - etapa `dev` (la que usa el compose, con `target: dev`): igual que hoy, `runserver`;
   - etapa `production`: `gunicorn config.wsgi` con `--workers` desde el entorno, sin `tests/` ni `scripts/`, usuario no root como hoy.
   - `hadolint` sin `DL3013`. Verifica que la imagen `production` construye y arranca (con variables de ejemplo) y anota el tamaño de las dos.
5. **SEC-13:** corrige los dos desajustes (`available-actions` es una lista sin paginar; `document_type` del broker) y documenta los errores que faltan con un *postprocessing hook* de spectacular (así no tocas 66 vistas a mano): `400` en toda operación con cuerpo, `404` en toda operación con id en la ruta, `428` donde se exige `If-Match`, todos con el esquema de error común. Es solo agregar respuestas de error: las 2xx no cambian. Regenera `schema.d.ts` y confirma que el typecheck del front pasa (`corepack pnpm typecheck` en `frontend/`).
6. **SEC-20:** `docs/API_REST_MVP_CREDITO.md`: las 9 rutas inexistentes pasan a una sección "Fuera del MVP" (no se borran); se agregan las 5 de direcciones del cliente con permiso y alcance, y las del portal del comprador a las tablas. Quita el `xfail` de `test_every_documented_route_exists`.
7. **SEC-16 (aceptado, decisión de Carlos):** se deja el `409 DUPLICATE_CLIENT_DOCUMENT`. Motivo, en sus palabras resumidas: el documento identifica a la persona y no tiene sentido crear el mismo cliente diez veces, uno por broker; la unicidad es regla de negocio. Mitigación: la respuesta no trae datos del otro cliente (ya probado) y SEC-10 limita cuántas veces se puede probar. Convierte la prueba `xfail` en una prueba normal que fija ese comportamiento aceptado (409 sin `resource_id` ni datos para quien no ve al cliente) y documenta el riesgo residual.

**Commit:** `fix(security): add production settings, key checks, local-only ports, a reproducible image and fix the contract inventory`

## 5. Parte 4 — Re-test, documentación y cierre
1. **Re-test completo** contra el 8010 (y el 8011 donde aplique) con los scripts de la Fase A: cada hallazgo con su "antes" (de la Fase A) y su "después". Corre de nuevo, acotados a 20 minutos cada uno, **schemathesis** y **ZAP** (las mismas versiones de la Fase A) y compara: ningún 5xx nuevo, ningún hallazgo nuevo de severidad media o más. Si aparece algo nuevo, va como `SEC-21…` con su ficha y se corrige si es pequeño.
2. `pytest tests/security` completo: **0 `xfail`** (salvo que algo quede aceptado con prueba normal). La matriz de acceso sigue igual o mejor (2 115 casos o los que haya).
3. **Documentos:**
   - `docs/seguridad/hallazgos.md`: columna **Estado** (`corregido` / `aceptado`) y "Cómo se solucionó" en cada ficha;
   - `docs/SEGURIDAD.md`: resumen ejecutivo actualizado (X corregidos, 1 aceptado, riesgo residual), tabla con el estado, la sección "Cómo se solucionó" de cada uno, y un apartado **"Re-test de la Fase B"** con fecha, versiones y resultados;
   - `docs/guia/12-auditorias.md`: la parte de seguridad con el mismo resumen y el enlace a `docs/SEGURIDAD.md` (no rehagas la guía; solo esa sección);
   - `backend/README.md`: variables nuevas (`ADMIN_ENABLED`, `ADMIN_URL_PATH`, `API_DOCS_PUBLIC`, tasas nuevas) y cómo construir la imagen de producción;
   - `README.md` (raíz): en Quality, la línea de la auditoría pasa a "Fase A: 20 hallazgos (0 críticos, 0 altos); Fase B: 19 corregidos y 1 aceptado". Solo esa línea.
4. Reporte final con: tabla de los 20 (id, severidad, estado, prueba que lo cubre), números de la verificación, archivos tocados y **título y descripción del PR en español** (sin firmas ni `Co-Authored-By`).

**Commit:** `docs(security): close phase B with the re-test and how each finding was fixed`
**PR:** `fix(security): close the security audit findings (phase B)`

## 6. Fuera de esta tarea (decidido)
- Brechas de contrato para los fronts y datos de demo completos: van en `TAREA-brechas-3-demo.md` (otro agente).
- Auditorías de performance y carga: después de esta.
- Despliegue real: no hay. `production.py` y la imagen quedan listos y probados en local.

## Precisiones acordadas
(las agrega el agente)

### Preparación y Parte 1 (2026-11-19)
- **P1. Imagen propia `mvp-secb-backend`.** La imagen compartida `mvp-credit-backend-backend` trae DRF 3.17.2; para no tocarla (la usan otros agentes) construí una propia desde `backend/Dockerfile` de este worktree. El 8010 (`mvp-secb-api`) corre con ella, con `AUTH_RATE_LIMIT_MULTIPLIER=1` (para medir los límites reales) y con un Redis (`mvp-secb-redis`) y un worker de Celery (`mvp-secb-worker`) propios, para medir SEC-14 como en producción.
- **P2. Stubs de DRF.** `djangorestframework-stubs` 3.18.x exige `django-stubs>=6.1.2`, fuera del rango `<6.0`: subí también `django-stubs[compatible-mypy]>=6.1.2,<6.2` (tipos, sin efecto en ejecución). Pidieron tres anotaciones (`request.data` y `serializer.context` ahora son `Mapping`/unión).
- **P3. Contrato.** Con DRF 3.18, dos `status` de solo lectura (`CommissionSettlement` y la membresía de constructora) ganan `"default": "ACTIVE"` en `contracts/openapi.json`; regeneré el contrato y `schema.d.ts` (solo dos comentarios `@default`; los tipos no cambian). No es un cambio de forma de respuesta. Si `feat/backend-gaps-3` entra antes, se regenera al traer `master`.
- **P4. Límites generales: qué es lectura.** `GET`, `HEAD` y `OPTIONS` cuentan como lecturas; el resto, como escrituras. Sin sesión cuentan por IP (también el login: 120 escrituras por minuto por IP, además de sus límites propios).
- **P5. Cupo de cambios de estado.** Un solo cupo `state_changes` (`20/1m`) compartido por cambios de estado, desistimientos y radicaciones (REQ §9.3: "20 cambios de estado o radicaciones por minuto"). Sumé las **transiciones de oportunidad** (`/opportunities/{id}/transitions`), que también son cambios de estado. Solo cuenta escrituras: listar radicaciones no consume ese cupo.
- **P6. `ScopedUserRateThrottle` propio** en vez de `ScopedRateThrottle` de DRF: el de DRF lee `DEFAULT_THROTTLE_RATES` y su clave es por usuario o IP; el propio lee `AUTH_RATE_LIMITS` (con el multiplicador) y cuenta por sesión del comprador también. Las vistas solo declaran `throttle_scope`.
- **P7. Excepción a los límites generales:** `StorageObjectView` (enlace firmado del almacenamiento en disco, solo con servicios falsos) sigue con `throttle_classes = []`; su emisión ya cuenta como descarga. Lo fija `test_every_api_view_keeps_the_general_limits`.
- **P8. Límite por cuenta sin correo.** Si el cuerpo no trae correo, el límite por cuenta no cuenta (lo cubre el de IP); así un cuerpo vacío no comparte un cupo global.
- **P9. SEC-14, el token se genera en el worker.** Para que el token en claro no pase por el broker (Redis), la petición encola solo el correo normalizado y la IP; la tarea busca el usuario, crea el token y envía. Ventaja extra: la petición hace exactamente lo mismo exista o no el correo. Sin reintentos: si el envío falla, queda en el log (sin el correo) y la persona lo vuelve a pedir.
- **P10. Invitaciones.** También eran síncronas: ahora el worker genera el token de la invitación pendiente (`issue_invitation_token`) y envía; la creación guarda un hash de relleno que nunca sale. El enlace del comprador (`send_buyer_access_email`) sigue síncrono: lo emite un asesor con sesión y no revela cuentas; queda fuera de esta tarea.
- **P11. Prueba de `Accept` cuadrático.** El cliente de pruebas de Django no reproduce el costo del `Accept` de CVE-2026-114138 (pasa igual con 3.17.2), así que no dejé una prueba que no discrimina: lo cubren `test_drf_has_the_fix_of_both_cves` y la medición en el 8010.
- **P12. `_without_request_id` ignora los minutos del texto del `429`.** El reloj de la VM de Docker salta unos segundos y el texto puede decir "60" o "61 minutos"; la igualdad existente/inexistente se compara con código y detalles, y los dos textos se revisan contra el prefijo en español.
- **P13. Guía.** `docs/guia/03-arquitectura.md`: la versión de DRF de la tabla pasa a 3.18 (dato que cambió con este PR). Lo demás de la guía queda para la Parte 4.

### Parte 2 (2026-11-19)
- **P14. `Vary: Cookie` siempre en `/api/v1/`**, también cuando la vista trae su propio `Cache-Control` (catálogos con ETag, descargas): la respuesta depende de la sesión en todos los casos. `no-store` solo si la vista no fijó uno. El middleware va justo después de `RequestIDMiddleware`, para cubrir también las respuestas que cortan otros middlewares (CORS, errores).
- **P15. `OPTIONS` sin sesión en rutas protegidas responde `401`**, no `405`: la autenticación de DRF corre antes del método. Ninguna da 5xx, que es lo que pide la spec.
- **P16. SEC-12 con `DEBUG`.** Django no usa `handler404`/`handler500` con `DEBUG`, así que en local (8010) sigue la página de depuración. El "después" se midió en el 8011 sin `DEBUG`.
- **P17. 8011 de auditoría.** Como en la Fase A, `config.settings.base` sin `DEBUG`, pero a través de un módulo fuera del repo (`_security-work/scripts/secb_nodebug.py`) que solo agrega `DOCUMENT_ALLOW_FAKE_SERVICES = True`, para no levantar SeaweedFS ni ClamAV; y `AUTH_COOKIE_SECURE=False` para que el script use la sesión por HTTP. El "antes" corrió con el código del commit de la Parte 1 (`git archive 6b06d30`, en `_security-work/antes-p2/`).
- **P18. SEC-15: un solo filtro.** Extendí el filtro existente (`RedactObjectTokensFilter`, ya conectado en `LOGGING`) en vez de agregar otro: no cambia `LOGGING`. Los parámetros se reconocen sin distinguir mayúsculas. El *access log* de gunicorn no pasa por los filtros de Django: en la Parte 3 la imagen de producción no lo activa.
- **P19. SEC-18: el límite del admin aplica siempre** que el admin esté publicado (con `DEBUG` también, multiplicado por `AUTH_RATE_LIMIT_MULTIPLIER`). Solo cuentan los `POST`. El `429` del admin es texto plano (no es la API) con el mismo mensaje en español y `Retry-After`. `ADMIN_URL_PATH` se normaliza a `algo/`.
- **P20. URLs según ajustes.** `config/urls.py` decide al importarse qué publica; las pruebas que encienden el admin o el esquema usan `tests.helpers.urls_with(...)`, que recarga `config.urls` y lo restaura al salir. `tests/test_platform.py::test_openapi_schema_is_public_and_documents_auth` pasó a `test_openapi_schema_documents_auth` con `API_DOCS_PUBLIC=True`.
- **P21. SEC-17 en el contrato.** `maxLength: 4000` en los dos `operational_notes` de `contracts/openapi.json` (solo una validación nueva de entrada); `schema.d.ts` no cambia.

### Parte 3 (2026-11-19)
- **P22. Claves en `test.py`.** El check de SEC-03 corre en cualquier comando sin `DEBUG` (`makemigrations`, `spectacular`), y el CI pasa `DJANGO_SECRET_KEY` de 32 caracteres: `config/settings/test.py` fija una `SECRET_KEY` larga (la JWT ya era fija). No toqué el workflow.
- **P23. Regla de `SECRET_KEY`.** La de Django completa (`security.W009`): menos de 50 caracteres, menos de 5 distintos **o** el prefijo `django-insecure-`. La clave JWT se mide en bytes UTF-8.
- **P24. Gunicorn no corre los *system checks*.** Para que una clave débil sí impida arrancar en producción, la imagen `production` corre `python manage.py check` y luego `exec gunicorn` (con `DJANGO_SETTINGS_MODULE=config.settings.production` en la imagen, `manage.py` también usa `production`).
- **P25. `SECURE_REDIRECT_EXEMPT` para `/health` y `/ready`**: el orquestador los consulta por HTTP dentro de la red. `W021` (HSTS *preload*) queda a propósito: con 3600 s no corresponde.
- **P26. Gunicorn por archivo de configuración** (`config/gunicorn.py`), no por flags: `GUNICORN_WORKERS` (3), `GUNICORN_BIND`, `GUNICORN_TIMEOUT`, `GUNICORN_MAX_REQUESTS(_JITTER)`, `GUNICORN_LOG_LEVEL`; `accesslog = None` (SEC-15). `# nosec B104` en el `0.0.0.0` con su motivo.
- **P27. Usuario de la imagen por nombre.** `hadolint` deja 2 `DL3066` informativos (como en la Fase A). No pasé a uid numérico: cambiaría el dueño del volumen `mvp_credit_documents_data` que ya existe en local.
- **P28. Tamaño de la imagen `production`** (588 MB frente a 590 MB de `dev`): `requirements.txt` trae también pruebas y calidad. Separarlo cambia el CI; queda como residual en SEC-06.
- **P29. `docker compose --profile full up` aislado.** El compose tiene nombre de proyecto, red y volúmenes fijos y compartidos con el Postgres que usan todos los agentes: levantarlo tal cual recrearía ese contenedor y otro Postgres podría montar el mismo volumen. Lo levanté desde una copia en el scratchpad con solo eso cambiado (proyecto `mvp-secb-compose`, volúmenes y red `secb_compose_*`, rutas absolutas al código del worktree y al `.env`, que lee Docker) y puertos 5543/8020/3020/8353 por variables. El frontend reusó la imagen ya construida. Lo bajé con `down -v`.
- **P30. SEC-13, `document_type` del broker.** El contrato ya tenía el `oneOf` bien; el fallo era el correo vacío con `format: email` (lo reproduje con `jsonschema` sobre la respuesta real). Arreglé el formato en los 6 esquemas cuyo campo admite vacío (`Client`, `ClientDetail`, `BrokerClient`, `BuyerProfile`, `Partner`, `PartnerDetail`) con `BlankableEmailField` (un `CharField`: spectacular deduce el formato del `EmailValidator`).
- **P31. SEC-13, el hook.** Además de 400/404/428, agrega la cabecera `If-Match` donde ya se documentaba el `428` sin ella (`PATCH /commission-plans/{plan_id}`). No reordena las respuestas, para no ensuciar el diff.
- **P32. SEC-20: eran 4 rutas de direcciones**, no 5 (las del contrato). Las rutas fuera del MVP van en §31.1 con la forma `` `GET /ruta` `` en una sola celda, que la prueba no cuenta como documentada. Agregué la prueba inversa (todo el contrato documentado).
- **P33. SEC-16**: además de fijar el `409` aceptado, una prueba de la mitigación (el límite general de escrituras corta el sondeo de cédulas).

### Merge de `master` (#36) y Parte 4 (2026-11-19)
- **P34. Merge.** Un solo conflicto real (`backend/apps/partners/serializers.py`: `status_label` del #36 y `BlankableEmailField` de SEC-13; quedan los dos). El resto se fusionó solo; revisé que conservara lo de las dos ramas (límites, metadata, middleware, admin, esquema, hook, `max_length`, `throttle_scope`, `pagination_class`) y los CRLF. Regenerados `contracts/openapi.json`, `schema.d.ts` y `03-matriz-acceso.md`: coinciden con lo fusionado. No toqué el índice de git.
- **P35. `security/seed_actors.py`.** Con la demo del #36 chocaba dos veces: creaba `constructora@demo.local` (que ahora trae la demo; si este script corría antes, `seed_demo_data` fallaba con `EmailAlreadyRegistered`) y usaba el prefijo de documento `9901`, que ahora es el del historial de la demo (con él no creaba al comprador B). Ya no crea la constructora (informa la de la demo) y su marca pasa a `9909`. Para tener la base limpia, recreé `mvp_credit_secb` (solo mía) en el orden documentado.
- **P36. Límites durante los escáneres.** Con SEC-10, un escáner a ~10 peticiones por segundo choca con los `429`. schemathesis y ZAP corrieron contra el 8010 con `AUTH_RATE_LIMIT_MULTIPLIER=1000` (solo vale con `DEBUG`) y sesiones de 120 minutos; los límites se midieron aparte con el multiplicador en 1. Antes de cada escaneo que escribe, la base se restauró desde una plantilla (`mvp_credit_secb_tpl`).
- **P37. Tiempo de los escáneres.** schemathesis: una corrida como admin (11 min) y otra sin sesión (9 min), 20 min en total; ZAP activo como admin, 15 min de escaneo. Hubo una corrida previa de schemathesis como admin (antes de extender el hook y de SEC-21) y un ZAP inválido (sin sesión); los dos quedan anotados y no cuentan.
- **P38. Hook de SEC-13, extensión.** La primera corrida de schemathesis mostró `404` de página fuera de rango y `400` de filtros inválidos sin documentar: el hook también agrega `400` donde hay parámetros de consulta y `404` donde hay `page`. `DELETE /application-participants/{id}` documenta su `400` en la vista.
- **P39. SEC-21 (nuevo, informativo, corregido):** las respuestas `*ByRole` pasan de `oneOf` a `anyOf` en el mismo hook (una página vacía valía para las dos formas). Con él son 21 hallazgos: 20 corregidos y 1 aceptado.
- **P40. Descartes del re-test:** ZAP `SQL Injection` (40018) × 4 es un falso positivo (reproducido con el estado fijo: misma respuesta con `AND 1=1`, `AND 1=2` y `OR 1=1`); schemathesis `ST112` (un login de 12,7 s) no se reproduce (mediana de 38 ms en 5 repeticiones).
- **P41. README raíz.** La línea de la auditoría está en inglés, como el resto del README: "Phase A: 20 findings (0 critical, 0 high); phase B: 19 fixed and 1 accepted", más SEC-21 y la cifra de la matriz que da `render_matrix.py` (2 124).
- **P42. Claves del `.env` local.** En el re-test, `manage.py check` sin `DEBUG` con el `.env` local ya no da avisos: el orquestador las regeneró. Los documentos lo dicen así.
- **P43. gitleaks.** Como el CI (imagen por digest, `--log-opts=--all`), sobre el `.git` del repo principal montado de solo lectura (60 commits de todas las ramas), más el diff sin commitear por `stdin`. 0 hallazgos.
