# TAREA — Documentación completa del proyecto (en español) y demo con un solo comando

**Agente:** docs (nuevo). **Worktree:** `wt-docs`, rama `docs/project-guide`, desde `origin/master`. Sin puerto: no levanta la app salvo en el paso final de la demo (ver Parte 4).
**Para quién se escribe:** un reclutador técnico, un líder de ingeniería o un dev que llega al repo y quiere entender **qué es, cómo está hecho y por qué se decidió así**, sin leer cientos de miles de líneas de código. El README es la puerta de entrada; esta documentación es el recorrido completo.

## Reglas
- Git solo lectura, buzón, no preguntes (decide, anota en "Precisiones acordadas", sigue), no leas ni edites `.env*`.
- **Todo en español**, en lenguaje humano: frases cortas, primero la idea en simple y después el detalle técnico. Cada término técnico la primera vez se explica en una línea. Nada de relleno ni frases de venta.
- **Diagramas con Mermaid** (GitHub los muestra): contexto y contenedores (estilo C4), secuencia, estados, ER y flujo. Cada diagrama con una línea que diga qué mirar en él. Sin imágenes externas.
- **Fuentes de verdad, en este orden:** el **código** en `master`, `contracts/openapi.json`, `docs/` (REQ, API, DER, modelo, SQL) y las **"Precisiones acordadas"** de cada `specs/TAREA-*.md` (ahí están las decisiones con su porqué). Si la doc vieja contradice el código, manda el código y lo anotas como "la spec decía X; quedó Y porque…".
- **No inventes**: cada afirmación técnica se puede rastrear a un archivo (pon la ruta: `apps/filings/responses.py`). Cifras (pruebas, cobertura, endpoints, tablas) contadas de verdad, con la fecha.
- **No toques código** (`apps/`, `config/`, `frontend/src/`) ni los documentos existentes de `docs/` (REQ, API, DER, SQL, modelo): esos son de los otros agentes. Tu trabajo es **nuevo** en `docs/guia/` y `docs/adr/`, más los scripts de la demo (Parte 4) y una sola línea en el README (Parte 5).
- **No escribas** `docs/SEGURIDAD.md`, `docs/PERFORMANCE.md` ni `docs/DESIGN-SYSTEM.md`: los hacen otros agentes. Enlázalos como "en preparación" si todavía no existen.
- Sin secretos, sin datos personales reales. Solo los usuarios y la contraseña **de demo** que ya están en el código.
- Pruebas pesadas: **no** corras la suite completa del backend ni del front (hay otros 3 agentes y poca memoria). Basta con verificar los enlaces y que Mermaid renderice (ver verificaciones).

## Estructura (archivos nuevos)
```
docs/guia/
  00-indice.md               mapa de toda la documentación y por dónde empezar según quién eres
  01-el-producto.md          qué problema resuelve, actores, recorrido del comprador, glosario
  02-negocio.md              el crédito de vivienda en Colombia como dominio: estados, reglas, decisiones de negocio con su porqué
  03-arquitectura.md         contexto y contenedores (C4), monolito modular, capas, contrato OpenAPI primero, front ↔ API, modos local
  04-system-design.md        requisitos no funcionales y cómo se cumplen (ver abajo)
  05-modelo-de-datos.md      grupos de tablas, ER por grupo, convenciones, desvíos del SQL
  06-modulos.md              índice de los 16 módulos + una sección por módulo (ver plantilla)
  07-flujos.md               la ruta crítica de punta a punta, con diagramas de secuencia y de estados
  08-frontend.md             arquitectura del front, las 22 vistas, permisos, datos, errores, design system
  09-calidad.md              estrategia de pruebas, CI con reporte en el PR, cobertura, E2E, accesibilidad, contrato
  10-operacion-local.md      cómo correrlo, modos, demo en un comando, comandos útiles, problemas comunes
  11-como-se-construyo.md    el método: specs cerradas, agentes en paralelo, revisión, CI como filtro, errores atrapados
  12-auditorias.md           las tres auditorías (seguridad, performance del front, carga del backend): qué se encontró y CÓMO SE SOLUCIONÓ
docs/adr/
  README.md                  qué es un ADR y la lista
  0001-....md … (12 a 15)
```

