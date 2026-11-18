# TAREA — F5 del frontend: Dashboard, Mi día y tareas, Reportes (vistas 2, 3 y 10)

**Agente:** front 2. **Worktree:** `wt-front-ops`, rama `feat/front-operations`, **desde `origin/feat/design-system`** (para tener la librería nueva de `components/ui`: `Card`, `DataList`, `PageHeader`, `DataTable`, `CardList`, `ListPagination`, `SidePanel`, `BottomSheet`, `ActionModal`, `Stepper`, `LoadingState`/`ErrorState`). Cuando el #28 se fusione, Carlos trae `master` y tu PR queda solo con lo tuyo. **Puerto 3001** (Playwright con `E2E_PORT=3001`).
**API:** toda existe en `master` (módulos 12 y 15). No hay mockups de estas vistas: se diseñan con `design/README.md`, el Storybook (`pnpm storybook` en `frontend/`, puerto 6006: **mira ahí los patrones antes de construir**) y el lenguaje del listado de solicitudes.

## Reglas
- Git solo lectura, buzón, no preguntes (decide, anota en "Precisiones acordadas", sigue), no leas `.env*`.
- **No cambies `components/ui`, `design/`, `features/applications` ni `features/clients`** (el front 1 los está migrando a la librería). Si te falta algo de la librería, lo haces local en tu feature y lo anotas como candidato.
- **Usa la librería** en todo lo nuevo (tablas, tarjetas, estados, modales, paneles, encabezados). Nada de copiar componentes de `features/applications`.
- Cero textos de negocio en el código: estados, etapas, segmentos, prioridades y etiquetas salen de la API o del bootstrap/catálogos. Tonos con `toneFor`. Formatos con `lib/format` (montos COP, fechas de Bogotá, porcentajes).
- **Gráficos**: sin librería nueva de gráficos. El embudo y las barras se dibujan con HTML/CSS (barras horizontales con ancho proporcional y el número escrito al lado) usando tokens; cada gráfico tiene su tabla equivalente accesible (o la tabla es el gráfico). Nada que dependa solo del color.
- Verificaciones al cerrar cada parte: lint, format, typecheck, `vitest --coverage` (≥ 70 %), build; capturas a 1440, 1280 y 390 en claro y oscuro; `axe` sin violaciones serias.
- Filtros y pestañas **en la URL** (mismo patrón que `/solicitudes`).
- `Idempotency-Key` (UUID por intento del usuario, reutilizado en reintentos) en los POST que lo admiten de esta tarea (exportación de reportes).

## Parte 1 — Dashboard (`/dashboard`, vista 2)
- **Menú:** "Dashboard" (primer ítem, grupo "Operación"), con `dashboard.read`. Es la pantalla de inicio después del login para quien tenga ese permiso (cambio mínimo y anotado en el redirect del login/home; si ese archivo es de `features/applications`, haz el cambio en `app/` o en `lib/navigation`, no en la feature).
- **Filtros** (barra arriba, en la URL): rango de fechas (por defecto el que devuelva la API en `period`: el mes en curso), asesor (solo admin; usa la lista de asesores con `users.read` si la tiene), banco y finalidad (catálogos). Un `403 FILTER_OUT_OF_SCOPE` se muestra en el filtro.
- **Bloques** (cada uno con su propio cargando/error, para que uno caído no tumbe la página):
  1. `GET /dashboard/summary`: tarjetas de cifras (clientes creados, solicitudes creadas, tareas vencidas y para hoy; y, si la respuesta trae `amounts`, solicitado, aprobado y desembolsado en COP). La **foto por estado** (`snapshot`) como lista de barras con `status_label`, el número y el tono; los estados en 0 se pueden ocultar con un "Mostrar todos".
  2. `GET /dashboard/funnel`: el embudo (6 etapas con `label`, `count`, `conversion` como porcentaje y `step_conversion`).
  3. `GET /dashboard/workload` (si no hay permiso o responde 403, el bloque no aparece): tabla por asesor (`DataTable`).
  4. `GET /dashboard/bank-results` (igual): tabla por banco, con `avg_days_to_response`.
- Las tarjetas de tareas enlazan a "Mi día" con el filtro de vencidas o de hoy; las barras de estado enlazan a `/solicitudes?status=<código>` si el listado acepta ese filtro (revisa; si no, sin enlace).
- **Broker:** ve solo lo que la API le da (conteos, sin montos ni carga ni bancos).
- **Commit:** `feat(frontend): add the operations dashboard`

