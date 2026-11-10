# Tarea: frontend Next.js — base y reparto en dos agentes

## Objetivo
Construir el frontend de la app (backoffice y portal del comprador) en `frontend/`, sobre el design system Umbral y los mockups aprobados, consumiendo la API Django por un cliente tipado desde el contrato OpenAPI.

Una sola app Next.js con dos zonas:
- **Backoffice**: usuarios internos (admin, asesor, broker, constructora). Navegación según los permisos de `/auth/me`.
- **Portal del comprador**: móvil primero. Sesión temporal desde el enlace mágico, sin contraseña.

## Requisitos previos
1. `TAREA-monorepo.md` fusionada: existen `backend/` y `contracts/openapi.json`.
2. El agente lee antes de empezar:
   - `design/README.md` y los mockups `design/screens/*.html` (se abren en el navegador);
   - `docs/API_REST_MVP_CREDITO.md`, secciones 2 a 9, 16, 17, 18, 19 y 28;
   - `docs/REQUERIMIENTOS_MVP_CREDITO.md`, §8.5 (el frontend no define listas ni estados) y §10.3–10.5 (pruebas).

## Reglas de trabajo
- El agente **no** hace `commit`, `push`, `merge` ni `rebase`; git solo en lectura. Trabaja por partes y al cerrar cada una propone un mensaje de commit corto, sin `Co-Authored-By`. Carlos commitea.
- Antes de cada parte, el agente presenta las ambigüedades que encuentre, una por una y con su recomendación. Las precisiones acordadas se agregan al final de esta spec.
- No se inventan endpoints. Si un mockup muestra algo que la API no da, se anota en "Brechas del backend" y se simula con MSW hasta que exista.

## Stack
Versiones estables vigentes al arrancar, fijadas en `package.json`. El agente verifica que sean compatibles entre sí antes de instalar.

| Pieza | Elección |
| --- | --- |
| Framework | Next.js (App Router) + React + TypeScript en modo `strict` |
| Paquetes | pnpm |
| UI | Ant Design con `@ant-design/nextjs-registry` y `StyleProvider layer`, más Tailwind CSS v4 para layout y utilidades |
| Tokens | `design/generated/tokens.css`, `tailwind-theme.css`, `antd-theme.ts` y `status-tones.ts`, importados desde `../design/generated`. **No se copian.** |
| Datos | TanStack Query (servidor) y TanStack Table (estado de tablas) |
| Formularios | React Hook Form + Zod |
| Cliente API | `openapi-typescript` (tipos desde `../contracts/openapi.json`) + `openapi-fetch` |
| Visor PDF | `pdfjs-dist` |
| Pruebas | Vitest + Testing Library + MSW; Playwright + `@axe-core/playwright` |
| Calidad | ESLint, Prettier y `tsc --noEmit` |

## Estructura

```
frontend/
├── src/
│   ├── app/
│   │   ├── (auth)/login/
│   │   ├── (backoffice)/            ← layout con AppShell y guarda de sesión interna
│   │   │   ├── solicitudes/
│   │   │   └── solicitudes/[id]/
│   │   ├── acceso/                  ← consume el enlace mágico
│   │   └── (portal)/portal/         ← layout móvil y guarda de sesión del comprador
│   │       └── documentos/
│   ├── components/ui/               ← piezas compartidas (de F0)
│   ├── features/                    ← una carpeta por funcionalidad (applications, buyer-portal, documents…)
│   ├── lib/api/                     ← cliente, errores, CSRF, ETag y tipos generados
│   ├── lib/format/                  ← COP, fechas y porcentajes
│   └── providers/                   ← Query, AntD, tema y toasts
├── e2e/                             ← Playwright
└── package.json
```

## Decisiones de arquitectura

### Mismo origen con la API
`next.config` reescribe `/api/v1/:path*` a `${API_ORIGIN}/api/v1/:path*` (local: `http://localhost:8000`). El navegador solo habla con el origen del frontend, así que:
- las cookies `__Host-*` quedan en ese origen y no hace falta CORS;
- Django valida CSRF con el `Origin` del frontend (`CSRF_TRUSTED_ORIGINS` ya incluye `http://localhost:3000`).

**Primero en F0:** verificar con login, `/auth/me` y una escritura que las cookies y el CSRF funcionan a través del rewrite. Si algo falla, parar y reportar antes de seguir.

### Cliente API (`lib/api`)
- Tipos generados con `pnpm api:gen` desde `../contracts/openapi.json`. El archivo generado se commitea, y el CI verifica que esté al día.
- Middleware del cliente:
  - en `POST`/`PUT`/`PATCH`/`DELETE`, agrega `X-CSRFToken` con el valor de la cookie `app_csrf`;
  - en toda petición, agrega `X-Request-ID` (UUID).
