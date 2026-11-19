# Auditoría de seguridad — Parte 2: análisis dinámico

Pruebas contra la API corriendo, solo en local: el servidor de auditoría `mvp-sec-api`
(`:8010`, base `mvp_credit_sec`, `DEBUG=True` como pide la spec) y, para ver la respuesta
real de producción, un segundo servidor de un solo uso `mvp-sec-api-prod` (`:8011`, misma
base, `config.settings.base`, `DEBUG=False`, `AUTH_COOKIE_SECURE=True`). Todo el
2026-11-18. Los reportes crudos están fuera del repo, en `_security-work/`.

Los hallazgos están en [`hallazgos.md`](hallazgos.md). Esta parte abre **7**: 3 Medias, 3
Bajas y 1 Informativa. Ninguno es Crítico ni Alto: **sin sesión, ninguna de las 209
operaciones protegidas que se probaron respondió 2xx**, y ni schemathesis ni ZAP
encontraron inyecciones.

| Id | Título | Severidad |
| --- | --- | --- |
| SEC-07 | `OPTIONS` responde 500 en 27 rutas, una de ellas pública (`/invitations/accept`) | Baja |
| SEC-08 | Las respuestas con datos personales no llevan `Cache-Control: no-store` (ni `Vary: Cookie`) | Media |
| SEC-09 | El límite de login y de recuperación se salta con otros correos o con otras IP | Media |
| SEC-10 | No existen los límites generales por usuario que piden REQ §9.3 y API §26 | Media |
| SEC-11 | Un JSON de más de 2,5 MB responde 500 (sin `DEBUG`) o la página de depuración (con `DEBUG`), no 413 | Baja |
| SEC-12 | Las rutas inexistentes y los ids que no son UUID responden HTML de Django, no el formato de error de la API | Baja |
| SEC-13 | El contrato no coincide con la API en 2 respuestas y no documenta varios estados | Informativa |

Además, la cabecera `Server: WSGIServer/0.2 CPython/3.11.18` (ZAP 10036) se suma a
**SEC-06** (es de `runserver`).

## Cómo se preparó

- **Base restaurable:** después de la preparación se copió `mvp_credit_sec` como plantilla
  (`CREATE DATABASE mvp_credit_sec_tpl TEMPLATE mvp_credit_sec`). Antes de cada corrida que
  escribe (las cuatro de schemathesis, los dos ZAP, los límites) se restauró la base desde
  la plantilla y se volvió a hacer login: cada corrida empieza con los mismos datos.
- **Duración del acceso:** el servidor 8010 se recreó con `-e AUTH_ACCESS_TOKEN_MINUTES=120`
  (solo en el contenedor de auditoría) para que la cookie de acceso no venza a mitad de un
  escaneo de 15 minutos.
- **Ids reales:** los parámetros de ruta se fijaron con ids del **lado A** (de
  `asesora.lucia`: la solicitud `SOL-000033`, aprobada, con participantes, perfil, ingresos,
  slots, archivo, radicación, respuesta, tarea, notificación, enlace, cliente, oportunidad,
  paquete). Sin eso, casi todo daba 404 por id inventado. Los que no tenían objeto en la
  demo (`rule_id`, `address_id`, `settlement_id`, `share_id`, `invitation_id`) quedaron
  aleatorios.
- **Operaciones excluidas** en todas las corridas (8 de 234): `POST /auth/logout`,
  `POST /auth/change-password`, `POST /auth/refresh` (rota el refresh y su reuso revoca la
  sesión de la corrida), `POST /buyer/session/logout`, `POST /users/{id}/deactivate`,
  `PUT /users/{id}/roles`, `PATCH /users/{id}` y `DELETE /partner-memberships/{id}`.

## 1. schemathesis

Herramienta: schemathesis **4.33.4**, instalado con `pip` en una imagen de un solo uso
basada en la del backend (`mvp-sec-tools:schemathesis-4.33.4`), en la red del compose.

