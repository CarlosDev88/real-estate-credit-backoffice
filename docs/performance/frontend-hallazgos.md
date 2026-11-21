# Hallazgos de la auditoría de performance del frontend

Estado final (Parte 4). La Parte 1 abrió los hallazgos con la línea base; cada uno lleva cómo se solucionó, con el antes y después de un **A/B del mismo día** (el código de la línea base, `19c75c7`, y el final, medidos uno detrás de otro el 2026-11-20). El informe público es [`docs/PERFORMANCE.md`](../PERFORMANCE.md). Los números son medianas de 5 corridas. La tabla completa y el método están en [`frontend-linea-base.md`](frontend-linea-base.md).

**Severidad** (`specs/TAREA-performance-front.md` §3):
- **Alta:** una Web Vital en "pobre" (LCP > 4 s, CLS > 0,25, INP > 500 ms) o Lighthouse móvil < 50 en una página principal.
- **Media:** "necesita mejorar" (LCP de 2,5 a 4 s, CLS de 0,1 a 0,25, INP de 200 a 500 ms), o más de 50 kB gzip evitables en una ruta.
- **Baja:** mejoras menores.
- **Informativa:** contexto, o lo que depende del backend.

**Criterio de corrección** (decidido en la spec): se corrigen todas las Altas y Medias y las Bajas pequeñas; lo que no se corrige queda como **aceptado**, con su motivo.

