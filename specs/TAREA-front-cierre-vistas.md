# TAREA — F7 del frontend: comisiones, broker, edición del expediente, acciones de la oportunidad y Storybook público

**Agente:** front 2, cuando se fusione el #30 (F5). **Worktree:** `wt-front-f7`, rama `feat/front-f7`, desde `origin/master`. **Puerto 3001**.
**API:** toda en `master` (módulos 8, 13, 16 y brechas 2). Sin mockups: Storybook + `design/README.md` + el lenguaje de las vistas ya hechas.

## Reglas
- Las mismas de la F5 (git solo lectura, buzón, no preguntes, librería de `components/ui` sin cambiarla, textos de negocio desde la API, filtros en la URL, verificaciones y capturas por parte).
- **Tú eres dueño de** `features/applications`, `features/clients`, `features/filings`, `features/document-review`, `features/buyer-*`, `features/dashboard`, `features/workday`, `features/reports` y lo nuevo de esta tarea. **No toques** `features/admin-*` ni `app/(backoffice)/admin/**` (los hace el front de la F6 en `wt-front-admin`, puerto 3002). En `nav-config.tsx`, cambio mínimo; no reordenes las entradas de "Administración".
- `Idempotency-Key` (con tu `useIdempotencyKey`) en todos los POST que lo admiten.

## Parte 1 — Comisiones
- **Administración** (`/comisiones`, con `commissions.read`; grupo "Administración" o "Finanzas", decide): pestañas "Liquidaciones" y "Planes".
  - Liquidaciones: `GET /commission-settlements` (estado, banco, asesor, broker, fechas, `needs_review`), detalle en `SidePanel` con sus partes; **pagar una parte** (`POST /commission-shares/{id}/pay`: fecha no futura y referencia), **anular** con motivo (`void`), **liquidar a mano** desde una solicitud desembolsada sin liquidación (`POST /applications/{id}/commission-settlement`). Marca visible de "Revisión pendiente".
  - Planes: `GET/POST/PATCH /commission-plans` (producto, tasa, reparto asesor/broker, vigencia; `PATCH` con `If-Match`), cerrar (`close`); "en uso" en solo lectura.
- **Mis comisiones** (`/mis-comisiones`, con `commissions.read_own`; asesor y broker): `GET /me/commissions` con estado y fechas; solo lo que trae la API (nunca base ni total).
- En el expediente desembolsado, una tarjeta "Comisión" con el estado de la liquidación (si el usuario tiene `commissions.read`).
- **Commit:** `feat(frontend): add commission settlements, plans and my commissions`

## Parte 2 — Broker y acciones de la oportunidad
- **Botones de transición de la oportunidad** en el panel (`features/clients`): de `available_actions` (`label`, `kind`, `target_status`, `reason_required` → motivo del catálogo `opportunity_lost_reason`), con `POST /opportunities/{id}/transitions`. Destructivas con confirmación. Quita "Asignarme" si la auto-asignación lo vuelve innecesario para el asesor (consérvalo para oportunidades `NEW` sin asesor).
- `Schemas["OpportunityAssignment"]` en lugar de la interfaz escrita a mano; `applications_count` en el listado de clientes; `status_label` donde se escribía.
- **Vista del broker** (REQ §6: "bandeja de prospectos, enlace de invitación y resumen de estados"): con su rol, el inicio es su bandeja (`GET /broker/opportunities` o `/opportunities` según el contrato: forma `BrokerOpportunity`), alta de cliente y oportunidad (lo que la API le permita), **enviar el enlace de autogestión** al comprador (`POST /applications/{id}/buyer-access-links`, si su permiso lo deja) y el **resumen de estado** de sus solicitudes (solo lo que trae la API: sin documentos ni finanzas). Navegación condicionada por rol (sin pantallas que le den 403).
- **Commit:** `feat(frontend): add the broker workspace and opportunity actions`

## Parte 3 — Edición del expediente por el asesor
- En el expediente (`features/applications`), editar en el lugar (tarjeta → modo edición, o `SidePanel`) con `If-Match`/`expected_version` y respetando el bloqueo después de `FILED` (la API responde el error; muéstralo):
  - participantes: agregar segundo solicitante o deudor solidario (`POST /applications/{id}/participants`), editar (`PATCH /application-participants/{id}`), quitar (`DELETE`, con confirmación);
  - perfil financiero e ingresos de cada participante (`PUT .../financial-profile`, `/financial-profiles/{id}/income-sources`, `/income-sources/{id}`);
  - inmueble (`PUT /applications/{id}/property`) y financiación (`PUT .../financing` con `GET .../eligible-bank-products`).
- **Quitar `RESPONSE_FORMS`** de la radicación: los campos por tipo de respuesta salen de `metadata` del catálogo (`fields`, `required`, `reason_catalog`).
- `CurrentFile` con `size_bytes`/`detected_mime_type`/`last_buyer_comment`: deja de pedir un `GET /document-files/{id}` por archivo. Lista de paquetes (`GET .../document-package-jobs`) en la pestaña Radicación. `is_response_overdue` en lugar del cálculo local.
- **Commit:** `feat(frontend): let advisors edit the dossier and use the new contract fields`

