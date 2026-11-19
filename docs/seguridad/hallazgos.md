# Hallazgos de la auditoría de seguridad (Fase A)

Lista viva: cada parte de la auditoría agrega los suyos. Formato y escala de severidad en
`specs/TAREA-seguridad.md` §5. Ningún hallazgo incluye secretos, tokens ni URL firmadas: si
uno expone un valor, se describe y se corta.

| Id | Título | Severidad | OWASP API Top 10 (2023) | Estado | Parte |
| --- | --- | --- | --- | --- | --- |
| [SEC-01](#sec-01--no-hay-configuración-de-producción-y-los-puntos-de-entrada-cargan-local-que-fuerza-debugtrue) | No hay configuración de producción y los puntos de entrada cargan `local`, que fuerza `DEBUG=True` | Baja | API8 | abierto | 1 |
| [SEC-02](#sec-02--la-configuración-base-no-endurece-https) | La configuración base no endurece HTTPS | Baja | API8 | abierto | 1 |
| [SEC-03](#sec-03--las-claves-no-se-validan-al-arrancar-la-clave-jwt-local-tiene-31-bytes) | Las claves no se validan al arrancar; la clave JWT local tiene 31 bytes | Baja | API8 | abierto | 1 |
| [SEC-04](#sec-04--djangorestframework-3172-tiene-dos-cve-de-denegación-de-servicio-sin-sesión) | `djangorestframework` 3.17.2 tiene dos CVE de denegación de servicio sin sesión | Media | API4 | corregido | 1 |
| [SEC-05](#sec-05--el-compose-publica-postgresql-y-el-backend-en-todas-las-interfaces-del-equipo) | El compose publica PostgreSQL y el backend en todas las interfaces del equipo | Baja | API8 | abierto | 1 |
| [SEC-06](#sec-06--imagen-del-backend-base-sin-digest-pip-sin-versión-y-runserver-como-comando) | Imagen del backend: base sin digest, `pip` sin versión y `runserver` como comando | Informativa | API8 | abierto | 1 |
| [SEC-07](#sec-07--options-responde-500-en-27-rutas-una-de-ellas-pública) | `OPTIONS` responde 500 en 27 rutas, una de ellas pública | Baja | API8 | corregido | 2 |
| [SEC-08](#sec-08--las-respuestas-con-datos-personales-no-llevan-cache-control-no-store-ni-vary-cookie) | Las respuestas con datos personales no llevan `Cache-Control: no-store` (ni `Vary: Cookie`) | Media | API8 | corregido | 2 |
| [SEC-09](#sec-09--el-límite-de-login-y-de-recuperación-se-salta-con-otros-correos-o-con-otras-ip) | El límite de login y de recuperación se salta con otros correos o con otras IP | Media | API2 | corregido | 2 |
| [SEC-10](#sec-10--no-existen-los-límites-generales-por-usuario-que-piden-req-93-y-api-26) | No existen los límites generales por usuario que piden REQ §9.3 y API §26 | Media | API4 | corregido | 2 |
| [SEC-11](#sec-11--un-json-de-más-de-25-mb-responde-500-sin-debug-o-la-página-de-depuración-con-debug-no-413) | Un JSON de más de 2,5 MB responde 500 (sin `DEBUG`) o la página de depuración (con `DEBUG`), no 413 | Baja | API8 | corregido | 2 |
| [SEC-12](#sec-12--las-rutas-inexistentes-y-los-ids-que-no-son-uuid-responden-html-de-django-no-el-formato-de-error-de-la-api) | Las rutas inexistentes y los ids que no son UUID responden HTML de Django, no el formato de error de la API | Baja | API8 | corregido | 2 |
| [SEC-13](#sec-13--el-contrato-no-coincide-con-la-api-en-2-respuestas-y-no-documenta-varios-estados) | El contrato no coincide con la API en 2 respuestas y no documenta varios estados | Informativa | API9 | abierto | 2 |
| [SEC-14](#sec-14--la-recuperación-de-contraseña-revela-si-el-correo-existe-cuando-falla-el-envío) | La recuperación de contraseña revela si el correo existe cuando falla el envío | Media | API2 | corregido | 4 |
| [SEC-15](#sec-15--el-log-de-peticiones-guarda-la-búsqueda-completa-documento-o-nombre) | El log de peticiones guarda la búsqueda completa (documento o nombre) | Baja | API8 | corregido | 4 |
| [SEC-16](#sec-16--un-409-al-crear-un-cliente-confirma-que-esa-cédula-ya-está-registrada) | Un `409` al crear un cliente confirma que esa cédula ya está registrada | Baja | API3 | abierto | 4 |
| [SEC-17](#sec-17--textos-de-la-configuración-de-bancos-sin-longitud-máxima) | Textos de la configuración de bancos sin longitud máxima | Informativa | API4 | corregido | 4 |
| [SEC-18](#sec-18--admin-de-django-está-publicado-con-la-api-y-su-login-no-tiene-límite-de-intentos) | `/admin/` de Django está publicado con la API y su login no tiene límite de intentos | Baja | API8 | corregido | 4 |
| [SEC-19](#sec-19--el-esquema-openapi-y-la-documentación-interactiva-son-públicos) | El esquema OpenAPI y la documentación interactiva son públicos | Informativa | API9 | corregido | 4 |
| [SEC-20](#sec-20--la-documentación-de-la-api-promete-9-rutas-que-no-existen-y-omite-5-que-sí) | La documentación de la API promete 9 rutas que no existen y omite 5 que sí | Informativa | API9 | abierto | 4 |

---

### SEC-01 — No hay configuración de producción y los puntos de entrada cargan `local`, que fuerza `DEBUG=True`
- **Severidad:** Baja (configuración de producción ausente; hoy el alcance es solo local). Sube a **Alta** el día que se despliegue así.
- **Categoría:** OWASP API8:2023 — Security Misconfiguration
- **Dónde:** `backend/manage.py:10`, `backend/config/wsgi.py:14`, `backend/config/asgi.py:14`, `backend/config/celery.py:13` (todos con `os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")`); `backend/config/settings/local.py` (`DEBUG = True` fijo). En `config/settings/` solo hay `base`, `local` y `test`.
- **Cómo reproducirlo:**
  ```
  docker run --rm --network mvp_credit_network --env-file <ENV> -e DATABASE_HOST=postgres \
    -e DJANGO_DEBUG=False -v <WT>\backend:/app -w /app mvp-credit-backend-backend \
    python -c "import config.wsgi; from django.conf import settings as s; print(s.DEBUG, s.EMAIL_BACKEND, s.AUTH_COOKIE_SECURE)"
  ```
  Imprime `True django.core.mail.backends.console.EmailBackend False` aunque `DJANGO_DEBUG=False`. `python manage.py check --deploy` con `-e DJANGO_DEBUG=False` (sin cambiar el módulo de settings) da además `security.W018` (DEBUG) y `security.W016` (cookie CSRF sin `Secure`).
- **Qué pasa:** `local.py` pisa lo que diga el entorno: `DEBUG=True`, correo a la consola, `AUTH_COOKIE_SECURE=False`, `CSRF_COOKIE_SECURE=False`, `SESSION_COOKIE_SECURE=False` y el navegador de DRF. Un despliegue con `gunicorn config.wsgi` (gunicorn ya está en `requirements.txt`) que no defina `DJANGO_SETTINGS_MODULE` queda con todo eso.
- **Qué debería pasar:** REQ §9: producción sin modo de depuración, cookies `Secure` y prefijo `__Host-`. El valor por defecto de los puntos de entrada no debería ser el de desarrollo.
- **Impacto (si se despliega así):** páginas de error de Django con traza, consultas y variables de configuración; los correos (enlaces mágicos del comprador, enlaces de restablecimiento e invitaciones, que llevan el token en la URL) salen al log del proceso; cookies de sesión sin `Secure`; con `DEBUG`, `apps/documents/storage.py` admite el almacenamiento en disco y el antivirus falso.
- **Corrección sugerida:** crear `config/settings/production.py` (`from .base import *`, `DEBUG = False` fijo, SMTP real, las cabeceras de SEC-02) y que `wsgi.py`, `asgi.py` y `celery.py` usen `production` por defecto (o no tengan valor por defecto y fallen sin `DJANGO_SETTINGS_MODULE`); `manage.py` puede seguir con `local`.
- **Esfuerzo estimado:** pequeño.

### SEC-02 — La configuración base no endurece HTTPS
- **Severidad:** Baja (endurecimiento; aplica al desplegar con HTTPS).
- **Categoría:** OWASP API8:2023 — Security Misconfiguration
- **Dónde:** `backend/config/settings/base.py` (no define `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE` ni `SECURE_PROXY_SSL_HEADER`).
- **Cómo reproducirlo:** `python manage.py check --deploy` con `-e DJANGO_DEBUG=False -e DJANGO_SETTINGS_MODULE=config.settings.base -e DOCUMENT_STORAGE_BACKEND=s3 -e DOCUMENT_SCANNER=clamd` → `security.W004` (HSTS), `security.W008` (redirección a HTTPS), `security.W012` (`SESSION_COOKIE_SECURE`).
- **Qué pasa:** con la configuración base, el navegador no recibe HSTS, HTTP no redirige a HTTPS y la cookie de sesión de Django (la usa solo `/admin/`) no lleva `Secure`. Las cookies propias sí están bien: `AUTH_COOKIE_SECURE` y `CSRF_COOKIE_SECURE` valen `True` por defecto en `base.py`.
- **Qué debería pasar:** en producción, HSTS (con un valor corto primero), redirección o terminación TLS en el proxy declarada con `SECURE_PROXY_SSL_HEADER`, y `SESSION_COOKIE_SECURE=True`.
- **Impacto:** degradación a HTTP en la primera visita (sin HSTS) y robo de la cookie de sesión del administrador de Django en una red no confiable.
- **Corrección sugerida:** en `production.py` (SEC-01): `SECURE_HSTS_SECONDS` (empezar con 3600 y subir), `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_SSL_REDIRECT=True` o `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` si el TLS termina en el proxy, `SESSION_COOKIE_SECURE=True`.
- **Esfuerzo estimado:** pequeño.

### SEC-03 — Las claves no se validan al arrancar; la clave JWT local tiene 31 bytes
- **Severidad:** Baja (la clave débil es la del `.env` local, que no está en git; lo que falta en el código es el control).
- **Categoría:** OWASP API8:2023 — Security Misconfiguration
- **Dónde:** `backend/config/settings/base.py` (`SECRET_KEY = env("DJANGO_SECRET_KEY")`, `AUTH_JWT_SIGNING_KEY = env("AUTH_JWT_SIGNING_KEY")`: se exige que existan, no que sean fuertes); `backend/apps/identity/tokens.py` (HS256).
- **Cómo reproducirlo:** en un contenedor de un solo uso con el `.env` local, imprimir **solo la longitud** de `settings.AUTH_JWT_SIGNING_KEY` → 31 bytes. `docker logs mvp-sec-api | grep InsecureKeyLengthWarning` → PyJWT 2.15.1 avisa en cada firma y verificación: "The HMAC key is 31 bytes long, which is below the minimum recommended length of 32 bytes for SHA256. See RFC 7518 Section 3.2". `check --deploy` da `security.W009` con la `SECRET_KEY` local (49 caracteres, por debajo de los 50 que pide Django).
- **Qué pasa:** el arranque acepta cualquier valor no vacío. El comentario de `base.py` pide una clave "de alta entropía", pero nada lo comprueba.
- **Qué debería pasar:** RFC 7518 §3.2: una clave HMAC para HS256 de al menos 256 bits. La API debería negarse a arrancar sin `DEBUG` con una clave más corta.
- **Impacto:** con una clave corta o de baja entropía, un atacante que obtiene un JWT válido puede intentar adivinar la clave fuera de línea y, si lo logra, firmar JWT de cualquier usuario (tomar la cuenta de otro).
- **Corrección sugerida:** un *system check* (o una validación en `IdentityConfig.ready`) que falle si `len(AUTH_JWT_SIGNING_KEY.encode()) < 32` o si `SECRET_KEY` no pasa la regla de Django, salvo con `DEBUG`; regenerar las claves locales con `python -c "import secrets; print(secrets.token_urlsafe(48))"` (lo hace Carlos en su `.env`).
- **Esfuerzo estimado:** pequeño.

### SEC-04 — `djangorestframework` 3.17.2 tiene dos CVE de denegación de servicio sin sesión
- **Severidad:** Media (CVSS 3.1 ~5.3: AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L). Sin sesión, pero se necesita volumen para tumbar el servicio.
- **Categoría:** OWASP API4:2023 — Unrestricted Resource Consumption
- **Dónde:** `backend/requirements.txt` (`djangorestframework>=3.17,<3.18`: el arreglo, 3.18.2, queda fuera del rango); `REST_FRAMEWORK["DEFAULT_PARSER_CLASSES"] = ["rest_framework.parsers.JSONParser"]` en `base.py`.
- **Cómo reproducirlo (servidor 8010):**
  - **CVE-2026-114136 / GHSA-3547-9m27-7rxg** (el `charset` del `Content-Type` elige un códec que descomprime): un cuerpo de **101 bytes** comprimido con bz2 y `Content-Type: application/json; charset=bz2_codec` a `POST /api/v1/auth/login` llega al serializer como un correo de **5 242 921 caracteres** (respuesta `400 VALIDATION_ERROR` con `MAX_LENGTH`). El mismo JSON sin comprimir lo corta Django antes (`RequestDataTooBig`). Es decir, `DATA_UPLOAD_MAX_MEMORY_SIZE` no protege.
  - **CVE-2026-114138 / GHSA-33wh-fxxf-88vv** (el `Accept` se analiza en tiempo cuadrático): un solo `Accept` de ~9 KB con un parámetro entre comillas lleno de `;` sube una petición sin sesión de ~6 ms a ~40 ms en `runserver`. `runserver` corta cabeceras de más de 64 KB (`431`), así que aquí no se puede escalar; el aviso mide 18,9 s de CPU con gunicorn por defecto.
- **Qué pasa:** cualquier vista que lea JSON (incluidas las públicas: login, restablecimiento, consumo del enlace mágico) descomprime sin límite lo que mande el cliente, y cualquier petición paga el análisis del `Accept` antes de autenticarse.
- **Qué debería pasar:** el límite de tamaño del cuerpo se aplica a lo que se procesa, y una cabecera no puede costar segundos de CPU.
- **Impacto:** un atacante sin cuenta, con pocas peticiones, agota memoria o CPU de los workers (la API deja de responder). No expone datos.
- **Corrección sugerida:** subir a `djangorestframework>=3.18.2,<3.19` (y `djangorestframework-stubs` compatible) y correr la suite completa en el CI. Mientras tanto: un `JSONParser` propio que rechace `charset` que no sea de texto (`codecs.lookup(enc)._is_text_encoding`) y un límite de tamaño de cabeceras en el proxy.
- **Esfuerzo estimado:** pequeño (subir una versión menor; las regresiones las detecta la suite).
- **En el CI:** los dos CVE están en `backend/security/pip-audit-ignore.txt` con `# SEC-04` (si no, `pip-audit` haría fallar el CI); al subir la versión se borran esas líneas.
- **Cómo se solucionó (Fase B):**
  1. **Causa:** `requirements.txt` fijaba `djangorestframework>=3.17,<3.18` y el arreglo de los dos CVE salió en 3.18.2.
  2. **Cambio:** `backend/requirements.txt` (`djangorestframework>=3.18.2,<3.19`; `djangorestframework-stubs>=3.18.2,<3.19` y, porque esos stubs la piden, `django-stubs[compatible-mypy]>=6.1.2,<6.2`; queda instalada DRF 3.18.3); `backend/security/pip-audit-ignore.txt` (sin las dos líneas `# SEC-04`). Los stubs nuevos pidieron tres anotaciones de tipos, sin cambio de comportamiento: `backend/apps/reporting/services.py`, `backend/apps/identity/buyer_portal_serializers.py` y `backend/tests/applications/idempotency/test_idempotency.py`. Con DRF 3.18, dos `status` de solo lectura del contrato ganan `"default": "ACTIVE"` (`contracts/openapi.json` y, solo como comentario `@default`, `frontend/src/lib/api/schema.d.ts`); las respuestas no cambian.
  3. **Verificación:** `backend/tests/security/test_resources.py::test_a_compressed_charset_is_not_expanded` y `::test_drf_has_the_fix_of_both_cves` (las dos fallan con 3.17.2). Contra el 8010 con `_security-work/scripts/sec04_bz2.py`: **antes** (3.17.2) el cuerpo bz2 de 96 bytes con `charset=bz2_codec` llega al serializer como un correo de 5 242 915 caracteres → `400 VALIDATION_ERROR` (586 ms); **después** (3.18.3) → `400 MALFORMED_REQUEST`, sin descomprimir (66 ms). `Accept` de ~9 KB en `GET /api/v1/auth/me` sin sesión: **antes** 64 ms de mediana (4 ms sin la cabecera); **después** `406` en 7 ms. `pip-audit` ya no necesita excepciones para DRF.
  4. **PR:** Fase B (este PR).
  5. **Estado:** corregido.

### SEC-05 — El compose publica PostgreSQL y el backend en todas las interfaces del equipo
- **Severidad:** Baja (entorno local; endurecimiento).
- **Categoría:** OWASP API8:2023 — Security Misconfiguration
- **Dónde:** `backend/docker-compose.yml`: `"${POSTGRES_HOST_PORT:-5433}:5432"`, `"${BACKEND_HOST_PORT:-8000}:8000"`, `"${FRONTEND_HOST_PORT:-3000}:3000"` y, con el perfil `full`, `"${DOCUMENT_STORAGE_HOST_PORT:-8333}:8333"`.
- **Cómo reproducirlo:** `docker ps --format '{{.Names}} {{.Ports}}'` → `0.0.0.0:5433->5432/tcp` y `0.0.0.0:8000->8000/tcp`.
- **Qué pasa:** sin IP en el mapeo, Docker escucha en todas las interfaces: cualquiera en la misma red (wifi de un café, oficina) llega a PostgreSQL con usuario y contraseña, y a la API en modo `DEBUG`.
- **Qué debería pasar:** en desarrollo, solo `127.0.0.1`. Redis y ClamAV ya están bien: solo en la red interna del compose.
- **Impacto:** en una red compartida, ataque de fuerza bruta a la base o acceso a las páginas de depuración del backend.
- **Corrección sugerida:** `"127.0.0.1:${POSTGRES_HOST_PORT:-5433}:5432"` y lo mismo en los otros puertos publicados.
- **Esfuerzo estimado:** pequeño.

### SEC-06 — Imagen del backend: base sin digest, `pip` sin versión y `runserver` como comando
- **Severidad:** Informativa (aplica al desplegar).
- **Categoría:** OWASP API8:2023 — Security Misconfiguration
- **Dónde:** `backend/Dockerfile`.
- **Cómo reproducirlo:** `hadolint` 2.15.1 → `DL3013` (línea 11, `pip install --upgrade pip` sin versión). En la Parte 2, ZAP (10036) y la revisión de cabeceras: `runserver` responde `Server: WSGIServer/0.2 CPython/3.11.18`, que revela la versión exacta de Python. En la Parte 4: `GET /static/../data/documents/` con `runserver` responde 500 (Django bloquea la ruta con `SuspiciousFileOperation`, no se lee nada); es el servidor de estáticos de desarrollo, solo con `DEBUG`. Revisión manual: `FROM python:3.11-slim` sin `@sha256:`; `CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]`; `COPY . ./` deja `tests/`, `scripts/` y `docker-compose.yml` dentro de la imagen.
- **Qué pasa:** dos construcciones de la misma versión del código pueden dar imágenes distintas (la base y `pip` cambian solas), y la imagen arranca con el servidor de desarrollo de Django.
- **Qué debería pasar:** imagen reproducible y servidor de aplicación (`gunicorn`, ya en `requirements.txt`) en la imagen de producción.
- **Lo que ya está bien (verificado):** usuario no root (`id` en el contenedor → `uid=100(app) gid=101(app)`, también en `mvp-sec-api`); sin `.env` en la imagen (`.dockerignore` lo excluye; `test -e /app/.env` → no existe); sin secretos en `ENV` ni en las capas (`docker image inspect` y `docker history`: el único `GPG_KEY` es el id público de la clave de firma de Python); `/data/documents` con dueño `app` y modo `755`.
- **Corrección sugerida:** `FROM python:3.11-slim@sha256:<digest>`, `pip install pip==<versión>`, una etapa o `CMD` de producción con `gunicorn config.wsgi` (junto con SEC-01), y excluir `tests/` del contexto de la imagen de producción.
- **Esfuerzo estimado:** pequeño.

### SEC-07 — `OPTIONS` responde 500 en 27 rutas, una de ellas pública
- **Severidad:** Baja (sin `DEBUG` la respuesta es el error genérico, sin fuga; una de las rutas no pide sesión).
- **Categoría:** OWASP API8:2023 — Security Misconfiguration
- **Dónde:** las vistas genéricas de DRF con escritura que no declaran `serializer_class` (lo arman a mano en `post`/`put`): `apps/identity/invitation_views.py` (`InvitationAcceptView`), `apps/identity/buyer_access_views.py` (`ApplicationBuyerAccessLinksView`), `apps/filings/views.py` (`ApplicationFilingListView`, `FilingResponseListView`), `apps/commissions` (`CommissionPlanListView`), `apps/tasks` (`TaskListView`) y las de `/applications`, `/clients`, `/users`, `/banks`, `/bank-products`, `/partners`, `/projects`, `/opportunities`, `/invitations`, `/document-types`, `/document-requirements`, `/reports/applications/export-jobs`, entre otras (lista completa en el reporte crudo `options_500_admin.txt`). La metadata de `OPTIONS` es la de DRF por defecto (`SimpleMetadata`): no hay `DEFAULT_METADATA_CLASS` en `base.py`.
- **Cómo reproducirlo:** `curl -X OPTIONS http://localhost:8010/api/v1/invitations/accept` (sin sesión) → `500`; con `DEBUG`, página de depuración con `AssertionError: 'InvitationAcceptView' should either include a serializer_class attribute…`; sin `DEBUG` (8011) → `500 INTERNAL_ERROR` y un "Error no controlado en la API" en el log. schemathesis (`ST101`, check `unsupported_method`) lo encontró en 6 vistas; un barrido con `OPTIONS` a las 175 rutas dio 27 con sesión de admin y 1 sin sesión.
- **Qué pasa:** `SimpleMetadata.determine_actions` llama `get_serializer()` para describir los campos de escritura; sin `serializer_class` salta el `assert` de DRF. Donde no falla, `OPTIONS` responde el nombre y la descripción de la vista, los *renderers* y los *parsers* (sin campos).
- **Qué debería pasar:** ningún 500 (spec §4, Parte 2: "cualquier 500 es hallazgo"). `OPTIONS` solo hace falta para el *preflight* de CORS, que ya responde `corsheaders` antes de llegar a DRF.
- **Impacto:** cualquiera, sin cuenta, llena el log de errores no controlados (ruido que tapa alertas reales y puede disparar avisos de monitoreo); con `DEBUG`, la traza revela rutas y código.
- **Corrección sugerida:** `REST_FRAMEWORK["DEFAULT_METADATA_CLASS"] = None` (DRF responde `405` a `OPTIONS` en las vistas; el *preflight* sigue funcionando por `corsheaders`) y una prueba que haga `OPTIONS` a todas las rutas y exija que ninguna dé 5xx.
- **Esfuerzo estimado:** pequeño.
- **Cómo se solucionó (Fase B):**
  1. **Causa:** la metadata por defecto de DRF (`SimpleMetadata`) describía los campos de escritura llamando `get_serializer()`, que falla en las vistas que arman el serializer a mano.
  2. **Cambio:** `backend/config/settings/base.py` (`REST_FRAMEWORK["DEFAULT_METADATA_CLASS"] = None`): `OPTIONS` responde `405 METHOD_NOT_ALLOWED` (o `401`/`403` si la ruta exige sesión) y no describe la vista. El *preflight* de CORS no cambia: lo responde `corsheaders` antes de la vista.
  3. **Verificación:** `backend/tests/security/test_http_responses.py::test_options_never_answers_5xx[anon]` y `[admin]` (todas las rutas del contrato), `::test_options_does_not_describe_the_view` y `::test_cors_preflight_still_works_from_the_frontend`. Barrido de las 175 rutas con `OPTIONS` (**antes** con el código del commit de la Parte 1 y **después** con el de este PR, los dos sin `DEBUG` en el 8011, `_security-work/secb_part2.txt` (script `secb_part2.py`)): **antes** sin sesión `200` × 7, `401` × 167 y `500` × 1 (`/api/v1/invitations/accept`); con admin `500` × 28. **Después** sin sesión `401` × 167 y `405` × 8; con admin `401` × 25, `403` × 48 y `405` × 102; ningún 5xx. El *preflight* desde `http://localhost:3000` responde `200` con `Access-Control-Allow-Origin: http://localhost:3000` y `Access-Control-Allow-Credentials: true`, antes y después.
  4. **PR:** Fase B (este PR).
  5. **Estado:** corregido.

### SEC-08 — Las respuestas con datos personales no llevan `Cache-Control: no-store` (ni `Vary: Cookie`)
- **Severidad:** Media (falta de una cabecera que importa; CVSS 3.1 ~4.3: AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:N/A:N).
- **Categoría:** OWASP API8:2023 — Security Misconfiguration
- **Dónde:** comportamiento por defecto de DRF; solo algunas vistas ponen la cabecera a mano (`apps/documents/dossier_views.py:318`, `storage_views.py:54`, `apps/identity/buyer_portal_views.py:80`, `apps/notifications/views.py:59`; `apps/catalogs/views.py:533` usa `private, no-cache` con ETag).
- **Cómo reproducirlo:** `curl -D - -H "Cookie: <admin>" http://localhost:8010/api/v1/auth/me` (y `/users`, `/applications/{id}`, `/clients/{id}`, `/application-participants/{id}/financial-profile`, `/reports/applications.csv`) → ninguna trae `Cache-Control`; el `Vary` es solo `origin` (sin `Cookie`). Igual en el servidor sin `DEBUG` (8011). ZAP 10049 ("Storable and Cacheable Content") lo marca en el perfil financiero y los participantes.
- **Qué pasa:** respuestas con nombre, documento, ingresos, deudas y datos de contacto se pueden guardar en la caché del navegador (disco) y, si hay un proxy o CDN delante, en una caché compartida: al no variar por `Cookie`, una caché compartida podría servir la respuesta de un usuario a otro con la misma URL.
- **Qué debería pasar:** spec §4, Parte 2.3: `Cache-Control: no-store` en respuestas con datos personales y en las descargas. Las descargas ya lo tienen; el resto de la API no.
- **Impacto:** exposición de datos personales y financieros en equipos compartidos (otro usuario del mismo navegador) o por una caché intermedia mal configurada.
- **Corrección sugerida:** un *middleware* que ponga `Cache-Control: no-store` (y `Vary: Cookie`) en toda respuesta de `/api/v1/` que no traiga ya un `Cache-Control` propio (así los catálogos con ETag conservan `private, no-cache`); una prueba que lo verifique en un listado, un detalle y el CSV.
- **Esfuerzo estimado:** pequeño.
- **Cómo se solucionó (Fase B):**
  1. **Causa:** DRF no pone `Cache-Control`; solo cinco vistas lo ponían a mano.
  2. **Cambio:** `backend/config/middleware.py` (`ApiNoStoreMiddleware`, nuevo) y `backend/config/settings/base.py` (en `MIDDLEWARE`, justo después de `RequestIDMiddleware`). En toda respuesta de `/api/v1/` (también los errores) pone `Cache-Control: no-store` si la vista no trajo uno propio, y agrega `Cookie` a `Vary` siempre. Los catálogos con ETag conservan `private, no-cache` y las descargas, el suyo.
  3. **Verificación:** `backend/tests/security/test_http_responses.py::test_personal_data_responses_are_not_stored` (listado y detalle de clientes, `/auth/me` y detalle de solicitud), `::test_the_reports_csv_is_not_stored`, `::test_errors_are_not_stored_either`, `::test_a_view_with_its_own_cache_control_keeps_it` y `::test_outside_the_api_nothing_changes`. Contra el servidor (**antes** con el código del commit de la Parte 1 y **después** con el de este PR, los dos sin `DEBUG` en el 8011, `_security-work/secb_part2.txt` (script `secb_part2.py`)), en `/auth/me`, `/clients`, `/clients/{id}`, `/applications/{id}` y `/reports/applications.csv`: **antes** sin `Cache-Control` y `Vary: origin`; **después** `Cache-Control: no-store` y `Vary: origin, Cookie`. El catálogo `municipality`: `private, no-cache` antes y después, ahora con `Vary: origin, Cookie`.
  4. **PR:** Fase B (este PR).
  5. **Estado:** corregido.

### SEC-09 — El límite de login y de recuperación se salta con otros correos o con otras IP
- **Severidad:** Media (límite de consumo que se salta; CVSS 3.1 ~5.3: AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N).
- **Categoría:** OWASP API2:2023 — Broken Authentication
- **Dónde:** `apps/identity/throttling.py`, `AuthRateThrottle.get_cache_key` (clave única `IP|correo`), usada por `LoginRateThrottle` y `PasswordResetRequestRateThrottle`. No hay límite por IP sobre todos los correos, ni por cuenta sobre todas las IP, ni demora progresiva.
- **Cómo reproducirlo (8010, `_security-work/scripts/rate_limits.py`):**
  - **rociado:** desde una IP, una contraseña contra 12 correos distintos → 12 × `401`, ningún `429`;
  - **una cuenta desde varias IP:** desde `172.20.0.5`, 5 × `401` y luego `429`; desde `172.20.0.6`, otros 5 × `401` y luego `429`; desde una tercera IP, la contraseña correcta → `200`. Cada IP nueva da 5 intentos más por cada 15 minutos;
  - **recuperación:** 6 correos distintos desde la misma IP → 6 × `202` (3 por correo e IP: con varias IP, una víctima recibe correos sin límite).
- **Qué pasa:** el número de intentos por cuenta crece con el número de IP del atacante, y desde una sola IP no hay tope si se cambia de correo.
- **Qué debería pasar:** REQ §9.3: "Login, recuperación y otros flujos sensibles requieren protección reforzada contra fuerza bruta y *credential stuffing*" y "demora progresiva" en el login. La clave "IP + correo" de API §26 se cumple, pero sola no alcanza.
- **Lo que sí funciona (probado):** el límite por IP + correo (`5/15m`, `3/1h`) con `Retry-After`; no se salta con mayúsculas, espacios, `X-Forwarded-For`, `X-Real-IP` ni otro `User-Agent`; el `429` y el `401` son iguales para un correo existente y uno inexistente.
- **Impacto:** *credential stuffing* y rociado de contraseñas contra todas las cuentas internas desde una sola máquina; fuerza bruta distribuida contra una cuenta concreta (por ejemplo, la del administrador); bombardeo de correos de recuperación a una persona.
- **Corrección sugerida:** sumar a la vista dos *throttles* más, con la misma caché: uno por IP sobre todos los correos (por ejemplo `20/15m` en login, `10/1h` en recuperación) y uno por correo sobre todas las IP (por ejemplo `10/15m` y `5/1h`); opcional, una demora progresiva por cuenta después del tercer fallo. Pruebas en `tests/security/` para los tres casos de arriba.
- **Esfuerzo estimado:** pequeño.
- **Cómo se solucionó (Fase B):**
  1. **Causa:** el único límite tenía la clave "IP + correo": cambiar de correo o de IP daba un cupo nuevo.
  2. **Cambio:** `backend/apps/identity/throttling.py` (cuatro límites nuevos con la misma caché: `LoginIPRateThrottle`, `LoginAccountRateThrottle`, `PasswordResetRequestIPRateThrottle` y `PasswordResetRequestAccountRateThrottle`; la clave guarda el correo con SHA-256, nunca en claro); `backend/apps/identity/views.py` (login y recuperación suman los dos nuevos al de IP + correo, que se queda); `backend/config/settings/base.py` (`AUTH_RATE_LIMITS`: `login_ip` `20/15m`, `login_account` `10/15m`, `password_reset_request_ip` `10/1h`, `password_reset_request_account` `5/1h`; los afecta `AUTH_RATE_LIMIT_MULTIPLIER` como a los demás). El `429` es el mismo para un correo que existe y uno que no.
     **Decisión:** sin demora progresiva con `sleep` (bloquearía los workers). El control "progresivo" de REQ §9.3 es el límite por cuenta: 10 fallos en 15 minutos, vengan de las IP que vengan, y la cuenta no acepta más intentos (ni la contraseña correcta) hasta que pase la ventana.
  3. **Verificación:** `backend/tests/security/test_rate_limits.py::test_password_spraying_from_one_ip_is_limited`, `::test_one_account_from_many_ips_is_limited`, `::test_reset_requests_to_many_emails_from_one_ip_are_limited`, `::test_reset_requests_to_one_email_from_many_ips_are_limited` y `::test_login_rates_are_the_agreed_ones`. Contra el 8010 con `_security-work/scripts/secb_part1.py` (una IP fija por contenedor con `--ip`): **antes** (Fase A) rociado de 12 correos → 12 × `401`, ningún `429`; la misma cuenta sumaba 5 intentos por cada IP nueva y la contraseña correcta entraba desde la tercera; recuperación a 6 correos → 6 × `202`. **Después:** rociado de 22 correos → 20 × `401` y `429` desde el 21.º (`Retry-After: 897`), también para la contraseña correcta de otra cuenta desde esa IP; `asesor.andres` desde 3 IP (4 + 4 + 2 fallos) → `429` en el 11.º y con la contraseña correcta desde una cuarta IP; recuperación a 12 correos desde una IP → 10 × `202` y `429`; la de `asesora.lucia` desde 3 IP → 5 × `202` y `429`.
  4. **PR:** Fase B (este PR).
  5. **Estado:** corregido. **Riesgo residual:** quien conozca el correo de una cuenta puede dejarla 15 minutos sin poder entrar (10 fallos desde cualquier lado). Se acepta: es el costo de cortar la fuerza bruta distribuida, y la recuperación de contraseña sigue disponible.

### SEC-10 — No existen los límites generales por usuario que piden REQ §9.3 y API §26
- **Severidad:** Media (límites de consumo que faltan).
- **Categoría:** OWASP API4:2023 — Unrestricted Resource Consumption
- **Dónde:** `backend/config/settings/base.py`, `REST_FRAMEWORK`: no hay `DEFAULT_THROTTLE_CLASSES` ni `DEFAULT_THROTTLE_RATES`. Solo tienen límite las vistas de `AUTH_RATE_LIMITS` (login, recuperación, enlace del comprador, cargas, descargas y reportes).
- **Cómo reproducirlo:** como `asesora.lucia`, 150 `POST /api/v1/clients` en 4 s → 150 × `400`, ningún `429`; 650 `GET /api/v1/clients` en 33 s → 650 × `200`. El ZAP activo hizo ~72 000 peticiones como admin en 16 minutos (unas 75 por segundo).
- **Qué pasa:** un usuario con sesión (o una sesión robada) puede escribir, cambiar estados y crear radicaciones sin tope.
- **Qué debería pasar:** REQ §9.3 y API §26: 120 escrituras por minuto, 600 lecturas por minuto, 20 cambios de estado o radicaciones por minuto, por usuario.
- **Impacto:** abuso de recursos (base de datos, almacenamiento, correo) por un usuario interno o con una sesión robada; automatización masiva de cambios sin freno.
- **Corrección sugerida:** `DEFAULT_THROTTLE_CLASSES` con dos *throttles* por usuario o sesión de comprador (lecturas y escrituras, según el método) y uno de alcance propio (`ScopedRateThrottle`) en `status-transitions`, `filings` y `withdrawals`, todos en la caché compartida; tasas en `AUTH_RATE_LIMITS` para poder ajustarlas.
- **Esfuerzo estimado:** pequeño.
- **Cómo se solucionó (Fase B):**
  1. **Causa:** `REST_FRAMEWORK` no tenía `DEFAULT_THROTTLE_CLASSES`; solo los flujos de `AUTH_RATE_LIMITS` tenían límite.
  2. **Cambio:** `backend/apps/identity/throttling.py` (`GeneralReadRateThrottle` para `GET`, `HEAD` y `OPTIONS`; `GeneralWriteRateThrottle` para el resto; `ScopedUserRateThrottle`, que solo actúa en las vistas con `throttle_scope`; los tres por usuario interno, por sesión del comprador o, sin sesión, por IP, en la lista `GENERAL_THROTTLES`); `backend/config/settings/base.py` (`DEFAULT_THROTTLE_CLASSES` y, en `AUTH_RATE_LIMITS` con el multiplicador, `general_read` `600/1m`, `general_write` `120/1m` y `state_changes` `20/1m`); las vistas con límites propios los suman a los generales (`throttle_classes = [*GENERAL_THROTTLES, ...]`) en `backend/apps/identity/views.py`, `invitation_views.py`, `buyer_access_views.py`, `buyer_portal_views.py`, `backend/apps/documents/buyer_views.py`, `dossier_views.py`, `package_views.py`, `backend/apps/filings/views.py`, `backend/apps/reporting/views.py` y `export_views.py`; `throttle_scope = "state_changes"` (un cupo común) en cambios de estado y desistimientos (`backend/apps/applications/views.py`), radicaciones (`backend/apps/filings/views.py`) y transiciones de oportunidad (`backend/apps/crm/views.py`). En las pruebas, `backend/config/settings/test.py` sube las tasas generales ×1000 y solo las pruebas de límites vuelven a las reales; `backend/tests/identity/test_database_cache.py` cuenta los contadores nuevos.
  3. **Verificación:** `backend/tests/security/test_rate_limits.py::test_general_rates_are_the_ones_of_the_requirements`, `::test_reads_are_limited_per_user`, `::test_buyer_reads_are_limited_per_session`, `::test_writes_are_limited_per_user`, `::test_writes_without_session_are_limited_per_ip`, `::test_state_changes_share_a_quota_of_twenty_per_minute`, `::test_every_api_view_keeps_the_general_limits` y `::test_state_change_views_declare_the_shared_scope`. Contra el 8010 (`secb_part1.py`, como `asesora.lucia`): **antes** (Fase A) 150 `POST /api/v1/clients` → 150 × `400` y 650 `GET /api/v1/clients` → 650 × `200`; **después** 130 `POST` → 120 × `400` y 10 × `429` (el primero en el 121.º, `Retry-After: 56`, «Hiciste demasiados intentos. Vuelve a intentarlo en 56 segundos.»), 610 `GET` → 600 × `200` y 10 × `429`, y 22 cambios de estado, desistimientos y radicaciones → 20 × `400` y `429` desde el 21.º, mientras las demás escrituras siguen.
  4. **PR:** Fase B (este PR).
  5. **Estado:** corregido.

### SEC-11 — Un JSON de más de 2,5 MB responde 500 (sin `DEBUG`) o la página de depuración (con `DEBUG`), no 413
- **Severidad:** Baja (el límite de tamaño sí corta; el problema es la respuesta). Con `DEBUG` la página de depuración es Informativa: solo pasa en local.
- **Categoría:** OWASP API8:2023 — Security Misconfiguration
- **Dónde:** `backend/config/exceptions.py`, `api_exception_handler`: `RequestDataTooBig` (de `DATA_UPLOAD_MAX_MEMORY_SIZE`, 2,5 MB por defecto) no es una excepción de DRF, así que el manejador devuelve `None` y termina en el 500 genérico.
- **Cómo reproducirlo:** `POST /api/v1/auth/login` (sin sesión) o `POST /api/v1/clients` (con sesión) con un JSON de 5 MB → en el 8011 (sin `DEBUG`) `500 INTERNAL_ERROR` y un "Error no controlado en la API" en el log por cada petición; en el 8010 (`DEBUG`) `400` con la página HTML de depuración (traza, rutas de `/app/` y `/usr/local`).
- **Qué pasa:** un cuerpo demasiado grande se trata como un error del servidor.
- **Qué debería pasar:** `413` con el formato de error de la API (como ya hacen las cargas de documentos con `PAYLOAD_TOO_LARGE`).
- **Impacto:** cualquiera, sin cuenta, genera errores no controlados en el log a voluntad; las métricas de 5xx dejan de servir para detectar fallas reales.
- **Corrección sugerida:** en `api_exception_handler`, convertir `RequestDataTooBig` en `413 PAYLOAD_TOO_LARGE` antes de llamar al manejador de DRF; una prueba con un cuerpo de 3 MB.
- **Esfuerzo estimado:** pequeño.
- **Cómo se solucionó (Fase B):**
  1. **Causa:** `RequestDataTooBig` no es una excepción de DRF: el manejador de errores devolvía `None` y terminaba en el 500 genérico.
  2. **Cambio:** `backend/config/exceptions.py` (`PayloadTooLarge`, nuevo `ApiError` con `413` y código `PAYLOAD_TOO_LARGE`; `api_exception_handler` convierte `RequestDataTooBig` antes de llamar al de DRF). El texto: «El cuerpo de la solicitud es demasiado grande.».
  3. **Verificación:** `backend/tests/security/test_http_responses.py::test_a_large_body_without_session_is_413` (login) y `::test_a_large_body_with_session_is_413` (`POST /clients`), con 3 MB. Contra el servidor (**antes** con el código del commit de la Parte 1 y **después** con el de este PR, los dos sin `DEBUG` en el 8011, `_security-work/secb_part2.txt` (script `secb_part2.py`)): **antes** `500 INTERNAL_ERROR` en los dos casos; **después** `413 PAYLOAD_TOO_LARGE`, con el formato de la API.
  4. **PR:** Fase B (este PR).
  5. **Estado:** corregido.

### SEC-12 — Las rutas inexistentes y los ids que no son UUID responden HTML de Django, no el formato de error de la API
- **Severidad:** Baja (mensajes; sin fuga fuera de `DEBUG`).
- **Categoría:** OWASP API8:2023 — Security Misconfiguration
- **Dónde:** `backend/config/urls.py`: no define `handler404` ni `handler500`. Las rutas usan `<uuid:…>`, así que un id mal formado no llega a DRF.
- **Cómo reproducirlo:** `GET /api/v1/no-existe` o `GET /api/v1/applications/abc` → `404` con `text/html` (en el 8011, la página "Not Found" de Django de 179 bytes; en el 8010, la página de depuración con la lista completa de rutas). schemathesis `ST105` y ZAP 100001 lo marcan en 13 operaciones.
- **Qué pasa:** el cliente recibe HTML donde espera `{code, message, details, request_id}`; con `DEBUG`, la página enumera todas las rutas de la API.
- **Qué debería pasar:** API §5.3: toda respuesta de error tiene el formato común.
- **Impacto:** bajo: el frontend no puede mostrar un error coherente y, en local, la página de depuración entrega el inventario de rutas.
- **Corrección sugerida:** `handler404` y `handler500` en `config/urls.py` que respondan JSON con `build_error_body` cuando la ruta empieza por `/api/`.
- **Esfuerzo estimado:** pequeño.
- **Cómo se solucionó (Fase B):**
  1. **Causa:** `config/urls.py` no definía `handler404` ni `handler500`, y una ruta que no resuelve (o un id que no es UUID) no llega a DRF.
  2. **Cambio:** `backend/config/views.py` (`page_not_found` y `server_error`: JSON con `build_error_body` cuando la ruta empieza por `/api/`; fuera, las páginas de Django) y `backend/config/urls.py` (`handler404` y `handler500`). Django solo los usa sin `DEBUG`: con `DEBUG` (solo local) sigue la página de depuración.
  3. **Verificación:** `backend/tests/security/test_http_responses.py::test_unknown_api_routes_answer_the_api_error_format` (`/api/v1/no-existe`, `/api/v1/applications/abc` y `/api/v1/clients/123/addresses`: `404 RESOURCE_NOT_FOUND` con el `request_id`), `::test_unknown_routes_outside_the_api_keep_the_django_page` y los dos de `server_error`. Contra el servidor (**antes** con el código del commit de la Parte 1 y **después** con el de este PR, los dos sin `DEBUG` en el 8011, `_security-work/secb_part2.txt` (script `secb_part2.py`)): **antes** `/api/v1/no-existe` y `/api/v1/applications/abc` → `404 text/html`; **después** → `404 application/json` con `RESOURCE_NOT_FOUND`; `/no-existe` (fuera de la API) sigue en HTML.
  4. **PR:** Fase B (este PR).
  5. **Estado:** corregido.

### SEC-13 — El contrato no coincide con la API en 2 respuestas y no documenta varios estados
- **Severidad:** Informativa (inventario; no expone datos).
- **Categoría:** OWASP API9:2023 — Improper Inventory Management
- **Dónde:** `contracts/openapi.json` frente a las vistas.
- **Cómo reproducirlo:** schemathesis (`ST108`, `ST103`, `ST203`):
  - `GET /applications/{id}/available-actions` devuelve una lista y el contrato dice `PaginatedAvailableActionList`;
  - `GET /clients` como broker devuelve `document_type: "CC"` (texto) y el contrato dice `CatalogItemRef` (objeto);
  - 400 de reglas de negocio y 404 sin documentar en ~66 operaciones; `428 PRECONDITION_REQUIRED` (sin `If-Match`) sin documentar en 6.
- **Qué pasa:** el contrato describe de menos o distinto lo que la API hace.
- **Qué debería pasar:** el contrato es la fuente de verdad del frontend y de las pruebas (`schema.d.ts`).
- **Impacto:** herramientas que validan contra el contrato (incluido el propio frontend tipado) no detectan cambios reales; dificulta auditar qué expone cada rol.
- **Corrección sugerida:** corregir los dos serializers o su `extend_schema`, y documentar `400`/`404`/`428` donde aplican; regenerar `schema.d.ts`.
- **Esfuerzo estimado:** pequeño.

### SEC-14 — La recuperación de contraseña revela si el correo existe cuando falla el envío
- **Severidad:** Media (enumeración de usuarios; CVSS 3.1 ~5.3: AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N).
- **Categoría:** OWASP API2:2023 — Broken Authentication
- **Dónde:** `backend/apps/identity/services.py`, `request_password_reset` (`transaction.on_commit(lambda: send_password_reset_email(...))`, solo si el usuario existe) y `backend/apps/identity/emails.py`, `send_password_reset_email` (`send_mail` síncrono, sin manejo de errores; el propio docstring dice "por ahora el envío es síncrono").
- **Cómo reproducirlo:** prueba `tests/security/test_auth.py::test_reset_request_answers_the_same_when_the_mail_fails` (xfail SEC-14): con un backend de correo que falla, `POST /api/v1/auth/password-reset-requests` responde `202` para un correo que no existe y **500** para uno que existe. Medido en el 8010 (correo a la consola): mediana de 42 ms con correo existente frente a 28 ms con inexistente (+14 ms, bajo el umbral de la spec); con SMTP real la diferencia es el tiempo de envío del correo.
- **Qué pasa:** el correo sale dentro de la misma petición. Si el SMTP está caído o lento, la respuesta (500 o segundos de más) solo cambia cuando el usuario existe.
- **Qué debería pasar:** REQ §9.3: "respuesta uniforme". La misma respuesta y el mismo tiempo exista o no el correo, y un fallo del correo no debe llegar a la respuesta (API §21: "sus fallos no revierten la operación principal").
- **Impacto:** un atacante sin cuenta confirma qué correos son de usuarios internos (insumo para *phishing* y para SEC-09), sobre todo en una caída del SMTP.
- **Corrección sugerida:** mandar el correo por la cola de notificaciones (Celery, como `apps/notifications`), o al menos envolver el envío en `try/except` con log y hacerlo fuera de la petición. Quitar la marca `xfail` de la prueba.
- **Esfuerzo estimado:** pequeño.
- **Cómo se solucionó (Fase B):**
  1. **Causa:** el correo salía con `send_mail` síncrono dentro de la petición, y solo cuando el usuario existía.
  2. **Cambio:** `backend/apps/identity/tasks.py` (nuevo: tareas de Celery `send_password_reset` y `send_invitation`, que registran el fallo en el log sin el correo y no lo propagan); `backend/apps/identity/services.py` (`request_password_reset` solo encola después del commit, exista o no el correo; la búsqueda del usuario, el token y el envío pasan a `issue_password_reset`, que corre en el worker); `backend/apps/identity/invitations.py` (las invitaciones también eran síncronas: ahora el worker genera su token con `issue_invitation_token` y envía el correo); `backend/apps/identity/emails.py` (documentación). El token en claro se genera en el worker: nunca pasa por el broker. La respuesta sigue siendo `202` con el mismo cuerpo.
  3. **Verificación:** `backend/tests/security/test_auth.py::test_reset_request_answers_the_same_when_the_mail_fails` (ya sin `xfail`), `::test_a_failed_reset_mail_is_logged_without_the_address`, `::test_reset_request_does_the_same_work_whether_the_email_exists` y `::test_an_invitation_answers_the_same_when_the_mail_fails`; `backend/tests/identity/test_passwords.py` y `test_invitations.py` siguen verdes. Contra el 8010 con un worker de Celery y Redis propios (`secb_part1.py reset_timing`, 20 pares desde 4 IP): **antes** (Fase A) +14 ms de mediana con un correo que existe, y `500` con el SMTP caído; **después** `202` en los 40 casos, mediana 50,0 ms con correo existente y 45,9 ms con uno que no (+4,1 ms, dentro del ruido).
  4. **PR:** Fase B (este PR).
  5. **Estado:** corregido. **Riesgo residual:** en el modo local simple (`CELERY_TASK_ALWAYS_EAGER=true`) la tarea corre en el mismo proceso: el error sigue sin llegar a la respuesta, pero el tiempo del envío sí se suma cuando el correo existe. Producción usa el worker. El enlace del comprador (`send_buyer_access_email`) sigue síncrono: lo emite un asesor con sesión y no revela cuentas.

### SEC-15 — El log de peticiones guarda la búsqueda completa (documento o nombre)
- **Severidad:** Baja (datos personales en logs operativos).
- **Categoría:** OWASP API8:2023 — Security Misconfiguration (REQ RNF-16)
- **Dónde:** el log de acceso (`django.server` con `runserver`; con gunicorn, su *access log*) escribe la URL con la consulta; `backend/config/log_redaction.py` solo oculta el token de las URL firmadas.
- **Cómo reproducirlo:** `GET /api/v1/clients?search=9900000013` y `GET /api/v1/applications?search=laura` en el 8010 → `docker logs mvp-sec-api` muestra la línea con el número de documento completo y el nombre. Prueba `tests/security/test_exposure.py::test_search_terms_are_not_written_to_the_access_log` (xfail SEC-15).
- **Qué pasa:** cada búsqueda del backoffice deja en el log el documento, el nombre o el correo que se buscó.
- **Qué debería pasar:** RNF-16: "los logs estructurados incluyen ese ID sin contener secretos ni PII sensible completa".
- **Impacto:** quien lee los logs (operación, un proveedor de logs) ve datos personales; los logs suelen guardarse más tiempo y con menos control que la base.
- **Corrección sugerida:** extender el filtro de `config/log_redaction.py` para reemplazar el valor de `search` (y de `email`, `document_number`) por `***` en cualquier mensaje; en producción, un formato de *access log* de gunicorn sin la consulta.
- **Esfuerzo estimado:** pequeño.
- **Cómo se solucionó (Fase B):**
  1. **Causa:** el filtro de `config/log_redaction.py` solo ocultaba el token de las URL firmadas; la consulta se escribía entera.
  2. **Cambio:** `backend/config/log_redaction.py` (`redact()`): el mismo filtro (`RedactObjectTokensFilter`, ya conectado al handler de consola) reemplaza por `***` el valor de `search`, `email`, `document_number` y `q` (sin distinguir mayúsculas) en la consulta de cualquier mensaje de log. Los demás parámetros (`status`, `page`…) se conservan.
  3. **Verificación:** `backend/tests/security/test_exposure.py::test_search_terms_are_not_written_to_the_access_log` (ya sin `xfail`), `::test_other_personal_query_values_are_redacted` (4 casos), `::test_other_query_values_are_kept` y `::test_any_log_message_is_redacted`. En el 8010: **antes** (Fase A) `docker logs` mostraba `?search=9900000013`; **después** `"GET /api/v1/clients?search=*** HTTP/1.1" 200`, `"GET /api/v1/applications?search=***&page=1 …"` y `"GET /api/v1/users?email=*** …" 403`.
  4. **PR:** Fase B (este PR).
  5. **Estado:** corregido. El *access log* de gunicorn no pasa por este filtro: la imagen de producción (Parte 3 de esta fase) no lo activa; los logs de Django, filtrados, siguen registrando las peticiones con error.

### SEC-16 — Un `409` al crear un cliente confirma que esa cédula ya está registrada
- **Severidad:** Baja (existencia de una persona en el CRM; documentado en API §13). Sube a Media mientras no exista SEC-10 (sin límite general, se puede probar a escala).
- **Categoría:** OWASP API3:2023 — Broken Object Property Level Authorization
- **Dónde:** `backend/apps/crm/services.py`, `create_client` y `_duplicate_client_error` (también la creación de participantes con el bloque de identidad).
- **Cómo reproducirlo:** como `broker.b`, `POST /api/v1/clients` con el tipo y número de documento de un cliente del lado A → `409 DUPLICATE_CLIENT_DOCUMENT`. La respuesta no trae el `resource_id` ni datos del otro cliente (bien: `tests/security/test_exposure.py::test_duplicate_document_never_reveals_the_other_client`), pero el código de estado confirma que esa persona ya es cliente. Prueba `test_a_broker_cannot_tell_whether_a_document_is_already_registered` (xfail SEC-16).
- **Qué pasa:** cualquiera con `clients.create` (también un broker independiente, que es externo) puede saber si una cédula está en la base, aunque el cliente sea de otro broker o asesor.
- **Qué debería pasar:** REQ §3: el broker solo ve lo que originó. Saber que un tercero ya es cliente es información de otro alcance.
- **Impacto:** fuga de que una persona tramita (o tramitó) un crédito con la empresa; competencia entre brokers por el mismo cliente.
- **Corrección sugerida:** decisión de producto. Opciones: para un actor que no ve al cliente, crear una solicitud de "cliente ya existente" que revise un asesor en lugar del 409 directo; o aceptar el riesgo y dejarlo en `docs/SEGURIDAD.md` con el límite de SEC-10 como mitigación.
- **Esfuerzo estimado:** mediano (si se cambia el flujo); pequeño (si se acepta).

### SEC-17 — Textos de la configuración de bancos sin longitud máxima
- **Severidad:** Informativa (solo el administrador los escribe).
- **Categoría:** OWASP API4:2023 — Unrestricted Resource Consumption
- **Dónde:** `backend/apps/banking/serializers.py`, `operational_notes` (líneas 87 y 99), sin `max_length`.
- **Cómo reproducirlo:** como admin, `POST /api/v1/banks` con `operational_notes` de 1 MB → `201`. Prueba `tests/security/test_resources.py::test_bank_operational_notes_have_a_maximum_length` (xfail SEC-17). En cambio, todos los textos libres que escriben asesores, brokers y compradores tienen tope (`test_free_text_fields_have_a_maximum_length`, 9 casos).
- **Qué pasa:** un texto de hasta el tamaño máximo del cuerpo (2,5 MB) queda guardado y viaja en cada lectura de `/banks`.
- **Qué debería pasar:** como el resto de la API, una longitud máxima razonable.
- **Impacto:** bajo: respuestas pesadas para los asesores que listan bancos, por un error o una sesión de admin robada.
- **Corrección sugerida:** `max_length=4000` en los dos campos (una línea cada uno).
- **Esfuerzo estimado:** pequeño.
- **Cómo se solucionó (Fase B):**
  1. **Causa:** los dos `operational_notes` de `apps/banking/serializers.py` no tenían `max_length`.
  2. **Cambio:** `backend/apps/banking/serializers.py` (`max_length=4000` al crear y al editar); el contrato gana `maxLength: 4000` en esos dos campos (`contracts/openapi.json`; `schema.d.ts` no cambia).
  3. **Verificación:** `backend/tests/security/test_resources.py::test_bank_operational_notes_have_a_maximum_length` (ya sin `xfail`) y `::test_bank_operational_notes_are_capped_on_update_too`. Contra el servidor (**antes** con el código del commit de la Parte 1 y **después** con el de este PR, los dos sin `DEBUG` en el 8011, `_security-work/secb_part2.txt` (script `secb_part2.py`)): `POST /banks` con 100 000 caracteres → **antes** `201`; **después** `400 VALIDATION_ERROR`.
  4. **PR:** Fase B (este PR).
  5. **Estado:** corregido.

### SEC-18 — `/admin/` de Django está publicado con la API y su login no tiene límite de intentos
- **Severidad:** Baja (hoy no hay usuarios `is_staff`, así que nadie puede entrar).
- **Categoría:** OWASP API8:2023 — Security Misconfiguration
- **Dónde:** `backend/config/urls.py` (`path("admin/", admin.site.urls)`), con 42 modelos registrados (`apps/*/admin.py`).
- **Cómo reproducirlo:** 12 intentos fallidos seguidos en `POST /admin/login/` del 8010 → 12 × 200, ninguno frenado. Prueba `tests/security/test_config_inventory.py::test_django_admin_login_is_rate_limited` (xfail SEC-18). `User.objects.filter(is_staff=True).count()` → 0.
- **Qué pasa:** el admin usa su propio login (sesión de Django, sin los límites de `AUTH_RATE_LIMITS`) y edita los modelos directamente, sin los servicios del dominio ni la auditoría funcional.
- **Qué debería pasar:** en producción, sin admin en el host público, o detrás de una red privada o de un límite de intentos.
- **Impacto:** si alguien crea un usuario `is_staff` (por ejemplo con `createsuperuser`), su contraseña queda expuesta a fuerza bruta sin límite y quien entre salta todas las reglas de negocio.
- **Corrección sugerida:** montar `admin/` solo con `DEBUG` o con una variable (`ADMIN_ENABLED`), en una ruta no obvia, y con un límite de intentos si se publica.
- **Esfuerzo estimado:** pequeño.
- **Cómo se solucionó (Fase B):**
  1. **Causa:** `config/urls.py` montaba `admin/` siempre, y su login no pasaba por ningún límite.
  2. **Cambio:** `backend/config/settings/base.py` (`ADMIN_ENABLED`, por defecto `False`; `ADMIN_URL_PATH`, por defecto `admin/`; tasa `admin_login` `10/15m` en `AUTH_RATE_LIMITS`); `backend/config/urls.py` (el admin solo con `DEBUG` o `ADMIN_ENABLED`, en `ADMIN_URL_PATH`, y su `login/` reemplazado por `config.views.admin_login`); `backend/config/views.py` (`admin_login`: los `POST` pasan por `AdminLoginRateThrottle`, por IP, y al pasar el límite responde `429` con `Retry-After`); `backend/apps/identity/throttling.py` (`AdminLoginRateThrottle`). Con `DEBUG` el admin sigue publicado (desarrollo) y el límite también aplica.
  3. **Verificación:** `backend/tests/security/test_config_inventory.py::test_django_admin_is_not_published_by_default` (`404`), `::test_django_admin_login_is_rate_limited` (ya sin `xfail`: con `ADMIN_ENABLED=True` y `ADMIN_URL_PATH=gestion-interna/`, 10 intentos y el 11.º `429`; otra IP no está afectada) y `::test_the_admin_login_rate_is_the_agreed_one`. Contra el servidor (**antes** con el código del commit de la Parte 1 y **después** con el de este PR, los dos sin `DEBUG` en el 8011, `_security-work/secb_part2.txt` (script `secb_part2.py`)): **antes** `GET /admin/login/` → `200` y 12 intentos fallidos → 12 × `200`; **después**, por defecto, `/admin/login/` → `404` (los 12 → `404`); con `ADMIN_ENABLED=True ADMIN_URL_PATH=gestion-interna/`, `/admin/login/` → `404`, `/gestion-interna/login/` → `200` y los 12 intentos → 10 × `200` y 2 × `429`.
  4. **PR:** Fase B (este PR).
  5. **Estado:** corregido.

### SEC-19 — El esquema OpenAPI y la documentación interactiva son públicos
- **Severidad:** Informativa.
- **Categoría:** OWASP API9:2023 — Improper Inventory Management
- **Dónde:** `backend/config/urls.py` (`/openapi.json` y `/docs`), sin autenticación también con `DEBUG=False` (servidor 8011 de la Parte 2).
- **Cómo reproducirlo:** `GET /openapi.json` y `GET /docs` sin sesión → 200. Prueba `tests/security/test_config_inventory.py::test_api_schema_and_docs_need_a_session` (xfail SEC-19).
- **Qué pasa:** cualquiera obtiene el mapa completo de la API: rutas, parámetros, códigos de error y nombres de permisos.
- **Qué debería pasar:** en producción, el esquema solo para usuarios internos (o no publicado); el frontend usa `contracts/openapi.json` del repo.
- **Impacto:** acelera el reconocimiento de un atacante; no expone datos por sí solo.
- **Corrección sugerida:** publicar `/openapi.json` y `/docs` solo con `DEBUG` (o con `IsAdminUser`), en `config/urls.py`.
- **Esfuerzo estimado:** pequeño.
- **Cómo se solucionó (Fase B):**
  1. **Causa:** `config/urls.py` publicaba `/openapi.json` y `/docs` siempre, sin sesión.
  2. **Cambio:** `backend/config/settings/base.py` (`API_DOCS_PUBLIC`, por defecto `False`) y `backend/config/urls.py` (las dos rutas solo con `DEBUG` o `API_DOCS_PUBLIC`). El frontend y la referencia publicada usan `contracts/openapi.json` del repo, que el CI genera con `manage.py spectacular`: no cambian.
  3. **Verificación:** `backend/tests/security/test_config_inventory.py::test_api_schema_and_docs_need_a_session` (ya sin `xfail`: `404`) y `::test_api_schema_and_docs_can_be_published_on_purpose` (`200` con `API_DOCS_PUBLIC=True`); `backend/tests/test_platform.py::test_openapi_schema_documents_auth` enciende la variable. Contra el servidor (**antes** con el código del commit de la Parte 1 y **después** con el de este PR, los dos sin `DEBUG` en el 8011, `_security-work/secb_part2.txt` (script `secb_part2.py`)): **antes** `/openapi.json` y `/docs` → `200`; **después** → `404`, y `200` con `API_DOCS_PUBLIC=True`.
  4. **PR:** Fase B (este PR).
  5. **Estado:** corregido.

### SEC-20 — La documentación de la API promete 9 rutas que no existen y omite 5 que sí
- **Severidad:** Informativa.
- **Categoría:** OWASP API9:2023 — Improper Inventory Management
- **Dónde:** `docs/API_REST_MVP_CREDITO.md` frente al contrato y a `config/urls.py` (que sí coinciden entre sí: `test_every_api_route_is_in_the_contract_and_back`).
- **Cómo reproducirlo:** prueba `tests/security/test_config_inventory.py::test_every_documented_route_exists` (xfail SEC-20). Documentadas y no implementadas: `GET /clients/{id}/activity`, `POST /clients/{id}/notes`, `GET /opportunities/{id}/activity`, `POST /opportunities/{id}/notes`, `GET /projects/{id}/summary`, `GET /metadata/form-schemas/{form_code}`, `GET /reports/advisors`, `GET /reports/banks`, `GET /reports/document-quality`. Implementadas y sin documentar en ninguna parte: las 5 de direcciones del cliente (`GET`/`POST /clients/{id}/addresses`, `PATCH`/`DELETE /client-addresses/{id}`); las del portal del comprador para perfil, ingresos, inmueble y financiación solo aparecen en el texto, no en las tablas.
- **Qué pasa:** quien audite o integre con la documentación espera permisos y rutas que no existen, y no ve rutas que sí reciben datos personales.
- **Qué debería pasar:** documentación, contrato y código con el mismo inventario.
- **Impacto:** las rutas sin documentar no pasan por las revisiones de acceso basadas en la documentación (aquí sí: la matriz se arma desde el contrato).
- **Corrección sugerida:** marcar las 9 como "fuera del MVP" o quitarlas de la tabla; agregar las 5 de direcciones con su permiso y alcance.
- **Esfuerzo estimado:** pequeño.
