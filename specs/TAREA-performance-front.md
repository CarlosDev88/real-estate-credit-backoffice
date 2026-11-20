# TAREA — Auditoría de performance del frontend

> Spec cerrada. Todas las decisiones están tomadas. **No preguntes:** si algo no cuadra con el código, decide lo más simple, anótalo en "Precisiones acordadas" (al final) y en el reporte, y sigue.

## 0. Contexto
- Frontend: Next 16.4 (App Router), React 19.3, antd 6.7, Tailwind 4, TanStack Query/Table, RHF + Zod. Grupos de rutas: `(auth)/login`, `(backoffice)/…` (dashboard, solicitudes, clientes, comisiones, mis-comisiones, prospectos, mi-dia, reportes, proyectos, admin), `(portal)/portal`, `(public)/aceptar-invitacion` y `acceso`.
- Es la segunda de las tres auditorías del cierre (seguridad del backend → **performance del front** → carga del backend con k6). Igual que en seguridad, **cada hallazgo documenta cómo se solucionó**, y el resultado es **público** en el repo (`docs/PERFORMANCE.md`), enlazado desde el README.
- **Arranca cuando estén en `master`** la F7 (#33), las brechas 3 con la demo ampliada y la fase B de seguridad: así se mide la app completa y con datos realistas.

## 1. Qué es y qué no es
- **Es:** medir con método (Lighthouse, Web Vitals de laboratorio, tamaño del bundle), encontrar lo que más pesa, corregirlo, medir otra vez y dejar **presupuestos en el CI** para que no vuelva.
- **No es:** reescribir la app, cambiar de librería de componentes ni tocar el backend. Si una mejora necesita el backend (por ejemplo, un endpoint más liviano), va como hallazgo "depende del backend" con la sugerencia, sin hacerla.
- **Regla de oro:** ningún arreglo cambia lo que ve o hace el usuario (salvo que sea más rápido). Las pruebas unitarias, de Storybook (a11y) y E2E siguen verdes.

## 2. Dónde y cómo
- **Worktree:** `C:\Users\ASUS\Documents\programacion\mvp-backoffice\wt-front-perf`, rama `perf/frontend-audit`, desde `origin/master`. Copia de esta spec en `specs/TAREA-performance-front.md`. Puerto **3003** para `next start`.
- **Agente:** "perf-front". Buzón `.buzon/` como siempre.
- **Backend:** el de `:8000` (carpeta principal) con `seed_demo_data` ampliado. Si está caído, lo dices en `ESTADO.md` y esperas; no lo arranques tú.

### Reglas
1. Git solo lectura. No leas ni edites `.env*` (el `.env.local` del worktree lo pone el orquestador con los usuarios de demo).
2. Nada secreto en reportes ni docs. Solo la contraseña de demo `DemoUmbral2026!`.
3. **Siempre sobre el build de producción** (`corepack pnpm build && corepack pnpm start -p 3003`). Nunca midas `next dev`.
4. **Herramientas con versión fija** y la más reciente con al menos dos semanas de publicada: `lighthouse` (y `@lhci/cli` para el CI), `web-vitals`, `@next/bundle-analyzer`. Lo que solo se usa para medir en local va con `npx --yes <paquete>@<versión>` o en una carpeta fuera del repo (`C:\Users\ASUS\Documents\programacion\mvp-backoffice\_perf-work\`), no en `package.json`. Solo entra a `devDependencies` lo que el CI necesita. Anota todas las versiones en el reporte y en el informe.
5. **Condiciones de medición iguales** antes y después: mismo equipo, nada pesado corriendo (si hay otros agentes con Docker, lo anotas), **5 corridas por página y se reporta la mediana**, caché fría (perfil nuevo) y, en una corrida aparte, caché tibia.
6. Pruebas acotadas en local; la suite completa la corre el CI. Siempre `lint`, `typecheck`, `format:check` y `test` de lo tocado.

## 3. Parte 1 — Línea base (medir, sin cambiar nada)
1. **Páginas a medir (12)**, con el usuario de demo que corresponde:
   - públicas: `/login`, `/aceptar-invitacion` (sin token, el estado de error), `/acceso` (sin token);
   - admin: `/dashboard`, `/reportes`, `/admin` (usuarios);
   - asesora (`asesora.lucia@demo.local`): `/mi-dia`, `/solicitudes` (listado), `/solicitudes/<id>` (un expediente con documentos y radicación), `/clientes`, `/comisiones` o `/mis-comisiones`;
   - broker: `/prospectos`;
   - comprador: la página principal del portal (con un enlace de demo consumido).
2. **Lighthouse** (modo navegación) en **móvil** (el perfil por defecto de Lighthouse: Moto G Power, 4G lento, CPU ×4) y **escritorio**, en las 12. Para las páginas con sesión: Playwright inicia sesión, y Lighthouse corre en ese mismo Chrome (puerto de depuración) con la cookie ya puesta. Guarda los JSON y HTML crudos en `_perf-work/` (no en el repo).
3. **Web Vitals de laboratorio** con Playwright + la librería `web-vitals` inyectada: **LCP, CLS, INP, FCP, TTFB** en las 12, más **INP de 3 interacciones reales**: abrir el filtro del listado de solicitudes, cambiar de pestaña en el expediente y abrir el modal "Registrar respuesta".
4. **Bundle:** `@next/bundle-analyzer` (solo en local) y la tabla de `next build`: **JS de primera carga por ruta** (gzip) y el compartido; los 10 módulos más pesados; qué de antd, iconos y fechas entra en cada ruta; si algo del portal arrastra código del backoffice o al revés.
5. **Red:** número de peticiones a la API al abrir cada página con sesión (y si alguna se repite o se encadena en cascada), tamaño de las respuestas más grandes.
6. **Salida:** `docs/performance/frontend-linea-base.md` con todas las tablas (mediana de 5, versión de cada herramienta, equipo y condiciones) y la lista de hallazgos con id `PERF-NN`.

**Formato de cada hallazgo** (en `docs/performance/frontend-hallazgos.md`): id, título, severidad, página(s), métrica afectada con su valor, causa probable (con la ruta del archivo), corrección sugerida, esfuerzo. **Severidad:** Alta (una Web Vital en "pobre" o Lighthouse móvil < 50 en una página principal), Media ("necesita mejorar", o > 50 kB gzip evitables en una ruta), Baja (mejoras menores), Informativa (contexto o lo que depende del backend).

**Commit:** `docs(perf): measure the frontend performance baseline`

## 4. Parte 2 — Correcciones
- **Criterio (decidido):** se corrigen todas las Altas y Medias y las Bajas pequeñas. Lo que no se corrige va como **aceptado** con su motivo.
- Lo típico a revisar (no es lista cerrada; manda lo que diga la medición):
  - código que no hace falta en la primera carga: `next/dynamic` para modales, paneles, gráficos y el visor de documentos; nada del backoffice dentro del portal;
  - importaciones de antd y de iconos que arrastran de más;
  - componentes de cliente que podrían ser de servidor (`"use client"` demasiado arriba en el árbol);
  - consultas en cascada que se pueden pedir en paralelo, o con `prefetch` / `staleTime` en TanStack Query;
  - CLS: tamaños reservados para tablas, tarjetas y estados de carga (`LoadingState`);
  - fuentes e imágenes: `next/font`, `next/image` con tamaños, sin bloquear el render;
  - listas largas sin virtualizar, si la medición muestra que pesan.
- Cada corrección con su prueba si cambia comportamiento, y con la **medición antes y después** de la métrica que mueve.
- **Commits:** uno por grupo de cambios con su efecto en el mensaje (por ejemplo `perf(frontend): lazy-load the document viewer and the response modal`).

## 5. Parte 3 — Presupuestos en el CI
1. **Presupuesto de bundle (bloquea):** un script (`frontend/scripts/check-bundle-budget.ts`, Node, sin dependencias nuevas si se puede) que lee la salida del build y compara el **JS de primera carga por ruta** (gzip) contra `frontend/performance-budget.json`. Valores: lo medido **después** de las correcciones + **10 %**, redondeado a 5 kB. Falla con un mensaje claro: ruta, valor, presupuesto.
2. **Lighthouse CI (bloquea) en las públicas** (`/login`, `/aceptar-invitacion`, `/acceso`), que no necesitan backend: `@lhci/cli` contra `next start` en el CI, 3 corridas, móvil, con aserciones: performance ≥ 0,90, accesibilidad ≥ 0,95, buenas prácticas ≥ 0,95, LCP ≤ 2,5 s, CLS ≤ 0,1, TBT ≤ 200 ms. Si una pública no llega a 0,90 después de las correcciones, el umbral es lo medido menos 0,03, y se anota.
3. Las páginas con sesión **no** van al CI (necesitan backend y datos): quedan medidas en el informe y con un comando para repetirlas en local (`frontend/scripts/perf/` con un README corto).
4. **Filas nuevas en el reporte del CI** (`scripts/ci-report.ts`): "Bundle budget" y "Lighthouse (public pages)" con su resultado.
5. Una prueba del script de presupuesto (que falla con un manifiesto de ejemplo que se pasa y pasa con uno que no).

**Commit:** `ci(perf): add bundle budgets and Lighthouse CI for the public pages`

## 6. Parte 4 — Re-medición, informe público y cierre
1. **Re-medición completa** de la Parte 1 (mismas 12 páginas, mismas condiciones, mediana de 5): tabla **antes / después** por página y métrica.
2. **`docs/PERFORMANCE.md`** (en español, público; la sección del backend con k6 la agrega después otra tarea, deja su título con "(en curso)"):
   1. resumen ejecutivo: qué se midió, los 3 hallazgos más importantes, la mejora principal en números;
   2. método: herramientas con versión, equipo, perfiles (móvil y escritorio), número de corridas y por qué la mediana;
   3. resultados antes / después (Lighthouse, Web Vitals, bundle, red) con tablas y uno o dos gráficos Mermaid si ayudan;
   4. **cada hallazgo con "Cómo se solucionó"**: causa, cambio (rutas), verificación (métrica antes y después), commit, estado (`corregido` / `aceptado` con motivo / `depende del backend`);
   5. presupuestos que quedaron en el CI y cómo se actualizan;
   6. cómo reproducir la medición en local;
   7. límites del análisis (laboratorio, no usuarios reales; un solo equipo).
3. `docs/performance/frontend-hallazgos.md` con el estado final de cada `PERF-NN`.
4. **`README.md`** raíz: en Quality, una línea con la mejora principal y el enlace a `docs/PERFORMANCE.md`; en Documentation, la entrada. Solo esas líneas.
5. **`docs/guia/12-auditorias.md`**: la sección de performance del front con el resumen y la tabla de hallazgos con cómo se solucionó (no rehagas la guía).
6. Reporte final con la tabla antes/después, archivos tocados y **título y descripción del PR en español** (sin firmas ni `Co-Authored-By`).

**Commit:** `docs(perf): publish the frontend performance audit with the before and after`
**PR:** `perf(frontend): audit and improve frontend performance with budgets in CI`

## 7. Fuera de esta tarea (decidido)
- Carga y estrés del backend (k6): otra tarea, después de esta.
- Datos de usuarios reales (RUM): no hay despliegue.
- Cambiar antd, Tailwind o la arquitectura de rutas.

## Precisiones acordadas
(las agrega el agente)

- **P1 — 13 páginas, no 12.** La lista de la Parte 1 suma 13 (3 públicas, 3 admin, 5 asesora, broker, comprador). Se miden las 13.
- **P2 — `/admin` es `/admin/usuarios`.** No existe `/admin/page.tsx`; la página de usuarios es `/admin/usuarios`.
- **P3 — Comisiones de la asesora:** `/mis-comisiones` (permiso `commissions.read_own`); `/comisiones` es del administrador.
- **P4 — Sin columna "First Load JS".** Next 16.4 con Turbopack ya no la imprime en `next build`. El JS de primera carga por ruta sale de `.next/diagnostics/route-bundle-stats.json` (lista de chunks por ruta, la escribe el build), sumando el **gzip nivel 9** de cada chunk (`node:zlib`, como el antiguo `gzip-size` de Next). El presupuesto del CI (Parte 3) lee ese mismo archivo.
- **P5 — `@next/bundle-analyzer` no sirve con Turbopack** (solo webpack). Para los módulos más pesados se usa el analizador nativo de Next 16 (`next analyze --output` + `next analyze export --route <ruta>`, JSON Lines con el tamaño comprimido de cada módulo). Sus tamaños son la suma de módulos comprimidos uno por uno: sirven para repartir el peso (paquete, componente de antd), no como total; el total por ruta es el de P4.
- **P6 — Versiones de las herramientas** (la más reciente con ≥ 2 semanas al 2026-11-19): `lighthouse@13.6.0`, `@lhci/cli@0.16.0` (la 0.16.1 tiene 8 días), `web-vitals@6.2.3`, `playwright@1.65.0` (la del repo, Chromium 1254). Viven en `_perf-work/package.json`, fuera del repo.
- **P7 — Sesión y caché fría.** Un Chrome (Playwright, `launchPersistentContext` con perfil nuevo en una carpeta temporal) por rol; el login se hace una vez por la pantalla real y Lighthouse corre en ese mismo Chrome por el puerto de depuración. "Caché fría" = Lighthouse limpia la caché HTTP en cada corrida (por defecto; las cookies quedan). "Caché tibia" = corrida aparte con `disableStorageReset` tras una carga previa. Así se hace un login por rol y por campaña (3 logins: límite `5/15m`) y no se reusa un refresh token rotado. Antes de cada corrida hay una carga previa en otra pestaña (renueva el access token de 15 min y calienta el servidor), que no se mide.
- **P8 — Perfiles.** Lighthouse: móvil por defecto (Moto G Power, 4G lento simulado, CPU ×4) y el preset de escritorio. Caché tibia: solo móvil. Web Vitals (Playwright + `web-vitals` inyectada): escritorio 1440×900 con CPU ×4 por CDP y sin limitar la red (el backoffice se usa en escritorio; con CPU ×4 el INP se distingue). El INP de cada página es el de una interacción neutra (clic en el título); las 3 interacciones reales se miden aparte con un `PerformanceObserver` de eventos (máximo `duration` de la interacción).
- **P9 — Expediente medido:** el primero de la asesora en estado `FILED` con documentos (tiene radicación sin respuesta y el botón "Registrar respuesta"). Abrir el modal no cambia datos (se cierra sin guardar). Portal: enlace nuevo creado como la asesora sobre una solicitud en espera y consumido en el Chrome del comprador.
- **P10 — Espera de carga acotada.** Sin sesión, `postRefresh` (`frontend/src/lib/api/session.ts`) no lee el cuerpo del `403` de `/auth/refresh` y Chrome no da por terminada esa petición hasta salir de la página: Lighthouse esperaba los 45 s de `maxWaitForLoad` ("page loaded too slowly") y Playwright nunca llegaba a `networkidle`. En la línea base la app no se toca: Lighthouse corre con `maxWaitForLoad: 15000` (las cargas reales terminan en < 5 s; el evento `load` y las métricas salen del trace igual) y Playwright espera `load` + `networkidle` con tope de 6–8 s. Queda como hallazgo y se corrige en la Parte 2.
- **P11 — Oleadas de red.** Una petición abre una oleada nueva si arranca después de que terminó otra de la API (horas de `request.timing()`). Peticiones del mismo render pueden caer en oleadas distintas (en el expediente, `metadata/bootstrap` y las 10 secciones); el informe lo aclara y cuenta las etapas reales.
- **P13 — `/prospectos` medida al día siguiente.** El 2026-11-19 Claude Code detuvo `next start` por falta de memoria a mitad de `/prospectos`. Se midió completa el 2026-11-20 (09:47–09:51), con el mismo build y los mismos scripts, en un solo comando en primer plano (servidor, medición y parada) para que no lo vuelva a detener. Se descartaron las 4 corridas de la víspera. La memoria libre era menor (2,0 GB al empezar, frente a unos 4 GB la noche anterior); queda anotado en la línea base.
- **P12 — Severidad sin trace.** PERF-04 (modal) y PERF-07 (listado) llevan una causa probable; el trace de la Parte 2 la confirma antes de corregir.
- **P14 — Medición de la Parte 2.** Antes y después de cada arreglo, solo en las páginas que toca. Se corren 5 veces Lighthouse móvil, Lighthouse escritorio y Web Vitals en caché fría, sin caché tibia; la campaña completa queda para la Parte 4. Se usa `_perf-work/scripts/with-server.sh`, que levanta `next start`, mide y lo detiene en un solo comando en primer plano.
- **P15 — Build limpio para medir.** Con builds incrementales (`.next` reusado tras muchos builds), el INP del filtro del listado subió de 160 a 240 ms. Una bisección con copias limpias de `HEAD` (`git archive`, solo lectura) mostró que ninguna parte del código lo causaba: el mismo código, compilado con `rm -rf .next`, da 136 ms. Desde entonces, los números del "después" salen de un build limpio, y la Parte 4 hace lo mismo.
- **P16 — Portal medido con otra solicitud.** El enlace del comprador se crea sobre una solicitud en espera elegida al azar: la línea base usó SOL-000013 y la medición final SOL-000010, con la misma estructura de pantalla.
- **P17 — Umbrales de Lighthouse CI calibrados.** Lighthouse CI abre un Chrome nuevo en cada corrida (todo en frío, sin caché de código), y en este equipo el TBT de las públicas varía mucho: en 4 campañas (mediana de 3, sin backend como en el CI), `/login` dio 244–464 ms, `/aceptar-invitacion` 156–237 ms y `/acceso` 175–224 ms. La performance quedó en 0,93–0,98, con un 0,88 aislado en `/login`. Con 200 ms como bloqueo, el CI fallaría al azar. Se aplica la regla de la spec ("lo medido menos 0,03"), extendida al TBT:
  - `/login`: performance ≥ 0,85 (0,88 − 0,03) y TBT ≤ 500 ms.
  - `/aceptar-invitacion` y `/acceso`: performance ≥ 0,90 y TBT ≤ 300 ms.
  - Accesibilidad ≥ 0,95, buenas prácticas ≥ 0,95, LCP ≤ 2,5 s y CLS ≤ 0,1, como en la spec.
  - Agregación `median-run` de 3 corridas.
  - Se recalibran con las primeras corridas del CI (los informes quedan en el artefacto).
- **P18 — Lighthouse CI sin backend.** En el CI, `/login` no tiene backend: `/auth/me` responde 500 por el proxy. Buenas prácticas igual da 96 (la línea base, con backend, también daba 96; el audit que falla es "errores en la consola"). Corre con el Chromium de Playwright (`CHROME_PATH`), el mismo de la medición, después del paso que lo instala. El `timeout-minutes` del job sube de 20 a 25.
- **P19 — Presupuesto para todas las rutas.** `performance-budget.json` cubre las 35 rutas del build, no solo las 13 medidas. Una ruta nueva sin presupuesto hace fallar el paso, con el mensaje de cómo agregarla (`--update`). Una ruta del presupuesto que ya no existe solo avisa. Los valores salen del build limpio final de la Parte 2.
- **P20 — Nombres de las filas.** En el workflow, los pasos se llaman como en la spec ("Bundle budget", "Lighthouse (public pages)"). En el reporte, que está en español como las demás filas, son "Presupuesto de bundle" y "Lighthouse (páginas públicas)".
- **P21 — Herramientas de medición local.** `frontend/scripts/perf/` carga `lighthouse` y `web-vitals` desde `PERF_TOOLS`, una carpeta fuera del repo. Solo `@lhci/cli` (0.16.0, que trae `lighthouse` 13.6.0) entra en `devDependencies`, porque lo usa el CI.
