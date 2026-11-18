# Auditoría de seguridad: cómo repetirla

Herramientas y scripts de la auditoría del backend (`docs/SEGURIDAD.md`). Todo corre en
local, contra contenedores de un solo uso y un servidor propio de auditoría. Nunca contra
`:8000`, internet ni servicios de terceros.

| Archivo | Para qué |
| --- | --- |
| `seed_actors.py` | Completa `seed_demo_data` con los actores de la matriz: `broker.b@`, `constructora@` y un segundo comprador. Solo con `DEBUG`; idempotente. |
| `render_matrix.py` | Genera `docs/seguridad/03-matriz-acceso.md` desde `tests/security/access_matrix.py`. `--check` falla si el documento no está al día (lo corre el CI). |
| `race_checks.py` | Carreras con transacciones reales (enlace mágico, radicación sin `Idempotency-Key`, `If-Match`, pago doble). Solo con `DEBUG`; escribe datos. |
| `pip-audit-ignore.txt` | Vulnerabilidades revisadas que el CI todavía no bloquea, cada una con su `SEC-NN`. |
| `../tests/security/` | La matriz de acceso y las pruebas de la revisión manual (corren en el CI con el resto de la suite). |
| `../../.gitleaks.toml` | Reglas de gitleaks y las excepciones revisadas. |

## Variables

Para no repetir (rutas de Windows del equipo de desarrollo; en Linux o macOS, las equivalentes):

```
WT  = <raíz del repo>
ENV = <raíz del repo>/backend/.env        # Docker la usa con --env-file; no se abre a mano
IMG = mvp-credit-backend-backend          # la imagen del compose
NET = mvp_credit_network
SW  = <carpeta fuera del repo para reportes crudos y cookies>
```

## 1. Preparación

```
# Base propia (no toca la del compose)
docker run --rm --network NET --env-file ENV -e DATABASE_HOST=postgres IMG \
  python manage.py shell -c "from django.db import connection; connection.cursor().execute('CREATE DATABASE mvp_credit_sec')"

# Migraciones, caché, datos de demo y actores (con un volumen propio de documentos)
docker run --rm --network NET --env-file ENV -e DATABASE_HOST=postgres -e DATABASE_NAME=mvp_credit_sec \
  -e DJANGO_DEBUG=True -v mvp_sec_documents:/data/documents -v WT/backend:/app -w /app IMG sh -c \
  "python manage.py migrate --noinput && python manage.py createcachetable && python manage.py seed_demo_data \
   && python manage.py shell -c \"exec(open('security/seed_actors.py').read())\""

# Servidor de auditoría en el 8010
docker run -d --name mvp-sec-api --network NET --env-file ENV -e DATABASE_HOST=postgres \
  -e DATABASE_NAME=mvp_credit_sec -e DJANGO_DEBUG=True \
  -e DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,mvp-sec-api,host.docker.internal \
  -e AUTH_ACCESS_TOKEN_MINUTES=120 -p 8010:8000 -v mvp_sec_documents:/data/documents \
  -v WT/backend:/app -w /app IMG python manage.py runserver 0.0.0.0:8000
```

`seed_demo_data` imprime una URL del portal con un token: no la copies a ningún documento.
Las sesiones para los escáneres salen de un `POST /api/v1/auth/login` normal y se guardan en
`SW`, nunca en el repo. Si el límite de consumo del enlace o del login se agota:
`docker exec mvp-sec-api python manage.py shell -c "from django.core.cache import cache; cache.clear()"`.

## 2. Análisis automático (Parte 1)

```
# Configuración de producción (los dos últimos -e: sin ellos la API no arranca sin DEBUG)
docker run --rm --network NET --env-file ENV -e DATABASE_HOST=postgres -e DATABASE_NAME=mvp_credit_sec \
  -e DJANGO_DEBUG=False -e DJANGO_SETTINGS_MODULE=config.settings.base \
  -e DOCUMENT_STORAGE_BACKEND=s3 -e DOCUMENT_SCANNER=clamd -v WT/backend:/app -w /app IMG \
  python manage.py check --deploy

# bandit y pip-audit (instalados en un contenedor de un solo uso)
docker run --rm -u root -v WT/backend:/src:ro -v SW:/out -w /src IMG sh -c \
  "pip install bandit==1.9.4 pip-audit==2.10.1 && bandit -r apps config -f json -o /out/bandit.json; \
   pip-audit -r requirements.txt --format json --output /out/pip-audit.json"

# semgrep
docker run --rm -e SEMGREP_SEND_METRICS=off -v WT/backend:/src:ro -v SW:/out -w /src semgrep/semgrep:1.186.0 \
  semgrep --metrics=off --config p/django --config p/python --config p/secrets --config p/jwt \
  --json -o /out/semgrep.json apps config

# gitleaks sobre todo el historial (montar la carpeta que tiene el .git completo)
docker run --rm -v WT:/repo:ro -v SW:/out zricethezav/gitleaks:v8.30.1 detect --source /repo \
  --config /repo/.gitleaks.toml --log-opts="--all" --redact --report-format json --report-path /out/gitleaks.json

# Dockerfile
docker run --rm -i hadolint/hadolint:v2.15.1 hadolint - < WT/backend/Dockerfile

# Dependencias del frontend (solo informar), sin instalar nada en el equipo
docker run --rm -e COREPACK_ENABLE_DOWNLOAD_PROMPT=0 -v WT/frontend:/src:ro -v SW:/out node:24-alpine sh -c \
  "mkdir /w && cp /src/package.json /src/pnpm-lock.yaml /w/ && cd /w && corepack enable && pnpm audit --prod --json > /out/pnpm-audit.json"
```