- **Errores.** Todo error se convierte en `ApiError { status, code, message, details, requestId }` (formato de API §5.3):

  | Respuesta | Qué hace el frontend |
  | --- | --- |
  | `details[].field` | Va al campo con `setError` de React Hook Form. |
  | Error sin campo | Toast de error (se queda hasta cerrarlo). |
  | `401` en el backoffice | Un solo `POST /auth/refresh` y se reintenta; si vuelve a fallar, va a `/login?next=…`. |
  | `401 SESSION_EXPIRED` en el portal | Pantalla "Tu acceso venció, pide un nuevo enlace a tu asesor". |
  | `403 CONSENT_REQUIRED` | Lleva a los consentimientos del portal. |
  | `409 STALE_VERSION` | Aviso "Alguien cambió esta solicitud" con botón para recargar. No se pisa nada. |
  | `409 APPLICATION_NOT_EDITABLE` / `APPLICATION_CLOSED` | Formularios en solo lectura. |
  | `429` | Mensaje con el tiempo de `Retry-After`. |

- **Concurrencia.** Las consultas del expediente guardan la versión que llega en `ETag`. Los `PUT`/`PATCH` la envían en `If-Match`, y las transiciones mandan `expected_version` en el cuerpo (API §6).

### Datos de negocio
- **Cero enums ni listas de negocio en el frontend** (REQ §8.5). Catálogos, bancos, productos, tipos de crédito, estados y etiquetas vienen de `/metadata/bootstrap` (cacheado, con `If-None-Match`) o de sus endpoints.
- El color del estado sale de `toneFor(kind, code)` en `status-tones.ts`. El texto siempre viene de la API.
- Las acciones de estado salen de `GET /applications/{id}/available-actions`.
- Los permisos salen de `/auth/me`. El menú y los botones se muestran por permiso, nunca por nombre de rol.
- Montos: enteros COP formateados con `Intl.NumberFormat("es-CO")` y `tabular-nums`. Nunca `float`.

### Estado de las listas en la URL
Filtros, búsqueda, orden y página viven en los query params (`/solicitudes?bank_id=…&page=2`). Un enlace copiado abre la misma vista. TanStack Table trabaja en modo manual: el servidor ordena, filtra y pagina.

### Tema
Claro por defecto y oscuro opcional, sin seguir al sistema operativo.
- La elección se guarda en `localStorage` con la clave `um-theme`.
- Un script en `<head>` aplica `data-theme="dark"` antes de pintar, para que no parpadee.
- `ConfigProvider` usa `darkTheme` o `lightTheme`: siempre los dos juntos.

### Componentes compartidos (F0, en `components/ui`)
Portados de los mockups, con el mismo comportamiento:

| Componente | Detalle |
| --- | --- |
| `AppShell` | Barra lateral, barra superior y menú lateral (drawer) en ≤ 860 px. |
| `ThemeToggle` | Botón de tema de la barra superior. |
| `StatusBadge` | Etiqueta de estado con su tono. |
| `Money` y `MoneyInput` | Montos en COP. |
| `CompletenessBar` | Barra de completitud del expediente. |
| `ScrollTabs` | Pestañas sin barra visible, con desvanecido, flechas y teclado. |
| `FilterChips` | Chips de filtros activos. |
| `EmptyState` | Estado vacío. |
| Toasts | `notification` de Ant Design con las reglas del README: 5 s, máximo 3, `role`. |
| `DocumentViewer` | Visor de documentos con PDF.js e imágenes. |
| `DocumentUploader` | `Upload.Dragger` en web; "Tomar foto" y "Elegir archivo" en móvil; valida tipo y tamaño. |

## Fases

### F0 — Base (un solo agente, rama `feat/front-base`)
Partes sugeridas, un commit por parte:
1. Scaffold de Next.js, TypeScript strict, ESLint, Prettier, Tailwind v4, Ant Design y el import de los tokens. Una página de prueba con componentes en claro y oscuro.
2. Providers: Query, AntD con registry y layer, tema y toasts. `AppShell` y `ThemeToggle`.
3. `lib/api`: tipos generados, cliente, CSRF, errores, ETag y rewrite. Verificar el mismo origen (ver arriba).
4. Login real contra el backend local (mockup `login.html`): `/auth/login`, `/auth/me`, guarda del grupo `(backoffice)`, logout y refresh.
5. Componentes compartidos de la tabla de arriba, con pruebas unitarias.
6. CI en `.github/workflows/frontend.yml`, con el job **"Frontend: lint, types and tests"**:
   - `pnpm install --frozen-lockfile`
   - `pnpm lint`
   - `pnpm typecheck`
   - `pnpm test --coverage`, con un mínimo de 70 % (REQ §10.5)
   - `pnpm api:gen` sin diferencias
   - `pnpm build`

   Después del merge, Carlos agrega el job como check obligatorio en `protect-master`.

