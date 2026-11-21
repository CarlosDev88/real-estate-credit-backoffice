# 12 · Auditorías: qué se encontró y cómo se solucionó

> **En simple:** además de las pruebas y el CI, el proyecto pasa por **tres auditorías independientes**: de seguridad, de rendimiento del frontend y de carga y estrés del backend. Cada una revisa con un método propio, deja su informe completo y una lista de hallazgos. Este documento junta las tres en lenguaje simple y, para cada hallazgo, cuenta **qué pasaba, por qué, qué se cambió, cómo se comprobó y en qué PR se cerró**.

> **Estado al 18 de noviembre de 2026: las tres auditorías están en curso.** Ninguna está fusionada en `master` todavía. Este documento deja la estructura completa y se llena al cierre, cuando terminen las correcciones. Lo que ya se sabe está marcado como tal.

---

## Índice

1. [Resumen](#1-resumen)
2. [Seguridad](#2-seguridad)
3. [Rendimiento del frontend](#3-rendimiento-del-frontend)
4. [Carga y estrés del backend](#4-carga-y-estrés-del-backend)
5. [Lo que aprendimos](#5-lo-que-aprendimos)
6. [Cómo leer las tablas](#6-cómo-leer-las-tablas)

---

## 1. Resumen

| Auditoría | Qué revisa | Informe | Hallazgos | Estado |
| --- | --- | --- | --- | --- |
| Seguridad | Autenticación, autorización por rol y objeto, archivos, datos personales, configuración | [`docs/SEGURIDAD.md`](../SEGURIDAD.md) y [`docs/seguridad/`](../seguridad/) | 21: 0 críticos, 0 altos, 5 medios, 10 bajos, 6 informativos | ✅ Fase A (#32) y Fase B (este PR): 20 corregidos y 1 aceptado |
| Rendimiento del frontend | Peso de las páginas, tiempos de carga y de interacción | [`docs/PERFORMANCE.md`](../PERFORMANCE.md) y [`docs/performance/`](../performance/) | 13: 4 altos, 5 medios, 1 bajo, 3 informativos | ✅ #39: 7 corregidos, 4 aceptados y 2 que dependen del backend |
| Carga y estrés del backend | Latencia bajo carga (el p95 < 800 ms de RNF-17), errores y límites | `docs/PERFORMANCE.md` *(en curso)* | Pendiente | 🔄 En preparación |

Los informes de rendimiento y carga se enlazarán aquí cuando se fusionen sus ramas.

---

## 2. Seguridad

Informe completo: [`docs/SEGURIDAD.md`](../SEGURIDAD.md) (resumen, método, modelo de amenazas, matriz de acceso, cada hallazgo con su ficha y el re-test). Fichas largas: [`docs/seguridad/hallazgos.md`](../seguridad/hallazgos.md). Cómo repetir la auditoría en local: [`backend/security/README.md`](../../backend/security/README.md).

### 2.1 Qué se revisó y con qué método

La API completa (las operaciones de `contracts/openapi.json`), con los cinco tipos de usuario, más el código, las dependencias, el historial de git y los contenedores. Con analizadores automáticos (bandit, semgrep, pip-audit, gitleaks, hadolint), ataques simulados contra una copia local (schemathesis y OWASP ZAP), una **matriz de acceso** que pide cada operación como cada uno de los 9 actores de la auditoría (2 124 casos, todos con el resultado esperado) y una revisión manual. La **Fase A** (#32) encontró y documentó; la **Fase B** (este PR) corrigió y volvió a probar con las mismas herramientas.

### 2.2 Hallazgos por severidad

| Severidad | Cuántos | Corregidos | Aceptados |
| --- | ---: | ---: | ---: |
| Crítica | 0 | — | — |
| Alta | 0 | — | — |
| Media | 5 | 5 | 0 |
| Baja | 10 | 9 | 1 |
| Informativa | 6 | 6 | 0 |
| **Total** | **21** (SEC-01 a SEC-21) | **20** | **1** |

SEC-21 (informativo) apareció en el re-test de la Fase B y se corrigió en el mismo PR.

### 2.3 Hallazgos y cómo se solucionó cada uno

| Id | Problema | Causa | Solución aplicada | Cómo se verificó | PR |
| --- | --- | --- | --- | --- | --- |
| SEC-01 | Sin configuración de producción | Los puntos de entrada cargaban `local` (`DEBUG=True`) | `config/settings/production.py`; `wsgi`, `asgi` y Celery la usan por defecto | `test_deployment.py`; `check --deploy` solo con `W021` | Fase B |
| SEC-02 | HTTPS sin endurecer | Nada fijaba HSTS, redirección ni cookies `Secure` | Lo fija `production.py` | `test_deployment.py`; la imagen redirige y manda HSTS | Fase B |
| SEC-03 | Claves sin validar | Se exigía que existieran, no que fueran fuertes | *System check* `identity.E001`/`E002` (aviso con `DEBUG`) | `test_deployment.py`; la imagen no arranca con claves débiles | Fase B |
| SEC-04 | DRF con dos CVE de DoS | El rango de `requirements.txt` dejaba fuera el arreglo | DRF `>=3.18.2,<3.19` | `test_resources.py`; el cuerpo bz2 ya no se expande | Fase B |
| SEC-05 | Puertos en todas las interfaces | El compose no ponía IP | `127.0.0.1:` en cada puerto | `test_deployment.py`; compose levantado | Fase B |
| SEC-06 | Imagen no reproducible y con `runserver` | Una sola etapa, base y `pip` sin fijar | Dos etapas, digest, `pip` fijo, gunicorn en `production` | `test_deployment.py`; hadolint sin `DL3013` | Fase B |
| SEC-07 | `OPTIONS` con 500 | La metadata de DRF fallaba en vistas sin `serializer_class` | `DEFAULT_METADATA_CLASS = None` | `test_http_responses.py`; 0 de 176 rutas con 5xx | Fase B |
| SEC-08 | Datos personales cacheables | DRF no pone `Cache-Control` | *Middleware* con `no-store` y `Vary: Cookie` | `test_http_responses.py` | Fase B |
| SEC-09 | Límite de login saltable | Una sola clave "IP + correo" | Límites por IP y por cuenta | `test_rate_limits.py`; corta en el 21.º correo y el 11.º fallo | Fase B |
| SEC-10 | Sin límites generales | No había `DEFAULT_THROTTLE_CLASSES` | 600 lecturas, 120 escrituras y 20 cambios de estado por minuto | `test_rate_limits.py` | Fase B |
| SEC-11 | 500 con un JSON grande | `RequestDataTooBig` no es de DRF | `413 PAYLOAD_TOO_LARGE` | `test_http_responses.py` | Fase B |
| SEC-12 | 404 en HTML | Sin `handler404`/`handler500` | JSON en `/api/` | `test_http_responses.py` | Fase B |
| SEC-13 | Contrato desalineado | Dos esquemas mal y errores sin documentar | Esquemas corregidos y un *hook* que documenta 400/404/428 | `test_deployment.py`; schemathesis sin `ST103` ni `ST108` | Fase B |
| SEC-14 | Enumeración por la recuperación | Correo síncrono, solo si el usuario existía | Correo por la cola de Celery; el token se genera en el worker | `test_auth.py`; 202 siempre y el mismo tiempo | Fase B |
| SEC-15 | Búsquedas en el log | El filtro solo ocultaba tokens | `***` en `search`, `email`, `document_number` y `q` | `test_exposure.py` | Fase B |
| SEC-16 | El `409` confirma una cédula | La unicidad del documento es regla de negocio | **Aceptado** (ver 2.4) | `test_exposure.py` fija el comportamiento | Fase B |
| SEC-17 | Textos de bancos sin tope | Sin `max_length` | `max_length=4000` | `test_resources.py` | Fase B |
| SEC-18 | `/admin/` publicado y sin límite | Se montaba siempre | Solo con `DEBUG` o `ADMIN_ENABLED`, con límite por IP | `test_config_inventory.py` | Fase B |
| SEC-19 | Esquema y Swagger públicos | Se montaban siempre | Solo con `DEBUG` o `API_DOCS_PUBLIC` | `test_config_inventory.py` | Fase B |
| SEC-20 | Documentación de la API desalineada | No se actualizó con el MVP | 9 rutas a "Fuera del MVP"; direcciones documentadas | `test_config_inventory.py` (en los dos sentidos) | Fase B |
| SEC-21 | `oneOf` ambiguo en respuestas por rol | Una página vacía valía para las dos formas | `anyOf` en el contrato | `test_deployment.py`; schemathesis sin `ST108` | Fase B |

### 2.4 Aceptados, con su motivo

- **SEC-16 (baja), aceptado por Carlos.** El documento identifica a la persona y no tiene sentido crear el mismo cliente una vez por broker: la unicidad es regla de negocio. Mitigación: el `409` no trae ningún dato del otro cliente y el límite general de escrituras (SEC-10) deja probar como mucho 120 cédulas por minuto. Riesgo residual: confirmar que una cédula ya es cliente, sin saber de quién.

---

## 3. Rendimiento del frontend

Informe completo: [`docs/PERFORMANCE.md`](../PERFORMANCE.md) (resumen, método, antes y después, cada hallazgo y los presupuestos del CI). Fichas largas: [`docs/performance/frontend-hallazgos.md`](../performance/frontend-hallazgos.md). Cómo repetir la medición en local: [`frontend/scripts/perf/README.md`](../../frontend/scripts/perf/README.md).

> **En simple:** el expediente cargaba de entrada todo lo que podía llegar a usar y pedía sus datos en cadena. El dashboard saltaba mientras cargaba, y abrir un modal congelaba la pantalla medio segundo. Hoy el expediente baja 30 % menos de JavaScript y muestra su contenido 1,3 s antes en un móvil, el dashboard no se mueve y el modal abre al instante. Y el CI no deja pasar un PR que engorde una página.

### 3.1 Qué se revisó y con qué método

- **13 páginas, con el usuario que corresponde a cada una:**
  - las 3 públicas (login, aceptar invitación y acceso del comprador);
  - del administrador: dashboard, reportes y usuarios;
  - de la asesora: Mi día, el listado, un expediente radicado, clientes y sus comisiones;
  - la del broker (prospectos);
  - el portal del comprador.
- **Herramientas:**
  - Lighthouse 13.6, en móvil (un teléfono de gama media con 4G lento simulado) y en escritorio;
  - Web Vitals de laboratorio (LCP, CLS, INP) con Playwright;
  - tres interacciones reales;
  - el tamaño del JavaScript de cada ruta.
- **Siempre sobre el build de producción**, con 5 corridas por página y la mediana.
- **Antes y después, el mismo día.** La línea base del primer día se midió con el equipo cargado, y el mismo código daba otros números. Por eso el antes y el después se miden el mismo día, uno detrás de otro.

### 3.2 Hallazgos por severidad

| Severidad | Cuántos | Corregidos | Aceptados | Dependen del backend |
| --- | ---: | ---: | ---: | ---: |
| Alta | 4 | 3 | 0 | 1 (el portal) |
| Media | 5 | 3 | 2 | 0 |
| Baja | 1 | 1 | 0 | 0 |
| Informativa | 3 | 0 | 2 | 1 |

PERF-01 está corregido; el resto de su LCP también depende del backend.

### 3.3 Hallazgos y cómo se solucionó cada uno

| Id | Problema | Causa | Solución aplicada | Antes → después | PR |
| --- | --- | --- | --- | --- | --- |
| PERF-01 | El expediente tardaba en mostrar su título | Pedía sus secciones después del detalle, cargaba de entrada todas sus pestañas y modales, y se repintaba entero con cada respuesta | Secciones en paralelo; pestañas, paneles y modales cargados al usarlos; cada tarjeta escucha solo su dato (`workspace-screen.tsx`, `route-prefetch.ts`) | LCP móvil 5,1 → 3,9 s; JS −30 % | #39 |
| PERF-02 | El dashboard saltaba mientras cargaba | Los bloques de carga eran mucho más bajos que el contenido | Las tarjetas muestran sus etiquetas desde el principio y los bloques reservan su alto (`summary-blocks.tsx`) | CLS 0,21–0,56 → 0 | #39 |
| PERF-03 | El portal del comprador tardaba en mostrar su texto principal | Formularios en la primera carga y la cadena sesión → solicitud | Retiro y carga de documentos, al abrirlos (`home-screen.tsx`) | LCP 5,3 → 4,7 s; JS −25 %. El resto depende del backend | #39 |
| PERF-04 | Abrir "Registrar respuesta" congelaba la pantalla | Se armaba todo el modal en el mismo clic | El modal se abre en una transición, con el botón en estado de carga (`response-timeline.tsx`) | INP 360 → 104 ms | #39 |
| PERF-05 | Las páginas con sesión pintan después de validar la sesión | La guarda espera la sesión | Se probó adelantar datos y se revirtió: no ayudaba | Aceptado: pide la sesión en el servidor | #39 |
| PERF-06 | Mi día y Prospectos saltaban al cargar | El mismo patrón que el dashboard | Esqueletos con la forma final (`tray.tsx`, `broker-screen.tsx`) | CLS 0,148 → 0,010 y 0,214 → 0 | #39 |
| PERF-07 | El listado tenía mucho trabajo en el hilo principal | La hidratación de Ant Design y de la tabla | Se probó un cambio en las pestañas y se revirtió: la medición mostró que no ayudaba | Aceptado; propuesta: el modo `zeroRuntime` de Ant Design | #39 |
| PERF-08 | "Aceptar invitación" sin token pintaba tarde | El aviso esperaba al JavaScript, y se cargaba el formulario entero | El servidor pinta el aviso; el formulario se carga solo con token (`accept-invitation-*.tsx`) | LCP móvil 3,7 → 0,8 s; JS −30 % | #39 |
| PERF-09 | Una petición de sesión quedaba abierta | No se leía el cuerpo de la respuesta | Se lee (`session.ts`) | Cargas que no terminaban: 5 de 5 → 0 | #39 |
| PERF-10 | El login cargaba Zod para dos campos | Validación en la primera carga | El esquema se carga al validar (`login-schema.ts`) | JS −9 % | #39 |
| PERF-11 | El catálogo de metadatos (36 kB) se descarga en cada carga | El backend lo marca como no cacheable | — | Depende del backend | — |
| PERF-12 | Fuentes sin precarga | `@fontsource` en el CSS | No se cambia: no hay nada que mover | Aceptado | — |
| PERF-13 | Cada fila del listado precarga su expediente | Comportamiento por defecto de Next | Se deja: hace instantánea la navegación | Aceptado | — |

**Lo que quedó en el CI para que no vuelva:**
- un presupuesto de JavaScript por ruta (lo medido + 10 %), que bloquea si una página engorda;
- Lighthouse CI en las tres páginas públicas, que bloquea si bajan la performance, la accesibilidad o las buenas prácticas, o si suben el LCP, el CLS o el bloqueo del hilo principal.

---

## 4. Carga y estrés del backend

### 4.1 Qué se revisó y con qué método

*(Se completa con el informe: herramienta de carga, escenarios — por ejemplo, listado de solicitudes, "Mi día", carga de documentos y reportes —, usuarios concurrentes, duración, y el objetivo de RNF-17: p95 menor a 800 ms en las lecturas normales.)*

Lo que el diseño ya prepara para esta auditoría está en [04 · System design §5](04-system-design.md#5-rendimiento): listas sin consultas por fila (48 aserciones de número de consultas en las pruebas), agregados en la base, índices para las pantallas y la completitud del listado guardada en lugar de calculada por fila.

### 4.2 Hallazgos por severidad

| Severidad | Cuántos | Corregidos | Aceptados |
| --- | ---: | ---: | ---: |
| *(pendiente)* | | | |

### 4.3 Hallazgos y cómo se solucionó cada uno

| Id | Problema | Causa | Solución aplicada | Antes → después (p95, errores) | PR |
| --- | --- | --- | --- | --- | --- |
| *(pendiente)* | | | | | |

---

## 5. Lo que aprendimos

*(Se completa al cierre con los patrones que se repitieron en las tres auditorías y la regla que quedó en el CI para que no vuelvan.)*

Mientras tanto, los patrones que ya se vieron durante la construcción y la regla automática que dejaron ([11 · Cómo se construyó §7](11-como-se-construyo.md#7-errores-reales-que-se-atraparon)):

| Patrón | Regla que quedó | Dónde |
| --- | --- | --- |
| Un cambio del backend rompe al front sin que nadie lo note | El CI regenera el contrato y los tipos del front y falla si hay diferencias | `.github/workflows/backend.yml`, `frontend.yml` |
| Un nombre de enum publicado cambia solo | Nombres fijos y una prueba que los protege | `backend/tests/test_contract_names.py` |
| Una operación con `If-Match` sin `ETag` declarado | Una prueba que recorre el esquema | `backend/tests/test_etag_contract.py` |
| Un `POST` nuevo con `@idempotent` sin declararlo a conciencia | Una lista esperada en la prueba del contrato | `backend/tests/applications/idempotency/test_idempotency.py` |
| Consultas que crecen con las filas | Aserciones de número de consultas en los listados | 20 archivos de `backend/tests/` |
| Colores escritos a mano y contraste insuficiente | Prueba sin colores fijos y `axe` en cada story en el CI | `frontend/src/test/no-hardcoded-colors.test.ts`, paso "Storybook (a11y)" |
| Secretos o documentos en la auditoría | Un fixture que revisa cada evento escrito en las pruebas | `backend/tests/applications/audit/` (P1.10 de [`specs/TAREA-auditoria.md`](../../specs/TAREA-auditoria.md)) |

---

## 6. Cómo leer las tablas

- **Id:** el identificador del hallazgo en su informe (por ejemplo, `SEC-04`).
- **Problema:** qué pasaba, en una frase y sin jerga.
- **Causa:** por qué pasaba (la raíz, no el síntoma).
- **Solución aplicada:** qué se cambió y dónde, con la ruta del archivo.
- **Cómo se verificó:** la prueba que lo cubre ahora, la medición antes y después o el re-test del auditor.
- **PR:** el que lo cerró.
- **Aceptado:** un hallazgo que se decidió no corregir en el MVP, siempre con su motivo.