## 3. Análisis dinámico (Parte 2)

Antes de cada corrida que escribe, restaurar la base desde una plantilla
(`CREATE DATABASE mvp_credit_sec_tpl TEMPLATE mvp_credit_sec` una vez después de la
preparación; después, `DROP` y `CREATE ... TEMPLATE mvp_credit_sec_tpl` con el 8010 detenido)
y volver a hacer login.

```
# schemathesis (una imagen de usar y tirar con la herramienta), una corrida por actor y otra sin sesión
docker run --rm --network NET -v SW:/w -v WT/contracts:/contracts:ro -w /w <imagen con schemathesis==4.33.4> \
  schemathesis --config-file /w/st.toml run /contracts/openapi.json --url http://mvp-sec-api:8000 \
  --checks all -n 25 --workers 1 --phases examples,coverage,fuzzing --seed 20261118 \
  --exclude-operation-id auth_logout --exclude-operation-id auth_change_password \
  --exclude-operation-id auth_refresh --exclude-operation-id buyer_session_logout \
  --exclude-operation-id users_deactivate --exclude-operation-id users_roles_update \
  --exclude-operation-id users_partial_update --exclude-operation-id partner_memberships_destroy \
  -H "Cookie: <sesión>" -H "X-CSRFToken: <csrf>" --report junit,ndjson --report-dir /w/st_<actor>
# st.toml: [parameters] con los ids del lado A ("path.application_id" = "...").
# Sin sesión: -n 10 --max-time 1080 (con -n 25 pasa de 20 minutos).

# OWASP ZAP: con una copia del contrato SIN las operaciones de arriba (la importación de ZAP no
# respeta globalexcludeurl) y con los ids reales en las rutas
docker run --rm --network NET -u zap -v SW/zap:/zap/wrk:rw zaproxy/zap-stable:2.17.0 \
  zap-api-scan.py -t /zap/wrk/openapi_zap.json -f openapi -O http://mvp-sec-api:8000 [-S] -I \
  -r zap.html -J zap.json -z "-config replacer.full_list(0).matchtype=REQ_HEADER \
  -config replacer.full_list(0).matchstr=Cookie -config replacer.full_list(0).replacement=<cookie sin espacios> \
  ... -config scanner.maxScanDurationInMins=15"
```

Cabeceras y CORS con `curlimages/curl:8.23.0` desde la red del compose; límites de consumo y
errores con scripts de Python estándar en la imagen del backend (detalle en
`docs/seguridad/02-dinamico.md`). Para ver la respuesta de producción, un segundo servidor de
un solo uso en el 8011 con `-e DJANGO_SETTINGS_MODULE=config.settings.base -e DJANGO_DEBUG=False
-e AUTH_COOKIE_SECURE=True -e DOCUMENT_STORAGE_BACKEND=s3 -e DOCUMENT_SCANNER=clamd`.

## 4. Matriz de acceso y revisión manual (Partes 3 y 4)

```
# Desde backend/, con una base de pruebas propia
pytest tests/security                      # ~2400 pruebas, ~105 s con base nueva
python security/render_matrix.py           # vuelve a generar docs/seguridad/03-matriz-acceso.md
python security/render_matrix.py --check   # lo que corre el CI

# Carreras, contra la base de auditoría y con el 8010 arriba
docker run --rm --network NET --env-file ENV -e DATABASE_HOST=postgres -e DATABASE_NAME=mvp_credit_sec \
  -e DJANGO_DEBUG=True -v mvp_sec_documents:/data/documents -v WT/backend:/app -w /app IMG \
  python manage.py shell -c "exec(open('security/race_checks.py').read())"
```

`race_checks.py` consume un enlace de la asesora Lucía: cierra la sesión del comprador de esa
solicitud (una sola sesión viva por cliente). Restaurar la base después.

## 5. Al terminar

```
docker rm -f mvp-sec-api
# Borrar las bases mvp_credit_sec y mvp_credit_sec_tpl, el volumen mvp_sec_documents,
# la imagen de schemathesis y la carpeta SW (cookies y reportes crudos).
```

## En el CI

`.github/workflows/backend.yml` corre en cada PR, además de la suite completa (que incluye
`tests/security`): `pip-audit` (bloquea si hay una vulnerabilidad con arreglo; las sin arreglo
salen como aviso; las revisadas, en `pip-audit-ignore.txt`), `gitleaks` sobre todo el historial
(bloquea ante cualquier secreto nuevo; las excepciones revisadas, en `.gitleaks.toml`),
`bandit` (bloquea solo la severidad alta; la media sale como aviso) y
`render_matrix.py --check`. El resumen de cada una sale en el comentario del PR
(`scripts/ci_report.py`).
