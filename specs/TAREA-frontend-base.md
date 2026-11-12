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
- **No se presentan dudas.** Lo que esta spec no cubra lo decide el agente con la opción más simple, lo anota en "Precisiones acordadas" y sigue. Solo se detiene si la decisión rompe el contrato de la API, cambia el alcance, borra o altera datos existentes, o exige tocar un `.env`.
- Cada parte se hace de corrido. Al cerrarla, el agente entrega: verificaciones en verde, la lista corta de decisiones que tomó por su cuenta y el mensaje de commit. Espera el "listo" de Carlos para la siguiente.
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
- El contrato (`contracts/openapi.json`) no declara la cabecera `ETag` en ninguna respuesta, aunque exige `If-Match` en 12 escrituras y API §6 dice que toda respuesta del expediente la lleva. El frontend la lee igual desde la respuesta, pero el contrato debe documentarla.
- El tipo documental que ve el comprador (`BuyerSlotDocumentType`) no trae `allowed_mime_types` ni `max_size_bytes`; el interno (`SlotDocumentType`) sí. Sin ellos, el uploader del portal no puede validar tipo y tamaño antes de enviar: lo valida solo la API (`422 UNSUPPORTED_FILE_TYPE` / `FILE_TOO_LARGE`, `413 PAYLOAD_TOO_LARGE`).

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

**Cliente API (parte 3):**
- El refresh completo vive en `lib/api` (candado entre pestañas, hora del último refresh, un reintento, rutas excluidas y `next` validado), con sus cuatro tests. Si falla, el cliente llama a un manejador inyectable que por defecto lleva a `/login?next=<ruta actual>`. La parte 4 conecta login, `/auth/me`, la guarda y el logout.
- Versión explícita:
  - El cliente devuelve `{ data, version }`, con `version` tomada del `ETag`. Las consultas del expediente guardan esa versión en la caché, junto a los datos.
  - Las escrituras pasan `If-Match` a mano; el contrato la tipa como obligatoria. Un helper normaliza `"7"`, `7` y `W/"7"`.
  - La versión nueva se toma del `ETag` de la respuesta de cada escritura, también en los `204`.
- Errores:
  - **Escrituras:** las maneja un `MutationCache.onError` global.
    - `details[].field` va al formulario con `applyFieldErrors(error, setError)`. Los detalles sin campo en el formulario van a un toast.
    - **Error sin campo:** toast de error persistente con el `message` y, debajo, pequeño, "Código: <request_id>".
    - **`409 STALE_VERSION`:** toast de advertencia "Alguien cambió esta solicitud" con el botón "Recargar" (`invalidateQueries`).
    - **`429`:** "Vuelve a intentarlo en N minutos", con N desde `Retry-After`.
    - **Error de red, sin respuesta del servidor:** toast "No hay conexión con el servidor. Revisa tu conexión e inténtalo de nuevo". También cuenta como error de red un 5xx sin el formato de la API y sin `X-Request-ID`: es el `500` que devuelve el rewrite de Next.js cuando la API no responde.
    - **Versión obsoleta:** el toast de `STALE_VERSION` dice "Recarga para ver los datos actuales. No se guardó nada." y se queda hasta cerrarlo, porque pide una acción.
    - Una escritura que maneja su error lo indica con `meta: { handlesErrors: true }`.
  - **Lecturas:** sin toast global; cada pantalla muestra su error en línea.
  - **Portal:** `401 SESSION_EXPIRED` y `403 CONSENT_REQUIRED` salen como eventos con manejador inyectable, y la pantalla la decide F2.
  - **Solo lectura:** `isReadOnlyError` identifica `APPLICATION_NOT_EDITABLE` y `APPLICATION_CLOSED`.
- Versiones con la regla de antigüedad: msw 3.0.4 y vite 8.3.7, porque msw 3.0.5 y vite 8.3.8 se publicaron hoy.

