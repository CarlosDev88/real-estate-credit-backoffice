# Tarea: F4 del frontend — clientes y oportunidades (vistas 4, 5 y 6)

## Objetivo
Que el asesor (y el administrador) gestione clientes y oportunidades, y **cree una solicitud de crédito desde una oportunidad**. Hoy no hay forma de crear solicitudes desde la app: el botón "Nueva solicitud" se quitó en la F1 por eso.

Vistas de REQ §6:
- 4: listado de clientes;
- 5: crear y editar cliente;
- 6: detalle del cliente, con sus oportunidades y solicitudes.

El backend ya existe (`crm`: `/clients`, `/opportunities`; API §13 y §14; `POST /applications`). **No hay mockup:** se diseña con `design/README.md` y los patrones del listado de solicitudes (F1).

## Cuándo y dónde
- **Agente:** front 2, cuando termine la F3 (radicación), en el worktree `wt-front-clients`, rama `feat/front-clients`, desde `master`.
- **En paralelo:** el front 1 hace el design system (Storybook) y es el **dueño de `components/ui`**.
- **Regla:** **no creas ni cambias componentes compartidos.** Si necesitas uno nuevo, lo haces dentro de `features/clients/components/` y lo anotas en el reporte ("candidato a la librería"). Si necesitas cambiar uno compartido, déjalo por escrito en el buzón y sigue con una alternativa local.
- **Solo tocas:** `(backoffice)/clientes/**`, `features/clients/`, `e2e/backoffice/clients*` y la entrada del menú (`lib/navigation/nav-config.tsx`, un cambio mínimo y anotado).
- **Puerto 3001**, como en la F3 (Playwright con `E2E_PORT=3001` y su propio archivo de sesión).

## Reglas de trabajo
- Las mismas de la F3: git solo en lectura, buzón, sin dudas, cero listas o textos de negocio en el código (tipos de documento, orígenes, estados y motivos vienen de catálogos o de la API), `toneFor`, `lib/format` y errores por el `MutationCache`.
- Verificaciones al cerrar cada parte: `lint`, `format:check`, `typecheck`, tests con cobertura ≥ 70 % y `build`.
- Pantallas a 1440, 1280 y 390 px, en claro y oscuro, y `axe` sin violaciones serias.

## Parte 1. Listado y alta de clientes
- **Menú:** "Clientes", en el grupo "Comercial", con el permiso de lectura de clientes que use la API (búscalo en el contrato y en `/auth/me`).
- **`/clientes`:**
  - `GET /clients`, con búsqueda (nombre, documento, correo), filtro por origen, orden y paginación, **todo en la URL** (mismo patrón que `/solicitudes`);
  - columnas: nombre, documento (con su tipo), correo, teléfono, origen, número de solicitudes (si la API lo da; si no, va a "Brechas") y fecha de creación;
  - tarjetas en móvil;
  - estados vacío, cargando y error.
- **"Nuevo cliente"** (`/clientes/nuevo`):
  - formulario con tipo de documento (catálogo), número, nombres, apellidos, correo, teléfono, fecha de nacimiento y origen;
  - validación de formato en el front y de negocio en la API (el documento duplicado responde su error en el campo);
  - al crear, va al detalle.
- **Editar** (`/clientes/[id]/editar`): `PATCH /clients/{id}`, con los campos que la API deje editar.

**Commit:** `feat(frontend): add the clients list and the create and edit client forms`

## Parte 2. Detalle del cliente, oportunidades y nueva solicitud
- **`/clientes/[id]`:**
  - **encabezado:** nombre, documento, contacto, origen y "Editar";
  - **pestañas** (`?tab=`): **Resumen** (datos y direcciones: `GET`/`POST /clients/{id}/addresses`, la primera es la principal), **Oportunidades** y **Solicitudes** (`GET /clients/{id}/applications`, con enlace al expediente de la F1).