```
schemathesis --config-file /w/st.toml run /contracts/openapi.json --url http://mvp-sec-api:8000 \
  --checks all -n 25 --workers 1 --phases examples,coverage,fuzzing --seed 20261118 \
  --request-timeout 30 --exclude-operation-id <las 8 de arriba> \
  -H "Cookie: <sesión>" -H "X-CSRFToken: <csrf>" --report junit,ndjson --output-sanitize true
```

- `--url` es el origen (`http://mvp-sec-api:8000`), no `.../api/v1`: las rutas del contrato
  ya incluyen `/api/v1`.
- `st.toml` solo tiene los ids del lado A (`[parameters]`, `"path.application_id" = …`).
- La fase `stateful` quedó apagada: encadena respuestas con operaciones y podía llegar a
  desactivar o cambiar el rol del propio usuario de la corrida.
- Cookies y CSRF van filtrados en los reportes (`[Filtered]`).

| Corrida | Casos | Fallas únicas | Duración | 5xx |
| --- | --- | --- | --- | --- |
| admin | 3 866 | 322 | 6,5 min | 6 (`OPTIONS`) |
| asesora.lucia | 8 368 | 220 | 12,3 min | 5 (`OPTIONS`) |
| broker | 14 630 | 72 | 14,8 min | 2 (`OPTIONS`) |
| sin sesión | 15 170 | 19 | 18 min (acotada) | 1 (`OPTIONS`, pública) |

**Corrida sin sesión acotada:** la primera, con `-n 25`, llevaba **46 minutos** cuando se
cortó (la fase de cobertura sola tardó 9 min y el *fuzzing* seguía). Se repitió con `-n 10` y
`--max-time 1080` (18 min de tope). Su log incompleto quedó como
`st_anon_cortada_46min.log`.

### Clasificación por tipo de resultado

| Check | admin | lucia | broker | anon | Clasificación |
| --- | --- | --- | --- | --- | --- |
| `ST101` Server error | 6 | 5 | 2 | 1 | **hallazgo SEC-07**: todos son `OPTIONS` y fallan con `AssertionError` de DRF |
| `ST401` acepta sin autenticación / con autenticación inválida | 59 / 65 | 34 / 46 | 4 / 7 | 0 / 0 | descartado: artefacto. El contrato declara la cookie `__Host-app_access`; schemathesis la quita o la altera, pero en local la cookie se llama `app_access` (sin prefijo) y va fija en `-H Cookie`, así que la petición sigue autenticada. La corrida sin sesión es la que mide esto: **0** |
| `ST201` acepta datos que violan el esquema | 59 | 34 | 4 | 0 | descartado: los 97 son el mismo artefacto ("Missing `__Host-app_access` at cookie") |
| `ST103` código de estado no documentado | 66 | 51 | 35 | 0 | **SEC-13** (Informativa): `400` de reglas de negocio y `404` sin documentar |
| `ST105` `Content-Type` no documentado | 13 | 13 | 13 | 13 | **SEC-12**: `404` en `text/html` cuando el id de la ruta no es un UUID |
| `ST108` respuesta fuera del esquema | 1 | 1 | 2 | 0 | **SEC-13**: `GET /applications/{id}/available-actions` devuelve una lista y el contrato dice página; `GET /clients` del broker devuelve `document_type: "CC"` y el contrato dice objeto |
| `ST202` rechaza datos válidos según el esquema | 47 | 30 | 5 | 5 | descartado: validaciones de negocio (`400`/`422`) que el esquema no puede expresar (fechas, estados, montos); no son de seguridad |
| `ST203` acepta sin cabecera obligatoria | 6 | 6 | 0 | 0 | descartado como seguridad: sin `If-Match` la API responde `428 PRECONDITION_REQUIRED`, que es lo correcto; el contrato no lo documenta (va en SEC-13) |

### Qué se buscaba, punto por punto

- **Cualquier 500:** solo los de `OPTIONS` (SEC-07). Ninguno con `GET`, `POST`, `PUT`,
  `PATCH` ni `DELETE` en ~42 000 casos. schemathesis solo prueba `OPTIONS` en algunas
  operaciones (6 vistas); un barrido aparte con `OPTIONS` a las 175 rutas del contrato dio
  **27 rutas con 500 como admin** (todas las vistas genéricas de DRF con escritura y sin
  `serializer_class`: `/applications`, `/clients`, `/users`, `/banks`, `/tasks`…) y **1 sin
  sesión** (`/invitations/accept`). Lista en `_security-work/options_500_admin.txt`.