**Login y guarda (parte 4):**
- `proxy.ts` protege todo menos lo público: su `matcher` excluye `/login`, `/acceso`, `/portal`, `/dev`, `/api`, `/_next` y los archivos estáticos. Una ruta pública nueva se suma a esa lista.
- Formulario con React Hook Form, Zod y `@hookform/resolvers` 5.9.2. En el cliente, correo requerido y con formato válido y contraseña requerida. Los mensajes van bajo cada campo con `aria-describedby`.
- `/` redirige a `/login`. `/login` con sesión válida lleva al destino: `next`, si es interno y el usuario puede verlo, o la primera entrada permitida del menú. `next` es visible si empieza con el `href` de una entrada del menú permitida por los permisos del usuario.
- Sin módulos visibles, el destino es `/sin-modulos`, dentro del shell.
- En `/login`, un `401` de `/auth/me` con refresh fallido no redirige otra vez al login: se queda en el formulario.
- Logout: `POST /auth/logout`, se vacía la caché de Query y se va a `/login`. Si falla, se queda en la página con un toast de error.
- `/solicitudes` en F0: título y subtítulo del mockup dentro del shell, sin lista, sin datos y sin llamar a la API. La construye el Agente A en F1.

**Componentes compartidos (parte 5):**
- `uploadFile({ path, file, fields, onProgress, signal })` en `lib/api`:
  - Usa `XMLHttpRequest` para tener progreso, con las mismas cabeceras (`X-CSRFToken` y `X-Request-ID`) y los errores como `ApiError`, incluido el de red.
  - En rutas internas, un `401` hace el mismo refresh y un reintento. En `/buyer/*` emite los eventos del portal.
  - Se puede cancelar con `signal`.
- `DocumentUploader` es solo interfaz: recibe `onUpload(file, onProgress)`, y cada feature conecta su endpoint.
- Fechas:
  - La zona horaria es fija, `America/Bogota`, en una sola constante de `lib/format`. Las fechas sin hora (`document_date`, `birth_date`) se muestran tal cual, sin pasar por zona horaria.
  - Fecha relativa: menos de 1 min, "Hace un momento"; menos de 1 h, "Hace N min"; mismo día, "Hace N h"; el día anterior, "Ayer"; hasta 3 días, "Hace N días"; después, "8 nov" ("8 nov 2025" si es de otro año). En el `title`, la fecha y hora completas.
  - La fecha relativa es un componente que se actualiza solo cada minuto, sin diferencias entre el HTML del servidor y el del cliente ni avisos de hidratación.
- Montos COP enteros con `Intl.NumberFormat("es-CO")` y porcentajes enteros ("62 %"), con `tabular-nums`.
- Fecha y hora en 12 h como es-CO: "24 ago 2026, 3:45 p. m.", con espacios de no separación en la hora.
- Visor: en modo local simple la URL de descarga es relativa (`/api/v1/storage/objects/<token>`), pasa por el rewrite y es del mismo origen, sin CORS. El riesgo de CORS aplica solo al modo full (SeaweedFS) y a S3 real, donde el almacenamiento debe permitir el origen del frontend.

**CI (parte 6):** se sigue el "Plan detallado" de abajo. Además, lo que decidió el agente:
- El reporte lo arma `frontend/scripts/ci-report.ts`: corre con Node 24, sin dependencias y con el mismo formato que `backend/scripts/ci_report.py`. Siete filas: ESLint (los *warnings* son ⚠️ y no bloquean), Prettier (formato), TypeScript, Tests, Cobertura, Contrato API y Build. Los E2E de Playwright no van en este job: necesitan el backend con datos.
- Cobertura:
  - Bloquea la de **líneas** (mínimo 70 %, REQ §10.5). Ramas y funciones solo se muestran.
  - Mide `src/**` y `scripts/**`, sin los tests, los *fixtures*, `src/test/**`, `schema.d.ts` ni las demos `src/app/(dev)/**`.
  - `reportOnFailure: true`, para que haya datos aunque fallen tests.
