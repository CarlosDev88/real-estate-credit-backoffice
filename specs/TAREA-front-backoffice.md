# Tarea: F1 del frontend — backoffice (listado y expediente)

## Objetivo
Construir las dos pantallas principales del asesor sobre la base de F0:
- el **listado de solicitudes** (mockup `design/screens/solicitudes.html`);
- el **expediente de una solicitud**, con su revisión documental (mockup `design/screens/solicitud.html`).

En esta fase el asesor **ve** los datos y **actúa**: cambia el estado, reasigna, envía el enlace al comprador, evalúa el banco, revisa, exonera y reabre documentos. **No edita** los datos del comprador: esos formularios llegan en una fase posterior y reutilizan los del portal (F2).

## Cuándo y dónde
- **Agente:** front, en el worktree `wt-front-backoffice`, rama `feat/front-backoffice`, creada desde `master` (ya tiene el PR #16 del listado).
- **Backend en paralelo:**
  - el backend A hace `TAREA-brechas.md`: datos de demo, etiquetas, `progress_stages`, `role_label` y `ETag` en el contrato;
  - el backend B hace la radicación, que **no** entra en F1.
- **Dependencia:**
  - la Parte 1 (listado) solo usa lo que ya está en `master`;
  - las Partes 2 y 3 usan campos de la tarea de brechas. **Antes de la Parte 2**, Carlos trae `master` a tu rama con las brechas fusionadas. Si al terminar la Parte 1 todavía no están, avisa y espera: no inventes campos ni escribas etiquetas en el código.

## Cómo corres el entorno
- **Backend:** `docker compose up -d postgres backend`, desde `real-estate-credit-backoffice\backend` (carpeta principal). **No levantes el contenedor `frontend`:** ocuparía el puerto 3000.
- **Front:** en `wt-front-backoffice\frontend`, `pnpm install` y `pnpm dev` (puerto 3000).
  - El `.env.local` con el usuario de prueba ya está copiado (lo hace Claude).
- **Datos:** cuando el backend A termine su Parte 0, el backend local tendrá unas 30 solicitudes de demo asignadas a `asesor.e2e@example.com`. Mientras tanto trabajas con MSW.
- **Tipos:** `pnpm api:gen` después de cada `merge` de `master`.

## Reglas de trabajo
- Git solo en lectura. Carlos hace todos los commits y push, sin `Co-Authored-By` ni firmas.
- **No se presentan dudas.** Lo que esta spec no cubra lo decides tú con la opción más simple y coherente con el mockup, lo anotas en "Precisiones acordadas" y sigues. Solo te detienes si necesitas un dato que la API no da (lo anotas en "Brechas" y lo dejas fuera, sin simularlo en producción), si cambia el alcance o si exige tocar un `.env`.
- Cada parte se hace de corrido. Al cerrarla entregas: verificaciones en verde (`lint`, `format:check`, `typecheck`, tests con cobertura ≥ 70 % y `build`), la lista de decisiones que tomaste y el mensaje de commit. Esperas el "listo" de Carlos.
- **Reglas de F0 que siguen vigentes:**
  - cero listas o textos de negocio en el código: estados, catálogos, etiquetas y acciones vienen de la API;
  - colores por `toneFor`;
  - montos con `Money`;
  - fechas con `lib/format` y `RelativeTime`;
  - errores por el `MutationCache` global;
  - versión por `ETag`/`If-Match` y `expected_version`;
  - permisos de `/auth/me`, nunca el nombre del rol.
- Solo tocas tu grupo de rutas, `features/applications` y `features/document-review`, más `e2e/backoffice`.
  - Si necesitas cambiar algo compartido (`components/ui`, `lib/` o `providers/`), hazlo en un commit aparte con el prefijo `refactor(ui)` o `fix(ui)` y anótalo: la F2 lo va a usar.
- Pantallas iguales al mockup en 1440, 1280 y 390 px, en claro y oscuro, sin violaciones serias de `axe`.

## Parte 1. Listado de solicitudes (`/solicitudes`)

### Datos
- **Filas:** `GET /applications`, con todo el estado en la URL: `quick_filter`, `search`, `bank_id`, `product_type`, `purpose`, `ordering`, `page` y `page_size`.
- **Pestañas:** `GET /applications/quick-filters`, con los mismos filtros (sin `quick_filter`). Muestran `label` y `count` en el orden de la API. Por defecto, `all`.
- **Opciones de los filtros:**
  - **Banco:** `GET /banks` (activos). En el chip se ve el `short_name`, o el `name` si viene vacío.
  - **Tipo de crédito:** catálogo `bank_product_type`.
  - **Finalidad:** catálogo `loan_purpose`, de `/metadata/bootstrap` o `/metadata/catalogs/{code}`.

### Lo que se ve
- **Encabezado:** título "Solicitudes" y el subtítulo del mockup.
- **Se quitan** "Nueva solicitud", "Exportar CSV", la selección masiva ("Reasignar asesor" y "Exportar selección"), "Más filtros" y la opción "Sin banco elegido": no tienen API. Se anotan en "Brechas".
- **Búsqueda:** campo con espera de 300 ms; va a `search`.
- **Filtros:** los tres del mockup, más los chips de filtros activos (`FilterChips`) y "Limpiar". En móvil (≤ 860 px), un panel "Filtros" con "Ver resultados".
- **Columnas** (tabla con TanStack Table en modo manual):

  | Columna | Dato |
  | --- | --- |
  | Código | `code`, con enlace a `/solicitudes/{id}` |
  | Titular | Nombre del titular. Debajo, en pequeño, los participantes adicionales desde `participants_summary` (por ejemplo, "+ 1 co-solicitante"). |
  | Estado | `StatusBadge` con `status_label`. Si `buyer_inactive` es `true`, un ícono de aviso con un tooltip armado con `last_buyer_activity_at`: "Sin actividad del comprador desde …" o "El comprador aún no entra". |
  | Monto | `Money` con `requested_amount_cop`, o "—". |
  | Expediente | `CompletenessBar` con `completeness_pct`, o "—" si es nulo. Si `ready_to_file_blocked` es `true`, un ícono de aviso con el tooltip "Ya no cumple para radicar". |
  | Banco | `short_name`, o `name`, o "Sin banco". |
  | Tipo de crédito | `bank_product.product_type.label`, o "—". |
  | Actualizada | `RelativeTime` con `updated_at`. |

- **Orden:** al hacer clic en el encabezado de una columna ordenable (`code`, `requested_amount`, `bank_name`, `applicant_name` y `updated_at`), se alterna entre ascendente y descendente. Por defecto, `-updated_at`. El encabezado lleva `aria-sort`.
- **Paginación:** "Mostrando 1–20 de 48", con tamaños de página 10, 20 (por defecto) y 50.
- **Móvil (≤ 860 px):** tarjetas con código, titular, estado, monto, barra de expediente y fecha.
- **Estados:**
  - cargando, con esqueleto;
  - vacío, con `EmptyState` y el texto del mockup;
  - error en línea, con "Reintentar".
- **Navegación:** al hacer clic en la fila (o con Enter sobre ella) se abre el expediente. El enlace del código sigue siendo un enlace real.

### Pruebas
Integración con MSW:
- pestañas con sus conteos;
- cada filtro va a la URL y vuelve desde la URL;
- búsqueda;
- orden;
- paginación;
- vacío y error;
- avisos de inactividad y de "ya no cumple";
- tarjetas en móvil;
- "Sin banco" y "—".

**Commit:** `feat(frontend): add the applications list with tabs, filters, sorting and pagination`

## Parte 2. Expediente: resumen, historial y acciones (`/solicitudes/[id]`)

### Datos
- `GET /applications/{id}`: guarda `version` desde el `ETag`.
- `GET /applications/{id}/completeness`, `GET /applications/{id}/participants` y el perfil financiero de cada participante.
- `GET /applications/{id}/property`, `GET /applications/{id}/financing` y `GET /applications/{id}/bank-rule-evaluations/latest`.
- `GET /applications/{id}/buyer-access-links`, `GET /applications/{id}/consents` y `GET /applications/{id}/status-history`.
- Un `404` muestra "No encontramos esta solicitud o no tienes acceso", con enlace al listado.

### Encabezado
- Migas "Comercial / Solicitudes / <código>" y "Volver a solicitudes".
- Código, `StatusBadge`, y el subtítulo armado con los nombres de los participantes (con `role_label` para los adicionales), la finalidad y el proyecto.
- **Acciones:**
  - **Transiciones de `available_actions`:** la primera es el botón principal y las demás van en un menú "Más acciones". Cada una abre un modal de confirmación con:
    - motivo, si la transición lo exige (catálogo `application_transition_reason`; revisa en API §16.3 cuándo se exige y anótalo);
    - comentario opcional;
    - envío de `POST /status-transitions` con `expected_version`.

    Al terminar se invalidan el detalle, la completitud y el historial.
  - **Razón de bloqueo:** si "Marcar lista para radicar" no está disponible o su guarda falla, va un texto debajo con los `ready_to_file_problems` de `/completeness`, como en el mockup.
  - **"Enviar enlace al comprador"** (con permiso de crear enlaces): modal con el canal de envío y la vigencia (los valores que acepte la API), y después muestra la URL con un botón "Copiar". Avisa que el enlace anterior queda revocado.
  - **"Evaluar reglas del banco":** `POST /bank-rule-evaluations` y refresca la tarjeta de evaluación.
  - **"Reasignar asesor":** solo si hay permiso `applications.assign` y el usuario puede listar usuarios (`GET /users` con rol asesor). Si no, no aparece. Modal con el asesor y el motivo.
  - **"Registrar desistimiento":** con permiso `applications.withdraw`; modal con el motivo (catálogo `application_withdrawal_reason`) y un comentario.
- **Franja de datos clave:**
  - monto solicitado;
  - valor del inmueble;
  - financiación (% = monto / valor, con un decimal, o "—");
  - banco y tipo de crédito;
  - plazo en meses;
  - origen (etiqueta y nombre del broker, si viene).
- **Etapas:** `progress_stages` (de la tarea de brechas) como un stepper horizontal, que en móvil pasa a vertical o se desplaza.

### Pestañas (`ScrollTabs`): Resumen, Documentos (con el número de pendientes) e Historial
La pestaña activa va en la URL (`?tab=`).

**Resumen:**
- **Completitud:** total, datos y documentos ("10 de 16 · 62 %"), más la lista de lo que falta, con los mensajes de la API.
- **Por revisar:** hasta 3 slots en estado de revisión (los que la API marque como cargados y pendientes de decisión), con "Revisar" (abre el panel de la Parte 3) y "Ver todos los documentos" (va a la pestaña Documentos).
- **Evaluación del banco:** elegible o no, vigente o vencida, y la lista de reglas que bloquean y de avisos, con sus textos.
- **Participantes:** nombre, `role_label`, perfil laboral, si el perfil está confirmado e ingreso mensual. Abajo, el ingreso y los gastos del hogar (sumas en el front). **No va el botón "Agregar"** (la edición queda para después).
- **Inmueble:** proyecto, unidad, ciudad, condición y valor.
- **Acceso del comprador:** estado del último enlace, sesión y vencimiento, y consentimientos aceptados de los requeridos.
- **"Actividad reciente"** se reemplaza por **"Últimos cambios de estado"**: los 3 primeros de `status-history`, con "Ver historial". El registro de actividad completo llega con el módulo de auditoría (se anota en "Brechas").

**Historial:**
- La lista paginada de `status-history`: "Pasó de <estado> a <estado>", actor (o "portal del comprador"), versión, motivo, comentario y fecha.

### Pruebas
- Render con MSW de cada tarjeta, incluidos los casos vacíos y nulos.
- Transición con motivo y sin motivo; `409 STALE_VERSION` (aviso global con "Recargar").
- Enlace del comprador: muestra la URL y copia.
- Reasignar oculto sin permiso.
- Desistimiento.
- `404`.
- Pestaña en la URL.

**Commit:** `feat(frontend): add the application workspace with summary, history and status actions`

## Parte 3. Documentos y revisión

### Pestaña Documentos
- `GET /applications/{id}/document-slots`, agrupados por participante (encabezado: nombre, `role_label` y perfil laboral). Los slots de la solicitud van aparte, con el título "Solicitud · Inmueble y trámite".
- Las versiones retiradas (`is_retired`) no se muestran.
- **Cada fila:**
  - etiqueta del slot ("Desprendible de nómina 2 de 3");
  - archivo vigente, con nombre, tamaño y regla de vigencia, si existe;
  - `StatusBadge` con la etiqueta de estado del slot;
  - el mensaje al comprador, si fue rechazado.
- **Acciones por fila,** según el estado y los permisos (revisa en API §19.1 qué decisiones admite cada estado y anótalo):
  - "Ver" abre el visor;
  - "Revisar" abre el panel;
  - "Exonerar" (si `is_waivable`) pide el motivo (catálogo `document_waiver_reason`) y una nota;
  - "Reabrir" para un aprobado o exonerado.
- **Errores en línea:**
  - análisis antivirus pendiente: "Analizando el archivo…";
  - archivo infectado: "El archivo no pasó el análisis de seguridad".
  - Descarga no disponible (`409` o `503`): mensaje en línea, sin romper la pantalla.

### Panel de revisión (drawer a la derecha; pantalla completa en móvil)
- **Encabezado:** participante y documento.
- **Datos del archivo:**
  - nombre, tamaño y fecha de carga (con "por el comprador" o el usuario);
  - análisis antivirus (`GET /document-files/{id}/scan-status`);
  - fecha del documento y vigencia, cuando aplica.
- "Abrir en el visor" abre el `DocumentViewer`. La URL sale de `GET /document-files/{id}/download` y no se guarda en la caché ni en el estado persistente: se pide cada vez.
- **Decisión:**
  - **Aprobar** o **Rechazar** con `PATCH /document-slots/{id}/review`, enviando `document_file_id` de la versión vigente.
  - Rechazar exige el motivo (catálogo `document_rejection_reason`) y el mensaje al comprador. La nota interna es opcional, y el texto aclara que el comprador no la ve.
  - Si el tipo documental exige fecha del documento, se pide `document_date`.
- **Al terminar:** se invalidan los slots, la completitud y el detalle, sale un toast de éxito y el panel pasa al siguiente documento por revisar, si lo hay ("Siguiente").
- **Versiones anteriores:** `GET /document-slots/{id}/versions` en una lista plegable, cada una con "Ver".

### Pruebas
- Agrupación por participante.
- Aprobar y rechazar (motivo y mensaje obligatorios).
- Exonerar.
- Reabrir.
- Antivirus pendiente.
- Visor que pide la URL.
- "Siguiente".
- Errores `409` y `503` en la descarga.
- Teclado: el drawer atrapa el foco y Escape lo cierra.

**Commit:** `feat(frontend): add document review with the viewer, waivers and reopen`

## Parte 4. E2E, accesibilidad y cierre
- **Playwright** contra el backend local, con los datos de demo:
  - login del asesor;
  - listado con pestañas y un filtro;
  - abrir una solicitud en revisión;
  - aprobar un documento;
  - rechazar otro con su motivo.

  `axe` en el listado y en el expediente, en claro y oscuro, sin violaciones serias ni críticas. Si la base no tiene datos de demo, la prueba se salta con un mensaje claro: no falla.
- **Capturas** en 1440, 1280 y 390 px, en claro y oscuro, del listado, el expediente y el panel de revisión, en `frontend/test-results/` (no se commitean). En el reporte dices qué difiere del mockup y por qué.
- **`specs/TAREA-frontend-base.md`, sección "Brechas":** agregas las que dejó esta fase (botones quitados y actividad completa).
- Trae `master` antes de entregar (Carlos hace el merge) y corre `pnpm api:gen`.
- Entregas el **título y la descripción del PR**, en español, sin firmas.

**Commit:** `test(frontend): add backoffice end-to-end and accessibility checks`

## Precisiones acordadas
_(las agrega el agente)_

### Parte 1 (listado)

**Entorno:**
- En Windows, el shim global de pnpm (11.1.1) no logra cambiar a la 12.18.0 que fija `packageManager`. Se corre con `node <store>/pnpm/12.18.0/…/node_modules/pnpm/bin/pnpm.mjs`. No cambia nada del repo.
- `@tanstack/react-table` 9.3.1 (la versión aprobada en F0) no estaba instalada: se agrega a `package.json`.
- Sin datos de demo ni acceso a las credenciales desde la terminal, la parte se verificó con MSW. La revisión visual contra el backend queda para la Parte 4.

**Datos y URL:**
- En la URL solo van los valores distintos del por defecto (`quick_filter=all`, `ordering=-updated_at`, `page=1` y `page_size=20` no se escriben). Un `ordering` fuera de las cinco columnas ordenables, o un `page_size` distinto de 10, 20 o 50, se ignora.
- Cambiar la pestaña, la búsqueda, un filtro, el orden o el tamaño vuelve a la página 1. Si la página ya no existe (`404` de la API), se vuelve a la 1.
- Mientras llega otra página o filtro, se ve la anterior atenuada (`keepPreviousData`); el esqueleto sale solo en la primera carga.
- La búsqueda se recorta (`trim`) antes de ir a la URL. Sale una sola petición por búsqueda, a los 300 ms de la última tecla.
- El filtro de banco aparece solo con el permiso `banks.read` de `/auth/me`. Pide `GET /banks?status=ACTIVE&ordering=name&page_size=100` (el máximo de la API).
- Los catálogos (`bank_product_type` y `loan_purpose`) salen de `/metadata/bootstrap`: solo los valores activos, por `order`. El bootstrap se cachea 10 min y el navegador revalida con `If-None-Match`.
- Si el valor de un filtro de la URL todavía no está entre las opciones (cargando o inactivo), el control y el chip muestran "…" en lugar del id.
- Un error de las pestañas se ve aparte ("No pudimos cargar las pestañas", con "Reintentar"), sin tapar el listado.

**Lo que se ve:**
- **Chips:** solo en móvil (≤ 860 px), donde los filtros quedan detrás de "Filtros (n)". En escritorio los tres selects están a la vista y, por la regla del design system ("los filtros visibles no se repiten como chips"), no se repiten. "Limpiar" está en los dos: en escritorio, como botón de texto en la barra (si hay algo activo); en móvil, en los chips y en la hoja.
- "Limpiar" (y "Limpiar filtros" del estado vacío) quita la búsqueda y los tres filtros; la pestaña se conserva. "Limpiar filtros" solo aparece si hay algo que limpiar.
- El control del filtro muestra "Banco: FNA" (y "Banco: todos" sin filtro); la lista de opciones, solo el valor. En la hoja de móvil, los selects son de 40 px y ocupan el ancho.
- Se quitan también el filtro de asesor (la spec pide los tres del mockup) y el botón "⋯" de cada fila (no hay acciones por fila en F1).
- **Titular:** si no hay participantes adicionales no va nada debajo (el mockup dice "Titular"). Con varios, "+ 1 co-solicitante · + 2 deudores solidarios". `participants_summary` solo trae conteos, así que el texto del rol lo arma el front; con `role_label` de la tarea de brechas se podrá cambiar en el detalle, pero el listado sigue sin etiquetas (ver "Brechas").
- **Tipo de crédito:** debajo, en pequeño, la finalidad (`purpose.label`), como en el mockup.
- **Banco:** con `title` del nombre completo, truncado a 150 px.
- **Avisos:** el texto de inactividad usa la fecha absoluta ("Sin actividad del comprador desde 8 nov 2026"). Los íconos llevan tooltip y el mismo texto oculto para lectores de pantalla; no son foco de teclado.
- **Orden:** la primera vez que se ordena una columna es descendente; después alterna. La columna "Código" queda fija a la izquierda al desplazar la tabla.
- **Fila:** `tabIndex=0`; clic o Enter abren `/solicitudes/{id}` con `router.push`. Los clics en enlaces y botones no cuentan. En las tarjetas, clic en la tarjeta o en el código.
- **Paginación:** `Pagination` de Ant Design (en móvil, `simple`). Con una sola página no se ven los botones. Sin resultados no hay pie: lo reemplaza el `EmptyState`.
- **Tarjetas** (≤ 860 px, el mismo corte del shell; el mockup pasa a tarjetas en 720): código y estado, titular con participantes, y monto, barra de expediente y fecha.
- El modo (tabla o tarjetas) se decide con `useMediaQuery`: en el servidor siempre es escritorio. Como los datos llegan en el cliente, en móvil solo se ve el esqueleto antes de pasar a tarjetas.

**Pruebas:**
- El router de Next se reemplaza por uno que escribe en la URL de jsdom (`history.replaceState`) y avisa a `useSearchParams`.
- Las pruebas del listado tienen 20 s de tiempo máximo: con los selects de Ant Design, bajo carga, pasan de los 5 s por defecto.

**Brechas (se pasan a `TAREA-frontend-base.md` en la Parte 4):**
- Quitados del listado por no tener API: "Nueva solicitud", "Exportar CSV", la selección masiva ("Reasignar asesor" y "Exportar selección"), "Más filtros" y "Sin banco elegido" en el filtro de banco.
- `participants_summary` trae solo conteos: el texto "co-solicitante" / "deudor solidario" está en el front. Si se quiere sacar, el resumen debería traer la etiqueta de cada rol.

### Parte 2 (expediente: resumen, historial y acciones)

**Orden de trabajo (pedido de Carlos):** se construyó todo lo que ya está en el contrato. Lo que depende de la tarea de brechas (el stepper con `progress_stages` y los `role_label`) queda para el cierre de la parte, después de traer `master` con las brechas.

**Cambio compartido** (commit aparte, `refactor(ui)`):
- `useShellTrail(label)` en `components/ui/app-shell.tsx`: una página agrega su última miga a la barra superior ("Comercial / Solicitudes / SOL-000182") y la entrada del menú pasa a ser un enlace. Se quita al desmontar.
- `formatPercentDecimal` en `lib/format`: "70,2 %", para la financiación sobre el valor del inmueble.

**Datos:**
- La versión sale del `ETag` del detalle (si no llega, `version` del cuerpo) y va en `expected_version` de transiciones y desistimientos.
- Todo el expediente cuelga de la clave `["application", id]`. Después de una transición, un desistimiento o una reasignación se invalida esa clave completa (detalle, completitud, historial y el resto) y también el listado.
- Inmueble, financiación y evaluación pueden no existir: su `404` se trata como "todavía no hay", no como error.
- El perfil financiero se pide solo para los participantes con `financial_profile_id`.
- "Por revisar" sale de `GET /document-slots?status=UPLOADED&page_size=3`: los 3 primeros y el `total`.
- El número de la pestaña Documentos es `required_total - completed_total` de `/completeness` (mockup: "6 pendientes" = 10 de 16).
- Las etiquetas de estado del historial salen del catálogo `application_status` del bootstrap (activos e inactivos). El estado actual usa su `status_label` como respaldo.
- Los asesores para reasignar salen de `GET /users?role=ADVISOR&status=ACTIVE&ordering=first_name&page_size=100`. El asesor actual no aparece en la lista.

**Acciones:**
- **Motivo de la transición (API §16.3):** es obligatorio al pasar a `CANCELLED`, `OWN_FUNDS` y `EXTERNAL_CREDIT_APPROVED`. El front no guarda esa lista: el modal siempre ofrece el motivo, marcado "(si el cambio lo exige)". Si falta, el `400` de la API cae en el campo (`details[].field = "reason_code"`). Ver "Brechas".
- Las acciones con `target_status = WITHDRAWN` no son transiciones: habilitan "Registrar desistimiento" (con el permiso `applications.withdraw`), que va por `/withdrawals`.
- **"Lista para radicar":** la acción con `guard_code = APPLICATION_READY_TO_FILE` queda deshabilitada si `completeness.ready_to_file` es falso, con `aria-describedby` a la razón. Si además hay documentos por revisar, la principal pasa a ser "Revisar N documentos" y la transición que sería principal va al menú.
- **Razón de bloqueo:** se ve si hay alguna transición disponible y `ready_to_file` es falso: los 3 primeros `ready_to_file_problems` y "Y N motivos más". La lista completa está en la tarjeta de completitud.
- **Menú "Más acciones"** (botón de ícono con ese nombre): primero las transiciones; después "Evaluar reglas del banco" (con `applications.update`, si hay producto y la solicitud no está cerrada), "Reasignar asesor" (con `applications.assign` y `users.read`, si no está cerrada) y, separado y en rojo, "Registrar desistimiento".
- "Enviar enlace al comprador" se ve con `buyer_access.create` y si la solicitud no está cerrada (`closed_at`).
- **Enlace del comprador:** el canal sale del catálogo `buyer_access_channel` y por defecto se elige el primero. La vigencia va en horas, de 1 a 168, y por defecto 72 (API §8). La URL se muestra una sola vez, en un campo de solo lectura con "Copiar". Si el portapapeles falla, sale un toast pidiendo copiarla a mano.
- **Reasignación:** si la API responde `204` (quien reasigna pierde el acceso), se vuelve al listado.
- "Evaluar reglas del banco" usa el manejo global de errores (por ejemplo, `422 BANK_PRODUCT_REQUIRED`). Al terminar, pone la evaluación nueva en la caché y refresca la completitud.
- **Errores de los modales:** los `details[].field` van a su campo y el resto al mismo toast global (incluido `409 STALE_VERSION` con "Recargar"). `comment` y `reason` se envían siempre, vacíos si no hay texto, porque el contrato los tipa como obligatorios (tienen `default: ""`). `reason_code` y `delivery_channel` no se envían si no hay valor.
- Los campos usan `FormField` (en `features/applications`): etiqueta, error y ayuda enlazados con `aria-describedby`.

**Resumen:**
- Las tarjetas van en una sola columna, como en el mockup: Completitud, Por revisar, Evaluación del banco, Participantes, Inmueble, Acceso del comprador y Últimos cambios de estado. Cada una muestra su propio esqueleto, y su error en línea con "Reintentar".
- **Completitud:** `CompletenessBar` y la lista de `items` con su mensaje (cumplido o pendiente, con el estado también en texto oculto), más `documents.message`.
- **Por revisar:** en esta parte, "Revisar" lleva a `?tab=documentos&slot=<id>`; la Parte 3 abre el panel desde ese parámetro. "Revisar N documentos" del encabezado lleva al primero.
- **Evaluación:** "Elegible" / "No elegible" con tono `success` / `danger`, "Evaluada hace … · vigente para la versión actual" o "· vencida: la solicitud cambió después", y las reglas en dos grupos ("Bloquean" y "Avisos (no bloquean)") con el `message` de la API. Sin reglas: "Cumple todas las reglas del producto".
- **Participantes:** perfil laboral (`employment_profile.label`), "Perfil confirmado" o "Perfil sin confirmar" (`data_confirmed_at`) e ingreso mensual. Sin perfil: "Sin perfil financiero". Abajo, "Ingreso del hogar" (suma de `monthly_income_cop`) y "Gastos del hogar" (suma de `monthly_expenses_cop`). Las deudas (`liabilities_cop`) son un saldo y no un gasto mensual, así que no se suman.
- **Inmueble:** la condición va con el tipo ("Nueva · Apartamento"). La ciudad muestra solo la etiqueta del municipio.
- **Acceso del comprador:** se ve si hay permiso `buyer_access.read` o `consents.read`. Muestra la fecha de envío del último enlace y, según las fechas, "Usado", "Revocado" o "Vence"; la sesión ("Activa hasta …" o "Sin sesión activa"); los consentimientos vigentes (el registro más reciente de cada definición es una aceptación) y la última actividad (`last_buyer_activity_at`).
- **Últimos cambios de estado:** los 3 primeros de la página 1 del historial (la misma consulta de la pestaña).
- **Historial:** "Pasó de <estado> a <estado>" (el registro de creación: "Se creó en <estado>"), seguido de fecha y hora, actor (o "portal del comprador" si viene `buyer_session_id`), versión, "Motivo: …" y el comentario citado. El punto lleva el tono del estado destino. Se pagina de a 20, con la página en el estado del componente (no en la URL).
- **Pestañas:** `?tab=documentos` o `?tab=historial`; "resumen" no se escribe. Cada panel es un `role="tabpanel"` con nombre.
- **Documentos:** en esta parte, un `EmptyState` provisional; la pestaña llega en la Parte 3.
- Un error distinto de `404` en el detalle se ve en línea: "No pudimos cargar la solicitud", con "Reintentar".

**Pruebas:**
- Se renderiza con el `QueryProvider` real, para probar el toast global de `STALE_VERSION`.
- En jsdom, el ícono de carga de los botones de Ant Design no termina su animación de salida, así que el nombre accesible queda "loading …". Por eso una prueba busca el botón con una regex.
- `userEvent.setup()` instala su propio portapapeles: se espía después de llamarlo.

**Brechas de esta parte (se pasan a `TAREA-frontend-base.md` en la Parte 4):**
- `AvailableAction` no dice si la transición exige motivo. El front lo resuelve con el error de la API. Un `reason_required` (o la lista de motivos válidos) en cada acción evitaría el intento fallido.
- `BuyerAccessLink.status` no trae etiqueta (`status_label`): la tarjeta muestra las fechas en lugar del estado del enlace. No está en la lista de 3.2 de la tarea de brechas.
- No hay endpoint interno con los consentimientos requeridos (vigentes) de la solicitud: se ven los aceptados, sin el "de N".
- El detalle no trae el nombre del broker que originó la oportunidad: en "Origen" va solo la etiqueta.
- "Actividad reciente" del mockup se reemplazó por "Últimos cambios de estado": el registro de actividad completo llega con el módulo de auditoría.
- Botón "Agregar" de participantes: queda fuera (la edición llega con F2).

### Parte 3 (documentos y revisión)

**Orden de trabajo (pedido de Carlos):** se hizo con lo que ya está en el contrato, sin esperar las brechas. Lo pendiente de las Partes 2 y 3 (stepper, `role_label` y etiquetas nuevas) se cierra en un solo commit cuando se fusione la tarea de brechas.

**Datos:**
- Slots: `GET /applications/{id}/document-slots?page_size=100`. Los retirados (`is_retired`) se filtran también en el front.
- **Etiqueta del estado del slot:** sale del catálogo `document_status` del bootstrap (Pendiente, Cargado, Aprobado, Rechazado, Exonerado). Cuando el slot traiga `status_label` (brechas 3.2), se usa ese. El color sale de `toneFor("documentSlot", status)`.
- **Tamaño, tipo y mensaje del rechazo:** la lista de slots no los trae. Se pide `GET /document-files/{id}` de la versión vigente de cada slot (en paralelo, con caché de 1 min). El mensaje al comprador es el `buyer_comment` de la revisión más reciente, si es un rechazo. Ver "Brechas".
- **Análisis antivirus:** en la fila, `current_file.scan_status`. En el panel, `GET /document-files/{id}/scan-status`, que se vuelve a consultar cada 3 s mientras está `PENDING`.
- **Descarga:** `GET /document-files/{id}/download` cada vez que se abre el visor, como mutación (no pasa por la caché de consultas). La URL vive solo mientras el visor está abierto. El pie del visor dice cuándo vence el enlace. Si es imagen (`detected_mime_type` `image/*`), se muestra directo; si no, va por PDF.js.
- Después de cualquier decisión se invalida todo el expediente (`["application", id]`: slots, completitud, detalle, "Por revisar"), los archivos, las versiones y el listado.

**Acciones por estado (API §19.1):**
- **Revisar** (aprobar o rechazar, con `documents.review`): sobre la versión vigente con análisis `CLEAN`, en `UPLOADED`, y también en `APPROVED` y `REJECTED`, porque "corregir es decidir otra vez". En un exonerado, no.
- **Exonerar** (`documents.waive`): si `is_waivable` y el slot no está aprobado ni exonerado.
- **Reabrir** (`documents.waive`): solo un exonerado. `REOPENED` deshace la exoneración y exige `internal_comment`. Un aprobado no se "reabre": se corrige con "Revisar" (la spec decía "Reabrir para un aprobado o exonerado"; la API solo reabre exoneraciones).
- **Ver** (`documents.download`): con análisis `CLEAN`.
- Con el análisis `PENDING`, la fila dice "Analizando el archivo…" y no ofrece ni Ver ni Revisar. Con `INFECTED` o `INVALID`, "El archivo no pasó el análisis de seguridad".
- Un error de descarga (`409`, `503` u otro) muestra el `message` de la API en línea: en la fila, en el panel o en la versión anterior que se intentó ver.

**Pestaña Documentos:**
- **Grupos:** uno por participante, en el orden de `/participants`, con la inicial, el nombre y el perfil laboral del perfil financiero. Al final, "Solicitud · Inmueble y trámite", como en el mockup (la API los da primero).
- **Cada fila:** etiqueta del slot; archivo, tamaño y regla de vigencia ("vigencia de 30 días · vence 2 dic 2026"); sin archivo, "Sin archivo" o "Exonerado: <motivo>"; `StatusBadge`; el mensaje al comprador si fue rechazado; los avisos del análisis y los errores de descarga.
- Los botones de la fila llevan el nombre del documento en texto oculto ("Revisar Certificado laboral").

**Panel de revisión:**
- Se abre con `?tab=documentos&slot=<id>` (desde la fila, "Por revisar" o "Revisar N documentos"). Cerrarlo quita `slot` de la URL.
- `Drawer` de Ant Design a la derecha (520 px), con pantalla completa en ≤ 860 px. Su nombre accesible es el título (participante y documento).
- **Foco:** al abrir y al pasar a otro documento, el foco va al título (`h2` con `tabIndex=-1`), sin depender de que termine la animación. El bloqueo de foco y Escape son los del `Drawer`.
- **Datos:** archivo, tamaño, "Cargado hace … · por el comprador" (si `uploaded_by_buyer_session_id`), análisis, fecha del documento y vigencia.
- **Decisión:** radios "Aprobar" / "Rechazar". El botón del pie dice "Aprobar documento", o "Rechazar documento" en rojo.
  - **Fecha del documento:** se pide si el slot tiene `validity_days` (la API exige `document_date` en ese caso). Viene con la del comprador, no puede ser futura y se envía al aprobar.
  - **Rechazo:** exige el motivo (`document_rejection_reason`) y el mensaje al comprador. La nota interna es opcional y su etiqueta dice que el comprador no la ve.
  - **Al terminar:** toast ("…: aprobado", o "…: rechazado" en advertencia) y el panel pasa al siguiente por revisar, en el orden de la pantalla y después del actual (`UPLOADED` con análisis limpio). Si no hay, se cierra. "Siguiente" pasa sin decidir.
- **Versiones anteriores:** un `Collapse` que, al abrirse, pide `/versions`. Muestra las que no son la vigente, con número, archivo, fecha, el último mensaje al comprador y "Ver".
- **Exonerar y Reabrir:** modales con `FormField`. Al exonerar, el motivo es obligatorio (`document_waiver_reason`) y la nota interna opcional; al reabrir, la nota interna es obligatoria.
- `useFormErrorHandler` pasó a `features/applications/form-field.tsx`, para compartirlo entre los dos módulos.

**Pruebas:**
- La pestaña se prueba dentro del expediente real (`WorkspaceScreen` con `?tab=documentos`), con el slot en la URL.
- **Bloqueo de foco:** el de Ant Design solo cuenta como enfocables los elementos visibles (`offsetParent`), que jsdom no calcula. La prueba lo simula. Al pasar el último control, jsdom deja el foco un momento en `body` y el bloqueo lo devuelve. La prueba verifica que nunca cae en un control de afuera.
- Los radios de Ant Design no reciben el puntero en su `input`: se hace clic en la etiqueta.

**Brechas de esta parte (se pasan a `TAREA-frontend-base.md` en la Parte 4):**
- **Pendiente de la tarea de brechas:** `status_label` del slot y de la versión (hoy sale del catálogo `document_status`) y `role_label` del participante del slot (encabezados de grupo y del panel).
- La lista de slots no trae el tamaño ni el tipo del archivo vigente, ni el último mensaje del rechazo: se pide un `GET /document-files/{id}` por cada archivo vigente. Con 16 slots son 16 peticiones. `CurrentFile` debería traer `size_bytes`, `detected_mime_type` y el `buyer_comment` vigente.
- `scan_status` no trae etiqueta: el panel usa los textos de la spec ("Analizando el archivo…", "El archivo no pasó el análisis de seguridad") y "Sin amenazas" para un archivo limpio. Debería venir `scan_status_label`.
- No hay un "deshacer" de una aprobación: se corrige rechazando (o aprobando) otra vez la versión vigente.
- `DocumentFile` no dice qué usuario interno cargó un archivo (solo `uploaded_by_buyer_session_id`): "por el comprador" sale cuando ese campo viene; si no, no se dice quién.

### Parte 4 (E2E y accesibilidad, primera mitad)

**Orden de trabajo (pedido de Carlos):** primero los E2E y `axe`, que no dependen de las brechas. Las capturas, las brechas en `TAREA-frontend-base.md`, el `merge` de `master` y el PR quedan para cuando `master` traiga las brechas.

**Instalación:**
- `@playwright/test` 1.65.0 y `@axe-core/playwright` 4.14.0 (las versiones aprobadas en F0), como dependencias de desarrollo.
- Solo Chromium (`playwright install chromium`).
- Script `pnpm e2e` (`playwright test`).

**Configuración** (`frontend/playwright.config.ts`):
- Pruebas en `e2e/`: `auth.setup.ts` y `e2e/backoffice/`. La salida va a `test-results/e2e/` y el informe a `playwright-report/`; las dos carpetas ya estaban en `.gitignore`.
- **Usuario de prueba:** se lee de `.env.local` con `process.loadEnvFile` (Node 24), sin dependencias. Las variables que ya existen en el entorno tienen prioridad.
- **Servidor:** `webServer` reutiliza el `pnpm dev` de :3000 si ya corre (`reuseExistingServer`). Si no, lo levanta con `node ./node_modules/next/dist/bin/next dev`: en este equipo el shim global de pnpm no funciona.
- **Ejecución:** un solo worker y sin paralelo, porque las pruebas cambian los datos de demo. Viewport de 1440 × 900, `es-CO`, `America/Bogota`, y traza y captura solo cuando una prueba falla.

**Sesión y saltos:**
- El proyecto `setup` hace el login por la pantalla real y guarda la sesión en `test-results/.auth/advisor.json`. Al empezar borra la de una corrida anterior.
- **Sin usuario:** el setup se salta ("Falta el usuario de prueba…") y las pruebas del backoffice también ("Sin sesión del asesor…"). Se revisa al correr, con un fixture que reemplaza `storageState`.
- **Sin datos de demo** (la pestaña "Todas" en 0): las pruebas se saltan con el comando para sembrar la demo.
- **Sin documentos para revisar:** si ninguna solicitud en revisión tiene dos documentos cargados por revisar, la prueba de aprobar y rechazar se salta con un mensaje claro. Cada corrida aprueba uno y rechaza otro, así que la demo se va gastando.

**Pruebas** (`e2e/backoffice/backoffice.spec.ts`):
- **Listado:** la pestaña "En revisión" va a la URL. El filtro por tipo de crédito usa la primera opción del catálogo. Se recarga y se conservan los dos; "Limpiar" quita el filtro.
- **Expediente:** se abre la primera solicitud en revisión con un clic en la fila. Se ven el código, la miga en la barra superior, la pestaña Resumen y la completitud.
- **Aprobar y rechazar:** se busca la primera solicitud en revisión con dos documentos por revisar y se aprueba uno. Si no tiene fecha del documento, se usa la de ayer. Después se rechaza el siguiente, con el primer motivo del catálogo y un mensaje. La fila rechazada muestra "Mensaje al comprador: …".
- **`axe`:** reglas WCAG 2.1 A y AA. Falla si hay violaciones serias o críticas en el listado y en las tres pestañas del expediente, en claro y en oscuro. El tema se elige con la cookie `um-theme`.
- En el fixture, el parámetro `use` de Playwright se llama `provide`: con `use`, la regla `react-hooks/rules-of-hooks` lo marca como error.

**Resultado contra :8000:** 6 de 6 pasan, y sin usuario las 6 se saltan. `axe` no encontró violaciones serias ni críticas.
