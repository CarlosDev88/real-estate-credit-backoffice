# Auditoría de seguridad — Parte 3: matriz de acceso (BOLA / BFLA)

> Documento generado por `backend/security/render_matrix.py` desde
> `backend/tests/security/access_matrix.py`. No se edita a mano.

**Qué se probó:** que nadie vea ni toque lo que no le corresponde (OWASP API1:2023 *Broken
Object Level Authorization* y API5:2023 *Broken Function Level Authorization*). Cada una
de las 236 operaciones del contrato se pide como cada uno de los 9 actores, sobre
los recursos del **lado A**, y se compara el estado con lo esperado: **2124 casos**.

**Resultado:** **ninguna brecha.** Todas las operaciones responden lo esperado para los 9 actores. Además, en las respuestas permitidas al broker y al comprador
se comprueba que no lleguen campos prohibidos (montos detallados, archivos y URL firmadas,
notas y comentarios internos) y que el documento del cliente llegue enmascarado al broker.

**Cómo se repite:** `pytest tests/security` (en el CI corre con el resto de la suite).
Son 2150 pruebas (la matriz, su cobertura del contrato y los casos explícitos); en local
tardan ~75 s con la base de pruebas ya creada, de los que ~18 s son la construcción del
mundo.

## Los actores

| Actor | Quién es en el mundo de prueba |
| --- | --- |
| `anon` | Sin sesión. |
| `admin` | `admin@demo.local` (`ADMIN`). |
| `advisor_owner` | `asesora.lucia@demo.local`, asesora asignada a las solicitudes del lado A. |
| `advisor_other` | `asesor.andres@demo.local`, asesor del lado B. |
| `broker_owner` | `broker@demo.local`, originó las oportunidades del lado A. |
| `broker_other` | `broker.b@demo.local`, originó las del lado B. |
| `partner` | `constructora@demo.local` (`CONSTRUCTION_PARTNER`), de la constructora del lado A. |
| `buyer_owner` | Sesión del comprador de la solicitud A. |
| `buyer_other` | Sesión del comprador de la solicitud B. |

El mundo (`backend/tests/security/conftest.py`) tiene dos de cada cosa, una por lado, creada
con los servicios del dominio: clientes, oportunidades, solicitudes radicada, desembolsada,
lista para radicar y en borrador, participantes, perfiles e ingresos, inmueble y
financiación, slots con archivos, paquete, radicación, respuestas con evidencia,
notificaciones, tareas, notas, enlace y sesión del comprador con consentimientos,
liquidación de comisión con sus partes, exportación de reportes y dos constructoras con un
proyecto activo cada una.

## Cómo leer la tabla

- **✓** = permitido: 2xx, o un 4xx de negocio que muestra que pasó la autorización
  (400, 409, 412, 422, 428). En las escrituras basta con eso: el efecto lo prueban los
  módulos.
- **✗ 401** = sin sesión válida para esa ruta (las rutas internas leen la cookie interna y
  las del portal, la del comprador).
- **✗ 403** = con sesión, sin el permiso del rol.
- **✗ 404** = con permiso, pero el recurso está fuera de su alcance: no confirma que existe
  (API §3).
- **⚠ SEC-NN** = brecha conocida: la prueba está marcada `xfail(strict=True)`.

Fuentes de lo esperado, en este orden: REQ §3 (si choca con la API, manda REQ), API §3,
API §25 y la sección de cada módulo, y el `required_permissions` de cada vista con los
permisos sembrados por rol.

## Resumen por actor

| Actor | ✓ | ✗ 401 | ✗ 403 | ✗ 404 |
| --- | --- | --- | --- | --- |
| `anon` | 7 | 229 | 0 | 0 |
| `admin` | 201 | 33 | 2 | 0 |
| `advisor_owner` | 129 | 33 | 74 | 0 |
| `advisor_other` | 54 | 33 | 74 | 75 |
| `broker_owner` | 38 | 33 | 165 | 0 |
| `broker_other` | 23 | 33 | 162 | 18 |
| `partner` | 20 | 33 | 183 | 0 |
| `buyer_owner` | 39 | 197 | 0 | 0 |
| `buyer_other` | 13 | 197 | 0 | 26 |

## Patrones

Cada fila de la matriz usa uno de estos patrones (una letra por actor: `A` permitido,
`U` 401, `F` 403, `H` 404, en el orden de la tabla).