- Contrato API:
  - El paso guarda el `schema.d.ts` commiteado, el generado y el diff.
  - El reporte compara los dos por bloques (rutas, operaciones y esquemas) para listar las rutas nuevas, quitadas y cambiadas (con sus métodos) y los esquemas nuevos, quitados y cambiados.
  - También muestra las primeras 50 líneas del diff.
- Anotaciones:
  - ESLint las pone el *matcher* `eslint-stylish` de `setup-node`, que recibe rutas absolutas.
  - TypeScript las imprime el script del reporte (`::error file=frontend/…`), porque `tsc` da rutas relativas a `frontend/` que el *matcher* `tsc` no encontraría. El paso de TypeScript lo quita con `::remove-matcher owner=tsc::`, así no se duplican.
- `setup-node` corre siempre, sin el `if` de "changes": el paso del reporte necesita Node 24 también cuando se omiten las verificaciones. Con `run=false` tampoco se sube el artefacto.
- `COREPACK_ENABLE_DOWNLOAD_PROMPT: "0"` en el `env` del job, para que corepack baje pnpm sin preguntar.
- Si `git diff <base>...<head>` falla, se verifica todo (`run=true`).
- TypeScript:
  - `allowImportingTsExtensions`, porque el test del script importa `./ci-report.ts` con extensión, como pide el plan.
  - `erasableSyntaxOnly`, para que todo el código pueda correr con *type stripping*. Por esto `ApiError` pasó a declarar sus campos sin propiedades de parámetro.
- Los *fixtures* (`scripts/__fixtures__/`) quedan fuera de Prettier, ESLint y `tsconfig`: Prettier cambiaría la indentación de 4 espacios del `schema.d.ts`, que es lo que lee el script.
- **Pendiente:** el escaneo de dependencias en cada PR que pide REQ §10.5 no está en la parte 6.

**Saltos de línea:** los archivos de `frontend/` van en LF (Prettier `endOfLine: "lf"`), y se verifica con `git ls-files --eol`.

## Plan detallado de lo que falta en F0
Partes 1 a 5 hechas. Faltan la 6 (CI), la 7 (contenedor del front) y el cierre. Todo lo de abajo ya está decidido: no se pregunta.

### Parte 6. CI del frontend
**Workflow `.github/workflows/frontend.yml`** (mismo esqueleto que `backend.yml`; copiar su estilo):
- `on`: `push` a `master` y `pull_request`. **Sin `paths:`**.
- `concurrency`: `group: ci-frontend-${{ github.ref }}`, `cancel-in-progress: true`. **Debe ser distinto del grupo del backend** (`ci-${{ github.ref }}`): si fuera el mismo, un workflow cancelaría al otro.
- Job `quality`:
  - `name: "Frontend: lint, types and tests"` (exacto: es el nombre del check obligatorio);
  - `runs-on: ubuntu-latest`, `timeout-minutes: 15`;
  - `permissions`: `contents: read` y `pull-requests: write`;
  - `defaults.run`: `working-directory: frontend` y `shell: bash`;
  - `env`: `CI_REPORT_DIR: .ci-report`, `CI_COVERAGE_MIN: "70"`, `NEXT_TELEMETRY_DISABLED: "1"` y `API_ORIGIN: http://localhost:8000`.
- **Solo acciones oficiales** (`actions/*`), fijadas por SHA con la versión en comentario:
  - `checkout` y `upload-artifact`: los mismos SHA que `backend.yml`;
  - `github-script`: el mismo SHA que `backend.yml`;
  - `setup-node` y `cache`: el SHA de su última versión estable.
  - Nada de `pnpm/action-setup` (no es oficial): pnpm sale de `corepack enable`, que respeta `packageManager`.

