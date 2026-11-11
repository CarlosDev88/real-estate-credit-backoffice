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
- El contrato lo genera el backend; el frontend no lo edita. Si hace falta regenerarlo (por ejemplo, después de traer cambios de la API), se corre desde `backend/` con el stack levantado, y luego `pnpm api:gen`:
  ```
  docker compose exec backend python manage.py spectacular --settings config.settings.test --format openapi-json --file /contracts/openapi.json --validate --fail-on-warn
  ```
  Ver `backend/README.md`, sección *OpenAPI Contract*.
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
- Marca de "ya no cumple" en solicitudes `READY_TO_FILE` y nombre corto del banco (filas 9 y 10 de esa spec).
- Etiqueta pública del estado de cada documento para el comprador ("Te falta", "Corrígelo", "En revisión", "No aplica"). Hoy el DTO del comprador trae el código; el texto no puede escribirse en el frontend. Va en el DTO de `/buyer/.../document-slots` (tarea pequeña aparte, después de la fase 10).
- Etiqueta del rol del usuario interno: `/auth/me` trae `role` y `roles` como códigos, sin texto. Mientras no exista, bajo el avatar van el nombre y el correo.
- Casilla "Mantener la sesión en este equipo" del login: `/auth/login` solo recibe correo y contraseña, y la sesión dura 8 h fijas. Se quita.
- Búsqueda global de la barra superior: no hay endpoint. Se quita.
- Campana de notificaciones internas de la barra superior: no hay endpoint. Se quita.

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

### F0

**Versiones** (fijadas exactas en `package.json`, sin `^`):
- Node 24 LTS (`engines >=24`) y pnpm 12.18.0 con `packageManager` (corepack).
- next y eslint-config-next 16.4.6; react y react-dom 19.3.1; TypeScript 5.9.3. La 7.x no es compatible con `typescript-eslint` (`<6.1`) ni con `openapi-typescript` (`^5`).
- antd 6.7.0, `@ant-design/cssinjs` 2.1.2 (la misma que usa antd) y `@ant-design/nextjs-registry` 1.3.0; tailwindcss y `@tailwindcss/postcss` 4.3.5.
- `@tanstack/react-query` 5.107.1 y `@tanstack/react-table` 9.3.1; react-hook-form 7.92.0, zod 4.6.7 y `@hookform/resolvers` 5.9.2. La línea 5 se prefiere a la 6 y la 7, que salieron con pocos días de diferencia.
- openapi-typescript 7.13.0 y openapi-fetch 0.17.0; pdfjs-dist 6.5.438.
- vitest y `@vitest/coverage-v8` 5.1.0, vite 8.3.x, `@vitejs/plugin-react` 6.3.0, jsdom 31.0.0; Testing Library: react 16.3.3, dom 10.4.2, user-event 14.6.9 y jest-dom 7.0.1; msw 3.0.5; `@playwright/test` 1.65.0 y `@axe-core/playwright` 4.14.0.
- eslint 10.14.0, typescript-eslint 8.72.2 y prettier 3.9.10. La línea 9.x de ESLint ya no tiene soporte. Se aceptan los avisos de peer dependencies de `eslint-plugin-react`, `eslint-plugin-import` y `eslint-plugin-jsx-a11y` (vienen con `eslint-config-next` y declaran ESLint hasta 9); con ESLint 10 funcionan. **Pendiente:** revisar cuando `eslint-config-next` declare soporte oficial para ESLint 10.
- Antigüedad mínima: si una versión aprobada cae dentro de la antigüedad mínima de publicación de pnpm (`minimumReleaseAge`), se usa la versión anterior. No se agregan excepciones en `pnpm-workspace.yaml`. Aplica a msw y vite cuando entren.
- Fuentes: `@fontsource/inter` y `@fontsource/jetbrains-mono` 5.3.0, solo con los pesos que usan los tokens (Inter 400, 500, 600 y 700; Mono 400 y 500). Declaran las familias con el mismo nombre que usan los tokens y `antd-theme.ts`, así que no se sobrescribe nada, y no hay peticiones a Google.

**Backend local y mismo origen:**
- En local (`AUTH_COOKIE_SECURE=false`) las cookies no llevan el prefijo `__Host-`: son `app_access` y `app_refresh`. Los nombres se configuran por entorno (`AUTH_ACCESS_COOKIE` y `AUTH_REFRESH_COOKIE`).
- El rewrite de `/api/v1` va desde la parte 1. Al cerrarla se verifica con `pnpm dev`: login, cookies guardadas en `localhost:3000`, `/auth/me` con `200` y una escritura con `X-CSRFToken` (`POST /auth/refresh` y luego `POST /auth/logout`). Si algo falla, se para y se reporta.
- Usuario de prueba: un `ADVISOR` creado en la base local, con las credenciales en `frontend/.env.local` (`E2E_USER_EMAIL` y `E2E_USER_PASSWORD`), que no se versiona (`.env*.local` en `.gitignore`).