## Parte 1 — Producto, negocio y arquitectura (01, 02, 03 y 00 en borrador)
- **01-el-producto:** el problema (asesores que arman expedientes a mano, compradores que mandan documentos por WhatsApp), los 5 roles y qué hace cada uno (REQ §3), el recorrido del comprador contado como historia, las 22 vistas en una tabla, glosario (radicar, legalización, desembolso, deudor solidario, etc.).
- **02-negocio:** estados de la oportunidad y de la solicitud (diagramas de estados), documentos y su revisión, radicación manual y respuestas del banco (con la tabla de qué cambia cada respuesta), comprador y enlace mágico, consentimientos, notificaciones, comisiones (reparto, redondeo, corrección), **todas las decisiones de negocio** con su porqué: las del anexo A de esta spec y las que encuentres en las "Precisiones acordadas" de cada spec.
- **03-arquitectura:** diagrama de contexto (asesor, comprador, banco fuera del sistema, correo), contenedores (Next.js, Django/DRF, PostgreSQL, almacenamiento, worker, antivirus; modo simple vs. completo), el **monolito modular** (por qué no microservicios), las capas dentro de un módulo (views → serializers → services → models; señales entre módulos), el **contrato OpenAPI primero** (backend lo genera, front genera tipos, CI verifica), mismo origen por el proxy de Next (cookies, CSRF, sin CORS en la demo), y cómo se pasaría a producción (qué cambia).

## Parte 2 — System design, datos y módulos (04, 05, 06)
- **04-system-design**, una sección por requisito no funcional, cada una con: qué pide REQ, cómo se resolvió, dónde está en el código y qué se probó:
  - **seguridad por diseño** (autenticación con JWT en cookies, permisos por código, alcance por rol con 404, enlace mágico de un solo uso, archivos con validación y antivirus, URL firmadas, auditoría inmutable; enlazar `docs/SEGURIDAD.md`);
  - **consistencia y concurrencia** (transacciones, `select_for_update`, `on_commit` para efectos, `ETag`/`If-Match`, idempotencia con `Idempotency-Key`);
  - **trabajo asíncrono** (Celery, modo eager en local, reintentos, qué va en segundo plano y por qué);
  - **rendimiento** (sin consultas por fila, agregados en la base, paginación, índices; enlazar `docs/PERFORMANCE.md`);
  - **observabilidad** (`request_id`, logs sin datos personales, auditoría, actividad);
  - **límites de consumo**; **privacidad** (enmascarado, qué ve cada rol); **escalabilidad** (qué se escalaría primero y cómo).
- **05-modelo-de-datos:** cuántas tablas y por grupo, un `erDiagram` por grupo (identidad, CRM, solicitudes, documentos, radicación, comunicación, reportes, comisiones), convenciones (UUID, `created_at/updated_at`, dinero en `BIGINT` COP, porcentajes `NUMERIC`, `CHECK`), y los **desvíos del SQL documentados** (`version`, unicidades parciales, etc.). Enlaza DER/SQL/modelo existentes.
- **06-modulos:** tabla de los 16 módulos (orden de construcción, dueño de qué tablas, depende de) y **una sección por módulo** con esta plantilla:
  - qué resuelve (en una frase), tablas que posee, endpoints principales (tabla), permisos y alcance, reglas de negocio clave, eventos que emite y escucha, decisiones con su porqué (de las Precisiones), cómo se prueba (archivos de `tests/`), y qué quedó fuera.