- **2xx donde el rol no debía tener acceso:**
  - *sin sesión:* las 209 operaciones protegidas dieron **solo 401**. Las 17 restantes son
    las 5 públicas (`login`, `password-reset-requests`, `password-resets/confirm`,
    `buyer-access/consume`, `invitations/accept`) y 12 con un id sin objeto en la demo, que
    Django corta con `404` antes de llegar a la vista (SEC-12).
  - *broker:* 2xx solo en `GET /applications`, `/applications/quick-filters`, `/auth/me`,
    `/broker/opportunities`, `/clients`, `/me/commissions`, `/metadata/*`, `/opportunities`,
    `/projects` y `/projects/{id}`. Sobre los ids del lado A (de Lucía), todo 403/404.
  - *asesora:* 2xx en la solicitud de la que es dueña y en catálogos de solo lectura; 403 en
    las 61 de administración (usuarios, roles, catálogos, bancos, planes de comisión,
    auditoría…) y 401 en las 32 del portal del comprador. Sin sorpresas frente a API §25.
  - La matriz completa (operación × actor, con dueño y no dueño) es la Parte 3.
- **Campos de más en la respuesta:** schemathesis no los detecta (el contrato no declara
  `additionalProperties: false`). Revisión a mano del broker: `document_number` llega
  enmascarado (`••••••0027`) en `/clients` y `/applications`; no hay montos ni archivos. La
  comprobación campo por campo (`FORBIDDEN_FIELDS_BY_ACTOR`) es la Parte 3.

## 2. OWASP ZAP

ZAP **2.17.0** (`zaproxy/zap-stable:2.17.0`, `sha256:9624669db72f…`), `zap-api-scan.py`,
con la sesión de admin inyectada con el *replacer* (cabeceras `Cookie` y `X-CSRFToken`).

```
zap-api-scan.py -t /zap/wrk/openapi_zap.json -f openapi -O http://mvp-sec-api:8000 [-S] -I \
  -r zap_<modo>.html -J zap_<modo>.json \
  -z "-config replacer.full_list(0)…matchstr=Cookie… -config replacer.full_list(1)…matchstr=X-CSRFToken… \
      -config scanner.maxScanDurationInMins=15 -config scanner.maxRuleDurationInMins=3"
```

- **Pasivo** = con `-S` (modo seguro: importa el contrato, hace cada petición una vez y solo
  analiza). **Activo** = sin `-S`, con la política por defecto.
- **Primer pasivo inválido:** `globalexcludeurl` no aplica a las peticiones que ZAP arma al
  importar el contrato, y ZAP llamó `POST /auth/logout`: la sesión de admin murió a mitad del
  escaneo (sus resultados quedaron como `zap_passive_invalida_logout.*` y no se usan). Se
  repitió con una copia del contrato **sin las 8 operaciones excluidas y con los ids reales
  del lado A en las rutas** (`_security-work/scripts/zap_spec.py`). Al terminar, la sesión de
  admin seguía viva (`GET /auth/me` → 200) en los dos escaneos.

| Escaneo | Peticiones | Duración | Alertas |
| --- | --- | --- | --- |
| Pasivo | 244 URL importadas | 52 s | 6 avisos, 0 FAIL, 115 PASS |
| Activo | ~72 000 (200: 1 806 · 400: 47 544 · 401: 6 416 · 404: 6 147 · 429: 7 400 · ningún 5xx) | 16 min | las mismas 6, **ninguna nueva** |

El escaneo activo no encontró inyección SQL, XSS, inyección de comandos, *path traversal*,
SSRF ni inclusión de archivos. Sus pruebas de cabecera `Host` con direcciones de metadatos de
nube (`169.254.169.254`, `metadata.google.internal`…) las rechazó `ALLOWED_HOSTS`
(`DisallowedHost`, 400).

