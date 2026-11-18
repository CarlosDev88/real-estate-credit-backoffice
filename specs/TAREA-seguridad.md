# TAREA — Auditoría de seguridad del backend (Fase A: encontrar brechas)

> Spec cerrada. Todas las decisiones están tomadas. **No preguntes:** si algo no cuadra con el código, decide lo más simple, anótalo en "Precisiones acordadas" (al final de este archivo) y en el reporte, y sigue.

## 0. Contexto en 30 segundos
- **Qué es:** el backoffice de crédito hipotecario (Django 5.2 + DRF, PostgreSQL 16) con 16 módulos: identidad y sesiones (JWT en cookies), comprador con enlace mágico, CRM, solicitudes, documentos con URL firmadas, radicación, tareas, notificaciones, idempotencia, auditoría técnica, reportes y comisiones.
- **Tamaño:** ~156 rutas y ~212 operaciones en `contracts/openapi.json`.
- **Roles:** `ADMIN`, `ADVISOR`, `INDEPENDENT_BROKER`, `CONSTRUCTION_PARTNER` (internos, con login) y el **comprador** (sin cuenta: entra con un enlace mágico que crea una `buyer_session`).
- **Fuentes de la verdad para "quién puede qué":** `docs/REQUERIMIENTOS_MVP_CREDITO.md` §3 (actores), §9 (seguridad, límites, auditoría) y `docs/API_REST_MVP_CREDITO.md` §25/§27 (matriz de acceso). Si REQ y API chocan, **manda REQ** (así se decidió en todo el proyecto: p. ej. la constructora no ve expedientes).
- **Ya existe** (no lo rehagas, verifícalo): alcance por rol en `apps/*/services.py` (un recurso fuera del alcance responde **404**, no 403), permisos por código (`HasPermissionCode`, `required_permissions`), throttles (`AUTH_RATE_LIMITS` en `config/settings/base.py`), auditoría (`apps/audit`), idempotencia (`apps/idempotency`), saneamiento de CSV (`apps/reporting/exports.py`), validación de archivos (`apps/documents/file_validation.py`, `scanning.py`).

## 1. Qué es esta tarea y qué NO es
- **Es:** encontrar brechas de seguridad con evidencia reproducible, documentarlas y dejar en el repo las pruebas y controles del CI que impiden que vuelvan.
- **No es:** corregir. **No cambies código de `apps/` ni de `config/`** (salvo lo que dice la Parte 5). Las correcciones son la Fase B, con otra spec y otro agente. Si un arreglo es obvio, escríbelo como "Corrección sugerida" dentro del hallazgo.
- **Alcance:** solo **backend** (y la dependencia del front en la Parte 1.7). Solo **local**: el servidor propio de la Parte 2 y contenedores de un solo uso. **Nada contra internet, GitHub ni servicios externos.** Es nuestra propia aplicación, en nuestro propio equipo.

## 2. Dónde y cómo
- **Worktree:** `C:\Users\ASUS\Documents\programacion\mvp-backoffice\wt-security`, rama `chore/security-audit`, desde `origin/master` con los 16 módulos.
- **Agente:** el primero de backend que quede libre ("auditor").
- **Buzón:** `.buzon/` como siempre (`PROTOCOLO.md`, `ESTADO.md`, `reportes/`, `PARA-AGENTE.md`).

### Reglas
1. **Git solo lectura** (nada de commit, add, mv, restore, fetch, push). Carlos hace los commits.
2. **No leas ni edites `.env*`.** El `--env-file` de los `docker run` lo usa Docker, tú no lo abres.
3. **Nunca escribas en reportes, docs, logs ni pruebas:** contraseñas reales, tokens, cookies, JWT completos, URL firmadas, claves. Si un hallazgo expone uno, descríbelo ("la respuesta incluye el token del enlace") y córtalo (`abc…xyz`). La única contraseña que puede aparecer es la **de demo** ya publicada en el código (`DemoUmbral2026!`), porque es un dato de prueba.
4. **Pruebas acotadas** en local (`tests/security/` y lo que toques); la suite completa la corre el CI. Siempre `ruff`, `mypy .`, `makemigrations --check`.
5. **Herramientas fuera del proyecto:** instálalas en contenedores de un solo uso (`docker run --rm …`) o con `pip install` **dentro** de un contenedor de un solo uso de la imagen del backend. **No las agregues a `requirements.txt`.** Las del CI (Parte 5) se instalan en el workflow con versión fijada. Anota la versión exacta de cada herramienta en el reporte.
6. **Memoria del equipo:** una herramienta pesada a la vez (ZAP y schemathesis no en paralelo).
7. **Tiempo:** ningún escaneo dinámico más de 20 minutos; si se pasa, acótalo (menos operaciones, menos ejemplos) y anótalo.

