# Hallazgos de la auditoría de seguridad (Fase A)

Lista viva: cada parte de la auditoría agrega los suyos. Formato y escala de severidad en
`specs/TAREA-seguridad.md` §5. Ningún hallazgo incluye secretos, tokens ni URL firmadas: si
uno expone un valor, se describe y se corta.

| Id | Título | Severidad | OWASP API Top 10 (2023) | Estado | Parte |
| --- | --- | --- | --- | --- | --- |
| [SEC-01](#sec-01--no-hay-configuración-de-producción-y-los-puntos-de-entrada-cargan-local-que-fuerza-debugtrue) | No hay configuración de producción y los puntos de entrada cargan `local`, que fuerza `DEBUG=True` | Baja | API8 | abierto | 1 |
| [SEC-02](#sec-02--la-configuración-base-no-endurece-https) | La configuración base no endurece HTTPS | Baja | API8 | abierto | 1 |
| [SEC-03](#sec-03--las-claves-no-se-validan-al-arrancar-la-clave-jwt-local-tiene-31-bytes) | Las claves no se validan al arrancar; la clave JWT local tiene 31 bytes | Baja | API8 | abierto | 1 |
| [SEC-04](#sec-04--djangorestframework-3172-tiene-dos-cve-de-denegación-de-servicio-sin-sesión) | `djangorestframework` 3.17.2 tiene dos CVE de denegación de servicio sin sesión | Media | API4 | abierto | 1 |
| [SEC-05](#sec-05--el-compose-publica-postgresql-y-el-backend-en-todas-las-interfaces-del-equipo) | El compose publica PostgreSQL y el backend en todas las interfaces del equipo | Baja | API8 | abierto | 1 |
| [SEC-06](#sec-06--imagen-del-backend-base-sin-digest-pip-sin-versión-y-runserver-como-comando) | Imagen del backend: base sin digest, `pip` sin versión y `runserver` como comando | Informativa | API8 | abierto | 1 |

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
- **Nota para la Parte 5:** hoy `pip-audit` haría fallar el CI por esto. Va en la configuración de `pip-audit` con `# SEC-04` hasta que la Fase B suba la versión.

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
- **Cómo reproducirlo:** `hadolint` 2.15.1 → `DL3013` (línea 11, `pip install --upgrade pip` sin versión). Revisión manual: `FROM python:3.11-slim` sin `@sha256:`; `CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]`; `COPY . ./` deja `tests/`, `scripts/` y `docker-compose.yml` dentro de la imagen.
- **Qué pasa:** dos construcciones de la misma versión del código pueden dar imágenes distintas (la base y `pip` cambian solas), y la imagen arranca con el servidor de desarrollo de Django.
- **Qué debería pasar:** imagen reproducible y servidor de aplicación (`gunicorn`, ya en `requirements.txt`) en la imagen de producción.
- **Lo que ya está bien (verificado):** usuario no root (`id` en el contenedor → `uid=100(app) gid=101(app)`, también en `mvp-sec-api`); sin `.env` en la imagen (`.dockerignore` lo excluye; `test -e /app/.env` → no existe); sin secretos en `ENV` ni en las capas (`docker image inspect` y `docker history`: el único `GPG_KEY` es el id público de la clave de firma de Python); `/data/documents` con dueño `app` y modo `755`.
- **Corrección sugerida:** `FROM python:3.11-slim@sha256:<digest>`, `pip install pip==<versión>`, una etapa o `CMD` de producción con `gunicorn config.wsgi` (junto con SEC-01), y excluir `tests/` del contexto de la imagen de producción.
- **Esfuerzo estimado:** pequeño.