| Alerta (id) | Riesgo ZAP | Instancias | Clasificación |
| --- | --- | --- | --- |
| Content Security Policy no definida (10038) | Medium | 5 | descartado para la API: las respuestas son JSON con `nosniff` y `X-Frame-Options: DENY`; CSP protege HTML. Las páginas HTML del backend (`/docs`, `/admin/`) se revisan en la Parte 4 (punto 9) |
| Permissions-Policy no definida (10063) | Low | 5 | descartado: mismo motivo |
| Cross-Origin-Resource-Policy ausente (90004) | Low | 5 | descartado: CORS ya limita quién lee las respuestas con credenciales (punto 3) |
| `Server` revela versión (10036) | Low | 5 | se suma a **SEC-06**: `WSGIServer/0.2 CPython/3.11.18` es `runserver` |
| *Unexpected Content-Type* (100001) | Low | 13 / 415 | **SEC-12**: los `404` en HTML |
| *Private IP Disclosure* (2) | Low | 1 | descartado: `GET /audit-events/{id}` (solo admin) muestra la IP del actor, que es lo que la auditoría debe guardar |
| *Sensitive Information in URL* (10024) | Info | 3 | descartado: son filtros de listados (`actor_user_id`, `email` de `/invitations`) para el admin |
| *Storable and Cacheable Content* (10049) | Info | 4 | **SEC-08**: confirma que respuestas con datos personales (perfil financiero, participantes) se pueden guardar en caché |

## 3. Cabeceras, CORS y cookies

Con `curl` 8.23.0 (`curlimages/curl:8.23.0`) desde la red del compose, contra el 8010 y el 8011.

**Cabeceras de seguridad** (iguales en los dos):

| Cabecera | Resultado |
| --- | --- |
| `X-Content-Type-Options: nosniff` | ✓ en todas |
| `Referrer-Policy: same-origin` | ✓ en todas |
| `X-Frame-Options: DENY` | ✓ en todas las de la API; `Cross-Origin-Opener-Policy: same-origin` también |
| `Cache-Control: no-store` | ✓ en `/buyer/session`, `/document-files/{id}/download`, `/document-package-jobs/{id}/download` y la descarga del objeto firmado (`storage_views.py`). ✗ en `/auth/me`, `/users`, `/applications/{id}`, `/clients/{id}`, `/application-participants/{id}/financial-profile` y en el CSV de `/reports/applications.csv`. Tampoco llevan `Vary: Cookie` (solo `Vary: origin`) → **SEC-08** |
| `Strict-Transport-Security` | ✗ en los dos: solo aplica con HTTPS → ya está en **SEC-02** |

**CORS** (preflight `OPTIONS` a `/auth/login` y `GET /auth/me` con cookie de admin, por
cada `Origin`):

| `Origin` | `Access-Control-Allow-Origin` | `Allow-Credentials` |
| --- | --- | --- |
| `http://evil.example` | — (no se refleja) | — |
| `null` | — | — |
| `http://localhost:3000.evil.example` | — | — |
| `https://localhost:3000` (otro esquema) | — | — |
| `http://localhost:3000` | `http://localhost:3000` | `true` |
| `http://localhost:3001` | `http://localhost:3001` | `true` |

Nunca se refleja un origen fuera de la lista. `localhost:3001` está permitido por el
`CORS_ALLOWED_ORIGINS` del `.env` local (no se abrió el archivo: se ve en la respuesta); en
producción la lista debe tener solo el dominio del frontend. Sin hallazgo.

**Cookies:**

| Cookie | 8010 (local) | 8011 (producción: `AUTH_COOKIE_SECURE=True`) |
| --- | --- | --- |
| acceso | `app_access`; `HttpOnly; Path=/; SameSite=Lax`; sin `Secure` | `__Host-app_access`; `HttpOnly; Path=/; SameSite=Lax; Secure` |
| refresh | `app_refresh`; igual, `Max-Age=28800` (8 h) | `__Host-app_refresh`; `HttpOnly; Path=/; SameSite=Lax; Secure` |
| comprador | `buyer_session`; `HttpOnly; Path=/; SameSite=Lax`, `Max-Age=86400` (24 h) | con el prefijo `__Host-` por el mismo código (`cookies.py`) |
| CSRF | `app_csrf`; legible por JavaScript **por diseño** (el frontend la copia en `X-CSRFToken`); `SameSite=Lax`, 1 año | `app_csrf`; `Secure; SameSite=Lax` |