| Id | Título | Severidad | Página(s) | Estado |
| --- | --- | --- | --- | --- |
| [PERF-01](#perf-01--el-expediente-encadena-4-etapas-de-peticiones-y-carga-todas-sus-pestañas-y-modales-de-entrada) | El expediente encadena 4 etapas de peticiones y carga todas sus pestañas y modales de entrada | Alta | `/solicitudes/<id>` | corregido (resto: depende del backend) |
| [PERF-02](#perf-02--el-dashboard-se-mueve-al-llegar-los-datos) | El dashboard se mueve al llegar los datos | Alta | `/dashboard` | corregido |
| [PERF-03](#perf-03--el-texto-principal-del-portal-espera-sesión-y-solicitud-en-cadena) | El texto principal del portal espera sesión y solicitud en cadena | Alta | `/portal` | depende del backend (front corregido) |
| [PERF-04](#perf-04--abrir-registrar-respuesta-bloquea-el-hilo-principal) | Abrir "Registrar respuesta" bloquea el hilo principal | Alta | `/solicitudes/<id>` | corregido |
| [PERF-05](#perf-05--las-páginas-con-sesión-no-pintan-nada-hasta-authme-y-piden-sus-datos-después) | Las páginas con sesión no pintan nada hasta `/auth/me` y piden sus datos después | Media | backoffice | aceptado |
| [PERF-06](#perf-06--mi-día-y-prospectos-se-mueven-al-llegar-los-datos) | Mi día y Prospectos se mueven al llegar los datos | Media | `/mi-dia`, `/prospectos` | corregido |
| [PERF-07](#perf-07--tbt-alto-en-el-listado-de-solicitudes) | TBT alto en el listado de solicitudes | Media | `/solicitudes` | aceptado |
| [PERF-08](#perf-08--aceptar-invitacion-sin-token-carga-el-formulario-entero-y-pinta-el-mensaje-tarde) | `/aceptar-invitacion` sin token carga el formulario entero y pinta el mensaje tarde | Media | `/aceptar-invitacion` | corregido |
| [PERF-09](#perf-09--el-cuerpo-del-403-de-authrefresh-no-se-lee-y-la-petición-queda-abierta) | El cuerpo del `403` de `/auth/refresh` no se lee y la petición queda abierta | Baja | páginas sin sesión | corregido |
| [PERF-10](#perf-10--el-login-carga-327-kb-gzip-y-tiene-tbt-móvil-de-520-ms) | El login carga 327 kB gzip y tiene TBT móvil de 520 ms | Media | `/login` | corregido (resto aceptado) |
| [PERF-11](#perf-11--metadatabootstrap-36-kb-viaja-en-cada-carga-con-no-store) | `metadata/bootstrap` (36 kB) viaja en cada carga con `no-store` | Informativa | backoffice | depende del backend |
| [PERF-12](#perf-12--fuentes-con-fontsource-dentro-del-css-bloqueante-sin-preload) | Fuentes con `@fontsource` dentro del CSS bloqueante, sin `preload` | Informativa | todas | aceptado |
| [PERF-13](#perf-13--cada-fila-del-listado-precarga-su-expediente-19-peticiones-rsc) | Cada fila del listado precarga su expediente (19 peticiones RSC) | Informativa | `/solicitudes` (y los listados con enlaces) | aceptado |

---

### PERF-01 — El expediente encadena 4 etapas de peticiones y carga todas sus pestañas y modales de entrada
- **Severidad:** Alta (LCP móvil en "pobre").
- **Página(s):** `/solicitudes/<id>` (asesora; SOL-000064).
- **Métrica afectada:**
  - Lighthouse móvil: LCP 5,81 s, performance 51, TBT 1.534 ms.
  - Web Vitals (escritorio, CPU ×4): LCP 3.160 ms.
  - Es la ruta más pesada: 480,7 kB gzip de primera carga, de los que 231,0 kB son propios.
  - Lighthouse estima 136 kB de JS sin usar.
- **Causa probable:**
  1. **Cascada.** `WorkspaceScreen` (`frontend/src/features/applications/workspace-screen.tsx:149`) espera a `useApplicationDetail(id)` antes de montar `Workspace`. Las 11 consultas de las secciones (completitud, participantes, inmueble, financiación, evaluación, documentos por revisar, enlace, consentimientos, historial, radicaciones y `metadata/bootstrap`) solo dependen del `id`, pero salen recién en la tercera etapa. Cadena medida: `auth/me` (0,9 s) → detalle (1,4 s) → secciones (2,1–2,7 s) → perfil financiero del participante (2,8 s). En el 4G simulado de Lighthouse, cada etapa suma un viaje de ida y vuelta largo.
  2. **Todo entra de una vez.** `workspace-screen.tsx:12-24` importa de entrada las 4 pestañas (`DocumentsTab`, `FilingsTab`, `HistoryPanel`), los paneles de edición (`FinancingEditPanel`, `PropertyEditPanel`, `ParticipantPanel`, `AddParticipantModal`) y la tarjeta de comisión. `features/filings/filings-tab.tsx:23` importa el modal de respuesta (`response-modal.tsx`, 670 líneas), y `document-review` trae el visor y el cargador. La pestaña inicial es Resumen.
- **Corrección sugerida:**
  - Lanzar las consultas de las secciones en paralelo con el detalle, con `prefetchQuery` en `WorkspaceScreen` o subiendo los hooks.
  - Cargar con `next/dynamic` las pestañas que no están activas, los paneles de edición y los modales.
- **Esfuerzo:** medio.
- **Cómo se solucionó:**
  1. **Causa:**
     - El expediente esperaba el detalle antes de pedir sus secciones: 4 etapas de red.
     - Cargaba de entrada las pestañas, los paneles de edición y los 4 modales de acciones (Zod, react-hook-form, `Select`).
     - `Workspace` escuchaba las 12 consultas y repintaba el expediente entero con cada respuesta.
  2. **Cambio:**
     - `frontend/src/features/auth/route-paths.ts` y `route-prefetch.ts` (nuevos), y `backoffice-guard.tsx`: si el usuario entra directo a `/solicitudes/<id>`, la guarda pide detalle, participantes e inmueble a la vez que `/auth/me`. El módulo se carga con `import()` solo en esa ruta.
     - `workspace-queries.ts`: `queryOptions` compartidos por la guarda y la página.
     - `workspace-screen.tsx`:
       - `WorkspacePrefetch` lanza las demás secciones en paralelo con el detalle.
       - `Workspace` se parte en encabezado, pestañas, una tarjeta por consulta y paneles.
       - Las pestañas Documentos, Radicación e Historial, los paneles de edición y la tarjeta de comisión pasan a `next/dynamic`.
     - `workspace-header.tsx`: los 4 modales de acciones, con `next/dynamic`, se montan al abrirse.
     - `status-history-entry.tsx`: la entrada del historial, aparte de su panel paginado.
     - `lib/hooks/use-lazy.ts`: precarga en reposo (`useIdlePreload`) y montaje al abrir (`useMountedOnce`).
  3. **Verificación** (A/B del mismo día, mediana de 5):
     - JS de primera carga: 480,6 → 337,1 kB gzip (−30 %).
     - Lighthouse móvil: LCP 5,14 → 3,85 s, performance 56 → 68, TBT 992 → 809 ms.
     - Escritorio: performance 95 → 98, LCP 1,27 → 1,07 s.
     - Web Vitals: LCP 2.664 → 2.180 ms.
     - Red: de 4 etapas a 3.
     - Pruebas: `workspace.test.tsx` ("pide las secciones sin esperar al detalle"), `route-prefetch.test.ts` y `use-lazy.test.ts`.
  4. **Lo que queda:** el LCP móvil está justo por debajo de 4 s. El resto es la cadena `auth/me` → detalle y las 14 peticiones compitiendo por las 6 conexiones HTTP/1.1 de la simulación.
     - Depende del backend: un endpoint agregado del expediente, o HTTP/2 en el despliegue.
  5. **Commits:** `aaa7810` (`perf(frontend): load dossier sections in parallel and lazy-load its tabs, panels and modals`) y el ajuste de la guarda de la Parte 4 (`perf(frontend): prefetch only the dossier from the guard and drop the bootstrap prefetch`).
  6. **Estado:** corregido (el resto, depende del backend).

### PERF-02 — El dashboard se mueve al llegar los datos
- **Severidad:** Alta (CLS en "pobre").
- **Página(s):** `/dashboard` (admin).
- **Métrica afectada:**
  - CLS: 0,564 en Lighthouse móvil, 0,187 en escritorio y 0,213 en Web Vitals (escritorio).
  - Lighthouse móvil: performance 55.
- **Causa probable:** `BlockState` (`frontend/src/features/dashboard/block-state.tsx:26`) muestra un bloque de carga de 160 px fijos, sea cual sea el bloque. Las tarjetas de resumen, el estado, el embudo, la carga por asesor y los resultados por banco llegan con otra altura, y todo lo de abajo se corre. Lighthouse culpa a `main#contenido > div.grid > div.grid`, la grilla de `StatusSnapshot` y `FunnelBlock` (`dashboard-screen.tsx:117`).
- **Corrección sugerida:** reservar en cada bloque la altura de su contenido final (`loadingBlocks` por bloque y alto mínimo en la grilla).
- **Esfuerzo:** pequeño.
- **Cómo se solucionó:**
  1. **Causa:** los bloques de carga medían 84 y 160 px. Las cifras llegan con 509 px en móvil y el estado y el embudo con 600 a 850 px, y todo lo de abajo se corría. Pasa cuando los datos llegan después de la primera pintura, que es lo normal con un backend lento o una red móvil.
  2. **Cambio:**
     - `BlockState` (`block-state.tsx`) acepta un esqueleto propio.
     - `SummaryTiles` (`summary-blocks.tsx`) pinta las mismas tarjetas con sus etiquetas, que son fijas, y un esqueleto en lugar del número.
     - El estado y el embudo reservan 520 y 376 px (`summary-blocks.tsx`, `detail-blocks.tsx`).
  3. **Verificación** (A/B del mismo día):
     - CLS en escritorio: 0,191 → 0,000 (las 5 corridas).
     - Web Vitals: 0,213 → 0,000.
     - Móvil en caché tibia: 0,564 → 0,000.
     - Bisección: la línea base con solo este cambio da CLS 0 en todas las corridas y el mismo TBT (~387 ms contra ~385).
     - Prueba: `dashboard.test.tsx`.
  4. **Commit:** `38c1dda` (`perf(frontend): reserve the final height of loading blocks on the dashboard, My day and prospects`).
  5. **Estado:** corregido.

### PERF-03 — El texto principal del portal espera sesión y solicitud en cadena
- **Severidad:** Alta (LCP móvil en "pobre").
- **Página(s):** `/portal` (comprador).
- **Métrica afectada:**
  - Lighthouse móvil: LCP 5,29 s (FCP 2,31 s), performance 62.
  - Web Vitals (escritorio, CPU ×4): LCP 2.000 ms.
  - Primera carga de 431,2 kB gzip.
- **Causa probable:**
  - El elemento LCP es el subtítulo con el banco y el código ("Tu crédito de compra de vivienda usada con Bancolombia · SOL…"). Depende de `GET /buyer/applications/<id>`, que solo puede salir cuando responde `GET /buyer/session` (`frontend/src/features/buyer-portal/portal-guard.tsx:78`): la sesión es lo que da el id. La cadena es HTML → JS → sesión → solicitud → render.
  - Además, la primera carga trae el cargador de documentos (`components/ui/document-uploader.tsx`) y los formularios (`zod` y RHF, 48 kB).
- **Corrección sugerida:**
  - En el front: diferir lo que no es del inicio (el cargador y los formularios) y reservar el espacio del encabezado.
  - Depende del backend: que `GET /buyer/session` devuelva el resumen de la solicitud, o que exista `GET /buyer/applications/current`. Así se ahorra una etapa.
- **Esfuerzo:** medio.
- **Cómo se solucionó:**
  1. **Causa:** la primera carga (431 kB gzip) traía el modal de retiro (Zod, react-hook-form, `Select`) y la hoja de carga de documentos. Además, el texto principal espera la cadena sesión → solicitud.
  2. **Cambio:** `frontend/src/features/buyer-portal/home-screen.tsx`: `WithdrawModal` y `UploadSheet` pasan a `next/dynamic`, se montan al abrirse y se precargan en reposo.
  3. **Verificación** (A/B del mismo día, mismo comprador, SOL-000013):
     - JS: 431,0 → 322,3 kB gzip (−25 %).
     - Lighthouse móvil: LCP 5,31 → 4,72 s, performance 63 → 70, TBT 590 → 416 ms.
     - Escritorio: LCP 1,11 → 1,00 s.
     - Web Vitals: LCP 1.936 → 1.656 ms.
  4. **Corrección del informe de la Parte 2:** allí se publicó "LCP 2,08 s, performance 95". Esa medición cayó en otra solicitud de demo (SOL-000010), cuyo comprador tenía consentimientos pendientes, y midió esa pantalla en lugar del inicio. Ahora el script fija la solicitud (`PERF_BUYER_APP_CODE`).
  5. **Lo que queda (depende del backend):** el LCP móvil sigue en "pobre". Para recortarlo falta la cadena sesión → solicitud: la sesión es la que trae el id. La sugerencia, para la tarea de carga: que `GET /buyer/session` devuelva el resumen de la solicitud, o un `GET /buyer/applications/current`.
  6. **Commit:** `a3b57b9` (`perf(frontend): keep forms and the upload sheet out of the first load of the portal, the invitation and the login`).
  7. **Estado:** depende del backend (la parte del front, corregida).

### PERF-04 — Abrir "Registrar respuesta" bloquea el hilo principal
- **Severidad:** Alta (INP en "pobre").
- **Página(s):** `/solicitudes/<id>?tab=radicacion`.
- **Métrica afectada:** INP de 576 ms (corridas: 432, 640, 600, 576 y 560), en escritorio con CPU ×4. Como referencia, abrir el filtro del listado da 168 ms y cambiar de pestaña, 72 ms.
- **Causa probable:** el clic monta de una vez `RecordResponseModal` (`frontend/src/features/filings/response-modal.tsx:338`): `ActionModal`, el formulario con `Select`, campos de fecha y montos, y su esquema Zod. Son componentes de antd que la página todavía no había pintado, así que el CSS-in-JS genera sus estilos en ese mismo clic. Se confirma con un trace en la Parte 2.
- **Corrección sugerida:**
  - Montar el modal con `next/dynamic` y precargarlo cuando la pestaña Radicación se ve o se pasa el cursor por el botón.
  - Separar lo pesado del primer frame: abrir el modal y pintar el formulario en una transición.
- **Esfuerzo:** medio.
- **Cómo se solucionó:**
  1. **Causa:** el perfil de CPU del clic (×4) dio 589 ms de trabajo en la misma tarea.
     - 154 ms son del CSS-in-JS de antd generando los estilos del modal y sus campos.
     - 140 ms son un layout forzado por la animación de entrada de rc-dialog (`getBoundingClientRect`).
     - 102 ms son de React.
  2. **Cambio:** `frontend/src/features/filings/response-timeline.tsx`: "Registrar respuesta" y "Corregir" abren el modal en `startTransition`. El clic pinta enseguida, con el botón en estado de carga, y el modal se arma sin bloquear la página.
  3. **Verificación:** INP 360 → 104 ms (A/B del mismo día; en la línea base de la Parte 1 dio 576 ms). Las pruebas de radicación siguen en verde.
  4. **Commit:** `7fd0768` (`perf(frontend): open the record-response modal in a transition`).
  5. **Estado:** corregido.

### PERF-05 — Las páginas con sesión no pintan nada hasta `/auth/me` y piden sus datos después
- **Severidad:** Media (LCP móvil en "necesita mejorar").
- **Página(s):** todo el backoffice. LCP móvil: `/dashboard` 2,53 s, `/mi-dia` 2,56 s, `/solicitudes` 2,69 s, `/clientes` 2,59 s, `/admin/usuarios` 2,38 s, `/mis-comisiones` 2,37 s, `/prospectos` 2,54 s y `/reportes` 2,22 s.
- **Métrica afectada:**
  - FCP = LCP en casi todas, porque lo primero que se pinta ya es el contenido.
  - Todas piden sus datos en una segunda oleada: `auth/me` termina hacia los 0,9 s y los datos de la página salen entre 1,4 y 1,7 s.
- **Causa probable:** `BackofficeGuard` (`frontend/src/features/auth/backoffice-guard.tsx:44`) muestra `AppShellSkeleton`, que no tiene contenido, hasta que responde `/auth/me`. Recién entonces monta la página, que pide sus datos. La guarda decide el menú y los permisos, así que no puede quitarse.
- **Corrección sugerida:** pedir en paralelo con `/auth/me` lo que todas las páginas usan. `metadata/bootstrap` (36 kB) aparece en la segunda oleada de 8 de las 9 páginas del backoffice medidas. Medir si conviene adelantar también la consulta principal de cada ruta, sin pedir nada que los permisos no dejen ver.
- **Esfuerzo:** pequeño a medio.
- **Cómo se resolvió:**
  1. **Qué se probó:** adelantar `metadata/bootstrap` desde la guarda, a la vez que `/auth/me` (Parte 2).
  2. **Qué mostró la medición:** con un A/B del mismo día y una bisección, no movió el LCP. Además, sumó ~115 ms de TBT en las páginas que no usan el bootstrap: `/admin/usuarios` dio 458 ms con el adelanto y 343 sin él. Se quitó en la Parte 4.
  3. **Lo que queda (aceptado):** el LCP móvil de las páginas con sesión está entre 2,2 y 2,6 s. Bajarlo de 2,5 s pide pintar la página sin esperar la sesión en el cliente (sesión en el servidor), lo que es cambiar la arquitectura de rutas, fuera de esta tarea (§7). En escritorio todas quedan en 98–100.
  4. **Commit:** `perf(frontend): prefetch only the dossier from the guard and drop the bootstrap prefetch` (Parte 4).
  5. **Estado:** aceptado.

### PERF-06 — Mi día y Prospectos se mueven al llegar los datos
- **Severidad:** Media (CLS en "necesita mejorar").
- **Página(s):** `/mi-dia` (asesora) y `/prospectos` (broker).
- **Métrica afectada:**
  - `/mi-dia`: CLS 0,148 en Lighthouse móvil (Web Vitals de escritorio: 0,009).
  - `/prospectos`: CLS 0,214 en Lighthouse móvil (las 5 corridas), 0,069 en escritorio y 0,065 en Web Vitals (escritorio).
- **Causa probable:** el mismo patrón de PERF-02. La sección que Lighthouse culpa (`main#contenido > div.grid > section.bg-bg-surface`) cambia de alto cuando llega su contenido; los bloques de `LoadingState` tienen alturas fijas (`frontend/src/components/ui/state-views.tsx:23`).
- **Corrección sugerida:** reservar la altura final en esas secciones.
- **Esfuerzo:** pequeño.
- **Cómo se solucionó:**
  1. **Causa:**
     - Mi día: el bloque de carga de los segmentos medía 64 px y con datos mide 277 px en móvil.
     - Prospectos: el resumen de estados no ocupaba lugar hasta llegar.
  2. **Cambio:**
     - `frontend/src/features/workday/tray.tsx`: `SegmentsSkeleton` usa la misma grilla, con "Todas" y los 7 segmentos.
     - `frontend/src/features/broker/broker-screen.tsx`: `StatusSummarySkeleton`, la tarjeta con su título y el alto de la lista.
  3. **Verificación** (A/B del mismo día):
     - Mi día: CLS móvil 0,148 → 0,010 (la línea base daba 0,148 en 3 de 5 corridas).
     - Prospectos: CLS en escritorio 0,069 → 0,010, en Web Vitals 0,065 → 0,009 y en caché tibia 0,214 → 0,000.
  4. **Commit:** `38c1dda`.
  5. **Estado:** corregido.

### PERF-07 — TBT alto en el listado de solicitudes
- **Severidad:** Media.
- **Página(s):** `/solicitudes` (asesora). El patrón se ve más suave en el resto del backoffice: 344–623 ms.
- **Métrica afectada:**
  - Lighthouse móvil: TBT 1.244 ms y performance 73 (en caché tibia, TBT 684 ms).
  - Escritorio: TBT 208 ms.
  - Evaluación de scripts: 2,2 s en el hilo principal (móvil).
- **Causa probable:** la tabla de 20 filas con celdas de antd (etiquetas, menús y tooltips) se pinta en un solo bloque cuando llegan los datos (`frontend/src/features/applications/list-cells.tsx`), además de la hidratación de la ruta. Se confirma con un trace en la Parte 2.
- **Corrección sugerida:** según el trace, aligerar las celdas (menús y tooltips montados al abrirlos) o partir el render.
- **Esfuerzo:** medio.
- **Cómo se resolvió:**
  1. **Qué se probó:** en la Parte 2, `ScrollTabs` dejó de medir en su efecto de montaje (commit `15e39b5`), porque el perfil le atribuía 270 ms de layout forzado.
  2. **Qué mostró la medición:** el A/B del mismo día lo desmintió.
     - En `/solicitudes` no mejora: TBT ~529 ms sin el cambio y ~508 con él.
     - Empeora otras páginas: `/reportes` pasa de ~271 a ~464 ms y `/admin/usuarios` de ~326 a ~465 ms.
     - El layout no se ahorra, se cambia de lugar.
     - La mejora de la Parte 2 (1.244 → 532 ms) venía de las condiciones: con el código de la línea base, el TBT de hoy es 644 ms.
     - **Se revirtió en la Parte 4.**
  3. **Lo que queda (aceptado):** el TBT del listado (630 ms en móvil; 61 ms en escritorio) es la hidratación de antd y la tabla. Va con la propuesta de PERF-10 (`zeroRuntime`).
  4. **Commit:** `revert(frontend): restore the ScrollTabs mount measurement` (Parte 4).
  5. **Estado:** aceptado.

### PERF-08 — `/aceptar-invitacion` sin token carga el formulario entero y pinta el mensaje tarde
- **Severidad:** Media (LCP móvil en "necesita mejorar" y más de 50 kB evitables).
- **Página(s):** `/aceptar-invitacion` (sin sesión).
- **Métrica afectada:**
  - Lighthouse móvil: LCP 3,73 s (FCP 0,77 s), performance 87.
  - Primera carga de 363,8 kB gzip, de los que 114,1 kB son propios. Lighthouse estima 155 kB sin usar, el máximo de las 13 páginas.
- **Causa probable:** `AcceptInvitationScreen` (`frontend/src/features/admin-users/accept-invitation-screen.tsx:280`) lee el token en un `useEffect`. Hasta entonces el servidor manda un estado vacío, y el mensaje sin token se pinta recién después de hidratar. Además, la ruta importa de entrada el formulario con `zod`, RHF y `Select` (49 kB de formularios), aunque sin token no se muestra.
- **Corrección sugerida:** cargar el formulario con `next/dynamic` solo cuando hay token, y que el estado inicial reserve el espacio del mensaje.
- **Esfuerzo:** pequeño.
- **Cómo se solucionó:**
  1. **Causa:** el aviso sin token se pintaba recién después de hidratar, y la ruta traía el formulario entero.
  2. **Cambio:**
     - La página (`app/(public)/aceptar-invitacion/page.tsx`) lee `searchParams` en el servidor y solo le dice a la pantalla si hay token: el token no se usa en el servidor.
     - El formulario pasa a `accept-invitation-form.tsx`, con `next/dynamic` y solo con token, y las piezas compartidas a `accept-invitation-parts.tsx`.
  3. **Verificación** (A/B del mismo día):
     - JS: 363,7 → 254,0 kB gzip (−30 %).
     - Lighthouse móvil: LCP 3,72 → 0,76 s y performance 88 → 99.
     - Web Vitals: LCP 1.024 → 236 ms.
     - Lighthouse CI en GitHub: 98/100/96.
     - Prueba: `accept-invitation.test.tsx`.
  4. **Commit:** `a3b57b9`.
  5. **Estado:** corregido.

### PERF-09 — El cuerpo del `403` de `/auth/refresh` no se lee y la petición queda abierta
- **Severidad:** Baja.
- **Página(s):** las páginas sin sesión que piden `/auth/me`: `/login`, y cualquier página del backoffice con la sesión vencida.
- **Métrica afectada:**
  - Chrome no da por terminada la petición `POST /auth/refresh` hasta salir de la página: el evento `loadingFinished` no llega.
  - Lighthouse esperaba los 45 s de `maxWaitForLoad` ("The page loaded too slowly") y Playwright nunca llegaba a `networkidle`. Para medir se bajó el tope a 15 s (P10).
  - Además, `/login` sin sesión hace 2 peticiones que no sirven: `auth/me` → 401 y `auth/refresh` → 403.
- **Causa probable:** `postRefresh` (`frontend/src/lib/api/session.ts:105`) devuelve `response.ok` sin leer ni cancelar el cuerpo.
- **Corrección sugerida:** leer o cancelar el cuerpo (`await response.body?.cancel()`) en `postRefresh` y en cualquier otra respuesta que solo se usa por su estado.
- **Esfuerzo:** pequeño.
- **Cómo se solucionó:**
  1. **Causa:** `postRefresh` devolvía `response.ok` sin leer el cuerpo.
  2. **Cambio:** `frontend/src/lib/api/session.ts` lee el cuerpo antes de devolver el estado.
  3. **Verificación:**
     - Con el código de la línea base, las 5 corridas de `/login` terminan con "page loaded too slowly"; con el código final, ninguna.
     - Cada corrida de Lighthouse baja de 31 a 8 s.
     - Prueba: `session.test.ts`, para 403 y 200.
     - En el TBT del login no se ve diferencia el mismo día (173 → 195 ms, dentro del ruido). La baja de 520 a 165 ms que se publicó en la Parte 2 venía de las condiciones.
  4. **Commit:** `f35f660` (`fix(frontend): read the refresh response body so pages without a session finish loading`).
  5. **Estado:** corregido.

### PERF-10 — El login carga 327 kB gzip y tiene TBT móvil de 520 ms
- **Severidad:** Media (más de 50 kB evitables según Lighthouse).
- **Página(s):** `/login`.
- **Métrica afectada:**
  - Lighthouse móvil: performance 87, TBT 520 ms (718 ms en caché tibia).
  - Primera carga de 327,3 kB gzip, de los que 250 kB son compartidos. Lighthouse estima 122 kB sin usar.
- **Causa probable:**
  - Lo compartido trae antd con `App`, `notification`, `message`, `modal` y `skeleton` (`frontend/src/providers/antd-provider.tsx`) y TanStack Query.
  - La pantalla suma `zod` y RHF para dos campos (`features/auth/login-form.tsx:3-9`).
  - Los estilos CSS-in-JS de antd se calculan al hidratar.
- **Corrección sugerida:** medir en la Parte 2 qué parte de lo compartido es evitable sin cambiar de librería. Por ejemplo, partes del `App` de antd que solo se usan al mostrar un toast. Ver si la validación del login puede ir sin Zod sin cambiar los mensajes. Lo que no se pueda, queda aceptado con el número.
- **Esfuerzo:** medio.
- **Cómo se solucionó:**
  1. **Causa:** Zod y su resolver entraban en la primera carga para validar dos campos.
  2. **Cambio:** el esquema pasa a `features/auth/login-schema.ts`. `login-form.tsx` lo carga al validar por primera vez (mismo esquema y mismos mensajes) y lo precarga en reposo.
  3. **Verificación:**
     - JS: 327,2 → 298,0 kB gzip (−9 %).
     - Lighthouse móvil: 98 → 97, sin cambio (el mismo día, la línea base ya estaba en 98).
     - Lighthouse CI en el runner de GitHub (primera corrida, #39): 93/100/96.
  4. **Lo que queda (aceptado):** los 250 kB compartidos son Next, React y el núcleo de antd del layout raíz. antd 6 trae `theme.zeroRuntime` con `antd/dist/antd.css`, que quitaría el CSS-in-JS en todas las páginas. Es la palanca grande para el TBT de toda la app, pero pide generar el CSS con los tokens del tema claro y oscuro y validar todas las pantallas: queda como propuesta para una tarea aparte.
  5. **Commit:** `a3b57b9`.
  6. **Estado:** corregido (el resto, aceptado).

### PERF-11 — `metadata/bootstrap` (36 kB) viaja en cada carga con `no-store`
- **Severidad:** Informativa (depende del backend).
- **Página(s):** todo el backoffice. Es la respuesta más grande en 8 de las 9 páginas del backoffice medidas.
- **Métrica afectada:** 36,6 kB sin comprimir en cada carga completa de página.
- **Causa probable:** el backend responde con `Cache-Control: no-store` (SEC-08), así que el navegador no la guarda. En memoria, TanStack Query la tiene 10 minutos (`staleTime`, `frontend/src/features/applications/queries.ts:91`), pero una recarga la vuelve a pedir. El comentario de `useBootstrap` habla de revalidar con `If-None-Match`, cosa que con `no-store` no ocurre.
- **Corrección sugerida (backend):** como los catálogos no son datos personales, la respuesta podría ir con `private, max-age` y `ETag`. Otra opción es partirla en catálogos (cacheables) y permisos. En el front no hay nada que cambiar; solo se corrige el comentario.
- **Esfuerzo:** pequeño (backend).
- **Estado:** depende del backend. Lo recoge la tarea de carga (k6). En el front no se cambió nada.

### PERF-12 — Fuentes con `@fontsource` dentro del CSS bloqueante, sin `preload`
- **Severidad:** Informativa.
- **Página(s):** todas.
- **Métrica afectada:**
  - El CSS bloqueante es uno solo, de 12 kB.
  - Las 4 variantes de Inter que se usan se descargan después del CSS, sin `preload`.
  - La auditoría de `font-display` de Lighthouse pasa (score 1) y ninguna página tiene CLS por fuentes.
- **Causa probable:** `frontend/src/app/layout.tsx:1-6` importa los CSS de `@fontsource` (6 archivos, con todos los subconjuntos por `unicode-range`) en lugar de `next/font`.
- **Corrección sugerida:** pasar a `next/font/local` con los mismos archivos, que agrega `preload` y `size-adjust`, solo si la Parte 2 mide una mejora de FCP o LCP. Si no, queda aceptado.
- **Esfuerzo:** pequeño.
- **Decisión:** no se migra a `next/font`. El LCP móvil del login es 0,91 s y Web Vitals da 376 ms; la auditoría de `font-display` pasa y ninguna página tiene CLS por fuentes. No hay una métrica que mover.
- **Estado:** aceptado.

### PERF-13 — Cada fila del listado precarga su expediente (19 peticiones RSC)
- **Severidad:** Informativa (encontrado en la Parte 2).
- **Página(s):** `/solicitudes`, y en general cada listado con enlaces `next/link` visibles.
- **Métrica afectada:** después del `load` de `/solicitudes` salen 39 peticiones al servidor de Next: 19 son `/solicitudes/<id>?_rsc=…` (una por fila visible), 12 son las entradas del menú (dos por entrada) y el resto son las de la API de la página. Pasa igual antes y después de las correcciones.
- **Causa:** el prefetch por defecto de `Link` en el App Router: cada enlace que entra en pantalla pide el RSC de su ruta (en las rutas dinámicas, hasta su límite de carga).
- **Decisión:** se deja como está. Hace instantánea la navegación al expediente y no aparece en el hilo principal: con esperas de 1,5 s y de 6 s antes de interactuar, el INP del filtro es el mismo. Queda como dato para la prueba de carga (k6): cada vista del listado son unas 30 peticiones extra al servidor de Next.
- **Estado:** aceptado.