**Pasos, en orden** (cada verificación con `id` y `continue-on-error: true`; salida a `$CI_REPORT_DIR`):
0. `Record start time`, igual que en el backend.
1. `checkout` con `fetch-depth: 2`.
2. **`changes`** (Detectar cambios):
   - en `pull_request`, compara el commit de merge con su primer padre (`git diff --name-only HEAD^1 HEAD`), como ya quedó en las precisiones;
   - si algún archivo empieza por `frontend/`, `contracts/openapi.json`, `design/generated/` o `.github/workflows/frontend.yml`, deja `run=true`; si no, `run=false`;
   - en `push` a `master`, siempre `run=true`.

   Todos los pasos siguientes llevan `if: steps.changes.outputs.run == 'true'`, salvo el gate.
3. `setup-node` con Node 24, más `corepack enable`.
4. Caché del store de pnpm con `actions/cache`, sobre `pnpm store path`, con la clave del hash de `frontend/pnpm-lock.yaml`.
5. **`install`:** `mkdir -p "$CI_REPORT_DIR"` y `pnpm install --frozen-lockfile`.
6. **`eslint`:**
   - `pnpm lint --format json --output-file "$CI_REPORT_DIR/eslint.json" || true`;
   - luego `pnpm lint`. El formato por defecto (stylish) lo anota en las líneas el *matcher* que registra `setup-node`.
   - Falla solo con errores; los *warnings* no lo hacen fallar (sin `--max-warnings`).
7. **`prettier`:** `pnpm format:check 2>&1 | tee "$CI_REPORT_DIR/prettier.txt"`.
8. **`typecheck`:** `pnpm typecheck 2>&1 | tee "$CI_REPORT_DIR/tsc.txt"`. Lo anota el *matcher* `tsc` de `setup-node`.
9. **`tests`:** Vitest con cobertura y JUnit:
   ```
   pnpm vitest run --coverage --coverage.reporter=text --coverage.reporter=json-summary --coverage.reportsDirectory="$CI_REPORT_DIR/coverage" --reporter=default --reporter=junit --outputFile.junit="$CI_REPORT_DIR/vitest.xml"
   ```
   - **El umbral no va en `vitest.config.mts`.** Así, este paso falla solo por tests rotos.
10. **`coverage`:** corre si existe `coverage-summary.json`, aunque hayan fallado los tests.
    - Usa `node scripts/ci-report.ts --check-coverage`, que falla si el total de **líneas** está por debajo de `CI_COVERAGE_MIN`.
11. **`api_contract`:** `pnpm api:gen` y luego `git diff --exit-code -- src/lib/api/schema.d.ts`.
    - Genera desde `contracts/openapi.json` del repo, sin backend.
    - `schema.d.ts` ya está excluido de Prettier y de ESLint. Si aun así queda distinto, el agente lo corrige en el script `api:gen`, no en el CI.
12. **`build`:** `pnpm build 2>&1 | tee "$CI_REPORT_DIR/build.txt"`.
13. **Build CI report** (`if: always()`): `node scripts/ci-report.ts`, con:
    - las `OUTCOME_*` de cada paso;
    - `CI_COMMIT_SHA`;
    - `CI_SKIPPED=true` cuando `run=false`.
14. **Upload artifact** `ci-report-frontend`: `frontend/.ci-report/`, con `include-hidden-files: true`, 7 días e `if-no-files-found: ignore`.
15. **Comentario en el PR** con el marcador `<!-- ci-report:frontend -->`. Es el mismo script de `backend.yml`, cambiando solo el marcador y la ruta.
    - Solo en PR del mismo repo.
    - **Cuando el PR no toca el frontend (`run=false`), no se publica comentario.**
16. **CI gate** (`if: always()`):
    - con `run=false`, sale en éxito;
    - si no, falla si alguna verificación terminó en `failure` o si `install` no terminó en `success`. Igual que en el backend.