El acceso dura 15 min por defecto (aquí 120 por la variable del contenedor de auditoría). En
local, sin `Secure` ni `__Host-`, es lo esperado (`local.py`); el riesgo de que eso llegue a
producción es **SEC-01**. Sin hallazgo nuevo.

## 4. Límites de consumo

Script `_security-work/scripts/rate_limits.py` (Python estándar, en la imagen del backend,
red del compose). Caché limpia antes de cada grupo.

| Flujo | Configurado (`AUTH_RATE_LIMITS`) | Medido | `Retry-After` |
| --- | --- | --- | --- |
| Login, mismo correo | `5/15m`, clave IP + correo | 5 × 401 y la 6.ª → 429 (igual con correo existente o inexistente) | `900` ✓ |
| Recuperación (`password-reset-requests`) | `3/1h`, IP + correo | 3 × 202 y la 4.ª → 429 | `3600` ✓ |
| Confirmación del restablecimiento | `10/15m`, IP | 10 × 400 y la 11.ª → 429 | `900` ✓ |
| Consumo del enlace mágico | `5/1h`, IP | 5 × 401 y la 6.ª → 429 | `3600` ✓ |
| Emisión del enlace | `3/1h`, usuario + solicitud | 3 × 201 y la 4.ª → 429 | `3600` ✓ |
| Carga de documentos del comprador | `60/1h`, sesión + solicitud | 60 × 422 (archivo inválido) y la 61.ª → 429 | `3597` ✓ |
| Descarga | `60/1h`, usuario o sesión | 60 × 200 y la 61.ª → 429 | `3597` ✓ |
| Dashboard y reportes | `20/1m`, usuario | 20 × 200 y la 21.ª → 429 | `59` ✓ |

**Intentos de saltar el límite** sobre el correo ya bloqueado:

| Variante | Resultado |
| --- | --- |
| Correo en MAYÚSCULAS | 429 ✓ (`normalize_email` pasa todo a minúsculas) |
| Correo con espacios alrededor | 429 ✓ (`normalize_email` hace `strip`) |
| `X-Forwarded-For` distinto | 429 ✓ (`NUM_PROXIES=0`: se ignora) |
| `X-Real-IP` distinto | 429 ✓ |
| Otro `User-Agent` | 429 ✓ |
| `+alias` en el correo | 401: es otro correo (no existe), no otra forma del mismo |
| **12 correos distintos desde la misma IP** (rociado de contraseñas) | 12 × 401, ningún 429 → **SEC-09** |
| **El mismo correo desde otra IP** (segundo contenedor, `172.20.0.5` y `172.20.0.6`) | otros 5 intentos en cada IP; después, la contraseña correcta desde una tercera IP → **200** → **SEC-09** |
| Recuperación con 6 correos distintos desde la misma IP | 6 × 202 → **SEC-09** |

