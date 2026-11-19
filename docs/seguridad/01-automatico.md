# Auditoría de seguridad — Parte 1: análisis automático

Código, dependencias, secretos y contenedor del backend (y, solo para informar, las
dependencias del frontend). Todo corrió en local, en contenedores de un solo uso, el
2026-11-18, sobre la rama `chore/security-audit` (desde `master` en `2a567bd`, con los 16
módulos). Los reportes crudos quedaron fuera del repo, en `_security-work/`.

Los hallazgos están en [`hallazgos.md`](hallazgos.md). Esta parte abre **6**: 1 Media, 4
Bajas y 1 Informativa. Ninguna herramienta encontró nada de severidad Alta o Crítica.

## Resumen

| # | Herramienta | Versión | Resultados | Hallazgos | Descartados |
| --- | --- | --- | --- | --- | --- |
| 1 | `manage.py check --deploy` | Django 5.2.19 | 4 avisos con `base` (6 con `local`) | SEC-01, SEC-02, SEC-03 | 0 |
| 2 | bandit | 1.9.4 | 41 (0 altos, 0 medios, 41 bajos) | 0 | 41 |
| 3 | pip-audit | 2.10.1 | 3 vulnerabilidades en 1 paquete | SEC-04 (2 CVE) | 1 |
| 4 | semgrep | 1.186.0 (188 reglas) | 1 | 0 | 1 |
| 5 | gitleaks | 8.30.1 | 7 (en 40 commits) | 0 | 7 |
| 6 | hadolint + revisión manual | 2.15.1 | 3 (1 aviso, 2 informativos) | SEC-05, SEC-06 | 2 |
| 7 | `pnpm audit --prod` (frontend) | pnpm 12.18.0 | 0 en 202 dependencias | 0 | 0 |

Imágenes usadas (fijadas por etiqueta; el digest es el que quedó en el equipo):

| Imagen | Digest |
| --- | --- |
| `mvp-credit-backend-backend` (la del compose; Python 3.11.18) | `sha256:fe74fa4e4b05…` |
| `semgrep/semgrep:1.186.0` | `sha256:6e1b04340e60…` |
| `zricethezav/gitleaks:v8.30.1` | `sha256:c00b6bd0aeb3…` |
| `hadolint/hadolint:v2.15.1` | `sha256:32dac94127fd…` |
| `node:24-alpine` (Node 24.22.2) | `sha256:a34ab6d7f6f4…` |

Variables de los comandos (como en la spec): `WT` = el worktree, `ENV` = el `.env` del
backend de la carpeta principal (solo lo usa Docker), `IMG = mvp-credit-backend-backend`,
`NET = mvp_credit_network`, `SW` = `_security-work`, `MAIN` = la carpeta principal del repo.

---

## 1. Configuración de Django (`check --deploy`)

```
docker run --rm --network NET --env-file ENV -e DATABASE_HOST=postgres -e DATABASE_NAME=mvp_credit_sec \
  -e DJANGO_DEBUG=False -e DJANGO_SETTINGS_MODULE=config.settings.base \
  -e DOCUMENT_STORAGE_BACKEND=s3 -e DOCUMENT_SCANNER=clamd \
  -v WT\backend:/app -w /app IMG python manage.py check --deploy
```

Con solo las dos variables de la spec, la API **se niega a arrancar**:
`ImproperlyConfigured: DOCUMENT_STORAGE_BACKEND=filesystem solo se admite con DEBUG o en pruebas.`
Es un control que funciona bien (`apps/documents/storage.py`, `validate_storage_settings`).
Para poder correr el chequeo se agregaron los valores de producción del almacenamiento y
del antivirus (`s3`, `clamd`); nada se conecta a ellos en un `check`.

**El repo no tiene configuración de producción** (solo `base`, `local` y `test`), y los
cuatro puntos de entrada (`manage.py`, `wsgi.py`, `asgi.py`, `celery.py`) usan `local` por
defecto. `local.py` fija `DEBUG = True`, así que **`DJANGO_DEBUG=False` no tiene efecto** si
no se cambia el módulo de settings. Con `local` y `-e DJANGO_DEBUG=False`, `check --deploy`
da 6 avisos: los 4 de abajo más `W016` (cookie CSRF sin `Secure`) y `W018` (`DEBUG`). → **SEC-01**.