**Script `frontend/scripts/ci-report.ts`**
- Lo ejecuta Node 24 directamente (*type stripping*): solo sintaxis que se puede borrar, sin `enum` ni `namespace`, con imports relativos con extensión `.ts` y sin importar nada de `src/` ni alias. Sin dependencias: solo `node:fs`, `node:path` y `node:process`.
- Lee:
  - `eslint.json`: errores y *warnings* por regla, con archivo y línea;
  - `prettier.txt`: archivos de las líneas `[warn]`;
  - `tsc.txt`: errores `TSxxxx` con archivo y línea;
  - `vitest.xml`: total, pasan, fallan, saltados, duración y los que fallan (nombre y primera línea del error);
  - `coverage/coverage-summary.json`: total de líneas contra el mínimo, y los 5 archivos con menos cobertura (ignorando los de 0 líneas);
  - el diff del contrato y `build.txt`: últimas 50 líneas si falló.
- **Estados por fila:**
  - ✅ pasó;
  - ⚠️ pasó con advertencias (solo ESLint con *warnings*);
  - ❌ falló;
  - ⏭️ no corrió.
- **Formato:** el del backend.
  - Encabezado `## Frontend CI · …`, con el commit corto, el enlace al run y la duración.
  - Tabla de 7 filas: ESLint, Prettier (formato), TypeScript, Tests, Cobertura, Contrato API y Build.
  - `<details>` de máximo 50 líneas, con "… y N más".
  - Texto escapado.
  - Con `CI_SKIPPED=true`, una sola línea: "Sin cambios en el frontend: verificaciones omitidas".
- Escribe en `$GITHUB_STEP_SUMMARY` y en `.ci-report/report.md`. Nunca falla el job, salvo en `--check-coverage`.
- **Pruebas** en `frontend/scripts/ci-report.test.ts`, con `// @vitest-environment node` y *fixtures* en `frontend/scripts/__fixtures__/`. Casos:
  - todo en verde;
  - fallos y *warnings* juntos;
  - falló la instalación (todo ⏭️);
  - `CI_SKIPPED`;
  - salida larga (truncado);
  - caracteres especiales (escape);
  - `--check-coverage` por encima y por debajo del mínimo.
- En `vitest.config.mts`, agregar `scripts/**/*.test.ts` a `include` y `scripts/**/*.ts` a la cobertura, sin contar `__fixtures__`.
- `.ci-report/` ya está en el `.gitignore` raíz (vale para cualquier carpeta).

**Verificación del agente antes de entregar**
- `pnpm lint`, `pnpm format:check`, `pnpm typecheck`, los tests con cobertura ≥ 70 %, `pnpm api:gen` sin diferencias y `pnpm build`, todo en local.
- Correr `node scripts/ci-report.ts` contra una carpeta `.ci-report` armada con los *fixtures*, y mostrar el Markdown que sale.
- Validar el YAML: que se lea y que los `id` usados en `OUTCOME_*` y en el gate existan.

**Verificación real (Carlos):** hace push y revisa, en el PR #15:
- que aparezcan los dos comentarios (backend y frontend) y los dos checks en verde;
- que ninguno de los dos workflows cancele al otro.

No se hace la rama de prueba en rojo: ese caso lo cubren los tests del script.

**Commit:** `ci(frontend): add the frontend CI job with a PR report`

### Parte 7. Contenedor del frontend (3 contenedores)
**Antes de empezar, Carlos trae `master` a la rama.** La rama no tiene el PR #14 (modo local simple). Carlos corre `git fetch` y `git merge origin/master` en el worktree.
- Si hay conflictos (lo más probable: esta spec y el README), el agente los resuelve editando los archivos: une las dos versiones sin perder nada.
- Carlos hace el commit del merge. El agente no corre comandos de git que escriban.

**Qué construir**
- **`.dockerignore` en la raíz del repo** (el contexto del build es la raíz), que excluya:
  - `.git`;
  - `**/node_modules` y `frontend/.next`;
  - `frontend/coverage`;
  - `**/.ci-report`;
  - `backend/` (el backend se construye con su propio contexto);
  - `docs/` y `specs/`;
  - los `.env*`.