## 3. Preparación (antes de la Parte 1)
Todo con la imagen y la red del compose. Variables para no repetir:
```
WT  = C:\Users\ASUS\Documents\programacion\mvp-backoffice\wt-security
ENV = C:\Users\ASUS\Documents\programacion\mvp-backoffice\real-estate-credit-backoffice\backend\.env
IMG = mvp-credit-backend-backend
NET = mvp_credit_network
```
1. **Dependencias de pruebas:** como siempre, `docker run --rm --network NET --env-file ENV -e DATABASE_HOST=postgres -e DATABASE_NAME=mvp_credit_sec -v WT\backend:/app -v WT\contracts:/contracts -w /app IMG <comando>`.
2. **Base propia** `mvp_credit_sec` (no toques `mvp_credit`, `mvp_credit_a` ni `mvp_credit_b`):
   ```
   docker run --rm --network NET --env-file ENV -e DATABASE_HOST=postgres IMG python manage.py shell -c "from django.db import connection; connection.cursor().execute('CREATE DATABASE mvp_credit_sec')"
   ```
   (si ya existe, sigue). Luego `migrate` y `createcachetable` con `-e DATABASE_NAME=mvp_credit_sec`.
3. **Servidor propio de auditoría en el puerto 8010** (no uses `:8000`: lo monta la carpeta principal y otro agente trabaja ahí):
   ```
   docker run -d --name mvp-sec-api --network NET --env-file ENV -e DATABASE_HOST=postgres -e DATABASE_NAME=mvp_credit_sec -e DJANGO_DEBUG=True -e DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,mvp-sec-api,host.docker.internal -p 8010:8000 -v WT\backend:/app -w /app IMG python manage.py runserver 0.0.0.0:8000
   ```
   Los escáneres que corren en contenedor lo alcanzan como `http://mvp-sec-api:8000` (misma red). Al terminar la tarea: `docker rm -f mvp-sec-api`.
4. **Datos:** `python manage.py seed_demo_data` contra `mvp_credit_sec`. Usuarios de demo (`@demo.local`, contraseña de demo): `admin@`, `asesora.lucia@`, `asesor.andres@`, `broker@`. El comando imprime una URL del portal de un solo uso.
5. **Actores que faltan para la matriz:** script `backend/security/seed_actors.py` (se versiona; solo corre con `DEBUG=True`, igual que `seed_demo_data`; idempotente). Crea, con la contraseña de demo:
   - `broker.b@demo.local` (segundo broker, con una oportunidad propia);
   - `constructora@demo.local` (`CONSTRUCTION_PARTNER`, miembro de una constructora con un proyecto activo);
   - un segundo comprador con su solicitud asignada a `asesor.andres@` (para probar comprador A contra comprador B).
   Se corre con `python manage.py shell -c "exec(open('security/seed_actors.py').read())"`. Imprime solo correos y códigos de solicitud, nunca tokens.