## Parte 2 — Mi día y tareas (`/mi-dia`, vista 3)
- **Menú:** "Mi día", con el permiso que use `GET /workday/applications` (búscalo en el contrato / `/auth/me`).
- **Resumen** (`GET /workday/summary`): los segmentos de atención con su número (lo que la API llame `attention`/segmentos); cada uno es un filtro.
- **Bandeja** (`GET /workday/applications`): búsqueda, etapa, banco, finalidad, segmento de atención, orden y paginación en la URL. Cada fila: código (enlace al expediente), cliente, etapa con tono, siguiente acción, días en la etapa y señal de atención. Tabla en escritorio, tarjetas en móvil (`DataTable` + `CardList`).
- **Tareas** (pestaña o columna lateral "Mis tareas", decide la que mejor quede en 1280 y 390):
  - `GET /tasks` con `assigned_to_id` = el usuario, filtros `due` (vencidas, hoy, próximas), `status` y `priority`;
  - crear (`POST /tasks`: título, descripción, vencimiento, prioridad del catálogo, vinculada a una solicitud u oportunidad si se crea desde ahí), editar (`PATCH`), completar y cancelar (con motivo si la API lo pide), con `ActionModal`;
  - el admin puede ver las de otro asesor (`assigned_to_id`), si tiene permiso.
- **Commit:** `feat(frontend): add My day with the attention tray and tasks`

## Parte 3 — Reportes (`/reportes`, vista 10) y cierre
- **Menú:** "Reportes", con `reports.read`.
- **Pestañas en la URL:** "Embudo" y "Solicitudes".
  - **Embudo** (`GET /reports/funnel`): los mismos filtros del dashboard + estado (multivalor) + "Agrupar por" (`advisor`, `bank`, `purpose`). Sin agrupar: el embudo; agrupado: una tabla con una fila por grupo y una columna por etapa (número y conversión).
  - **Solicitudes** (`GET /reports/applications`): tabla paginada con las columnas de la API (el documento ya viene enmascarado: muéstralo tal cual).
- **Exportar** (con `reports.export`):
  - "Descargar CSV" (`GET /reports/applications.csv` con los filtros actuales; descarga directa). Si responde `422 EXPORT_TOO_LARGE`, ofrece "Preparar exportación".
  - "Preparar exportación" (`POST /reports/applications/export-jobs` con los filtros en el cuerpo y `Idempotency-Key`): un panel "Mis exportaciones" (`GET /reports/applications/export-jobs`) con estado (`status_label`), filas, fecha y vencimiento; consulta cada 3 s mientras haya alguna `PENDING`/`RUNNING`; "Descargar" pide la URL firmada cada vez (`/report-export-jobs/{id}/download`) y maneja `409`/`410`. `429 TOO_MANY_EXPORTS` se muestra en el botón.
- **Avisos del portal del comprador** (brecha F2, la API ya existe): `/portal/avisos` con `GET /buyer/notifications` (no leídos primero), marcar leído al abrir (`PATCH .../read`), "Marcar todos como leídos" (`POST read-all`) y el número en la navegación del portal (`unread-count`). **Excepción a la regla de no tocar otras features:** puedes tocar `features/buyer-portal` solo para agregar la entrada de navegación y el contador; lo demás va en `features/buyer-notifications/`.
- **E2E** (Playwright, `:3001`): dashboard carga y filtra; Mi día filtra por segmento, crea y completa una tarea; reportes cambia de pestaña, agrupa, descarga el CSV y prepara una exportación hasta "Descargar"; el comprador ve sus avisos y marca uno como leído.
- **Brechas** en `specs/TAREA-frontend-base.md` ("Brechas que dejó la F5"), **candidatos a la librería**, merge de `master` (Carlos), `api:gen`, título y descripción del PR (en español).
- **Commits:** `feat(frontend): add operational reports with CSV and async exports`, `feat(frontend): add the buyer notifications page`, `test(frontend): add operations end-to-end and accessibility checks`.

## Después (no en esta tarea)
- Los **botones de transición de la oportunidad** (cuando el B termine la Parte 1 de `TAREA-brechas-2.md` y esté en master): un PR corto aparte que toca `features/clients` — se coordina con el front 1.

## Precisiones acordadas

