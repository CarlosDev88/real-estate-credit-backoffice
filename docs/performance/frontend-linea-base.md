# Línea base de performance del frontend

> **Nota de cierre (Parte 4).** Esta es la foto original del 2026-11-19, con el equipo cargado (la demo de punta a punta acababa de terminar y había ~4 GB libres). Al medir de nuevo, el mismo código daba otros números: por ejemplo, el TBT móvil del listado pasó de 1.244 a 644 ms. Por eso el antes y el después del informe ([`docs/PERFORMANCE.md`](../PERFORMANCE.md)) es un A/B del mismo día: el código de esta línea base (`19c75c7`) y el código final, medidos uno detrás de otro el 2026-11-20. Las tablas de aquí siguen siendo la referencia de qué se encontró y por qué.

Parte 1 de la auditoría de performance del front (`specs/TAREA-performance-front.md`): medir sin cambiar nada. Es la foto de `master` en `269702d` (F7, brechas 3 con la demo ampliada y la fase B de seguridad). Los hallazgos están en [`frontend-hallazgos.md`](frontend-hallazgos.md).

## Resumen

- **Peor página:** el expediente (`/solicitudes/<id>`). En móvil saca 51 en Lighthouse, con un LCP de 5,8 s y un TBT de 1,5 s. Al abrirlo se hacen 14 peticiones a la API en 4 etapas encadenadas.
- **El portal del comprador** tiene un LCP móvil de 5,3 s: el texto principal espera la sesión del comprador y luego la solicitud.
- **El dashboard se mueve mientras carga:** CLS de 0,56 en móvil y de 0,21 en escritorio. Son los bloques de carga de altura fija.
- **Abrir el modal "Registrar respuesta"** tarda 576 ms de INP, en el rango "pobre". Las otras dos interacciones medidas están bien: 168 ms y 72 ms.
- **Todas las páginas con sesión** muestran su primer contenido entre 2,2 y 2,7 s en móvil. Nada se pinta hasta que responde `/auth/me` y corre el JS de la página. Todas las páginas piden sus datos en una segunda oleada, después de `/auth/me`.
- **JS de primera carga (gzip):** 250 kB compartidos por todas las rutas; entre 261 kB (`/acceso`) y 481 kB (expediente). Lighthouse estima entre 54 y 155 kB de JS sin usar por página.
- **Lo que está bien:** las 13 páginas sacan 100 en accesibilidad y 96 en buenas prácticas. El escritorio está en 88–100. La caché tibia baja el peso transferido a 7–26 kB. No hay peticiones repetidas. El portal no arrastra código del backoffice.

## Método

### Herramientas (versiones fijas)

| Herramienta | Versión | Para qué |
|---|---|---|
| Next.js (`next build` + `next start -p 3003`) | 16.4.6 (Turbopack) | Build de producción medido; nunca `next dev`. |
| `lighthouse` (API de Node) | 13.6.0 | Lighthouse en modo navegación, móvil y escritorio. |
| `web-vitals` (IIFE inyectada) | 6.2.3 | LCP, CLS, INP, FCP y TTFB de laboratorio. |
| `playwright` + Chromium | 1.65.0 + Chromium 158 (build 1254) | Login, sesión, Web Vitals, red e interacciones. |
| `next analyze` (analizador nativo de Turbopack) | el de Next 16.4.6 | Peso por módulo y por paquete. `@next/bundle-analyzer` no funciona con Turbopack (P5). |
| `node:zlib` (gzip nivel 9) | Node 24.14.0 | JS de primera carga por ruta desde `.next/diagnostics/route-bundle-stats.json` (P4). |

Son las versiones más recientes con al menos dos semanas de publicadas al 2026-11-19. Viven en `_perf-work/package.json`, fuera del repo. `@lhci/cli` 0.16.0 queda para la Parte 3.

### Equipo y condiciones