6. **Sesiones para los escáneres:** login normal (`POST /api/v1/auth/login`) con los usuarios de demo; las cookies resultantes (`app_access`/`app_refresh` o como se llamen en `apps/identity/cookies.py`, y `app_csrf`) se guardan en una carpeta **fuera del repo**, para que nunca terminen en git: `C:\Users\ASUS\Documents\programacion\mvp-backoffice\_security-work\` (ahí van también los reportes crudos de las herramientas). Al terminar la tarea se borra. Para el comprador: pide un enlace como asesor (`POST /api/v1/applications/{id}/buyer-access-links`) y consúmelo (`/buyer-access/consume`, revisa la ruta real). **Límite:** 5 consumos por hora por IP; el servidor 8010 tiene su propia caché, así que si se agota: `docker exec mvp-sec-api python manage.py shell -c "from django.core.cache import cache; cache.clear()"`.

## 4. Las partes de la auditoría

### Parte 1 — Análisis automático (código, dependencias, secretos, contenedor)
Para cada herramienta: comando exacto, versión, número de resultados por severidad y la **clasificación de cada resultado**: `hallazgo` (pasa a la lista `SEC-NN`) o `descartado` (con el porqué en una línea).

1. **Configuración de Django:** `python manage.py check --deploy` con `-e DJANGO_DEBUG=False -e DJANGO_SETTINGS_MODULE=config.settings.base`. **Ojo:** el repo no tiene settings de producción (solo `base`, `local` y `test`): eso en sí es un hallazgo de configuración a evaluar (Baja/Informativa, porque el alcance es local), y cada aviso de `check --deploy` se clasifica según aplique a producción.
2. **bandit** (`pip install bandit==<última estable>` en contenedor): `bandit -r apps config -f json -o /tmp/bandit.json` y resumen. Revisa a mano **todos** los de severidad media y alta, y los bajos de `subprocess`, `pickle`, `yaml.load`, `random` (para tokens), `hashlib.md5/sha1`, `assert` en código de producción, `try/except/pass`.
3. **pip-audit** (`pip-audit -r requirements.txt --format json`): cada vulnerabilidad con su paquete, versión, CVE/GHSA, si hay versión con arreglo y si el código usa la parte afectada.
4. **semgrep** (imagen `semgrep/semgrep`, versión fijada): `semgrep --config p/django --config p/python --config p/secrets --config p/jwt --json apps config`.
5. **gitleaks** (imagen `zricethezav/gitleaks`, versión fijada) sobre **todo el historial**: `gitleaks detect --source /repo --log-opts="--all" --report-format json --redact`. Monta el repo en solo lectura (`-v <raíz del repo>:/repo:ro`). Como el worktree comparte `.git` con la carpeta principal, monta la carpeta principal para tener el historial completo. Clasifica: claves de CI de ejemplo (`ci-secret-key-not-for-production`), contraseñas de demo y fixtures de prueba son `descartado` si son claramente de prueba; cualquier otra cosa es hallazgo.
6. **Dockerfile y compose** (revisión manual + `hadolint` en contenedor): usuario no root (ya lo hay: verifícalo en el contenedor con `id`), imagen base sin fijar por digest, `runserver` como comando (en producción iría gunicorn: Informativa), secretos en capas o en `ENV`, puertos de Postgres expuestos al host, `DEBUG` por defecto, volúmenes con permisos.
7. **Dependencias del front** (solo informar, no es backend): `pnpm audit --prod --json` en `frontend/` con la imagen `node` (no instales en el host).

**Entregable:** `docs/seguridad/01-automatico.md`.

### Parte 2 — Análisis dinámico (contra el servidor 8010)
1. **schemathesis** (`pip install schemathesis==<versión fijada>` en contenedor, en la red `NET`):
   - Tres corridas: con cookies de **admin**, de **asesora.lucia** y de **broker**; y una **sin sesión**.
   - `schemathesis run /contracts/openapi.json --base-url http://mvp-sec-api:8000/api/v1 --checks all --hypothesis-max-examples 25 --workers 1` con las cookies y el `X-CSRFToken` como cabeceras (`-H`). Excluye `POST /auth/logout`, `POST /auth/change-password` y los que borren o revoquen datos de los usuarios de la corrida (anota cuáles excluiste).
   - Qué buscar: **cualquier 500** (hallazgo siempre: posible fuga de información o DoS), respuestas que no cumplen el contrato, campos de más en la respuesta (exposición de datos), 2xx donde el rol no debía tener acceso.
2. **OWASP ZAP** (imagen `zaproxy/zap-stable`, versión fijada): `zap-api-scan.py -t /zap/wrk/openapi.json -f openapi -O http://mvp-sec-api:8000 -r zap.html -J zap.json` con la sesión de admin inyectada por `-z "-config replacer..."` (cabecera `Cookie`). Primero **pasivo** (`-S` no; usa el modo por defecto del api-scan) y luego **activo** con política por defecto. Reporte HTML en `_security-work`, resumen en la doc.
3. **Cabeceras y CORS** (con `curl` desde un contenedor):
   - en respuestas de la API: `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`/`frame-ancestors`, `Cache-Control: no-store` en respuestas con datos personales y en las descargas, `Strict-Transport-Security` (anota que aplica con HTTPS);
   - CORS: preflight desde `http://evil.example` y desde `http://localhost:3000`; que `Access-Control-Allow-Origin` nunca refleje un origen no permitido con `Allow-Credentials: true`;
   - cookies: `HttpOnly`, `Secure` (con `AUTH_COOKIE_SECURE`), `SameSite`, `Path`, vencimiento; la de CSRF es legible por diseño (anótalo).
4. **Límites de consumo** (scripts cortos en contenedor): para login, `password-reset`, consumo y emisión del enlace mágico, carga de documentos, descarga y reportes:
   - ¿se cumple el número de `AUTH_RATE_LIMITS`?
   - ¿se salta con `X-Forwarded-For` distinto, con el correo en mayúsculas o con espacios, con otro `User-Agent`?
   - ¿el `429` trae `Retry-After` y no revela si el usuario existe?
5. **Errores:** un 404/405/415/400 malformado y un JSON gigante (por ejemplo 5 MB): ¿la respuesta tiene el formato de error de la API, sin trazas, sin rutas de archivos, sin SQL? ¿hay límite de tamaño del cuerpo (`DATA_UPLOAD_MAX_MEMORY_SIZE`)?

**Entregable:** `docs/seguridad/02-dinamico.md`.

### Parte 3 — Matriz de acceso (BOLA / BFLA) — la más importante
**Objetivo:** probar que **nadie ve ni toca lo que no le corresponde**. Esto es lo que más falla en las API reales (OWASP API1 y API5).