## Parte 4 — Storybook público y cierre
- **Storybook en GitHub Pages** (decidido por Carlos): workflow `.github/workflows/storybook-pages.yml`: en push a `master` y manual (`workflow_dispatch`), `pnpm install --frozen-lockfile`, `pnpm build-storybook`, `actions/upload-pages-artifact` + `actions/deploy-pages`; permisos mínimos (`contents: read`, `pages: write`, `id-token: write`); acciones fijadas por SHA como en los otros workflows; `concurrency` propio. Revisa antes que **ningún story llame a la API real ni muestre datos personales reales** (solo fixtures). Rutas relativas (Storybook se sirve en `/real-estate-credit-backoffice/`). Carlos activa Pages (Settings → Pages → Source: GitHub Actions).
- **Referencia de la API en la misma publicación** (decidido por Carlos): el mismo workflow genera una página estática desde `contracts/openapi.json` y la publica en `/api/` (URL esperada `https://carlosdev88.github.io/real-estate-credit-backoffice/api/`). Usa **Redoc** como HTML estático (`@redocly/cli build-docs contracts/openapi.json -o <salida>/api/index.html`, versión fijada) o Swagger UI estático; decide y anótalo. Sin servidor detrás: es solo lectura (sin "probar"), con buscador, ejemplos, errores y permisos. Título "API · Real Estate Credit Backoffice". El artefacto de Pages junta las dos salidas (`storybook-static/` en la raíz y la API en `api/`). Revisa que el contrato no tenga datos personales ni secretos en los ejemplos.
- **`docs/DESIGN-SYSTEM.md`**: qué es Umbral, cómo abrirlo (local y el enlace público), qué hay (fundamentos, componentes, patrones, guía), de dónde salen los tokens, reglas (colores, a11y en CI, tonos, redacción), capturas claro/oscuro y cómo agregar un componente. Enlázalo desde el `README.md` (Project Status y Documentation) con un badge "Storybook" al enlace público **y otro "API reference" al de `/api/`** (también en "Documentation"). Toca solo esas líneas del README.
- **E2E** (`:3001`): pagar una parte de comisión y verla en "Mis comisiones" del asesor; transición de una oportunidad a perdida con motivo; el broker ve su bandeja y envía un enlace; el asesor edita el inmueble antes de radicar.
- Brechas, candidatos a la librería, merge de `master`, `api:gen`, título y descripción del PR (en español).
- **Commits:** `ci(ui): publish Storybook to GitHub Pages`, `docs(ui): add the design system guide`, `test(frontend): add commissions, broker and dossier editing end-to-end checks`.

## Precisiones acordadas
- **Parte 4 — referencia de la API con Redoc** (`@redocly/cli@2.72.1 build-docs --inlineBundle`): un solo HTML sin CDN ni servidor (solo pide a `cdn.redoc.ly` el logo "API docs by Redocly"). Redoc no tiene "probar", así que la página es de solo lectura sin configurar nada.
- **Parte 4 — workflow de Pages en dos jobs** (`build` con `contents: read`; `deploy` con `pages: write` e `id-token: write` y el entorno `github-pages`). En `push` a `master` corre solo si cambia `frontend/**`, `design/**`, `contracts/openapi.json` o el propio workflow; `concurrency` propio (`pages-<ref>`) sin cancelar un despliegue en curso.
- **Parte 4 — `docs/DESIGN-SYSTEM.md` en español**, como la guía y `docs/SEGURIDAD.md`; las líneas del README siguen en inglés.
- **Parte 4 — datos de los stories:** los nombres y el documento de ejemplo (`1032445908`) son fixtures inventados que ya están en el repo público (pruebas y Storybook); publicar Storybook no los expone más. Los archivos del visor son de muestra ("Sin datos reales").
- **Parte 4 — E2E con usuarios `@demo.local`:** el pago de comisión (administrador de demo), "Mis comisiones" (el asesor de demo dueño de la parte) y el broker usan la contraseña de demo publicada en el backend (`E2E_DEMO_PASSWORD` la cambia). La oportunidad y el inmueble usan el asesor de `.env.local`.
- **Cierre — liquidación de la tarjeta "Comisión":** con `application_id` llegan todas las de la solicitud; gana la vigente y, si no hay, la primera (la más reciente). Ya no se acota por banco ni fechas.
- **Cierre — `oneOf` de `/applications`:** cada pantalla afirma la forma que le toca por su rol (`PaginatedApplicationSummaryList` el broker; `PaginatedApplicationList` la liquidación a mano, que es del administrador), igual que hizo el #36 en el listado y el expediente.
- **Cierre — `status_label` de `BrokerOpportunity`:** la bandeja del broker usa el texto de la API; el catálogo `opportunity_status` queda solo para el filtro.
- **Cierre — E2E de `clients.spec.ts`:** desde el #36 la oportunidad que crea un asesor nace asignada a él; la prueba pulsa "Asignarme" solo si aparece.