- **Equipo:** portátil con Intel Core i5-11300H (4 núcleos, 8 hilos, 3,1 GHz), 15,7 GB de RAM y Windows 11 (10.0.26300). Índice de benchmark de Lighthouse: 2241.
- **Servidor:** el front corre con `next start` en el mismo equipo. El backend es el de `:8000` (Docker Desktop) con `seed_demo_data` ampliado (64 solicitudes en 6 meses).
- **Carga del equipo:** estaban arriba los contenedores de la demo (`:8000`, PostgreSQL y el front del compose en `:3000`, sin uso). No había otros agentes con Docker ni procesos pesados; el agente de documentación solo escribía texto.
- **Incidente de memoria:** a las 19:29 (hora local) Claude Code detuvo `next start` por falta de memoria en el equipo. Pasó mientras se medía `/prospectos`. Las otras 12 páginas se midieron completas el 2026-11-19, entre las 18:12 y las 19:28.
- **Corridas:** 5 por página y perfil; se reporta la **mediana**. La mediana no se deja arrastrar por una corrida rara (un GC o un salto del reloj de la VM), mientras que el promedio sí.
- **Caché fría:** perfil nuevo de Chrome por rol, y Lighthouse limpia la caché HTTP en cada corrida (las cookies quedan). **Caché tibia:** corrida aparte, con una carga previa y sin limpiar (`disableStorageReset`).
- **Sesión:** Playwright inicia sesión una vez por rol en la pantalla real, y Lighthouse corre en ese mismo Chrome por el puerto de depuración. Antes de cada corrida hay una carga previa en otra pestaña, que no se mide: renueva el access token de 15 min y calienta el servidor (P7).

### Perfiles

- **Lighthouse móvil:** el perfil por defecto (Moto G Power, 4G lento simulado: RTT de 150 ms y 1,6 Mbps; CPU ×4).
- **Lighthouse escritorio:** el preset `desktop` (RTT de 40 ms, 10 Mbps, CPU ×1).
- **Web Vitals de laboratorio:** Playwright a 1440×900 (el backoffice se usa en escritorio), CPU ×4 por CDP y red sin limitar. El INP por página es el de un clic neutro en el título. Las 3 interacciones reales se miden aparte con un `PerformanceObserver` de eventos: el máximo de `duration` de esa interacción (P8).
- **Espera de carga:** Lighthouse corre con `maxWaitForLoad` de 15 s en lugar de 45 s (P10; ver PERF-09).

### Páginas y usuarios

| Página | Usuario de demo |
|---|---|
| `/login`, `/aceptar-invitacion` (sin token), `/acceso` (sin token) | sin sesión |
| `/dashboard`, `/reportes`, `/admin/usuarios` | `admin@demo.local` |
| `/mi-dia`, `/solicitudes`, `/solicitudes/<id>`, `/clientes`, `/mis-comisiones` | `asesora.lucia@demo.local` |
| `/prospectos` | `broker@demo.local` |
| `/portal` | comprador de SOL-000013 (enlace de demo creado por la asesora y consumido) |

El expediente es SOL-000064: radicada, con documentos y una radicación sin respuesta (P9). La spec dice 12 páginas, pero su lista suma 13 (P1). `/admin` es `/admin/usuarios` (P2).

### `/prospectos`, medida aparte

`/prospectos` se midió completa el 2026-11-20, de 09:47 a 09:51, con el mismo build, los mismos scripts y el mismo backend. Se descartaron las 4 corridas de la víspera. La única diferencia de condiciones es la memoria: había 2,0 GB libres al empezar y 1,7 GB al terminar; la noche anterior, unos 4 GB. Sus números quedan en línea con los de las otras páginas del backoffice: performance móvil 70, LCP 2,54 s, TBT 643 ms y escritorio 99.

## Resultados

### Lighthouse móvil (caché fría, mediana de 5)