| Aviso (con `base`) | Qué dice | ¿Aplica a producción? | Clasificación |
| --- | --- | --- | --- |
| `security.W004` | `SECURE_HSTS_SECONDS` sin valor | Sí, con HTTPS | hallazgo **SEC-02** |
| `security.W008` | `SECURE_SSL_REDIRECT` no es `True` | Sí, salvo que el proxy redirija (y entonces falta `SECURE_PROXY_SSL_HEADER`) | hallazgo **SEC-02** |
| `security.W009` | `SECRET_KEY` corta o de pocos caracteres distintos | La clave es la del `.env` local (no está en git); en el código falta validar la fortaleza al arrancar | hallazgo **SEC-03** |
| `security.W012` | `SESSION_COOKIE_SECURE` no es `True` | Sí: la sesión de Django la usa `/admin/` | hallazgo **SEC-02** |

Lo que el chequeo **no** marcó con `base`, y está bien: `CSRF_COOKIE_SECURE` y
`AUTH_COOKIE_SECURE` valen `True` por defecto, `X_FRAME_OPTIONS` y
`SECURE_CONTENT_TYPE_NOSNIFF` quedan con los valores seguros de Django, `ALLOWED_HOSTS`
viene del entorno sin comodín por defecto.

Revisión adicional de las claves (solo longitudes, nunca valores): la `AUTH_JWT_SIGNING_KEY`
local tiene **31 bytes**, por debajo de los 32 que pide RFC 7518 §3.2 para HS256; PyJWT 2.15.1
lo avisa en el log del servidor 8010 (`InsecureKeyLengthWarning`) en cada firma y
verificación. Es distinta de `SECRET_KEY`. → **SEC-03**.

## 2. bandit

```
docker run --rm -u root -v WT\backend:/src:ro -v SW:/out -w /src IMG sh -c \
  "pip install bandit==1.9.4 && bandit -r apps config -f json -o /out/bandit.json"
```

37 569 líneas analizadas, 0 `nosec`. **0 altos, 0 medios, 41 bajos.** Se revisaron todos
a mano:

| Regla | Cuántos | Dónde | Clasificación |
| --- | --- | --- | --- |
| `B101` `assert_used` | 33 | `applications`, `audit/sanitize.py`, `banking/rule_engine.py`, `catalogs/fields.py`, `crm`, `documents`, `filings`, `identity/throttling.py`, `identity/users.py`, `notifications/emails.py`, `reporting`, `tasks`, `config/api.py`, `config/exceptions.py` | descartado: todos son *narrowing* de tipos para mypy o invariantes que ya garantiza el serializer o la consulta anterior. Ninguno decide autorización, alcance, validación de entrada ni límites: con `python -O` no se abre ningún control. |
| `B105` `hardcoded_password_string` | 7 | `base.py:236-238` (tasas `"5/15m"` de `AUTH_RATE_LIMITS`), `identity/tokens.py:21` (`JWT_ALGORITHM = "HS256"`), `identity/views.py:39` (mensaje de restablecimiento), `documents/storage.py:54` (sal de la firma de URL, no es una clave), `applications/demo_data.py:61` (`DEMO_PASSWORD`, la de demo publicada) | descartado: ninguno es una credencial. La contraseña de demo solo sirve con `DEBUG` (`seed_demo_data` lo exige). |
| `B106` `hardcoded_password_funcarg` | 1 | `identity/models/user.py:106` (`Q(password="")`, filtro de usuarios sin contraseña) | descartado: es un filtro de consulta. |

Búsqueda manual de lo que pide la spec aunque bandit no lo marque (`grep -rn` en `apps` y
`config`): **sin** `subprocess`, `pickle`, `yaml.load`, `eval`/`exec`, `hashlib.md5`/`sha1`,
ni `try/except/pass`. El módulo `random` no se usa para tokens: los tokens salen de
`secrets` (se verifica en la Parte 4). → nada nuevo.

## 3. pip-audit

```
docker run --rm -u root -v WT\backend:/src:ro -v SW:/out -w /src IMG sh -c \
  "pip freeze > /out/image_freeze.txt && pip install pip-audit==2.10.1 && \
   pip-audit -r requirements.txt --format json -o /out/pip_audit_requirements.json && \
   pip-audit -r /out/image_freeze.txt --no-deps --disable-pip --format json -o /out/pip_audit_image.json"
```

Se corrió dos veces: contra `requirements.txt` (lo que resolvería el CI hoy, 68 paquetes) y
contra los paquetes **instalados** en la imagen (`pip freeze`, 69 paquetes). Mismo resultado:
**3 vulnerabilidades en 1 paquete**.