**Terminado F0:** login funcionando contra el backend local, que lleva a `/solicitudes` (vacía, dentro del shell); el tema funciona; el CI está verde.

### F1 y F2 — En paralelo (dos agentes, dos worktrees)
Arrancan cuando F0 está fusionada en `master`.

| | Agente A — Backoffice | Agente B — Portal del comprador |
| --- | --- | --- |
| Rama | `feat/front-backoffice` | `feat/front-portal` |
| Carpeta (worktree) | `../wt-front-backoffice` | `../wt-front-portal` |
| Puerto de `pnpm dev` | 3000 | 3001 |
| Rutas | `(backoffice)/solicitudes`, `(backoffice)/solicitudes/[id]` | `acceso`, `(portal)/portal`, `(portal)/portal/documentos` |
| Mockups | `solicitudes.html`, `solicitud.html` | `portal.html`, `portal-documentos.html` |
| Carpetas propias | `features/applications`, `features/document-review` | `features/buyer-portal`, `features/buyer-documents` |

**Agente A:**
- **Listado.** Pestañas, búsqueda, filtros de banco, tipo de crédito, finalidad y asesor, chips, orden, paginación, selección masiva y tarjetas en móvil.
- **Espacio de trabajo.** Resumen, participantes, perfil financiero, inmueble, financiación, evaluación bancaria, completitud y acciones de estado. Revisión documental y visor cuando existan los endpoints de la fase 10.

**Agente B:**
- **`/acceso`.** Lee `token` de la URL, llama a `POST /buyer-access/consume` y borra el token con `history.replaceState`. Muestra los errores `MAGIC_LINK_*`.
- **Portal.** Inicio, consentimientos, datos del titular, perfil financiero e ingresos, inmueble, financiación (productos elegibles) y desistimiento.
- **`/portal/documentos`.** Carga, reemplazo, versiones, motivo de rechazo y visor, sobre los endpoints de comprador de la fase 10.

**Reglas para no chocar:**
- Cada agente solo toca su grupo de rutas, sus carpetas de `features/` y su carpeta `e2e/<zona>`.
- `components/ui`, `lib/`, `providers/` y la configuración son compartidos. Un cambio ahí va en un PR pequeño y aparte, que se fusiona primero; después Carlos rebasa la otra rama.
- Para el puerto 3001, Carlos agrega `http://localhost:3001` a `CSRF_TRUSTED_ORIGINS` en `backend/.env`.

Comandos para Carlos (PowerShell, desde la raíz del repo y con `master` al día):

```
git worktree add ..\wt-front-backoffice -b feat/front-backoffice
git worktree add ..\wt-front-portal -b feat/front-portal
```

Cada agente se abre en su carpeta. Al terminar: `git worktree remove ..\wt-front-backoffice` (y lo mismo con el otro).

## Brechas del backend vistas en los mockups
Se resuelven en `TAREA-applications-listado.md`. Mientras tanto, se simulan con MSW.
- Tipo de crédito (`bank_product_type`) en el listado, y filtro por tipo.
- Monto solicitado, completitud y número de co-solicitantes en cada fila.
- Conteos de las pestañas del listado y qué estados agrupa cada una (no los puede definir el frontend).

## Pruebas
- **Unitarias** (Vitest + Testing Library): componentes de `ui`, formularios con validación, manejo de `ApiError` y formato de montos.
- **Integración** con MSW: errores de la API, `409 STALE_VERSION`, `CONSENT_REQUIRED`, carga y reemplazo de documentos, filtros en la URL.
- **E2E** (Playwright, contra el backend local con semilla):
  - el login y el listado del asesor;
  - el enlace mágico → consentimiento → datos → carga de un documento.

  En cada pantalla se corre `axe`, sin violaciones serias.
- **Accesibilidad:** foco visible, navegación por teclado (pestañas, combobox, modales), `aria-describedby` en los errores de campo y estado nunca solo por color.

## Definición de terminado (por fase)
- CI del frontend y del backend en verde.
- Las pantallas se ven como el mockup en 1440, 1280 y 390 px, en claro y en oscuro.
- Ninguna lista de negocio escrita a mano en el código (revisar en el PR).
- Ninguna violación de `axe` seria o crítica.

## Precisiones acordadas
_(se completan al resolver las ambigüedades de cada fase)_
