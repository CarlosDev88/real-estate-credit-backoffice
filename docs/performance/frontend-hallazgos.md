# Hallazgos de la auditoría de performance del frontend

Lista viva: la Parte 1 los abre con la línea base y las Partes 2 y 4 agregan cómo se solucionó cada uno y su estado final. Los números son medianas de 5 corridas. La tabla completa y el método están en [`frontend-linea-base.md`](frontend-linea-base.md).

**Severidad** (`specs/TAREA-performance-front.md` §3):
- **Alta:** una Web Vital en "pobre" (LCP > 4 s, CLS > 0,25, INP > 500 ms) o Lighthouse móvil < 50 en una página principal.
- **Media:** "necesita mejorar" (LCP de 2,5 a 4 s, CLS de 0,1 a 0,25, INP de 200 a 500 ms), o más de 50 kB gzip evitables en una ruta.
- **Baja:** mejoras menores.
- **Informativa:** contexto, o lo que depende del backend.

**Criterio de corrección** (decidido en la spec): se corrigen todas las Altas y Medias y las Bajas pequeñas; lo que no se corrige queda como **aceptado**, con su motivo.

| Id | Título | Severidad | Página(s) | Estado |
| --- | --- | --- | --- | --- |
| [PERF-01](#perf-01--el-expediente-encadena-4-etapas-de-peticiones-y-carga-todas-sus-pestañas-y-modales-de-entrada) | El expediente encadena 4 etapas de peticiones y carga todas sus pestañas y modales de entrada | Alta | `/solicitudes/<id>` | abierto |
| [PERF-02](#perf-02--el-dashboard-se-mueve-al-llegar-los-datos) | El dashboard se mueve al llegar los datos | Alta | `/dashboard` | abierto |
| [PERF-03](#perf-03--el-texto-principal-del-portal-espera-sesión-y-solicitud-en-cadena) | El texto principal del portal espera sesión y solicitud en cadena | Alta | `/portal` | abierto |
| [PERF-04](#perf-04--abrir-registrar-respuesta-bloquea-el-hilo-principal) | Abrir "Registrar respuesta" bloquea el hilo principal | Alta | `/solicitudes/<id>` | abierto |
| [PERF-05](#perf-05--las-páginas-con-sesión-no-pintan-nada-hasta-authme-y-piden-sus-datos-después) | Las páginas con sesión no pintan nada hasta `/auth/me` y piden sus datos después | Media | backoffice | abierto |
| [PERF-06](#perf-06--mi-día-y-prospectos-se-mueven-al-llegar-los-datos) | Mi día y Prospectos se mueven al llegar los datos | Media | `/mi-dia`, `/prospectos` | abierto |
| [PERF-07](#perf-07--tbt-alto-en-el-listado-de-solicitudes) | TBT alto en el listado de solicitudes | Media | `/solicitudes` | abierto |
| [PERF-08](#perf-08--aceptar-invitacion-sin-token-carga-el-formulario-entero-y-pinta-el-mensaje-tarde) | `/aceptar-invitacion` sin token carga el formulario entero y pinta el mensaje tarde | Media | `/aceptar-invitacion` | abierto |
| [PERF-09](#perf-09--el-cuerpo-del-403-de-authrefresh-no-se-lee-y-la-petición-queda-abierta) | El cuerpo del `403` de `/auth/refresh` no se lee y la petición queda abierta | Baja | páginas sin sesión | abierto |
| [PERF-10](#perf-10--el-login-carga-327-kb-gzip-y-tiene-tbt-móvil-de-520-ms) | El login carga 327 kB gzip y tiene TBT móvil de 520 ms | Media | `/login` | abierto |
| [PERF-11](#perf-11--metadatabootstrap-36-kb-viaja-en-cada-carga-con-no-store) | `metadata/bootstrap` (36 kB) viaja en cada carga con `no-store` | Informativa | backoffice | depende del backend |
| [PERF-12](#perf-12--fuentes-con-fontsource-dentro-del-css-bloqueante-sin-preload) | Fuentes con `@fontsource` dentro del CSS bloqueante, sin `preload` | Informativa | todas | abierto |

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

### PERF-02 — El dashboard se mueve al llegar los datos
- **Severidad:** Alta (CLS en "pobre").
- **Página(s):** `/dashboard` (admin).
- **Métrica afectada:**
  - CLS: 0,564 en Lighthouse móvil, 0,187 en escritorio y 0,213 en Web Vitals (escritorio).
  - Lighthouse móvil: performance 55.
- **Causa probable:** `BlockState` (`frontend/src/features/dashboard/block-state.tsx:26`) muestra un bloque de carga de 160 px fijos, sea cual sea el bloque. Las tarjetas de resumen, el estado, el embudo, la carga por asesor y los resultados por banco llegan con otra altura, y todo lo de abajo se corre. Lighthouse culpa a `main#contenido > div.grid > div.grid`, la grilla de `StatusSnapshot` y `FunnelBlock` (`dashboard-screen.tsx:117`).
- **Corrección sugerida:** reservar en cada bloque la altura de su contenido final (`loadingBlocks` por bloque y alto mínimo en la grilla).
- **Esfuerzo:** pequeño.

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

### PERF-04 — Abrir "Registrar respuesta" bloquea el hilo principal
- **Severidad:** Alta (INP en "pobre").
- **Página(s):** `/solicitudes/<id>?tab=radicacion`.
- **Métrica afectada:** INP de 576 ms (corridas: 432, 640, 600, 576 y 560), en escritorio con CPU ×4. Como referencia, abrir el filtro del listado da 168 ms y cambiar de pestaña, 72 ms.
- **Causa probable:** el clic monta de una vez `RecordResponseModal` (`frontend/src/features/filings/response-modal.tsx:338`): `ActionModal`, el formulario con `Select`, campos de fecha y montos, y su esquema Zod. Son componentes de antd que la página todavía no había pintado, así que el CSS-in-JS genera sus estilos en ese mismo clic. Se confirma con un trace en la Parte 2.
- **Corrección sugerida:**
  - Montar el modal con `next/dynamic` y precargarlo cuando la pestaña Radicación se ve o se pasa el cursor por el botón.
  - Separar lo pesado del primer frame: abrir el modal y pintar el formulario en una transición.
- **Esfuerzo:** medio.

### PERF-05 — Las páginas con sesión no pintan nada hasta `/auth/me` y piden sus datos después
- **Severidad:** Media (LCP móvil en "necesita mejorar").
- **Página(s):** todo el backoffice. LCP móvil: `/dashboard` 2,53 s, `/mi-dia` 2,56 s, `/solicitudes` 2,69 s, `/clientes` 2,59 s, `/admin/usuarios` 2,38 s, `/mis-comisiones` 2,37 s, `/prospectos` 2,54 s y `/reportes` 2,22 s.
- **Métrica afectada:**
  - FCP = LCP en casi todas, porque lo primero que se pinta ya es el contenido.
  - Todas piden sus datos en una segunda oleada: `auth/me` termina hacia los 0,9 s y los datos de la página salen entre 1,4 y 1,7 s.
- **Causa probable:** `BackofficeGuard` (`frontend/src/features/auth/backoffice-guard.tsx:44`) muestra `AppShellSkeleton`, que no tiene contenido, hasta que responde `/auth/me`. Recién entonces monta la página, que pide sus datos. La guarda decide el menú y los permisos, así que no puede quitarse.
- **Corrección sugerida:** pedir en paralelo con `/auth/me` lo que todas las páginas usan. `metadata/bootstrap` (36 kB) aparece en la segunda oleada de 8 de las 9 páginas del backoffice medidas. Medir si conviene adelantar también la consulta principal de cada ruta, sin pedir nada que los permisos no dejen ver.
- **Esfuerzo:** pequeño a medio.

### PERF-06 — Mi día y Prospectos se mueven al llegar los datos
- **Severidad:** Media (CLS en "necesita mejorar").
- **Página(s):** `/mi-dia` (asesora) y `/prospectos` (broker).
- **Métrica afectada:**
  - `/mi-dia`: CLS 0,148 en Lighthouse móvil (Web Vitals de escritorio: 0,009).
  - `/prospectos`: CLS 0,214 en Lighthouse móvil (las 5 corridas), 0,069 en escritorio y 0,065 en Web Vitals (escritorio).
- **Causa probable:** el mismo patrón de PERF-02. La sección que Lighthouse culpa (`main#contenido > div.grid > section.bg-bg-surface`) cambia de alto cuando llega su contenido; los bloques de `LoadingState` tienen alturas fijas (`frontend/src/components/ui/state-views.tsx:23`).
- **Corrección sugerida:** reservar la altura final en esas secciones.
- **Esfuerzo:** pequeño.

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

### PERF-08 — `/aceptar-invitacion` sin token carga el formulario entero y pinta el mensaje tarde
- **Severidad:** Media (LCP móvil en "necesita mejorar" y más de 50 kB evitables).
- **Página(s):** `/aceptar-invitacion` (sin sesión).
- **Métrica afectada:**
  - Lighthouse móvil: LCP 3,73 s (FCP 0,77 s), performance 87.
  - Primera carga de 363,8 kB gzip, de los que 114,1 kB son propios. Lighthouse estima 155 kB sin usar, el máximo de las 13 páginas.
- **Causa probable:** `AcceptInvitationScreen` (`frontend/src/features/admin-users/accept-invitation-screen.tsx:280`) lee el token en un `useEffect`. Hasta entonces el servidor manda un estado vacío, y el mensaje sin token se pinta recién después de hidratar. Además, la ruta importa de entrada el formulario con `zod`, RHF y `Select` (49 kB de formularios), aunque sin token no se muestra.
- **Corrección sugerida:** cargar el formulario con `next/dynamic` solo cuando hay token, y que el estado inicial reserve el espacio del mensaje.
- **Esfuerzo:** pequeño.

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

### PERF-11 — `metadata/bootstrap` (36 kB) viaja en cada carga con `no-store`
- **Severidad:** Informativa (depende del backend).
- **Página(s):** todo el backoffice. Es la respuesta más grande en 8 de las 9 páginas del backoffice medidas.
- **Métrica afectada:** 36,6 kB sin comprimir en cada carga completa de página.
- **Causa probable:** el backend responde con `Cache-Control: no-store` (SEC-08), así que el navegador no la guarda. En memoria, TanStack Query la tiene 10 minutos (`staleTime`, `frontend/src/features/applications/queries.ts:91`), pero una recarga la vuelve a pedir. El comentario de `useBootstrap` habla de revalidar con `If-None-Match`, cosa que con `no-store` no ocurre.
- **Corrección sugerida (backend):** como los catálogos no son datos personales, la respuesta podría ir con `private, max-age` y `ETag`. Otra opción es partirla en catálogos (cacheables) y permisos. En el front no hay nada que cambiar; solo se corrige el comentario.
- **Esfuerzo:** pequeño (backend).

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