**Sesión interna:**
- El refresh se dispara con `401 NOT_AUTHENTICATED` y con `401 SESSION_EXPIRED`. Cuando vence la cookie de acceso, el navegador deja de enviarla y llega `NOT_AUTHENTICATED`.
- El refresh se serializa:
  - Entre pestañas, con `navigator.locks` (candado `um-auth-refresh`). Con el candado tomado, si otra pestaña refrescó después de que salió la petición, solo se reintenta. Si no, `POST /auth/refresh`, se guarda la hora y se reintenta la petición una vez.
  - Dentro de la pestaña, los `401` simultáneos comparten una sola promesa. Sin `navigator.locks`, queda solo esta.
- En `localStorage` va solo la hora del último refresh, nunca tokens ni datos de la sesión. Lecturas y escrituras van con try/catch; si fallan, se actúa como si no hubiera dato.
- `/auth/login`, `/auth/refresh`, `/auth/logout` y `/buyer/*` no disparan el refresh.
- Si el refresh falla, se va a `/login?next=…`. `next` solo acepta rutas internas; un valor externo se ignora.
- Pruebas obligatorias:
  - dos `401` a la vez en la misma pestaña hacen un solo refresh;
  - con un refresh reciente de otra pestaña, no se vuelve a refrescar;
  - un refresh fallido lleva a `/login` con un `next` interno;
  - un `next` externo se ignora.

**Guarda del `(backoffice)`:**
- `proxy.ts` solo redirige a `/login?next=…` cuando no hay cookie de acceso ni de refresh. Es una decisión de experiencia de uso: no mira permisos ni datos. La seguridad la pone la API.
- El layout del grupo pide `/auth/me` con TanStack Query y muestra el shell con un esqueleto mientras carga. Un `401` sigue el flujo de refresh; si falla, va al login.
- `/login` con una sesión válida redirige a `next` o al destino por defecto.

**Login (mockup `login.html`):**
- Se quita la casilla "Mantener la sesión en este equipo" (ver "Brechas").
- El enlace "¿La olvidaste?" queda fuera de F0. **Pendiente:** pantallas de recuperación de contraseña sobre `POST /auth/password-reset-requests` y `POST /auth/password-resets/confirm`, que ya existen.
- Errores:
  - **Título del aviso:** el `message` de la API.
  - **`INVALID_CREDENTIALS`:** el texto de ayuda del mockup, con `aria-invalid` en los dos campos y sin decir cuál falló.
  - **`RATE_LIMITED` (`429`):** "Vuelve a intentarlo en N minutos", con N calculado desde `Retry-After`.
  - **`USER_INACTIVE` y cualquier otro código:** solo el `message`.

**Shell y menú:**
- Se quitan la búsqueda global y la campana (ver "Brechas"). Bajo el avatar van el nombre y el correo.
- El menú se arma desde una configuración de navegación: ruta, texto, ícono, grupo y permiso exigido. Solo aparecen las rutas que existen. En F0, "Solicitudes" (`applications.read`), en el grupo "Comercial". Un grupo sin entradas visibles no se pinta. El conteo de "Mi día" entra con su pantalla, si la API lo da.
- Destino después del login: `next`, si es interno y el usuario puede verlo. Si no, la primera entrada del menú que su permiso le deja ver. Si no ve ninguna, una pantalla en el shell: "Tu usuario todavía no tiene módulos habilitados. Pídele acceso a un administrador."

**Página de prueba:** `/dev/ui`, solo en desarrollo (`notFound()` en producción), sin sesión ni API. Muestra tokens, componentes de Ant Design con el tema y los componentes de `components/ui`. Playwright la usa para `axe` en claro y en oscuro y para revisarla en 1440, 1280 y 390 px.

**Tema (parte 2):**
- `localStorage` (`um-theme`) es la fuente. La elección también se copia en la cookie `um-theme`: no `HttpOnly`, `SameSite=Lax`, un año, solo `light` o `dark`. Cualquier otro valor se trata como `light`.
- El layout raíz lee la cookie en el servidor y pinta `data-theme` y el `ConfigProvider` con ese tema, así Ant Design no parpadea. Por eso todas las páginas se generan en cada petición.
- El script de `<head>` es el respaldo: sin cookie, toma el tema de `localStorage` y aplica `data-theme`.

**Cierre de sesión en el shell (parte 2):** el bloque del usuario (avatar, nombre y correo) es un botón que abre un menú hacia arriba con "Cerrar sesión".
- Teclado: Enter o Espacio abren el menú, las flechas recorren las opciones y Escape lo cierra y devuelve el foco al botón. El botón lleva `aria-haspopup` y `aria-expanded`.
- El `AppShell` recibe `onLogout` como prop y el logout real se conecta en la parte 4. En `/dev/ui` solo muestra un toast.

**Saltos de línea:** los archivos de `frontend/` van en LF (Prettier `endOfLine: "lf"`), y se verifica con `git ls-files --eol`.
