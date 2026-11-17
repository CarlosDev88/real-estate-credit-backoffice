# Tarea: F3 del frontend — radicación en el backoffice (vista 9)

## Objetivo
Que el asesor cierre el flujo completo desde el expediente:
1. pedir y descargar el paquete del expediente;
2. registrar la radicación manual en el banco;
3. registrar las respuestas del banco (recibida, en análisis, devuelta con observaciones, aprobada, rechazada, desembolsada u otra), con evidencia opcional;
4. ver el historial de radicaciones y respuestas.

El backend ya está en `master` (PR #19, `specs/TAREA-radicacion.md` y API §20). **No hay mockup:** se diseña con el lenguaje de `design/README.md` y el estilo del expediente de la F1 (`design/screens/solicitud.html`).

## Cuándo y dónde
- **Agente:** front 2, en el worktree `wt-front-filings`, rama `feat/front-filings`, desde `master`.
- **En paralelo:** el front 1 hace la F2 (portal del comprador) en `wt-front-portal`. Los backends A y B trabajan en los módulos 12 y 13.
- **Solo tocas:**
  - `features/filings/` (nueva);
  - la pestaña nueva del expediente: el registro de la pestaña en `features/applications/workspace-screen.tsx`, como cambio mínimo;
  - `e2e/backoffice/filings*`.
- **Lo compartido** (`components/ui`, `lib/`, `providers/`): evítalo. Si es imprescindible, va en un commit aparte (`refactor(ui)` o `fix(ui)`) y lo anotas: el front 1 lo puede estar usando.

## Cómo corres el entorno
- **Puerto 3001** (el 3000 es del front 1):

  ```
  node ./node_modules/next/dist/bin/next dev --port 3001
  ```

  El backend ya acepta `http://localhost:3001` (CSRF y CORS en `backend/.env`; lo hizo Claude).
- **`pnpm install`** con `node <ruta>/pnpm.mjs`: el atajo global de pnpm está roto en este equipo.
- **El `.env.local`** con el usuario de prueba ya está copiado.
- **Playwright:**
  - `baseURL` y `webServer` en el puerto **3001**, con una variable (`E2E_PORT=3001`), sin cambiar el valor por defecto del front 1 (3000);
  - un archivo de sesión propio (`test-results/.auth/advisor-3001.json`), para no pisar el del front 1.
- **Backend:** el de `:8000`. Lo edita el backend A, así que si ves `socket hang up` o `502`, espera 10 s y reintenta.
- **Datos de demo** (33 solicitudes):
  - `SOL-000031` en `CREDIT_ANALYSIS`;
  - `SOL-000032` en `BANK_OBSERVATION`, con un documento observado;
  - `SOL-000033` en `APPROVED`;
  - las de la pestaña "Listas para radicar", para radicar.
- **Tipos:** `pnpm api:gen` no debería dar diferencias. Después de cada merge de `master`, se vuelve a correr.

## Reglas de trabajo
- Git solo en lectura. Carlos hace todos los commits y push, sin `Co-Authored-By` ni firmas.
- **Comunicación por buzón** (`.buzon/PROTOCOLO.md`): reporte completo, `ESTADO.md` al día y en la consola una línea.
- **No se presentan dudas.** Lo que no esté cubierto lo decides tú con la opción más simple y coherente con la F1, lo anotas en "Precisiones acordadas" y sigues. Solo te detienes si falta un dato de la API (va a "Brechas" y se deja fuera), si cambia el alcance o si exige tocar un `.env`.
- **Reglas de F0 y F1 vigentes:**
  - cero listas o textos de negocio en el código: tipos de respuesta, estados, motivos, canales y etiquetas vienen de la API o de sus catálogos;
  - `toneFor`, `Money` y `lib/format`;
  - errores por el `MutationCache` global;
  - `expected_version` desde el `ETag` del detalle;
  - permisos de `/auth/me`.
- Verificaciones al cerrar cada parte: `lint`, `format:check`, `typecheck`, tests con cobertura ≥ 70 % y `build`.
- Pantallas a 1440, 1280 y 390 px, en claro y oscuro, y `axe` sin violaciones serias.

## Parte 1. Pestaña "Radicación" del expediente, con paquete y radicación
- **Pestaña nueva:** "Radicación", entre Documentos e Historial (`?tab=radicacion`).
  - Solo se ve con el permiso `filings.read`.
  - El conteo de la pestaña es el número de radicaciones.
- **Estado vacío** (sin radicaciones): explica en una línea que la radicación se registra después de entregar el paquete al banco.
- **Paquete del expediente:**
  - "Preparar paquete" (`POST /applications/{id}/document-package-jobs`), con el estado consultado cada 3 s mientras no termine (`GET /document-package-jobs/{id}`), y "Descargar ZIP" cuando esté listo. La URL se pide cada vez y no se guarda.
  - Mostrar los errores de la API: paquete vencido, expediente que cambió, etc.
  - **Botón principal** solo con la solicitud en `READY_TO_FILE` y el permiso `filings.create`.
- **"Registrar radicación"** (modal):
  - producto (el de la financiación, de solo lectura);
  - canal (catálogo `filing_channel`);
  - referencia externa (opcional);
  - fecha y hora de entrega (no futura; por defecto, ahora);
  - comentario (opcional);
  - el paquete que se usa (el último terminado).

  Envía `POST /applications/{id}/filings` con `expected_version`. Las precondiciones que fallan muestran el `message` de la API. Al terminar se invalidan el detalle, las etapas, la completitud, las radicaciones y el historial.
- **Lista de radicaciones:** número (#1, #2), banco y producto, canal, referencia, quién y cuándo, `status_label` con su tono, fecha objetivo de respuesta (si existe y si está vencida) y número de respuestas.
  - **"Corregir referencia o comentario"** (`PATCH /filings/{id}`), con permiso `filings.update`.
  - **"Documentos entregados"** (`GET /filings/{id}/document-snapshots`), plegable, para el administrador y el asesor asignado.

**Pruebas (Vitest + MSW):**
- la pestaña oculta sin permiso;
- el estado vacío;
- el paquete: pedir, esperar, listo y error;
- radicar: éxito, precondición fallida y `STALE_VERSION`;
- la lista;
- la corrección;
- los documentos entregados.

**Commit:** `feat(frontend): add the filing tab with package download and manual filing`

## Parte 2. Respuestas del banco
- **Debajo de cada radicación:** su línea de tiempo de respuestas (`GET /filings/{id}/responses`) con tipo y etiqueta, fecha, referencia y mensaje público. La nota interna, los montos y la evidencia solo se ven si la API los envía, porque depende del rol.
- **"Registrar respuesta"**, solo en la **última** radicación y con permiso `filings.record_response`. Un formulario que **pide solo los campos del tipo elegido**:
  - **Tipo:** catálogo `filing_response_type`.
  - **Campos por tipo:** los obligatorios salen de la tabla de API §20.2 (`RECEIVED`/`IN_ANALYSIS`: fecha; `RETURNED`: motivo, mensaje y observaciones; `APPROVED`: monto, plazo, vigencia y mensaje; `REJECTED`: motivo y mensaje; `DISBURSED`: monto; `OTHER`: nota interna).
    - Esa relación entre tipo y campos es una regla de pantalla, no de negocio: va en **una sola constante** del feature, con prueba.
    - La API sigue validando y sus errores de campo van al campo.
  - **Motivos:** `filing_return_reason` o `filing_rejection_reason`, según el tipo.
  - **Observaciones de una devolución:** se eligen documentos del expediente (slots vigentes con versión, agrupados por participante como en Documentos) y cada uno lleva un motivo (`document_rejection_reason`) y un mensaje al comprador.
  - **Evidencia opcional:** después de crear la respuesta, `POST /filing-responses/{id}/evidence` con `uploadFile` (PDF, JPG o PNG, validación local de tipo y tamaño). "Ver evidencia" pide la URL de descarga cada vez.
  - **Corrección** (`corrects_response_id`): solo para la última respuesta del mismo tipo, cuando la API lo permite. Si la API la rechaza, se muestra su mensaje.
  - Envía `expected_version`. Al terminar se invalida todo el expediente (estado, etapas, documentos, radicaciones e historial).
- **Banner del estado en la pestaña:**
  - en `BANK_OBSERVATION`: "El banco observó N documentos", con enlace a cada uno en la pestaña Documentos;
  - después, "Lista para radicar de nuevo", que es la transición `MARK_READY_TO_REFILE` de `available_actions` (ya la maneja el encabezado de la F1).
  - en `APPROVED`: un recordatorio de la acción "Iniciar legalización" del encabezado.

**Pruebas:**
- el formulario cambia los campos por tipo;
- cada tipo con éxito y con error de campo de la API;
- devolución con dos observaciones;
- evidencia: carga, tipo inválido y ver;
- registrar solo en la última radicación;
- lo que se ve según el rol (con y sin nota interna);
- los banners.

**Commit:** `feat(frontend): record bank responses with observations and evidence`

## Parte 3. E2E, accesibilidad y cierre
- **Playwright** en el puerto 3001, con los datos de demo:
  - preparar el paquete y radicar una solicitud de "Listas para radicar";
  - registrar `RECEIVED` y `IN_ANALYSIS`;
  - en `SOL-000032`, ver la observación;
  - en `SOL-000033`, ver la aprobación.

  `axe` en la pestaña Radicación y en los modales, en claro y oscuro. Si no hay datos, las pruebas se saltan con un mensaje.
- **Capturas** de la pestaña y de los modales en 1440, 1280 y 390 px, en claro y oscuro, en `frontend/test-results/` (no se versionan).
- **`specs/TAREA-frontend-base.md`, "Brechas":** las que deje esta fase.
- **Trae `master` antes de entregar** (Carlos hace el merge) y corre `pnpm api:gen`.
- Entregas el **título y la descripción del PR**, en español, sin firmas.

**Commit:** `test(frontend): add filing end-to-end and accessibility checks`

## Precisiones acordadas

### Parte 1
1. **Tonos de la radicación.** `status-tones` no tenía tipo para la radicación: se agregó `filing` en `design/tokens/tokens.json` (`FILED`, `RECEIVED` e `IN_ANALYSIS` → `info`; `RETURNED` → `warning`; `APPROVED` y `DISBURSED` → `success`; `REJECTED` → `danger`; `OTHER` → `neutral`), que también sirve para los tipos de respuesta de la Parte 2. De paso, `BANK_OBSERVATION` → `warning` en `application` (salía `neutral`). Es compartido: va en un commit aparte.
2. **El paquete vive en la pestaña.** La API no lista los trabajos de paquete de una solicitud (solo `POST` y `GET /{id}`). El id se guarda en el estado del panel; si se cambia de pestaña y se vuelve, "Preparar paquete" devuelve el mismo trabajo vivo (`200`, misma huella). Al radicar, el panel se limpia.
3. **Panel "Entregar al banco"** solo con la solicitud en `READY_TO_FILE`. "Preparar paquete" y "Descargar ZIP" piden `filings.prepare` (el permiso de la API §19.2); "Registrar radicación", `filings.create`. Hay una sola acción principal, y solo con `filings.create`: primero preparar, después descargar y al final registrar. Sin paquete listo, "Registrar radicación" queda deshabilitado y debajo se explica por qué.
4. **Estado del paquete sin etiqueta.** `DocumentPackageJob` no trae `status_label`, así que no se pinta un badge: se muestran frases de interfaz ("Preparando el paquete…", "Paquete listo", "El paquete venció", "No se pudo armar el paquete", con el `error_code` de la API tal cual). Queda en "Brechas".
5. **Descarga.** La URL firmada se pide en cada clic y se abre con un `<a>` temporal (`features/filings/download.ts`); no se guarda en la caché. Si la API responde `PACKAGE_EXPIRED`, se vuelve a leer el trabajo.
6. **Producto del modal:** el `bank_product` del detalle de la solicitud (el mismo que muestra la franja de datos clave).
7. **Fecha de entrega:** `<input type="datetime-local">` en la hora del navegador, con `max` = ahora y una validación local "no futura" (con un minuto de margen). No se agregó `dayjs` como dependencia para el `DatePicker`.
8. **Errores al radicar:** los `details[].field` van a su campo; las precondiciones (`409`/`422`) y `STALE_VERSION` van al toast global con el `message` de la API, y el modal sigue abierto.
9. **"Vencida"** en la fecha objetivo de respuesta: si pasó `target_response_at` y la radicación todavía no tiene respuestas (`responses_count = 0`).
10. **Documentos entregados:** se ven si `me.roles` incluye `ADMIN` o si el usuario es el asesor asignado (`detail.assigned_advisor.id`). Se piden al desplegar y llevan la etiqueta del slot (de `document-slots`); si el slot ya no está, se muestra `document_type_code`.
11. **Corrección:** el `PATCH` siempre envía los dos campos; vacío se manda como `null` (la API lo borra).
12. **Sin `filings.read`**, `?tab=radicacion` muestra el Resumen.