**Parte 1 (front 2, 2026-11-18):**
- **Contrato:** esta rama (desde `feat/design-system`) no traía el módulo 15. Se copiaron tal cual `contracts/openapi.json` y `frontend/src/lib/api/schema.d.ts` de `origin/master` (idénticos byte a byte: el merge de `master` no tendrá conflicto en esos dos archivos).
- **Inicio después del login:** "Dashboard" es la primera entrada de `NAV_ITEMS` (`lib/navigation/nav-config.tsx`, grupo "Operación", `dashboard.read`); `defaultDestination` ya toma la primera permitida, así que no se tocó el login ni `app/page.tsx`. Sin `dashboard.read`, el inicio sigue siendo `/solicitudes`.
- **Filtros en la URL** con los nombres de la API: `date_from`, `date_to`, `advisor_id`, `bank_id`, `purpose_code`. Sin fechas en la URL, los campos muestran el `period` que devuelve la API. Fechas con `<input type="date">` (sin dayjs ni librería nueva).
- **Asesor:** el filtro aparece con `users.read` y lista `GET /users?role=ADVISOR&status=ACTIVE` (código del rol, no texto). **Banco:** con `banks.read`. **Finalidad:** catálogo `loan_purpose` del bootstrap.
- **Errores de filtro:** un `400` o un `403 FILTER_OUT_OF_SCOPE` con `details[].field` de un filtro se muestra en ese filtro (`aria-invalid` + mensaje de la API) y los bloques dicen "Corrige el filtro marcado" sin "Reintentar". Un `403` que no es de filtro (`PERMISSION_DENIED`) oculta el bloque de carga o de bancos.
- **Tarjetas de tareas:** se ven con `tasks.read` (el broker recibe siempre 0) y enlazan a `/mi-dia?due=overdue` y `/mi-dia?due=today` si el usuario tiene `workday.read`. **La Parte 2 debe leer `due` de la URL de `/mi-dia`** con esos valores (los de `GET /tasks`).
- **Barras de estado sin enlace:** el listado `/solicitudes` no lee `status` de la URL (`list-params.ts` de `features/applications`), aunque la API lo acepta. Queda como brecha para el front 1.
- **Gráficos:** foto por estado = lista de barras (texto y número escritos, barra `aria-hidden`, color con `toneFor`); embudo = tabla con barra (la tabla es el gráfico). En contenedores angostos la barra baja debajo del nombre (container queries).
- **Piezas locales candidatas a la librería:** `StatTile`, `BarList`/`Bar`, `FunnelTable`, `DashboardIcon`, `EmptyNote` (vacío de una línea dentro de una tarjeta).

**Parte 2 (front 2, 2026-11-18):**
- **Menú:** "Mi día" es la segunda entrada del grupo "Operación", con `workday.read` (el permiso de `GET /workday/applications`).
- **Pestañas en la URL** (`tab=bandeja|tareas`) y no una columna lateral: en 1280 la tabla de la bandeja necesita todo el ancho. Con `due` en la URL y sin `tab`, se abre "Mis tareas". Por eso los enlaces del dashboard quedaron en `/mi-dia?tab=tareas&due=overdue|today`.
- **Bandeja:**
  - Los segmentos de `GET /workday/summary` son botones con `aria-pressed`: "Todas" (con `total`) y un botón por segmento. Un segundo clic quita el filtro.
  - Filtros en la URL: `search`, `stage`, `bank_id`, `purpose`, `attention`, `advisor_id` (solo con `users.read`), `ordering`, `page` y `page_size`. El resumen recibe los mismos filtros, menos el segmento, la búsqueda (la API no la acepta) y la página.
  - Etapas: las del catálogo `application_status`, filtradas a los códigos no terminales del enum `stage` del contrato (`WORKDAY_STAGES`).
  - Orden: un select con los campos de `ordering_fields` (`days_in_stage`, `updated_at`, `code`) y encabezados ordenables. Sin orden, se usa el de la API (primero lo que pide atención).
  - En la tabla, la etapa y la siguiente acción van en la misma celda, para que quepa en 1280 sin desplazamiento horizontal. En móvil, tarjetas.
  - Las señales de atención van en tono neutro: `toneFor` no tiene un tipo para los segmentos. El texto sale de la API.
- **Tareas:**
  - `GET /tasks` con `assigned_to_id` = el usuario actual por defecto. El administrador (`users.read`) elige otro asesor o "todos" (`assigned_to_id=all` en la URL, que no se manda a la API).
  - Filtros: `due`, `task_status` (pendientes por defecto) y `priority` (catálogo `task_priority`).
  - **Textos de las opciones de `due` y `status`:** el contrato fija esos valores pero no trae un catálogo con sus textos, así que los nombres de las opciones del filtro ("vencidas", "hoy", "próximas", "pendientes", "completadas", "canceladas") están en el front. El estado de cada tarea se muestra con `status_label`. Es una brecha para el backend: un catálogo `task_status`.