## Parte 3 — Flujos, frontend, calidad, método y ADRs (07, 08, 09, 11, adr/)
- **07-flujos:** diagramas de **secuencia** de: alta de cliente → oportunidad → solicitud; enlace mágico → consentimientos → datos → carga de documentos (con antivirus); revisión → lista para radicar; paquete → radicación → respuestas del banco (devolución, corrección, aprobación, legalización, desembolso); liquidación de comisión y pago; exportación de reportes. Cada uno con qué valida el backend en cada paso.
- **08-frontend:** App Router y grupos de rutas, `features/` por dominio, `components/ui` y el design system (enlaza `docs/DESIGN-SYSTEM.md` y Storybook), datos (TanStack Query + `openapi-fetch` con tipos generados), formularios (RHF + Zod: formato en el front, negocio en la API), errores y sesión (`MutationCache`, `SESSION_EXPIRED`, `CONSENT_REQUIRED`), navegación por permisos, portal móvil primero, accesibilidad, y la tabla de las 22 vistas con ruta, rol y endpoints.
- **09-calidad:** la pirámide (unitarias, integración con MSW, E2E con Playwright, axe), los números reales (pruebas de backend y front, cobertura, stories), el CI (los dos jobs obligatorios, el reporte en cada PR con la captura `docs/images/ci-report.png`, `CI gate`), el contrato verificado, la regla de colores, las auditorías (enlaces).
- **11-como-se-construyo:** el método con IA contado con honestidad: specs cerradas con las decisiones tomadas, agentes en paralelo con carpetas propias (worktrees), git en solo lectura para los agentes y commits del autor, revisión de cada parte, el CI como filtro, y **errores reales que se atraparon** (están en las specs y en los PR: por ejemplo el grupo de concurrencia del CI compartido, el reloj de Docker, el botón destructivo como principal, migraciones con el mismo número, la prueba de idempotencia con la lista a mano, imports rotos después de mover componentes). Sin nombres de herramientas comerciales que no estén en el repo.
- **docs/adr/** (formato: contexto, opciones consideradas, decisión, consecuencias, estado), 12 a 15, por ejemplo: monolito modular; DRF + contrato OpenAPI generado; JWT en cookies `HttpOnly` con CSRF y proxy de mismo origen; enlace mágico sin cuenta para el comprador; alcance por rol con 404; auditoría inmutable con trigger; señales después del commit en lugar de outbox; idempotencia opcional por cabecera; `ETag`/`If-Match`; almacenamiento con URL firmadas y antivirus; Celery con modo eager en local; Next.js App Router + TanStack Query + tipos generados; design system propio en Storybook con a11y en el CI; comisiones con `Decimal` y redondeo al peso; modo local simple vs. completo.

## Parte 3b — `12-auditorias.md`: hallazgos y cómo se solucionaron (pedido de Carlos: es importante)
- Un documento que junta las **tres auditorías** en lenguaje humano: **seguridad** (`docs/SEGURIDAD.md`, `docs/seguridad/`), **performance del front** y **carga/estrés del backend** (`docs/PERFORMANCE.md`).
- Para cada auditoría: qué se revisó y con qué método (2-3 líneas y enlace al informe completo), el conteo de hallazgos por severidad y una **tabla de hallazgos con cómo se solucionó cada uno**: id, problema en una frase, **causa**, **solución aplicada** (qué se cambió y dónde, con la ruta), **cómo se verificó** (la prueba que lo cubre, la medición antes/después o el re-test) y el **PR** que lo cerró; los aceptados con su motivo.
- Una sección final "lo que aprendimos": los patrones que se repitieron y qué regla quedó en el CI para que no vuelva a pasar.
- **Hoy las auditorías están en curso**: deja la estructura completa con las secciones y la tabla de seguridad llenada hasta donde haya (los hallazgos SEC-01 a SEC-13 están en `docs/seguridad/hallazgos.md` de la rama `chore/security-audit`, aún sin fusionar: si no está en master, déjala como "en curso" con el enlace). Se completa al cierre, cuando terminen las correcciones.

## Parte 4 — Demo con un solo comando (10-operacion-local + scripts)
- **Scripts en la raíz del repo:** `demo.ps1` (Windows, PowerShell 7) y `demo.sh` (Linux/macOS), que encadenan los pasos existentes:
  1. revisar que Docker esté corriendo (mensaje claro si no);
  2. si **no existe** `backend/.env`, crearlo desde `.env.example` **generando claves nuevas y fuertes** (`DJANGO_SECRET_KEY`, `AUTH_JWT_SIGNING_KEY` de ≥ 48 bytes con `secrets`) y `DJANGO_DEBUG=True`; **si ya existe, no lo toca nunca**;
  3. `docker compose up -d --build` (modo simple);
  4. esperar a que `/health` y `/ready` respondan (con tiempo máximo y mensaje si falla);
  5. `seed_demo_data` (idempotente);
  6. imprimir un resumen: URL del backoffice, de la API y de la documentación de la API, usuarios de demo con su rol y la contraseña de demo, y la URL de un enlace del portal del comprador (la que imprime el seed);
  7. opciones: `-Stop`/`--stop` (detiene sin borrar), `-Reset`/`--reset` (borra volúmenes **solo** con confirmación explícita escrita) y `-Full`/`--full` (modo completo con el perfil `full`).
- Mensajes en español, colores solo si la terminal los soporta, salida con código de error correcto.
- **Pruebas:** lógica separada para poder probarla sin Docker (por ejemplo, la generación del `.env` en un directorio temporal). **No corras la demo de punta a punta** mientras haya otros agentes usando `:8000`: el compose usa nombres fijos y reiniciaría su backend. Deja una sección "Cómo la probé" y el orquestador te avisa cuándo correrla completa.
- **10-operacion-local:** requisitos, la demo, los dos modos, comandos útiles (migrar, seed, limpiar límites, logs), puertos, problemas comunes (reloj de Docker, puertos ocupados, el shim de pnpm en Windows) y cómo detener todo sin perder datos.

## Parte 5 — Revisión, índice y PR
- **00-indice:** "por dónde empezar" según quién eres (reclutador: 01 → 11 → 12-auditorias; ingeniero: 03 → 04 → 06 → adr; quien quiere correrlo: 10), y el mapa completo con una línea por documento.
- Revisa: todos los enlaces relativos funcionan, cada Mermaid renderiza (`npx --yes @mermaid-js/mermaid-cli@11` en un contenedor `node:22` sobre cada bloque, o el render de GitHub si prefieres: anota cuál usaste), ortografía, cifras con fecha.
- **README:** agrega **una sola línea** en "Documentation" que enlace `docs/guia/00-indice.md` ("Guía completa del proyecto, en español"). Nada más del README (otros agentes lo tocan).
- Reporte de cierre con: lista de documentos y su tamaño, diagramas por documento, decisiones que interpretaste, y título y descripción del PR (en español).

## Entregas
| Parte | Commit propuesto |
| --- | --- |
| 1 | `docs: add the product, business and architecture guide` |
| 2 | `docs: add the system design, data model and module guide` |
| 3 | `docs: add the flows, frontend, quality and method guide with ADRs` |
| 4 | `feat(dev): start the whole demo with a single command` |
| 5 | `docs: add the documentation index and link it from the README` |

## Anexo A — Decisiones de negocio y de producto tomadas con Carlos (para 02-negocio y los ADR)
- Alcance cerrado: 16 módulos, 22 vistas (14 de operación y 8 del portal), solo local + CI, sin despliegue; la única publicación es el Storybook en GitHub Pages.
- Radicación: tipos de respuesta del catálogo más `DISBURSED`; la legalización es manual; el desembolso es una respuesta con monto; una devolución lleva la solicitud a `BANK_OBSERVATION` y el comprador corrige solo lo observado; la evidencia de la respuesta es opcional.
- Portal: la tarjeta del asesor muestra nombre, correo y WhatsApp; el comprador ve su línea de tiempo filtrada (sin notas internas).
- Tareas: sin tareas automáticas en el MVP (todas manuales).
- Reportes: alcance "medio" (dashboard, embudo, listado, CSV directo y exportación asíncrona solo CSV; sin XLSX); embudo por **cohorte** + foto actual; fechas elegibles con el mes en curso por defecto y máximo 366 días; admin todo, asesor lo suyo, broker solo conteos, constructora nada; un filtro fuera de alcance responde 403.
- Comisiones: solo al desembolsar; tasa sobre el monto desembolsado; reparto asesor/broker según el plan si el origen es broker y 100 % al asesor en cualquier otro (la constructora no cobra); liquidación única e inmutable; pago de cada parte por separado; corrección del desembolso: sin pagos se anula y recalcula, con pagos queda para revisión manual. Plan de demo: 1 %, 70/30.
- Oportunidades: si la crea un asesor queda asignada a él; si la crea un broker o el admin, queda sin asesor.
- Corregir un desembolso: solo el admin y solo la última respuesta.
- Fuera del MVP: la campana de notificaciones internas del backoffice, "deshacer" una aprobación de documento, integración con bancos, DataCrédito, firma electrónica.
- Límites de intentos: se mantienen estrictos (fuerza bruta); en local se pueden aflojar solo con `DEBUG`.
- Calidad: cada PR pasa dos CI obligatorios con reporte en el PR; auditorías de seguridad, performance del front y carga del backend, publicadas.

## Precisiones acordadas

### Parte 1 (docs, 2026-11-18)
- **P1.1 Las 8 vistas del portal.** REQ §6 las nombra por función y el front las agrupó en otras rutas. Mapeo usado en 01: acceso → `/acceso` + `/portal/consentimientos` + `/portal/datos`; tablero → `/portal`; datos financieros y segundo solicitante → `/portal/ingresos` (una sección por participante); financiación → `/portal/financiacion` + `/portal/inmueble`; documentos → `/portal/documentos`; seguimiento, notificaciones, desistimiento y contacto → `/portal` + `/portal/avisos`. "Mis procesos" no tiene pantalla: la sesión del enlace es de una sola solicitud (decisión 2 de `TAREA-buyer-access.md`); la API `GET /buyer/processes` sí existe.
- **P1.2 Vistas 11 a 14** (usuarios, proyectos, partners, catálogos): no están en `master`; se marcan "en construcción en otra rama" sin leer las carpetas de los otros agentes. La API ya existe.
- **P1.3 Tablas: 57 y no 58.** Contadas por `db_table` en `backend/apps/`. El SQL y el DER dicen 58: la diferencia es `outbox_events`, que no se implementó (señales después del commit). Se anota en 02 §14 y en 03 §3.
- **P1.4 Conteo del contrato** (`contracts/openapi.json`, 18-11-2026): 175 rutas, 235 operaciones (34 del comprador = rutas `/api/v1/buyer/*` más `/api/v1/buyer-access/consume`; 201 internas) y 374 esquemas.
- **P1.5 Diagramas C4 con `flowchart`**, no con `C4Context`: la sintaxis C4 de Mermaid es experimental y el `flowchart` se ve igual de claro en GitHub.
- **P1.6 Verificación de Mermaid:** parser de `mermaid@11.12.1` con `jsdom@26.1.0` en un contenedor `node:22-slim` de un solo uso (valida la sintaxis, no genera imágenes). Las dependencias quedan en el volumen de Docker `docs_mermaid_nm` para las partes siguientes.
- **P1.7 Storybook en GitHub Pages:** el Anexo A lo nombra como la única publicación, pero en `master` ningún workflow publica. La guía dice "publicación prevista".
- **P1.8 README desactualizado:** dice 15 de 16 módulos y comisiones en curso; el código tiene las 16 apps instaladas y comisiones completa (pagos y "mis comisiones", PR #27). La guía usa el código. El README no se toca (Parte 5: una sola línea).
- **P1.9 Sin `.env.example`:** la regla prohíbe leer `.env*`. Los modos locales se documentan desde `backend/config/settings/base.py`, `backend/docker-compose.yml` y `TAREA-local-simple.md`.
- **P1.10 Línea de tiempo del comprador:** la API la expone (`GET /buyer/applications/{id}/activity`, solo filas `BUYER`), pero el front de `master` no la usa. Se dice así en 01 y 02.
- **P1.11 Porqué inferido:** cuando la fuente no escribe el motivo, 02 lo explica con lo que el código hace necesario y lo dice (por ejemplo, la devolución no pasa por `WAITING_DOCUMENTS` porque ese estado está en `EDITABLE_APPLICATION_STATUSES`).
- **P1.12 Personas del recorrido** (Laura, Marta, Juan): ficticias, sin datos reales.
- **P1.13 Enlaces a documentos futuros** (04 a 12 y `docs/adr/`): se dejan puestos y marcados "(en preparación)". El verificador de enlaces los reporta como faltantes hasta que existan; los demás enlaces y todas las anclas resuelven.