| Página | Perf. | A11y | Buenas pr. | FCP | LCP | TBT | CLS | SI | Peso total | JS (transfer.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `/login` | 87 | 100 | 96 | 0,93 s | 0,93 s | 520 ms | 0,000 | 0,93 s | 458 kB | 334 kB |
| `/aceptar-invitacion` | 87 | 100 | 96 | 0,77 s | 3,73 s | 173 ms | 0,000 | 0,77 s | 443 kB | 372 kB |
| `/acceso` | 99 | 100 | 96 | 0,77 s | 0,77 s | 137 ms | 0,002 | 0,77 s | 334 kB | 267 kB |
| `/dashboard` | 55 | 100 | 96 | 2,53 s | 2,53 s | 623 ms | 0,564 | 2,53 s | 485 kB | 373 kB |
| `/reportes` | 88 | 100 | 96 | 2,22 s | 2,22 s | 344 ms | 0,000 | 2,22 s | 500 kB | 394 kB |
| `/admin/usuarios` | 88 | 100 | 96 | 2,38 s | 2,38 s | 355 ms | 0,000 | 2,38 s | 541 kB | 436 kB |
| `/mi-dia` | 73 | 100 | 96 | 2,56 s | 2,56 s | 596 ms | 0,148 | 2,56 s | 565 kB | 431 kB |
| `/solicitudes` | 73 | 100 | 96 | 2,69 s | 2,69 s | 1.244 ms | 0,000 | 2,69 s | 530 kB | 389 kB |
| `/solicitudes/<id>` | 51 | 100 | 96 | 1,78 s | 5,81 s | 1.534 ms | 0,036 | 2,12 s | 655 kB | 492 kB |
| `/clientes` | 78 | 100 | 96 | 2,59 s | 2,59 s | 609 ms | 0,000 | 2,59 s | 529 kB | 394 kB |
| `/mis-comisiones` | 81 | 100 | 96 | 2,37 s | 2,37 s | 541 ms | 0,000 | 2,37 s | 514 kB | 390 kB |
| `/prospectos` | 70 | 100 | 96 | 2,54 s | 2,54 s | 643 ms | 0,214 | 2,54 s | 551 kB | 446 kB |
| `/portal` | 62 | 100 | 96 | 2,31 s | 5,29 s | 614 ms | 0,000 | 2,31 s | 587 kB | 441 kB |

### Lighthouse escritorio (caché fría, mediana de 5)

| Página | Perf. | FCP | LCP | TBT | CLS | SI |
|---|---:|---:|---:|---:|---:|---:|
| `/login` | 100 | 0,26 s | 0,26 s | 0 ms | 0,002 | 0,26 s |
| `/aceptar-invitacion` | 100 | 0,23 s | 0,80 s | 0 ms | 0,001 | 0,23 s |
| `/acceso` | 100 | 0,22 s | 0,22 s | 0 ms | 0,000 | 0,22 s |
| `/dashboard` | 88 | 0,63 s | 0,63 s | 56 ms | 0,187 | 0,63 s |
| `/reportes` | 100 | 0,61 s | 0,61 s | 25 ms | 0,000 | 0,61 s |
| `/admin/usuarios` | 100 | 0,55 s | 0,55 s | 15 ms | 0,000 | 0,57 s |
| `/mi-dia` | 100 | 0,60 s | 0,60 s | 62 ms | 0,006 | 0,64 s |
| `/solicitudes` | 93 | 0,71 s | 0,71 s | 208 ms | 0,000 | 0,71 s |
| `/solicitudes/<id>` | 88 | 0,42 s | 1,40 s | 228 ms | 0,033 | 0,70 s |
| `/clientes` | 100 | 0,60 s | 0,60 s | 53 ms | 0,000 | 0,60 s |
| `/mis-comisiones` | 100 | 0,58 s | 0,58 s | 28 ms | 0,000 | 0,58 s |
| `/prospectos` | 99 | 0,58 s | 0,58 s | 41 ms | 0,069 | 0,65 s |
| `/portal` | 98 | 0,55 s | 1,13 s | 34 ms | 0,000 | 0,55 s |

### Lighthouse móvil (caché tibia, mediana de 5)

| Página | Perf. | FCP | LCP | TBT | CLS | Peso transferido |
|---|---:|---:|---:|---:|---:|---:|
| `/login` | 82 | 0,84 s | 0,84 s | 718 ms | 0,000 | 17 kB |
| `/aceptar-invitacion` | 99 | 0,63 s | 0,97 s | 101 ms | 0,000 | 11 kB |
| `/acceso` | 100 | 0,63 s | 0,63 s | 84 ms | 0,002 | 7 kB |
| `/dashboard` | 95 | 1,01 s | 1,01 s | 248 ms | 0,000 | 20 kB |
| `/reportes` | 98 | 0,84 s | 0,84 s | 177 ms | 0,000 | 13 kB |
| `/admin/usuarios` | 97 | 0,84 s | 0,84 s | 189 ms | 0,000 | 22 kB |
| `/mi-dia` | 93 | 0,90 s | 0,90 s | 291 ms | 0,000 | 20 kB |
| `/solicitudes` | 83 | 1,01 s | 1,01 s | 684 ms | 0,000 | 26 kB |
| `/solicitudes/<id>` | 79 | 1,05 s | 2,16 s | 841 ms | 0,036 | 25 kB |
| `/clientes` | 90 | 0,97 s | 0,97 s | 404 ms | 0,000 | 22 kB |
| `/mis-comisiones` | 96 | 0,89 s | 0,89 s | 220 ms | 0,000 | 10 kB |
| `/prospectos` | 82 | 0,97 s | 0,97 s | 324 ms | 0,214 | 12 kB |
| `/portal` | 92 | 0,88 s | 1,52 s | 340 ms | 0,000 | 17 kB |

### Web Vitals de laboratorio (caché fría, escritorio, CPU ×4, mediana de 5)

| Página | LCP | FCP | TTFB | CLS | INP (clic neutro) |
|---|---:|---:|---:|---:|---:|
| `/login` | 660 ms | 660 ms | 33 ms | 0,002 | 32 ms |
| `/aceptar-invitacion` | 1.036 ms | 232 ms | 20 ms | 0,001 | 24 ms |
| `/acceso` | 248 ms | 248 ms | 13 ms | 0,000 | 24 ms |
| `/dashboard` | 1.792 ms | 1.792 ms | 19 ms | 0,213 | 24 ms |
| `/reportes` | 1.944 ms | 1.944 ms | 16 ms | 0,000 | 32 ms |
| `/admin/usuarios` | 1.832 ms | 1.832 ms | 15 ms | 0,003 | 32 ms |
| `/mi-dia` | 2.032 ms | 2.032 ms | 21 ms | 0,009 | 40 ms |
| `/solicitudes` | 1.696 ms | 1.696 ms | 15 ms | 0,000 | 40 ms |
| `/solicitudes/<id>` | 3.160 ms | 1.860 ms | 17 ms | 0,027 | 40 ms |
| `/clientes` | 1.688 ms | 1.688 ms | 20 ms | 0,000 | 40 ms |
| `/mis-comisiones` | 1.612 ms | 1.612 ms | 14 ms | 0,000 | 40 ms |
| `/prospectos` | 2.236 ms | 2.236 ms | 20 ms | 0,065 | 32 ms |
| `/portal` | 2.000 ms | 1.468 ms | 15 ms | 0,000 | 24 ms |

### Web Vitals de laboratorio (caché tibia, escritorio, CPU ×4, mediana de 5)

| Página | LCP | FCP | TTFB | CLS | INP (clic neutro) |
|---|---:|---:|---:|---:|---:|
| `/login` | 624 ms | 624 ms | 35 ms | 0,002 | 24 ms |
| `/aceptar-invitacion` | 524 ms | 236 ms | 22 ms | 0,001 | 24 ms |
| `/acceso` | 224 ms | 224 ms | 15 ms | 0,000 | 32 ms |
| `/dashboard` | 1.560 ms | 1.560 ms | 17 ms | 0,213 | 24 ms |
| `/reportes` | 1.688 ms | 1.688 ms | 17 ms | 0,000 | 24 ms |
| `/admin/usuarios` | 1.628 ms | 1.628 ms | 15 ms | 0,003 | 24 ms |
| `/mi-dia` | 1.704 ms | 1.704 ms | 16 ms | 0,009 | 32 ms |
| `/solicitudes` | 1.544 ms | 1.544 ms | 16 ms | 0,000 | 24 ms |
| `/solicitudes/<id>` | 2.008 ms | 932 ms | 15 ms | 0,030 | 24 ms |
| `/clientes` | 1.040 ms | 1.040 ms | 16 ms | 0,000 | 24 ms |
| `/mis-comisiones` | 1.008 ms | 1.008 ms | 15 ms | 0,000 | 24 ms |
| `/prospectos` | 1.228 ms | 1.228 ms | 21 ms | 0,065 | 32 ms |
| `/portal` | 1.712 ms | 1.344 ms | 15 ms | 0,000 | 24 ms |

### Red: peticiones a la API al abrir la página (caché fría)

| Página | Peticiones | Oleadas (cascada) | Repetidas |
|---|---:|---:|---:|
| `/login` | 2 | 2 | 0 |
| `/aceptar-invitacion` | 0 | 1 | 0 |
| `/acceso` | 0 | 1 | 0 |
| `/dashboard` | 8 | 2 | 0 |
| `/reportes` | 5 | 2 | 0 |
| `/admin/usuarios` | 3 | 2 | 0 |
| `/mi-dia` | 6 | 2 | 0 |
| `/solicitudes` | 5 | 2 | 0 |
| `/solicitudes/<id>` | 14 | 5 | 0 |
| `/clientes` | 3 | 2 | 0 |
| `/mis-comisiones` | 3 | 2 | 0 |
| `/prospectos` | 4 | 2 | 0 |
| `/portal` | 5 | 3 | 0 |

### INP de 3 interacciones reales (asesora, escritorio, CPU ×4, mediana de 5)

| Interacción | INP (ms) | Corridas |
|---|---:|---|
| abrir el filtro del listado | 168 | 224, 152, 200, 168, 152 |
| cambiar de pestaña en el expediente | 72 | 72, 80, 56, 120, 56 |
| abrir el modal Registrar respuesta | 576 | 432, 640, 600, 576, 560 |


### Bundle: JS de primera carga por ruta

Esta tabla sale de `next build`; no depende del equipo. La columna "Primera carga" suma el gzip (nivel 9) de cada chunk que `.next/diagnostics/route-bundle-stats.json` lista para la ruta. "Propio" es lo que queda al restar lo compartido. Las columnas con * salen de `next analyze`: suman el peso comprimido módulo por módulo, así que sirven para repartir el peso, no como total (P5).

| Ruta | Primera carga (gzip) | Propio de la ruta (gzip) | Sin comprimir | antd + rc-component* | zod + RHF* | Carga diferida* |
|---|---:|---:|---:|---:|---:|---:|
| `/login` | 327,3 kB | 77,6 kB | 1033,7 kB | 140,6 kB | 49,0 kB | — |
| `/aceptar-invitacion` | 363,8 kB | 114,1 kB | 1141,2 kB | 188,3 kB | 49,0 kB | — |
| `/acceso` | 260,9 kB | 11,2 kB | 815,6 kB | 116,4 kB | — | — |
| `/dashboard` | 363,7 kB | 114,1 kB | 1125,4 kB | 216,8 kB | — | — |
| `/reportes` | 385,2 kB | 135,5 kB | 1190,9 kB | 231,4 kB | — | — |
| `/admin/usuarios` | 425,8 kB | 176,1 kB | 1330,9 kB | 226,4 kB | 47,8 kB | — |
| `/mi-dia` | 421,5 kB | 171,8 kB | 1320,1 kB | 221,6 kB | 47,8 kB | — |
| `/solicitudes` | 380,3 kB | 130,6 kB | 1174,4 kB | 232,8 kB | — | — |
| `/solicitudes/[id]` | 480,7 kB | 231,0 kB | 1520,0 kB | 253,1 kB | 47,8 kB | 136,4 kB |
| `/clientes` | 384,5 kB | 134,9 kB | 1186,1 kB | 231,4 kB | — | — |
| `/mis-comisiones` | 380,2 kB | 130,5 kB | 1174,9 kB | 232,8 kB | — | — |
| `/prospectos` | 435,9 kB | 186,2 kB | 1361,8 kB | 230,7 kB | 47,8 kB | — |
| `/portal` | 431,2 kB | 181,5 kB | 1332,0 kB | 246,6 kB | 47,8 kB | — |

Compartido por todas las rutas: 249,7 kB gzip (784,5 kB sin comprimir), 11 chunks.

**Los 10 módulos más pesados** (el mayor peso de cada módulo entre las rutas medidas):

| # | Módulo | Peso (comprimido, módulo suelto) | Rutas |
|---|---|---:|---|
| 1 | `next/dist/compiled/react-dom/cjs/react-dom-client.production.js` | 62,4 kB | todas |
| 2 | `react-hook-form/dist/index.esm.mjs` | 14,6 kB | 7 |
| 3 | `zod/v4/core/schemas.js` | 8,8 kB | 7 |
| 4 | `next/dist/compiled/react-server-dom-turbopack/cjs/react-server-dom-turbopack-client.browser.production.js` | 7,6 kB | todas |
| 5 | `next/dist/client/components/segment-cache/cache.js` | 6,3 kB | todas |
| 6 | `src/features/applications/participant-edit.tsx` | 5,1 kB | 1 |
| 7 | `zod/v4/core/util.js` | 4,0 kB | 7 |
| 8 | `next/dist/client/components/render-tree.js` | 3,9 kB | todas |
| 9 | `next/dist/client/components/segment-cache/scheduler.js` | 3,9 kB | todas |
| 10 | `zod/v4/classic/schemas.js` | 3,4 kB | 7 |

**Paquetes más pesados** (suma comprimida módulo a módulo, en la ruta donde más pesan): next 166,4 kB, antd 144,1 kB, zod 33,2 kB, @rc-component/select 15,5 kB, react-hook-form 14,6 kB, @tanstack/query-core 14,5 kB, @rc-component/form 11,4 kB, @tanstack/table-core 9,9 kB, @rc-component/menu 9,9 kB, @rc-component/trigger 9,2 kB, @rc-component/util 8,6 kB, @rc-component/virtual-list 7,9 kB

**Qué entra en cada ruta:**

- **antd:** entra en todas, porque el `ConfigProvider` y el `App` del layout raíz traen `notification`, `message`, `modal` y `skeleton`. Va de 59 kB (`/acceso`) a 144 kB (expediente), y los paquetes `@rc-component/*` suman otro tanto. Las importaciones ya son por nombre desde `antd`; no hay importaciones de `antd/lib`.
- **Iconos:** no hay librería de iconos. Son SVG propios (`components/ui/icons.tsx`, `features/admin-common/icons.tsx`), de 1 a 2 kB.
- **Fechas:** no entra `dayjs` ni ninguna otra librería de fechas. El formato usa `Intl` (`lib/format`).
- **Formularios:** `zod` (33 kB) más `react-hook-form` (15 kB) entran en las 7 rutas con formulario en la primera carga. Eso incluye `/login` y `/aceptar-invitacion`, aunque esta última sin token solo muestra un mensaje de error.
- **Carga diferida:** solo el visor de PDF (`pdfjs-dist`, `components/ui/pdf-loader.ts`) se carga aparte, con 136 kB en el expediente. Ninguna ruta usa `next/dynamic`.
- **Portal y backoffice:** el portal solo trae código de `features/buyer-*`, `components/ui`, `lib` y `providers`. No arrastra pantallas del backoffice. En sentido contrario, el login trae unos 2 kB de iconos del menú (`lib/navigation/nav-config.tsx`), porque calcula el destino después del login.

### Red: detalle por página (caché fría, corrida 1)

Las "oleadas" se calculan así: una petición que arranca cuando ya terminó otra de la API abre una oleada nueva. En el expediente, la petición de `metadata/bootstrap` y las 10 de las secciones salen del mismo render. Por eso, aunque el cálculo da 5 oleadas, la cadena real tiene 4 etapas: `auth/me` → detalle → secciones → perfil financiero del participante.

- `/login`: 2 peticiones en 2 oleadas. Mayores: `GET /api/v1/auth/me` < 1 kB, `POST /api/v1/auth/refresh` < 1 kB.
- `/aceptar-invitacion`: sin llamadas a la API.
- `/acceso`: sin llamadas a la API.
- `/dashboard`: 8 peticiones en 2 oleadas. Mayores: `GET /api/v1/metadata/bootstrap` 36 kB, `GET /api/v1/auth/me` 2 kB, `GET /api/v1/users` 2 kB.
- `/reportes`: 5 peticiones en 2 oleadas. Mayores: `GET /api/v1/metadata/bootstrap` 36 kB, `GET /api/v1/auth/me` 2 kB, `GET /api/v1/users` 2 kB.
- `/admin/usuarios`: 3 peticiones en 2 oleadas. Mayores: `GET /api/v1/roles` 15 kB, `GET /api/v1/users` 4 kB, `GET /api/v1/auth/me` 2 kB.
- `/mi-dia`: 6 peticiones en 2 oleadas. Mayores: `GET /api/v1/metadata/bootstrap` 36 kB, `GET /api/v1/workday/applications` 10 kB, `GET /api/v1/auth/me` 1 kB.
- `/solicitudes`: 5 peticiones en 2 oleadas. Mayores: `GET /api/v1/metadata/bootstrap` 36 kB, `GET /api/v1/applications` 26 kB, `GET /api/v1/auth/me` 1 kB.
- `/solicitudes/<id>`: 14 peticiones en 5 oleadas. Mayores: `GET /api/v1/metadata/bootstrap` 36 kB, `GET /api/v1/applications/<id>/completeness` 3 kB, `GET /api/v1/applications/<id>` 3 kB.
- `/clientes`: 3 peticiones en 2 oleadas. Mayores: `GET /api/v1/metadata/bootstrap` 36 kB, `GET /api/v1/clients` 10 kB, `GET /api/v1/auth/me` 1 kB.
- `/mis-comisiones`: 3 peticiones en 2 oleadas. Mayores: `GET /api/v1/metadata/bootstrap` 36 kB, `GET /api/v1/me/commissions` 1 kB, `GET /api/v1/auth/me` 1 kB.
- `/prospectos`: 4 peticiones en 2 oleadas. Mayores: `GET /api/v1/metadata/bootstrap` 35 kB, `GET /api/v1/broker/opportunities` 6 kB, `GET /api/v1/dashboard/summary` 1 kB.
- `/portal`: 5 peticiones en 3 oleadas. Mayores: `GET /api/v1/buyer/applications/<id>/document-slots` 6 kB, `GET /api/v1/buyer/applications/<id>` 3 kB, `GET /api/v1/buyer/participants/<id>/financial-profile` 1 kB.
Los tamaños son los del cuerpo sin comprimir.

## Hallazgos

El detalle de cada uno (causa, archivo, corrección sugerida y esfuerzo) está en [`frontend-hallazgos.md`](frontend-hallazgos.md).

| Id | Título | Severidad | Página(s) | Métrica |
|---|---|---|---|---|
| PERF-01 | El expediente encadena 4 etapas de peticiones y carga todas sus pestañas y modales de entrada | Alta | `/solicitudes/<id>` | LCP móvil 5,81 s; perf. 51; TBT 1.534 ms; 481 kB gzip |
| PERF-02 | El dashboard se mueve al llegar los datos (bloques de carga de altura fija) | Alta | `/dashboard` | CLS móvil 0,564; escritorio 0,187 (WV 0,213) |
| PERF-03 | El texto principal del portal espera sesión y solicitud en cadena | Alta | `/portal` | LCP móvil 5,29 s; perf. 62 |
| PERF-04 | Abrir "Registrar respuesta" bloquea el hilo principal | Alta | `/solicitudes/<id>` | INP 576 ms |
| PERF-05 | Las páginas con sesión no pintan nada hasta `/auth/me` y piden sus datos después | Media | todas las del backoffice | FCP/LCP móvil 2,22–2,69 s |
| PERF-06 | Mi día y Prospectos se mueven al llegar los datos | Media | `/mi-dia`, `/prospectos` | CLS móvil 0,148 y 0,214 |
| PERF-07 | TBT alto en el listado de solicitudes | Media | `/solicitudes` (y el resto del backoffice) | TBT móvil 1.244 ms; perf. 73 |
| PERF-08 | `/aceptar-invitacion` sin token carga el formulario entero y pinta el mensaje tarde | Media | `/aceptar-invitacion` | LCP móvil 3,73 s; 114 kB propios |
| PERF-09 | El cuerpo del `403` de `/auth/refresh` no se lee y la conexión queda abierta | Baja | `/login` (y toda página sin sesión) | carga "sin terminar" 45 s en Lighthouse |
| PERF-10 | El login carga 327 kB gzip y tiene TBT móvil de 520 ms | Media | `/login` | perf. móvil 87; TBT 520 ms; 122 kB sin usar |
| PERF-11 | `metadata/bootstrap` (36 kB) viaja en cada carga con `no-store` | Informativa (depende del backend) | todas las del backoffice | respuesta más grande |
| PERF-12 | Fuentes con `@fontsource` dentro del CSS bloqueante, sin `preload` | Informativa | todas | CSS bloqueante 12 kB; `font-display` correcto |