- **Oportunidades:**
  - lista con estado, origen, proyecto y asesor (`GET /clients/{id}/opportunities`);
  - **"Nueva oportunidad"** (`POST /opportunities`): origen y proyecto opcional;
  - detalle en un panel lateral (`GET /opportunities/{id}`), con sus acciones disponibles (`POST /opportunities/{id}/transitions`; el motivo de pérdida sale de su catálogo) y la asignación de asesor (`POST /opportunities/{id}/assignments`, solo con permiso);
  - **"Crear solicitud de crédito"** (`POST /applications`, desde una oportunidad que lo permita según la API): finalidad (catálogo `loan_purpose`) y lo demás que pida el contrato. Al crearla, va al expediente nuevo (`/solicitudes/{id}`). El error "ya hay una solicitud abierta" muestra el mensaje con un enlace a la existente, si la API da el id.
- **Volver a poner "Nueva solicitud" en `/solicitudes`:** lleva a `/clientes` con un texto de ayuda ("Elige el cliente y su oportunidad"). Es un cambio mínimo en `features/applications` y va anotado.

**Commit:** `feat(frontend): add the client detail with opportunities and creating an application`

## Parte 3. E2E, accesibilidad y cierre
- **Playwright** (puerto 3001):
  - crear un cliente;
  - ver el error de documento duplicado;
  - crear una oportunidad;
  - crear una solicitud desde la oportunidad;
  - llegar al expediente.

  `axe` en el listado, el formulario y el detalle, en claro y oscuro.
- **Capturas** a 1440, 1280 y 390 px, en claro y oscuro.
- **"Brechas"** en `TAREA-frontend-base.md`.
- **Lista de componentes candidatos a la librería** en el reporte.
- Trae `master` (Carlos hace el merge) y corre `pnpm api:gen`.
- Entregas el **título y la descripción del PR**, en español, sin firmas.

**Commit:** `test(frontend): add clients end-to-end and accessibility checks`

## Precisiones acordadas
_(las agrega el agente)_

**Parte 1 (front 2, 2026-11-17):**
- **Permisos:** menú y rutas `/clientes/**` con `clients.read` (API §13, `ClientListView`); "Nuevo cliente" con `clients.create`; "Editar" con `clients.update`.
- **Orden:** la API ordena por `last_names`, `first_names`, `created_at` y `updated_at`. La columna "Nombre" ordena por `last_names` y "Creado" por `created_at` (por defecto `-created_at`, igual que la API). Las demás columnas no ordenan.
- **Filtro:** solo origen (`lead_origin`), como pide la spec; la API también acepta `document_type`, que no se expone.
- **Número de solicitudes:** `Client` no lo trae; la columna no va y queda en "Brechas" (Parte 3).
- **Validación del front (formato):** obligatorios, longitudes del contrato, correo, teléfono E.164 (quitando espacios, paréntesis y guiones, como la API), caracteres del documento (letras, dígitos, puntos, guiones) y fecha de nacimiento anterior a hoy (Bogotá). El formato por tipo de documento (solo dígitos para CC) es regla de negocio: lo valida la API y su error vuelve al campo.
- **Documento duplicado (`409 DUPLICATE_CLIENT_DOCUMENT`):** el mensaje de la API va al campo "Número de documento"; si la API da `details[].resource_id`, se ve el enlace "Ver el cliente existente".
- **Edición:** `PATCH` solo con los campos cambiados; vaciar correo o teléfono manda `""` y vaciar fecha u origen manda `null`. Asesor y administrador pueden corregir el documento (`PatchedClientUpdateRequest`). "Guardar cambios" queda deshabilitado sin cambios. Si el tipo u origen actual ya no está activo en el catálogo, se ofrece igual con su etiqueta.
- **Detalle mínimo en la Parte 1:** `/clientes/[id]` existe desde ya (encabezado con nombre, documento, contacto, origen y "Editar", y la tarjeta de datos) para que "al crear, va al detalle" funcione; la Parte 2 le suma las pestañas.
- **Broker:** el backoffice F4 es para asesor y administrador. La vista del broker (`BrokerClientSerializer`: `document_type` como texto, sin origen) no coincide con `Client` del contrato; va a "Brechas".