**El 429 no revela si el usuario existe:** el cuerpo es el mismo para un correo existente y
uno inexistente (`RATE_LIMITED`, "Solicitud fue regulada (throttled). Se espera que esté
disponible en N segundos."); solo cambia N. Los 401 previos también son idénticos
(`INVALID_CREDENTIALS`).

**Límites generales** (REQ §9.3 y API §26: 120 escrituras/min, 600 lecturas/min, 20 cambios
de estado o radicaciones/min por usuario): como Lucía, **150 `POST /clients` en 4 s → 150 ×
400, ningún 429**; **650 `GET /clients` en 33 s → 650 × 200**. El ZAP activo hizo ~72 000
peticiones como admin en 16 min (~75 por segundo) y solo lo frenaron los límites
específicos. `REST_FRAMEWORK` no tiene `DEFAULT_THROTTLE_CLASSES` → **SEC-10**.

## 5. Errores

Script `_security-work/scripts/errors.py`, contra el 8010 (con `DEBUG`) y el 8011 (sin
`DEBUG`). "Fuga" busca trazas, rutas (`/app/`, `/usr/local`, `site-packages`), SQL,
`psycopg` y nombres de variables de configuración en el cuerpo.

| Caso | 8010 (`DEBUG`) | 8011 (sin `DEBUG`) |
| --- | --- | --- |
| Ruta inexistente `/api/v1/no-existe` | 404 HTML de depuración (lista de rutas) | 404 HTML de Django, 179 bytes, sin fuga → **SEC-12** |
| Id que no es UUID `/applications/abc` | 404 HTML de depuración | 404 HTML → **SEC-12** |
| UUID inexistente | 404 `RESOURCE_NOT_FOUND` ✓ | igual ✓ |
| `DELETE /auth/me` | 405 `METHOD_NOT_ALLOWED` ✓ | igual ✓ |
| Login con `text/plain` | 415 `UNSUPPORTED_MEDIA_TYPE` ✓ | igual ✓ |
| JSON roto / con `NaN` | 400 `MALFORMED_REQUEST` ✓ | igual ✓ |
| `Accept: application/xml` | 406 `NOT_ACCEPTABLE` ✓ | igual ✓ |
| **JSON de 5 MB** (login sin sesión, y `POST /clients` con sesión) | 400 HTML de depuración de `RequestDataTooBig`, con traza y rutas | **500 `INTERNAL_ERROR`** (sin fuga, pero un error no controlado en el log por petición) → **SEC-11** |
| Multipart de 11 MB a una carga | 413 `PAYLOAD_TOO_LARGE` ✓ (`DOCUMENT_UPLOAD_MAX_REQUEST_BYTES`) | igual ✓ |
| `POST` con sesión sin `X-CSRFToken` | 403 `CSRF_FAILED` ✓ | igual ✓ |
| `?page=abc` | 404 `RESOURCE_NOT_FOUND` ✓ | igual ✓ |
| `?page_size=100000` | 200 con `page_size: 100` (tope `max_page_size`) ✓ | igual ✓ |
| `?ordering=password` en `/users` | 400 `VALIDATION_ERROR` ✓ | igual ✓ |
| `OPTIONS /invitations/accept` sin sesión | 500 HTML de depuración | 500 `INTERNAL_ERROR` → **SEC-07** |

**Límite de tamaño del cuerpo:** `DATA_UPLOAD_MAX_MEMORY_SIZE` no se cambia en `base.py`, así
que vale el de Django (2,5 MB) y **sí corta** el JSON de 5 MB; el problema es el código de
respuesta (SEC-11). Las cargas tienen su propio límite y responden bien (413). El salto del
límite con un `charset` de compresión es SEC-04 (Parte 1).

## Observaciones de la Parte 1, cerradas

- **Login por IP con correos distintos** → es lo documentado (API §26: "IP + correo
  normalizado"), pero deja pasar el rociado de contraseñas y el ataque distribuido a una
  cuenta, contra lo que pide REQ §9.3 ("protección reforzada contra fuerza bruta y
  *credential stuffing*", "demora progresiva") → **SEC-09**.
- **HTML de depuración con 5 MB** → con `DEBUG` es Informativa (solo local); sin `DEBUG` es
  un 500 → **SEC-11** (Baja).

## Notas para las partes siguientes

- Al recrear el 8010 (para el acceso de 120 min) se perdieron los archivos de la demo: el
  almacenamiento en disco vivía dentro del contenedor y la base los sigue nombrando (la
  descarga del objeto firmado da 404). Para las pruebas de archivos de la Parte 4 se vuelve
  a crear el 8010 con un volumen propio y se siembra otra vez.
- `/openapi.json`, `/docs` y `/admin/login/` responden sin sesión también sin `DEBUG`
  (8011): se clasifican en la Parte 4 (punto 9).
- `OPTIONS` con sesión devuelve los metadatos de DRF (nombre de la vista, *renderers*,
  *parsers*), sin los campos de los serializers: información mínima, anotada en SEC-07.