| Patrón | Letras | Operaciones | Razón |
| --- | --- | --- | --- |
| `PUBLIC` | `AAAAAAAAA` | 7 | Sin sesión: cualquiera llega a la validación (API §3 `PUBLIC`). |
| `NO_REFRESH_COOKIE` | `UUUUUUUUU` | 1 | Sin cookie de refresh: 401 para todos. |
| `ANY_INTERNAL` | `UAAAAAAUU` | 6 | Cualquier usuario interno con sesión. |
| `ADMIN_ONLY` | `UAFFFFFUU` | 71 | Solo administración (API §25). |
| `ADMIN_ADVISOR` | `UAAAFFFUU` | 27 | Administrador y asesor, sin alcance por objeto. |
| `ADMIN_ADVISOR_PARTNER` | `UAAAFFAUU` | 5 | Además la constructora sobre lo de su partner (API §11 y §12). |
| `ADMIN_PARTNER` | `UAFFFFAUU` | 2 | Administrador y la constructora dueña (API §11.2). |
| `INTERNAL_NO_PARTNER` | `UAAAAAFUU` | 8 | Listados con alcance; la constructora no ve expedientes (REQ §3). |
| `ASSIGNED` | `UAAHFFFUU` | 57 | Asesor asignado; otro asesor 404; broker y constructora 403 (REQ §3, API §25). |
| `ASSIGNED_OR_ORIGINATED` | `UAAHAHFUU` | 15 | Además el broker originador (resumen y seguimiento, REQ §3); los otros, 404. |
| `ORIGINATED_NO_FILES` | `UAAHFHFUU` | 3 | Archivos o enlace ajeno: broker originador 403, otro broker 404. |
| `BROKER_ONLY` | `UFFFAAFUU` | 1 | Solo brokers, cada uno lo suyo. |
| `OWN_COMMISSIONS` | `UFAAAAFUU` | 1 | Asesor y broker, solo su parte (API §25). |
| `BUYER_SESSION` | `UUUUUUUAA` | 6 | Cualquier sesión de comprador, sobre lo suyo. |
| `BUYER_OWN` | `UUUUUUUAH` | 26 | Recurso del comprador A: el comprador B, 404 (API §8). |

## La matriz

### `/application-participants`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /application-participants/{participant_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /application-participants/{participant_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `DELETE /application-participants/{participant_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /application-participants/{participant_id}/financial-profile` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PUT /application-participants/{participant_id}/financial-profile` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/applications`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /applications` | `INTERNAL_NO_PARTNER` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /applications` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /applications/{application_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/activity` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /applications/{application_id}/assignments` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/available-actions` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /applications/{application_id}/bank-rule-evaluations` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/bank-rule-evaluations/latest` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/buyer-access-links` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /applications/{application_id}/buyer-access-links` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /applications/{application_id}/commission-settlement` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/completeness` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/consents` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/document-package-jobs` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /applications/{application_id}/document-package-jobs` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/document-slots` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /applications/{application_id}/document-slots/refresh` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/eligible-bank-products` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/filings` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /applications/{application_id}/filings` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/financing` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PUT /applications/{application_id}/financing` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/notes` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /applications/{application_id}/notes` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/notifications` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/participants` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /applications/{application_id}/participants` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/property` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PUT /applications/{application_id}/property` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/status-history` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /applications/{application_id}/status-transitions` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/{application_id}/summary` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /applications/{application_id}/withdrawals` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /applications/quick-filters` | `INTERNAL_NO_PARTNER` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 403 | ✗ 401 | ✗ 401 |

### `/audit-events`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /audit-events` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /audit-events/{event_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/auth`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `POST /auth/change-password` | `ANY_INTERNAL` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 401 | ✗ 401 |
| `POST /auth/login` | `PUBLIC` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `POST /auth/logout` | `PUBLIC` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `GET /auth/me` | `ANY_INTERNAL` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 401 | ✗ 401 |
| `POST /auth/password-reset-requests` | `PUBLIC` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `POST /auth/password-resets/confirm` | `PUBLIC` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `POST /auth/refresh` | `NO_REFRESH_COOKIE` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 |

### `/bank-policy-rules`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /bank-policy-rules` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /bank-policy-rules` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /bank-policy-rules/fields` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /bank-policy-rules/{rule_id}` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /bank-policy-rules/{rule_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /bank-policy-rules/{rule_id}/activate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /bank-policy-rules/{rule_id}/deactivate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /bank-policy-rules/{rule_id}/test` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /bank-policy-rules/{rule_id}/versions` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/bank-products`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /bank-products` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /bank-products` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /bank-products/{product_id}` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /bank-products/{product_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /bank-products/{product_id}/activate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /bank-products/{product_id}/deactivate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PUT /bank-products/{product_id}/purposes` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/banks`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /banks` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /banks` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /banks/{bank_id}` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /banks/{bank_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /banks/{bank_id}/activate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /banks/{bank_id}/deactivate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/broker`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /broker/opportunities` | `BROKER_ONLY` | ✗ 401 | ✗ 403 | ✗ 403 | ✗ 403 | ✓ | ✓ | ✗ 403 | ✗ 401 | ✗ 401 |