1. **Inventario:** saca de `contracts/openapi.json` todas las operaciones (método + ruta). Para cada una, anota en `backend/tests/security/access_matrix.py` (una tabla de Python, legible) qué espera cada actor, a partir de API §27, REQ §3 y el `required_permissions` de la vista:
   - **Actores (9):** `anon`, `admin`, `advisor_owner` (asesora.lucia, dueña del recurso), `advisor_other` (asesor.andres), `broker_owner` (el que originó la oportunidad), `broker_other` (broker.b), `partner` (constructora), `buyer_owner` (sesión del comprador del recurso), `buyer_other` (sesión del otro comprador).
   - **Resultado esperado:** `ALLOW` (2xx o un 4xx de validación como 400/409/422, que muestra que pasó la autorización), `DENY_401`, `DENY_403`, `HIDE_404` (fuera de alcance: no confirma que existe).
   - Si la documentación no define un caso, aplica la regla general del proyecto: **fuera del alcance → 404**; **sin el permiso del rol → 403**; **sin sesión → 401**. Anota cada caso decidido así.
2. **Mundo de prueba** (`backend/tests/security/conftest.py`): un fixture que crea **una vez por módulo** un "mundo" con dos de cada cosa, una del lado A y otra del lado B: clientes, oportunidades (una de broker A), solicitudes (A asignada a lucía, B a andrés), participantes, inmueble y financiación, slots y archivos de documento (limpios), paquete, radicación y respuesta del banco (con evidencia), tareas, notas, notificaciones, enlace y sesión de comprador, consentimientos, planes y liquidación de comisión, trabajo de exportación de reportes, proyecto de constructora. Usa los factories y fixtures que ya existen en `tests/` (no los dupliques). Los parámetros de ruta (`{application_id}`, `{slot_id}`, …) se llenan **siempre con los ids del lado A**.
3. **La prueba** (`backend/tests/security/test_access_matrix.py`): parametrizada por (operación × actor). Para cada caso arma la petición con un cuerpo mínimo válido (puedes tomar ejemplos del contrato) y compara el estado obtenido con el esperado. Reglas:
   - **Escrituras permitidas:** basta con que no sea 401/403/404; no compruebes el efecto (eso ya lo prueban los módulos).
   - Cada caso corre en su propia transacción (lo normal de pytest-django), así un `DELETE` no rompe los demás.
   - **Presupuesto de tiempo:** toda la matriz debe correr en **menos de 3 minutos** en el CI. Si no alcanza, el mundo es de alcance de sesión (`django_db_blocker`) y los casos `ALLOW` de escrituras se marcan como cubiertos por las pruebas de cada módulo (anótalo).
   - **Si un caso falla hoy** (brecha real): no lo corrijas. Márcalo `pytest.param(..., marks=pytest.mark.xfail(strict=True, reason="SEC-NN"))` para que el CI quede verde y, cuando la Fase B lo corrija, el `xfail` estricto obligue a quitar la marca.
   - Además del estado, en los `ALLOW` del **broker** y del **comprador**, comprueba que la respuesta **no tenga** campos prohibidos: datos financieros detallados, archivos/URL firmadas (broker), notas internas, `internal_comment`, documentos completos de otras personas (lista en `access_matrix.py`, `FORBIDDEN_FIELDS_BY_ACTOR`).
4. **Casos que sí o sí deben estar** (aparte de la tabla, una prueba explícita por cada uno):
   - ids del lado B en el **cuerpo** (no en la ruta): `application_id`, `slot_id`, `client_id`, `opportunity_id`, `participant_id`, `filing_id`, `assigned_to`, `beneficiary_user_id`;
   - el comprador A con su sesión pidiendo `/buyer/applications/{id_B}`, `/buyer/document-files/{id_B}/download`, `/buyer/notifications/{id_B}/read`;
   - filtros de listados con ids de otro alcance (`?advisor_id=`, `?client_id=`, `?application_id=`): deben dar 403 o vacío **según lo documentado**, nunca datos ajenos;
   - el broker sobre `/applications/{id}` de su propia oportunidad: solo el resumen permitido;
   - la constructora sobre cualquier ruta de expedientes: 403/404;
   - un usuario **desactivado** con una cookie de acceso todavía vigente;
   - un usuario al que **le quitaron el rol** con la cookie vigente (¿el permiso se vuelve a leer en cada petición?).

**Entregable:** `docs/seguridad/03-matriz-acceso.md` con la tabla legible (operación × actor, con ✓ / ✗ y el estado), generada por un script desde `access_matrix.py` (`backend/security/render_matrix.py`), y la lista de brechas.

### Parte 4 — Revisión manual (lo que las herramientas no ven)
Para cada punto: qué revisaste (archivos y funciones), cómo lo probaste (una prueba en `tests/security/` cuando sea posible, si no un comando reproducible) y el resultado.