- **Crear y editar** con `ActionModal`:
  - Título, descripción, vence (`datetime-local`) y prioridad (por defecto `MEDIUM`, el valor por omisión del contrato).
  - Responsable: solo el administrador.
  - Desde una fila de la bandeja, la solicitud ya viene elegida. Desde "Nueva tarea", hay un buscador de solicitudes (`GET /workday/applications?search=`).
  - Las tareas de oportunidad no se crean desde Mi día: eso va en `features/clients`. Mi día sí las lista; no hay ruta de oportunidad, así que van sin enlace.
- **Completar y cancelar:** completar es una confirmación; cancelar pide el motivo (obligatorio en la API). Un `409 TASK_NOT_PENDING` va al toast y refresca la lista.
- **Piezas locales candidatas a la librería:** `FilterToolbar` (búsqueda, selects, hoja inferior y chips), los segmentos como botones con conteo, y `MyDayIcon`.

**Parte 3 (front 2, 2026-11-18):**
- **Reportes:**
  - "Reportes" es la tercera entrada de "Operación", con `reports.read`.
  - Pestañas en la URL (`tab=embudo|solicitudes`).
  - Reusa la barra de filtros del dashboard: se le agregaron "filtros extra" para el estado multivalor (`status=…&status=…`, catálogo `application_status`) y "Agrupar por", que solo aparece en el embudo.
  - Embudo sin agrupar: `FunnelTable`, la misma del dashboard. Agrupado: `DataTable` con la fila "Total" arriba, una fila por grupo y una columna por etapa (número y conversión). Las etapas y sus nombres salen de la respuesta.
  - "Solicitudes": `DataTable` o `CardList`, paginado. El documento llega enmascarado y se muestra tal cual. Las filas no enlazan: `ReportApplication` no trae `id`.
- **Exportar** (con `reports.export`):
  - "Descargar CSV" baja el archivo de la respuesta (`parseAs: "blob"`) con el nombre de `Content-Disposition`.
  - Un `422 EXPORT_TOO_LARGE` muestra un aviso con "Preparar exportación".
  - "Mis exportaciones" es un `SidePanel` que se abre desde el encabezado y sola al preparar una. Muestra estado (`status_label`), periodo, filas, cuándo se pidió y vencimiento.
  - **Consulta cada 3 s por trabajo:** las que están `PENDING`/`RUNNING` se consultan una por una (`GET /report-export-jobs/{id}`), no el listado, porque el listado gasta del cupo de 20 por minuto de `/reports/*`. Se consulta mientras el panel está abierto.
  - "Descargar" pide la URL firmada cada vez; un `409` o un `410` van al toast y refrescan la lista.
  - Un `429 TOO_MANY_EXPORTS` se muestra junto al botón (`role="alert"` + `aria-describedby`).
  - `Idempotency-Key`: un UUID por intento (`lib/api/idempotency.ts`). Se reusa si se reintenta con los mismos filtros y se cambia al terminar bien o con otros filtros.
- **Avisos del portal:**
  - `/portal/avisos`, en `features/buyer-notifications/`. Los no leídos van primero (orden en el front) y se piden de a 50, con "Ver avisos anteriores".
  - Cada aviso es un botón con `aria-expanded` que abre el mensaje; al abrir uno sin leer se marca (`PATCH .../read`) y no cambia de lugar mientras dura la visita.
  - "Marcar todos como leídos" aparece si hay sin leer.
  - En `features/buyer-portal` solo cambió lo permitido: la entrada "Avisos" con su ícono, el número sin leer (`unread-count`, leído "N sin leer") y la barra inferior de 3 columnas. También el handler de `unread-count` en `portal.fixtures.ts` y la prueba de la navegación, que antes comprobaba que "Avisos" no estuviera.
- **E2E:**
  - `e2e/backoffice/operations.spec.ts`: dashboard, Mi día y reportes, con axe en claro para no pasar el cupo de 20 por minuto.
  - Los avisos van dentro del flujo existente de `e2e/portal/portal.spec.ts`, para no gastar otro enlace del comprador por proyecto.
  - `e2e/auth.setup.ts` ahora espera `/dashboard` después del login (el inicio nuevo).