| Paquete | Versión | Id | Arreglo | ¿El código usa la parte afectada? | Clasificación |
| --- | --- | --- | --- | --- | --- |
| `djangorestframework` | 3.17.2 | CVE-2026-114136 / GHSA-3547-9m27-7rxg — `JSONParser` descomprime con el `charset` del cliente y salta `DATA_UPLOAD_MAX_MEMORY_SIZE` | 3.18.2 | **Sí**: `JSONParser` es el parser por defecto. Reproducido en el 8010: 101 bytes → un correo de 5 242 921 caracteres en el serializer de login | hallazgo **SEC-04** |
| `djangorestframework` | 3.17.2 | CVE-2026-114138 / GHSA-33wh-fxxf-88vv — la negociación de contenido analiza el `Accept` en tiempo cuadrático | 3.18.2 | **Sí**: toda vista de DRF negocia antes de autenticar. Medido en el 8010: un `Accept` de ~9 KB, ~6 ms → ~40 ms sin sesión | hallazgo **SEC-04** |
| `djangorestframework` | 3.17.2 | CVE-2026-114137 / GHSA-xw6w-gcfp-cf8m — borrar un token con `TokenProxy` no lo borra | 3.18.2 | **No**: `rest_framework.authtoken` no está en `INSTALLED_APPS`; la autenticación es propia (`CookieJWTAuthentication`) | descartado |

El arreglo **queda fuera del rango** de `requirements.txt` (`>=3.17,<3.18`): hace falta
cambiar el rango, no basta con reconstruir la imagen. Django 5.2.19, PyJWT 2.15.1, Celery
5.6.3, psycopg, argon2-cffi y el resto: sin vulnerabilidades conocidas.

## 4. semgrep

```
docker run --rm -e SEMGREP_SEND_METRICS=off -v WT\backend:/src:ro -v SW:/out -w /src \
  semgrep/semgrep:1.186.0 semgrep --metrics=off --config p/django --config p/python \
  --config p/secrets --config p/jwt --json -o /out/semgrep.json apps config
```

188 reglas de la comunidad (las *pro* piden iniciar sesión en semgrep.dev: no se usaron),
381 archivos, 0 errores de análisis. **1 resultado** (WARNING):

| Regla | Dónde | Clasificación |
| --- | --- | --- |
| `python-logger-credential-disclosure` | `apps/identity/services.py:279` (`logger.warning("Reutilización de refresh token detectada; se revocó la cadena de la sesión %s", session.pk)`) | descartado: el mensaje dice "token" pero lo que se escribe es el id (UUID) de la sesión, no el token de refresh. |

## 5. gitleaks (todo el historial)

```
docker run --rm -v MAIN:/repo:ro -v SW:/out zricethezav/gitleaks:v8.30.1 detect \
  --source /repo --log-opts="--all" --report-format json --report-path /out/gitleaks.json --redact
```

Se montó la carpeta principal (el worktree comparte su `.git`), en solo lectura. **40
commits, ~10 MB, 7 resultados**, todos de la regla `generic-api-key`. Cada uno se revisó en su
commit con `git show` (solo lectura); los valores no se copian aquí.

| Archivo | Commit | Qué es | Clasificación |
| --- | --- | --- | --- |
| `contracts/openapi.json:18517` | `b90519c2`, `2f0db7f8` | `"key"` de un grupo del embudo en un **ejemplo** del contrato: un UUID inventado | descartado (2) |
| `backend/apps/reporting/report_views.py:91` | `2f0db7f8` | el mismo UUID de ejemplo en el `OpenApiExample` del dashboard | descartado |
| `backend/tests/applications/idempotency/test_idempotency.py:40` | `5000abab` | `KEY`: un `Idempotency-Key` (UUID) de una prueba | descartado |
| `tests/identity/test_users.py:17`, `test_invitations.py:21`, `test_passwords.py:25` | `176f0fe9`, `2fefd592`, `cbe88ea2` | `NEW_PASSWORD`: contraseñas inventadas de las pruebas de identidad (ruta vieja, antes del monorepo) | descartado (3) |

Revisión adicional: en todo el historial no hay ningún `.env` ni archivos `*.pem`, `*.key` o
`id_rsa` (`git log --all --name-only`); solo los tres `.env.example`, que gitleaks analizó sin
resultados (no se abrieron a mano: la regla de la tarea prohíbe leer `.env*`). Las claves
del CI (`ci-secret-key-not-for-production`, `ci-jwt-signing-key-not-for-production`,
`ci_password` en `.github/workflows/backend.yml`) son de una base efímera del CI: descartado.
`.gitignore` excluye `.env` en cualquier carpeta y `.env*.local`.

**Para la Parte 5:** los 7 van a la `allowlist` de `.gitleaks.toml` (por commit y ruta, con
el porqué), para que el CI solo bloquee secretos nuevos.

## 6. Dockerfile y compose