1. **Autenticación interna** (`apps/identity/authentication.py`, `tokens.py`, `cookies.py`, `views.py`):
   - JWT: algoritmo fijo (que no acepte `none` ni cambio de algoritmo), `iss`/`aud`/`exp` verificados, `leeway` de 5 s, clave propia (`AUTH_JWT_SIGNING_KEY`);
   - token de **refresh**: rotación, reutilización de uno ya usado, revocación al cerrar sesión y al **cambiar o restablecer la contraseña** (¿las otras sesiones mueren?);
   - **CSRF**: cada método que cambia algo exige `X-CSRFToken`; prueba un `POST` autenticado sin la cabecera y con otra;
   - **enumeración**: login con correo existente vs. inexistente, y `password-reset` igual: mismo mensaje, mismo código **y tiempo parecido** (mide 20 intentos de cada uno; una diferencia sistemática de más de 100 ms es hallazgo);
   - política de contraseñas (`AUTH_PASSWORD_VALIDATORS`), Argon2;
   - token de restablecimiento: un solo uso, vencimiento de 30 min, no aparece en logs.
2. **Enlace mágico y sesión del comprador** (`apps/identity/buyer_access*.py`, `buyer_sessions.py`, `buyer_authentication.py`):
   - entropía del token (bits; cómo se genera: `secrets`), se guarda **hasheado**, un solo uso, vencimiento, revocación;
   - **carrera:** dos consumos **simultáneos** del mismo token (10 hilos): solo uno debe ganar;
   - el token no queda en logs, en la auditoría ni en un `Referer` (la página del front lo borra de la URL: verifica que el backend no lo devuelva en redirecciones);
   - la sesión del comprador: duración (`BUYER_SESSION_HOURS`), cierre, que una sesión no sirva para otra solicitud.