- **`frontend/Dockerfile`** de producción, en varias etapas, con `node:24-alpine` fijado por versión:
  1. `deps`: `corepack enable` y `pnpm install --frozen-lockfile`, copiando solo `package.json` y `pnpm-lock.yaml`.
  2. `build`: copia `frontend/`, `design/generated/` y `contracts/` respetando la estructura (`/app/frontend`, `/app/design/generated`, `/app/contracts`), porque el front importa `../design/generated`. Corre `pnpm build`.
     - **`API_ORIGIN` entra como `ARG`, con valor por defecto `http://backend:8000`**, y se exporta como `ENV` en esta etapa. Next fija los *rewrites* al compilar, así que no basta con ponerlo al arrancar.
  3. `run`: `NODE_ENV=production`, usuario sin privilegios (`node`), `EXPOSE 3000` y `pnpm start` (o el servidor `standalone`, si el agente lo activa en `next.config.ts`; lo que sea más simple y lo anota).
- **Servicio `frontend` en `backend/docker-compose.yml`:**
  - sin perfil;
  - `build.context: ..`, `dockerfile: frontend/Dockerfile` y `args.API_ORIGIN: http://backend:8000`;
  - `ports: "${FRONTEND_HOST_PORT:-3000}:3000"`;
  - `depends_on: backend` (`condition: service_started`).

  Con `docker compose up -d` quedan exactamente `postgres`, `backend` y `frontend`. El perfil `full` no cambia.
- **Host del backend:** el *rewrite* llega a Django con el host `backend`.
  - Si Django responde `400` por `DJANGO_ALLOWED_HOSTS`, el agente **se detiene y le dice a Carlos la línea exacta** que hay que cambiar en `backend/.env` y en `backend/.env.example`. No los toca.
  - Lo mismo si hace falta algo en `CSRF_TRUSTED_ORIGINS`.
- **Desarrollo vs. demo** (va en el README):
  - para mostrar el proyecto, `docker compose up -d --build` y abrir `http://localhost:3000`;
  - para programar el front, `docker compose up -d postgres backend` y `pnpm dev` (el contenedor `frontend` ocuparía el puerto 3000).
- **README raíz y `backend/README.md`:** los tres contenedores, las URLs (`:3000` front y `:8000` API), los dos modos (demo y desarrollo) y el usuario de prueba (sin la contraseña: "créalo con…").

**Verificación del agente**
- `docker compose up -d --build` levanta los 3 contenedores.
- Con `curl` contra `http://localhost:3000`:
  - `/login` responde `200`;
  - `POST /api/v1/auth/login` con el usuario de `.env.local` devuelve las cookies;
  - `/api/v1/auth/me` con esas cookies responde `200`.

  El agente lee el usuario de `.env.local` solo si sus permisos se lo dejan. Si no, le pide a Carlos que lo pruebe en el navegador.
- `docker compose --profile full config` sigue siendo válido.
- Después, deja corriendo `postgres` y `backend` (sin `frontend`), para no ocupar el 3000.

**Commit:** `chore(frontend): run the frontend as the third local container`

### Cierre de F0
- **README del frontend** (`frontend/README.md`): requisitos (Node 24 y corepack), comandos (`dev`, `lint`, `format`, `typecheck`, `test`, `api:gen` y `build`), cómo regenerar tipos después de un cambio de API y la carpeta de cada cosa.
- **"Brechas del backend":** marcar como resueltas las del listado (`TAREA-applications-listado.md`) cuando se fusione ese PR. Las demás quedan para la tarea de "brechas".
- **El agente entrega el título y la descripción del PR #15**, en español y sin firmas de Claude, con:
  - lo que trae cada parte;
  - las decisiones de arquitectura principales;
  - cómo correrlo;
  - el CI;
  - lo que queda para F1 y F2.
- **Después del merge (Carlos):** agregar "Frontend: lint, types and tests" como check obligatorio en `protect-master`.