**Parte 2 (front 2, 2026-11-17):**
- **Pestañas** en `?tab=` (`resumen` por defecto, `oportunidades`, `solicitudes`). "Oportunidades" pide `opportunities.read` y "Solicitudes" pide `applications.read`. Una pestaña sin permiso vuelve al resumen. El panel lateral de una oportunidad va en `?tab=oportunidades&oportunidad=<id>`, así un enlace abre la misma vista.
- **Direcciones:** `GET`/`POST /clients/{id}/addresses` (permiso de escritura `clients.update`). En la primera no se pregunta si es principal: la API la marca. En las demás, una casilla "Usar como dirección principal". El municipio sale del catálogo bajo demanda `municipality` (`GET /metadata/catalogs/municipality`), con búsqueda.
- **Estado de la oportunidad:** la etiqueta sale del catálogo `opportunity_status` del bootstrap, con activos e inactivos. `toneFor` no tiene el tipo `opportunity`, así que el badge va en tono neutro (candidato para el front 1).
- **Nueva oportunidad** (`opportunities.create`): origen (por defecto, el del cliente) y proyecto opcional, solo `ACTIVE` (`GET /projects?status=ACTIVE`). `409 DUPLICATE_OPPORTUNITY` va al campo "Proyecto". Al crearla, se abre su panel.
- **Asignar o cambiar asesor:** con `opportunities.assign` y `users.read` (para listar asesores), como "Reasignar" en la F1. El asesor no tiene `users.read`, así que solo lo ve el administrador.
- **Crear solicitud de crédito** (`applications.create`): pide la finalidad (`loan_purpose`) y, si la oportunidad no tiene asesor, el asesor (con `users.read`). No manda `project_id` ni `property`: la API exige `property` cuando llega `project_id`, y el inmueble se completa en el expediente. Al crearla va a `/solicitudes/{id}`. `409 APPLICATION_ALREADY_OPEN` se ve en el modal, con "Ir a la solicitud en curso" si llega `resource_id`.
- **Bloqueo de contrato (transiciones):** `OpportunityDetail.available_actions` trae solo códigos de transición (`MARK_CONTACTED`, `CANCEL_NEW`, `CONVERT_ASSIGNED`…). No trae etiqueta ni estado destino, y el asesor no tiene `workflow.read`. Por eso los botones de transición (contactada, en gestión, perdida con motivo, cancelar) no están, y "Crear solicitud" se muestra con el permiso, sin filtrar por estado: la API decide. Propuesta para el backend: `available_actions` como `AvailableAction` de solicitudes (`{code, label, target_status, target_status_label}`).
- **"Nueva solicitud" en `/solicitudes`:** con `applications.create` y `clients.read`, lleva a `/clientes?nueva_solicitud=1`. Ahí se ve la ayuda "Elige el cliente y su oportunidad" (se puede cerrar y se conserva al filtrar), y el cliente abre en su pestaña Oportunidades. El parámetro no va a la API.
- **Listas del detalle:** oportunidades y solicitudes del cliente se piden con `page_size=100`, sin paginar en la vista: un cliente tiene pocas.

**Parte 3 (front 2, 2026-11-17):**
- **Transiciones de la oportunidad:** se decidió que el backend cambie `available_actions` a `[{code, label, kind, target_status, target_status_label}]`. Los botones van en un PR corto aparte cuando llegue a `master`; la F4 se entrega sin ellos.
- **"Asignarme":** una oportunidad nueva queda `NEW` sin asesor y no se puede convertir. Quien tiene `opportunities.assign` pero no `users.read` (el asesor) ve "Asignarme", que manda su propio id (`/auth/me`) a `POST /opportunities/{id}/assignments`. Con `users.read` (el administrador) sigue "Asignar / Cambiar asesor" con el selector. Sin esto, el asesor no podía terminar el flujo de la spec.
- **Error de asesor no visible:** si la oportunidad no tiene asesor y el usuario no puede elegir uno, el error `assigned_advisor_id` de la API va al aviso, no a un campo oculto.
- **E2E (`e2e/backoffice/clients.spec.ts`, puerto 3001):** crea datos reales con un documento distinto en cada corrida. Elige la primera opción de cada catálogo, así que no fija etiquetas de negocio. Cierra los avisos antes de usar el panel lateral, porque arriba a la derecha tapan sus botones durante 5 s (observación para el design system). `axe` corre en la suite normal: listado, formulario con errores, detalle y pestaña Oportunidades, en claro y oscuro. Las capturas siguen en `clients-screenshots.spec.ts` (con `E2E_SCREENSHOTS=1`).