3. **Archivos** (`apps/documents/uploads.py`, `file_validation.py`, `scanning.py`, `storage.py`, `downloads.py`; evidencia en `apps/filings/evidence.py`):
   - tipo real por contenido, no por extensión ni `Content-Type`; un PDF con JavaScript, un "PDF" que es HTML, un PNG con HTML, un SVG (¿se rechaza?), un ZIP;
   - nombres de archivo con `../`, `\`, bytes nulos, unicode raro, 300 caracteres: ¿el nombre del cliente llega a la clave de almacenamiento o solo al `Content-Disposition`? ¿se escapa en el `Content-Disposition`?
   - tamaño máximo (10 MB) y qué pasa con 10 MB + 1 byte y con un cuerpo que miente en `Content-Length`;
   - un archivo `PENDING` o `INFECTED` nunca se firma para descarga (`409 FILE_NOT_CLEAN`);
   - URL firmadas: duración (5 min), que no sirvan para otra clave, que no salgan en logs ni en la auditoría;
   - el almacenamiento en disco del modo local: ¿se puede leer un archivo por ruta directa sin firma?
4. **Inyección:**
   - SQL: busca `raw(`, `RawSQL`, `.extra(`, `cursor.execute` (hoy solo hay un `nextval` con parámetro: verifícalo), `Func`/`Value` con texto del usuario;
   - **ordenamiento y filtros libres:** `?ordering=` con campos no permitidos (`password`, `assigned_advisor__password`, campos relacionados) en **todos** los listados; filtros armados con `**request.query_params`;
   - **CSV:** reportes (ya saneado) y cualquier otra exportación;
   - **plantillas de correo** (`apps/notifications`, `identity/emails.py`): datos del usuario en HTML sin escapar;
   - **cabeceras:** `X-Request-ID` del cliente se guarda (hasta 64): ¿se valida el formato antes de ir a logs (inyección de líneas `\r\n`)?
5. **Asignación masiva** (OWASP API3): en cada serializer de escritura, ¿acepta campos que el rol no debe tocar? Prueba con campos extra: `status`, `version`, `assigned_advisor`, `is_active`, `is_superuser`, `roles`, `client_id`, `application_id`, montos, `public_status`, `review_status`, `scan_status`, `paid_at`. Un campo extra **ignorado** está bien; uno **aplicado** es hallazgo Alta.
6. **Exposición de datos** (OWASP API3):
   - respuestas al broker y al comprador: campo por campo contra REQ §3;
   - **logs**: busca `logger.` con `email`, `phone`, `document_number`, `token`, `url`, `password`, `str(request.data)`; corre una petición de cada flujo sensible con el servidor 8010 y revisa `docker logs mvp-sec-api`;
   - mensajes de error y `details` con datos de otras personas;
   - la auditoría: corre el escáner que ya trae `tests/applications/audit` sobre los eventos que generaste.
7. **Lógica de negocio** (OWASP API6):
   - transiciones de estado no permitidas por `POST /applications/{id}/status-transitions` (saltar de `DRAFT` a `APPROVED`);
   - editar el expediente después de `FILED` (con `If-Match` viejo y nuevo);
   - el comprador cambiando banco/producto/financiación después de `FILED`;
   - doble radicación **sin** `Idempotency-Key` en paralelo (10 hilos): ¿cuántas se crean?;
   - liquidar dos veces, pagar dos veces la misma parte, anular con partes pagadas (comisiones);
   - concurrencia con `If-Match`: dos `PATCH` simultáneos con la misma versión.
8. **Consumo de recursos** (OWASP API4): `page_size` máximo (¿se puede pedir 100000?), búsqueda con comodines largos, reportes con el rango máximo, exportaciones simultáneas (3 por usuario), tamaño de `metadata` y textos libres (notas de 1 MB).
9. **Secretos y configuración** (OWASP API8): `SECRET_KEY` y `AUTH_JWT_SIGNING_KEY` sin valor por defecto (que fallen si faltan), `DEBUG` por defecto falso, `ALLOWED_HOSTS`, `/admin/` de Django expuesto (¿con qué protección?), `/openapi.json` y la documentación expuestos sin login (Informativa), `health`/`ready` sin datos internos.
10. **Inventario** (OWASP API9): rutas que existen en `config/urls.py` pero no en el contrato, o al revés; versiones viejas; endpoints de depuración.

**Entregable:** `docs/seguridad/04-manual.md`.

### Parte 5 — Lo que queda en el repo (único cambio de código permitido)
1. **Pruebas de seguridad** en `backend/tests/security/`: la matriz (Parte 3), los casos explícitos (3.4) y las pruebas de la Parte 4 que se puedan automatizar. Cada brecha real con `xfail(strict=True, reason="SEC-NN")`. Deben pasar con `pytest tests/security` y no bajar la cobertura del CI (umbral 95 %).
2. **`backend/security/`**: `seed_actors.py`, `render_matrix.py` y un `README.md` corto de cómo repetir la auditoría (comandos de las Partes 1 y 2).
3. **CI del backend** (`.github/workflows/backend.yml` + `backend/scripts/ci_report.py`): tres verificaciones nuevas, cada una con su `id`, `continue-on-error: true`, salida a `$CI_REPORT_DIR/<nombre>.txt`, su `CheckSpec` en `CHECKS` (con su función `check_*` que resume el resultado en una línea en español, como las demás) y su `outcome` en el paso **"CI gate"**:
   | Verificación | Versión | Bloquea |
   | --- | --- | --- |
   | **pip-audit** (`pip-audit -r requirements.txt`) | fijada | Sí, si hay una vulnerabilidad con versión arreglada disponible. Las sin arreglo salen como aviso. |
   | **gitleaks** (acción o binario fijado por versión y checksum; `--redact`) | fijada | Sí, ante cualquier secreto nuevo. Los de prueba ya revisados van en `.gitleaks.toml` (`allowlist`) con un comentario del porqué. |
   | **bandit** (`bandit -r apps config -lll` para bloquear solo severidad alta; un segundo comando `-ll` sale como aviso) | fijada | Solo severidad **alta**. |
   Pruebas de las funciones nuevas de `ci_report.py` en `backend/tests/` (como las que ya existen para el reporte). Si la Parte 1 encuentra hoy algo que haría fallar estas verificaciones, **no lo arregles**: agrégalo a la `allowlist`/configuración con `# SEC-NN` para que la Fase B lo quite.
4. **`docs/SEGURIDAD.md`** (para el portafolio; en español; las dos primeras secciones las debe entender alguien no técnico):
   1. **Resumen en simple:** qué se revisó, cómo, cuántos hallazgos por severidad y los 3 más importantes en una frase cada uno.
   2. **Modelo de amenazas:** actores (asesor curioso, broker que quiere ver datos de otro, comprador que cambia un id, atacante externo sin cuenta, alguien con un enlace mágico robado), activos (expedientes, documentos de identidad e ingresos, datos personales, comisiones), fronteras de confianza (navegador → Next → API → PostgreSQL y almacenamiento) con un diagrama Mermaid.
   3. **Controles que ya existen** y dónde viven en el código (tabla).
   4. **Hallazgos:** tabla `SEC-NN` | título | severidad | OWASP API Top 10 | estado (`abierto`, `corregido en #NN`, `aceptado` con motivo) | enlace a la sección del detalle.
   5. **Cómo repetir la auditoría** (enlace a `backend/security/README.md`).

## 5. Formato de cada hallazgo
En `docs/seguridad/hallazgos.md`, uno por sección:
```
### SEC-07 — El broker ve el monto aprobado en el detalle de la solicitud
- **Severidad:** Alta (CVSS 3.1 ~7.1: AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N)
- **Categoría:** OWASP API3:2023 — Broken Object Property Level Authorization
- **Dónde:** `apps/applications/serializers.py`, `ApplicationBrokerSerializer`
- **Cómo reproducirlo:** prueba `tests/security/test_access_matrix.py::test_access[GET /applications/{id}-broker_owner]` (xfail SEC-07) o: login como broker → `GET /api/v1/applications/<id>`.
- **Qué pasa:** la respuesta trae `approved_amount_cop`.
- **Qué debería pasar:** REQ §3: el broker no ve datos financieros detallados.
- **Impacto:** …
- **Corrección sugerida:** …
- **Esfuerzo estimado:** pequeño / mediano / grande.
```
**Escala de severidad (decidida):**
- **Crítica:** acceso sin sesión a datos personales o documentos; tomar la cuenta de otro; ejecución de código.
- **Alta:** un usuario ve o cambia datos de otro alcance (BOLA/BFLA); salto de autenticación del comprador; secreto real filtrado.
- **Media:** exposición de campos de más dentro del propio alcance; límites de consumo que se saltan; enumeración de usuarios; falta de una cabecera que importa.
- **Baja:** endurecimiento (cabeceras menores, mensajes, configuración de producción ausente).
- **Informativa:** buena práctica o algo que solo aplica al desplegar.

## 6. Entregas por parte (una por reporte, como siempre)
| Parte | Entrega | Commit propuesto |
| --- | --- | --- |
| Preparación + 1 | `backend/security/seed_actors.py`, `docs/seguridad/01-automatico.md`, hallazgos iniciales | `docs(security): add the automated security scan results` |
| 2 | `docs/seguridad/02-dinamico.md` | `docs(security): add the dynamic API scan results` |
| 3 | `tests/security/` (matriz y casos), `render_matrix.py`, `03-matriz-acceso.md` | `test(security): add the role access matrix for every API operation` |
| 4 | pruebas de la Parte 4, `04-manual.md` | `test(security): add manual security checks for auth, files and business rules` |
| 5 | CI, `.gitleaks.toml`, `docs/SEGURIDAD.md`, `backend/security/README.md` | `ci(security): add pip-audit, gitleaks and bandit to the backend CI` y `docs(security): add the security overview and findings` |

Cada reporte trae además: **hallazgos nuevos** de la parte (id, título, severidad), versiones de las herramientas y, en el último, el conteo final por severidad y **la lista para la Fase B** ordenada por severidad y esfuerzo.

## 7. Fase B — Corrección (la escribe el orquestador, no tú)
Criterio ya decidido con Carlos:
- **Crítica y Alta:** se corrigen todas antes de cerrar el proyecto.
- **Media:** se corrige si el esfuerzo es pequeño; si no, queda `aceptado` con el motivo en `docs/SEGURIDAD.md`.
- **Baja e Informativa:** se documentan; se corrigen solo si son de una línea.
- Cada corrección quita su `xfail` o su entrada de la `allowlist` y actualiza la tabla de `docs/SEGURIDAD.md`.

## Precisiones acordadas
(El agente agrega aquí lo que decida durante la tarea.)

**Preparación y Parte 1 (2026-11-18):**
- **P1. `check --deploy` con `base`:** con solo `DJANGO_DEBUG=False` y `config.settings.base`, la API no arranca (el almacenamiento en disco solo se admite con `DEBUG`). Se agregan `-e DOCUMENT_STORAGE_BACKEND=s3 -e DOCUMENT_SCANNER=clamd`, los valores de producción; el `check` no se conecta a ellos. Además se corrió con `local` para mostrar que `DJANGO_DEBUG=False` no tiene efecto (SEC-01).
- **P2. pip-audit dos veces:** contra `requirements.txt` (lo que resolvería el CI) y contra el `pip freeze` de la imagen (`--no-deps --disable-pip`, lo que corre de verdad). Si difieren, manda el de la imagen; hoy dan lo mismo.
- **P3. semgrep:** solo reglas de la comunidad (188); las *pro* piden cuenta en semgrep.dev y no se usan.
- **P4. Comprador A = `SOL-000013`** (de asesora.lucia, en `WAITING_DOCUMENTS`), no la del enlace que imprime `seed_demo_data` (`SOL-000012`, que el reparto deja a andrés). Así A es del lado de Lucía y B (`SOL-000034`, de `seed_actors.py`) del de Andrés, como pide la matriz.
- **P5. `seed_actors.py`:** reutiliza `_build_case` de la demo (servicios del dominio, con historial); clientes con prefijo de documento `9901` (la demo usa `9900`); la idempotencia se decide por ese prefijo. La oportunidad del broker B queda asignada a Andrés. El proyecto de la constructora lo crea y aprueba el admin (`DRAFT → PENDING_REVIEW → ACTIVE`).
- **P6. Sesiones:** se guardan como cabecera `Cookie` lista para usar (`_security-work/sessions/<actor>.cookie`) y el CSRF aparte (`.csrf`): en local las cookies no llevan `Secure` ni `__Host-`. El acceso dura 15 min: antes de cada escaneo de la Parte 2 se vuelve a hacer login.
- **P7. Claves locales:** solo se midió su longitud (nunca el valor). La JWT local de 31 bytes es un hallazgo de control faltante (SEC-03), no de secreto filtrado: no está en git.

**Parte 2 (2026-11-18):**
- **P8. Base restaurable:** plantilla `mvp_credit_sec_tpl` (copia de `mvp_credit_sec` tras la preparación). Antes de cada corrida que escribe se restaura desde ella y se vuelve a hacer login.
- **P9. Acceso de 120 min en el 8010:** el contenedor de auditoría se recrea con `-e AUTH_ACCESS_TOKEN_MINUTES=120` (solo esa variable, solo ese contenedor) para que la cookie no venza a mitad de un escaneo.
- **P10. Ids reales:** schemathesis (`st.toml`, `[parameters]`) y ZAP (copia del contrato con las rutas ya resueltas) usan ids del lado A (de Lucía, `SOL-000033`); sin eso todo daba 404.
- **P11. `--url` de schemathesis** = `http://mvp-sec-api:8000` (las rutas del contrato ya traen `/api/v1`). Fase `stateful` apagada (podía desactivar o cambiar el rol del usuario de la corrida). Excluidas en todas las corridas: `logout`, `change-password`, `refresh` (su reuso revoca la sesión), `buyer/session/logout`, `users/{id}/deactivate`, `users/{id}/roles`, `PATCH users/{id}`, `DELETE partner-memberships/{id}`.
- **P12. Corrida sin sesión acotada:** con `-n 25` pasó de 46 min; se repitió con `-n 10 --max-time 1080` (18 min).
- **P13. ZAP:** pasivo = `-S`; activo = sin `-S`, política por defecto, `scanner.maxScanDurationInMins=15`. `globalexcludeurl` no frena las peticiones de la importación del contrato (el primer pasivo hizo `logout`): las exclusiones se aplican quitando esas operaciones de la copia del contrato.
- **P14. Servidor sin `DEBUG` de un solo uso** (`mvp-sec-api-prod`, `:8011`, `config.settings.base`, `AUTH_COOKIE_SECURE=True`, `s3`/`clamd`) para ver errores, cabeceras y cookies como en producción. Se borró al terminar la parte.
- **P15. Severidades de la Parte 2:** los ST401/ST201 de las corridas con sesión son artefacto (cookie `__Host-` del contrato frente a `app_access` local) y se descartan; manda la corrida sin sesión. El HTML de depuración con 5 MB es Informativa (solo con `DEBUG`); el 500 sin `DEBUG` es Baja (SEC-11).

**Parte 3 (2026-11-18):**
- **P16. El mundo usa los constructores de la demo**, no los fixtures de `tests/applications`: esos son de alcance de función y viven por carpeta; un mundo por caso (2106 casos) no entra en 3 minutos. Los constructores (`_build_case`, `_file_and_respond`, `seed_plans`, `seed_tasks`) ya son los servicios del dominio, así que no se duplica ninguna fábrica. Se reutiliza `MAX_LTV_CONDITION` de `tests/banking/conftest.py`.
- **P17. Alcance de paquete** (`tests/security`), dentro de una transacción externa marcada `_from_testcase` (como las de `TestCase`, para que la auditoría se comporte igual que en producción) y revertida al final; cada caso tiene su punto de guardado. Las llaves foráneas diferidas del mundo se verifican una vez (`check_constraints`): sin eso cada caso tardaba ~105 ms en vez de ~30. El `_clear_document_storage` raíz se reemplaza por uno vacío (los archivos del mundo viven todo el paquete).
- **P18. Lado A / lado B:** por lado, cuatro solicitudes (aprobada con portal, desembolsada y liquidada, lista para radicar con paquete, borrador). Rutas siempre con ids del lado A; `job_id` según la ruta (paquete o exportación); `catalog_code` = `contract_type` (lo entregan las dos rutas de metadatos); `user_id` = un usuario "objetivo" que no es ningún actor.
- **P19. Petición mínima:** cuerpo `{}` (multipart con un PDF en las dos cargas), siempre `If-Match: "1"` e `Idempotency-Key` nuevo. Por eso `412` y `428` cuentan como `ALLOW`, igual que 400/409/422. La matriz no manda cookie de refresh (`/auth/refresh` es 401 para todos; la rotación es de la Parte 4).
- **P20. Notación:** una cadena de 9 letras por fila (`A`/`U`/`F`/`H`, orden fijo de actores) con 15 patrones con nombre y su fuente. Lo que la documentación no define queda en `GENERAL_RULE_DECISIONS` (9 casos).
- **P21. API §25 frente a §12 en proyectos:** el asesor edita proyectos (`projects.update` en §12, permisos sembrados, RF-17 y `update_project`); §25 dice "lectura relacionada". Se toma §12: no es brecha.
- **P22. Ids ajenos en el cuerpo:** cada caso se prueba con tres valores: el id propio (debe pasar la validación del id), el del lado B y uno inexistente; el del lado B debe responder igual que el inexistente (estado y código), nombrar el campo en `details` y nunca 2xx. Los campos de la spec que no existen en ningún cuerpo del contrato (`participant_id`, `filing_id`, `slot_id`, `assigned_to`, `beneficiary_user_id`) quedan vigilados por una prueba.
- **P23. Asignar a otro asesor una tarea de una solicitud propia** está permitido por API §15 (`assigned_to_id`: ADMIN o ADVISOR activo); queda fijado en una prueba, no es brecha.