```
docker run --rm -i hadolint/hadolint:v2.15.1 hadolint - < backend/Dockerfile
docker run --rm -i hadolint/hadolint:v2.15.1 hadolint - < frontend/Dockerfile
```

| Resultado | Dónde | Clasificación |
| --- | --- | --- |
| `DL3013` warning: `pip install --upgrade pip` sin versión | `backend/Dockerfile:11` | hallazgo **SEC-06** |
| `DL3066` info: usuario por nombre (`app`) y no por número | `backend/Dockerfile:23` | descartado: el usuario existe en la imagen (`uid=100`); solo importa si el host tuviera que resolverlo |
| `DL3066` info: usuario `node` por nombre | `frontend/Dockerfile:38` | descartado: mismo motivo |

Revisión manual, punto por punto de la spec:

| Punto | Resultado | Clasificación |
| --- | --- | --- |
| Usuario no root | `docker run --rm IMG id` → `uid=100(app) gid=101(app)`; igual en `mvp-sec-api` y en el backend del compose. El frontend corre como `node`. | bien |
| Imagen base sin digest | `FROM python:3.11-slim` y `node:24.22.2-alpine` por etiqueta | **SEC-06** (Informativa) |
| `runserver` como comando | `CMD [... "runserver", "0.0.0.0:8000"]` y el `command` del compose | **SEC-06** (Informativa; en producción, gunicorn) |
| Secretos en capas o en `ENV` | `docker image inspect` y `docker history`: ningún secreto; el único `GPG_KEY` es el id público de la clave de firma de Python. Sin `.env` en `/app` (`.dockerignore` lo excluye). | bien |
| Puertos expuestos al host | PostgreSQL `0.0.0.0:5433`, backend `0.0.0.0:8000`, frontend `0.0.0.0:3000` (y SeaweedFS `8333` con el perfil `full`) | **SEC-05** (Baja) |
| `DEBUG` por defecto | `base.py`: `DJANGO_DEBUG` falso por defecto, pero los puntos de entrada cargan `local` y `local.py` lo fija en `True` | **SEC-01** |
| Volúmenes con permisos | `/data/documents` con dueño `app`, modo `755`; el código se monta como volumen solo en desarrollo | bien |
| Servicios internos | Redis sin contraseña y ClamAV, pero solo en la red interna del compose (no publicados); SeaweedFS exige credenciales y deniega el acceso anónimo | bien (Redis sin contraseña: anotado en SEC-05 como aceptable en local) |

## 7. Dependencias del frontend (solo informar)

```
docker run --rm -e COREPACK_ENABLE_DOWNLOAD_PROMPT=0 -v WT\frontend:/src:ro -v SW:/out node:24-alpine sh -c \
  "mkdir /w && cp /src/package.json /src/pnpm-lock.yaml /w/ && cd /w && corepack enable && \
   pnpm audit --prod --json > /out/pnpm_audit.json"
```

Con el lockfile y sin instalar nada en el host (`pnpm` 12.18.0, el de `packageManager`).
**0 vulnerabilidades** (info 0, low 0, moderate 0, high 0, critical 0) en 202 dependencias
de producción (100 directas e indirectas más 102 opcionales). Next 16.4.6, React 19.3.1.

---

## Observaciones para las partes siguientes

No son hallazgos todavía: salieron al preparar la auditoría y se prueban donde corresponde.

- **Parte 2 (límites):** el throttle del login usa "IP más correo normalizado"
  (`apps/identity/throttling.py`). En la preparación, seis logins seguidos desde la misma IP
  con seis correos distintos pasaron todos (límite `5/15m`). Falta ver si es lo documentado o
  si permite probar contraseñas contra muchos correos desde una IP.
- **Parte 2 (errores):** con `DEBUG=True` (el 8010), un cuerpo de 5 MB a `/auth/login` responde
  la página HTML de depuración de `RequestDataTooBig` con `400`, no el formato de error de la
  API. Hay que ver la respuesta sin `DEBUG`.
- **Parte 4 (secretos en logs):** con `local`, el correo va a la consola (`EmailBackend` de
  consola). Hay que confirmar qué correos llevan el token en la URL (restablecimiento,
  invitación, enlace del comprador por correo) y que no lleguen al log fuera de `DEBUG`.
  Por ahora, en el log del 8010 no aparece ningún `token=` (las emisiones de la preparación
  fueron con `COPY_LINK`).
- **Herramientas, búsqueda manual:** `hashlib` solo con `sha256`; los tokens con
  `secrets.token_urlsafe(32)` (`apps/identity/tokens.py:38`, 256 bits); ni `random`, ni
  `subprocess`, `pickle`, `yaml.load`, `eval`/`exec`, ni `except` seguido de `pass`.