### `/buyer-access-links`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DELETE /buyer-access-links/{link_id}` | `ORIGINATED_NO_FILES` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/buyer-access`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `POST /buyer-access/consume` | `PUBLIC` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

### `/buyer`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /buyer/applications/{application_id}` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/applications/{application_id}/activity` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/applications/{application_id}/consents` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `POST /buyer/applications/{application_id}/consents` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/applications/{application_id}/document-slots` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/applications/{application_id}/eligible-bank-products` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/applications/{application_id}/financing` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `PUT /buyer/applications/{application_id}/financing` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/applications/{application_id}/participants` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/applications/{application_id}/profile` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `PATCH /buyer/applications/{application_id}/profile` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/applications/{application_id}/property` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `PUT /buyer/applications/{application_id}/property` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `POST /buyer/applications/{application_id}/withdrawals` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/document-files/{file_id}/download` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/document-slots/{slot_id}` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `POST /buyer/document-slots/{slot_id}/uploads` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/document-slots/{slot_id}/versions` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/financial-profiles/{profile_id}/income-sources` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `POST /buyer/financial-profiles/{profile_id}/income-sources` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `PATCH /buyer/income-sources/{income_source_id}` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `DELETE /buyer/income-sources/{income_source_id}` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/metadata/catalogs/{catalog_code}` | `BUYER_SESSION` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✓ |
| `GET /buyer/notifications` | `BUYER_SESSION` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✓ |
| `PATCH /buyer/notifications/{notification_id}/read` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `POST /buyer/notifications/read-all` | `BUYER_SESSION` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✓ |
| `GET /buyer/notifications/unread-count` | `BUYER_SESSION` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✓ |
| `GET /buyer/participants/{participant_id}/financial-profile` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `PUT /buyer/participants/{participant_id}/financial-profile` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `POST /buyer/participants/{participant_id}/financial-profile/confirmation` | `BUYER_OWN` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✗ 404 |
| `GET /buyer/processes` | `BUYER_SESSION` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✓ |
| `GET /buyer/session` | `BUYER_SESSION` | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✓ | ✓ |
| `POST /buyer/session/logout` | `PUBLIC` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

### `/catalog-items`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /catalog-items/{item_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /catalog-items/{item_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /catalog-items/{item_id}/activate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /catalog-items/{item_id}/deactivate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/catalogs`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /catalogs` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /catalogs` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /catalogs/{catalog_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /catalogs/{catalog_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /catalogs/{catalog_id}/items` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /catalogs/{catalog_id}/items` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PUT /catalogs/{catalog_id}/items/order` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/client-addresses`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `PATCH /client-addresses/{address_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `DELETE /client-addresses/{address_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/clients`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /clients` | `INTERNAL_NO_PARTNER` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /clients` | `INTERNAL_NO_PARTNER` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /clients/{client_id}` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /clients/{client_id}` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /clients/{client_id}/addresses` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /clients/{client_id}/addresses` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /clients/{client_id}/applications` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /clients/{client_id}/opportunities` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/commission-plans`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /commission-plans` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /commission-plans` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /commission-plans/{plan_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /commission-plans/{plan_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /commission-plans/{plan_id}/close` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/commission-settlements`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /commission-settlements` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /commission-settlements/{settlement_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /commission-settlements/{settlement_id}/void` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/commission-shares`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `POST /commission-shares/{share_id}/pay` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/dashboard`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /dashboard/bank-results` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /dashboard/funnel` | `INTERNAL_NO_PARTNER` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /dashboard/summary` | `INTERNAL_NO_PARTNER` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /dashboard/workload` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/document-files`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /document-files/{file_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /document-files/{file_id}/download` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /document-files/{file_id}/scan-status` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/document-package-jobs`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /document-package-jobs/{job_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /document-package-jobs/{job_id}/download` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/document-requirements`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /document-requirements` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /document-requirements` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /document-requirements/{requirement_id}` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /document-requirements/{requirement_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /document-requirements/{requirement_id}/activate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /document-requirements/{requirement_id}/deactivate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /document-requirements/preview` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/document-slots`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /document-slots/{slot_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /document-slots/{slot_id}/review` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /document-slots/{slot_id}/versions` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/document-types`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /document-types` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /document-types` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /document-types/{document_type_id}` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /document-types/{document_type_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /document-types/{document_type_id}/activate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /document-types/{document_type_id}/deactivate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/filing-responses`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /filing-responses/{response_id}` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /filing-responses/{response_id}/evidence` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /filing-responses/{response_id}/evidence/download` | `ORIGINATED_NO_FILES` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/filings`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /filings/{filing_id}` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /filings/{filing_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /filings/{filing_id}/document-snapshots` | `ORIGINATED_NO_FILES` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /filings/{filing_id}/responses` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /filings/{filing_id}/responses` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/financial-profiles`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /financial-profiles/{profile_id}/income-sources` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /financial-profiles/{profile_id}/income-sources` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/income-sources`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `PATCH /income-sources/{income_source_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `DELETE /income-sources/{income_source_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/invitations`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /invitations` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /invitations` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `DELETE /invitations/{invitation_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /invitations/{invitation_id}/resend` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /invitations/accept` | `PUBLIC` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

### `/me`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /me/commissions` | `OWN_COMMISSIONS` | ✗ 401 | ✗ 403 | ✓ | ✓ | ✓ | ✓ | ✗ 403 | ✗ 401 | ✗ 401 |

### `/metadata`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /metadata/bootstrap` | `ANY_INTERNAL` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 401 | ✗ 401 |
| `GET /metadata/catalogs/{catalog_code}` | `ANY_INTERNAL` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 401 | ✗ 401 |

### `/opportunities`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /opportunities` | `INTERNAL_NO_PARTNER` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /opportunities` | `INTERNAL_NO_PARTNER` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /opportunities/{opportunity_id}` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /opportunities/{opportunity_id}` | `ASSIGNED_OR_ORIGINATED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✓ | ✗ 404 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /opportunities/{opportunity_id}/assignments` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /opportunities/{opportunity_id}/transitions` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/partner-memberships`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /partner-memberships/{membership_id}` | `ADMIN_PARTNER` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✓ | ✗ 401 | ✗ 401 |
| `PATCH /partner-memberships/{membership_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `DELETE /partner-memberships/{membership_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/partners`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /partners` | `ADMIN_ADVISOR_PARTNER` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✓ | ✗ 401 | ✗ 401 |
| `POST /partners` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /partners/{partner_id}` | `ADMIN_ADVISOR_PARTNER` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✓ | ✗ 401 | ✗ 401 |
| `PATCH /partners/{partner_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /partners/{partner_id}/activate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /partners/{partner_id}/deactivate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /partners/{partner_id}/members` | `ADMIN_PARTNER` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✓ | ✗ 401 | ✗ 401 |
| `POST /partners/{partner_id}/members` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/projects`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /projects` | `ANY_INTERNAL` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 401 | ✗ 401 |
| `POST /projects` | `ADMIN_ADVISOR_PARTNER` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✓ | ✗ 401 | ✗ 401 |
| `GET /projects/{project_id}` | `ANY_INTERNAL` | ✗ 401 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ 401 | ✗ 401 |
| `PATCH /projects/{project_id}` | `ADMIN_ADVISOR_PARTNER` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✓ | ✗ 401 | ✗ 401 |
| `POST /projects/{project_id}/activate` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /projects/{project_id}/archive` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /projects/{project_id}/reject` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /projects/{project_id}/submit` | `ADMIN_ADVISOR_PARTNER` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✓ | ✗ 401 | ✗ 401 |

### `/report-export-jobs`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /report-export-jobs/{job_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /report-export-jobs/{job_id}/download` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/reports`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /reports/applications` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /reports/applications.csv` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /reports/applications/export-jobs` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /reports/applications/export-jobs` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /reports/funnel` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/roles`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /roles` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/tasks`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /tasks` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /tasks` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /tasks/{task_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /tasks/{task_id}` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /tasks/{task_id}/cancel` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /tasks/{task_id}/complete` | `ASSIGNED` | ✗ 401 | ✓ | ✓ | ✗ 404 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/users`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /users` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /users` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /users/{user_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /users/{user_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /users/{user_id}/activate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /users/{user_id}/deactivate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PUT /users/{user_id}/roles` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/workday`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /workday/applications` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /workday/summary` | `ADMIN_ADVISOR` | ✗ 401 | ✓ | ✓ | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

### `/workflow-transitions`

| Operación | Patrón | sin sesión | admin | asesor dueño | otro asesor | broker dueño | otro broker | constructora | comprador dueño | otro comprador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /workflow-transitions` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /workflow-transitions` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `GET /workflow-transitions/{transition_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `PATCH /workflow-transitions/{transition_id}` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /workflow-transitions/{transition_id}/activate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |
| `POST /workflow-transitions/{transition_id}/deactivate` | `ADMIN_ONLY` | ✗ 401 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 | ✗ 401 |

## Casos explícitos (spec §3.4)

`backend/tests/security/test_explicit_cases.py`, aparte de la tabla:

| Caso | Qué se comprueba | Resultado |
| --- | --- | --- |
| Ids del lado B en el **cuerpo** (`opportunity_id`, `client_id` (asesor y broker), `application_id` y `opportunity_id` de tareas, `package_job_id`, `corrects_response_id`, `observations[].document_slot_id`, `document_file_id`) | Con el id propio la operación pasa; con el del lado B responde **igual que con un id que no existe** (mismo estado y código, el error nombra el campo) y nunca 2xx | ✓ los 10 |
| `participant_id`, `filing_id`, `slot_id`, `assigned_to`, `beneficiary_user_id` en el cuerpo | El contrato no tiene esos campos en ninguna escritura (una prueba lo vigila) | no aplica |
| Tarea de una solicitud propia asignada a otro asesor | Permitido por API §15 (`assigned_to_id` debe ser ADMIN o ADVISOR activo); queda fijado en una prueba | ✓ documentado |
| Comprador A con ids del comprador B en `/buyer/applications/{id}`, `/buyer/document-files/{id}/download`, `/buyer/notifications/{id}/read` | 404 y la notificación ajena sigue sin leer | ✓ |
| Filtros con ids de otro alcance (`advisor_id`, `client_id`, `broker_id`, `application_id`, `opportunity_id`, `assigned_to_id`, `participant_id`, `partner_id`) en 16 listados | 200 sin ningún id ni código del lado B (o 403) | ✓ los 16 |
| Filtros de reportes y dashboard con `advisor_id` ajeno (7 rutas) y exportación con `advisor_id` ajeno | 403, como pide API §22 | ✓ los 8 |
| Broker en `/applications/{id}` y `/applications/{id}/summary` de su solicitud | Solo los campos del resumen (`BROKER_APPLICATION_SUMMARY_FIELDS`) | ✓ |
| Constructora en todas las rutas de expedientes, clientes y oportunidades (lado A y B) | 403 o 404 en todas | ✓ |
| Constructora sobre la otra constructora y su proyecto | 404 | ✓ |
| Usuario **desactivado** con la cookie de acceso vigente | 401 en la siguiente petición | ✓ |
| Usuario al que **le quitaron el rol**, con la cookie vigente | 403 en la siguiente petición: los permisos se leen en cada petición | ✓ |

## Casos decididos con la regla general

Donde la documentación no define el caso (o se contradice) se aplicó la regla general del
proyecto o lo ya decidido:

- `POST /auth/logout`: Público y sin cookie de acceso: responde 204 a cualquiera (cierra lo que traiga la cookie de refresh, si hay).
- `POST /buyer/session/logout`: Mismo criterio que el logout interno.
- `DELETE /buyer-access-links/{link_id}`: API §25: el broker 'revoca los propios'. El enlace del lado A lo emitió la asesora: el broker originador lo ve en el listado, así que 403 (no 404).
- `GET /filing-responses/{response_id}/evidence/download`: El broker tiene `filings.read`, pero REQ §3: 'no ve archivos'. 403 al originador; 404 al otro broker, porque la radicación está fuera de su alcance.
- `GET /filings/{filing_id}/document-snapshots`: Igual que la evidencia: son archivos.
- `PATCH /projects/{project_id}`: API §25 dice 'lectura relacionada' para el asesor, pero API §12 (`projects.update`), los permisos sembrados, RF-17 (asesor o administrador aprueban) y `update_project` (el asesor corrige cualquier proyecto no archivado) lo permiten. Se toma §12.
- `GET /clients/{client_id}/addresses`: API §25 'Clientes: Propios' para el broker no detalla direcciones; la vista exige un permiso que el broker no tiene (403). Más restrictivo que la matriz: no es brecha.
- `GET /me/commissions`: El administrador no tiene `commissions.read_own` (no tiene 'su parte'): 403. Consulta las liquidaciones en `/commission-settlements`.
- `POST /auth/change-password`: Solo pide sesión interna; el cuerpo vacío da 400 a los cuatro roles.

## Brechas

Ninguna. La matriz y los casos explícitos pasan sin `xfail`. Los hallazgos abiertos de las otras partes están en [`hallazgos.md`](hallazgos.md).
