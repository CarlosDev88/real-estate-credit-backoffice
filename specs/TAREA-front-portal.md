# Tarea: F2 del frontend — portal del comprador

## Objetivo
Construir el portal donde el comprador entra con el enlace mágico, acepta los consentimientos, completa sus datos, elige la financiación, carga sus documentos y sigue su solicitud. Es **móvil primero**.

- **Mockups:** `design/screens/portal.html` (inicio y hoja de carga) y `design/screens/portal-documentos.html`.
- **Formularios:** no tienen mockup. Se construyen con el mismo lenguaje visual (`design/README.md`): una columna en móvil, dos en escritorio cuando haya espacio, componentes de Ant Design con el tema Umbral y las reglas de texto del README.

## Cuándo y dónde
- **Agente:** front, después de fusionar F1.
- **Worktree y rama:** `wt-front-portal`, rama `feat/front-portal`, desde `master`. Ya debe tener fusionada `TAREA-brechas.md`: catálogos del comprador, `public_status`, `needs_action`, `role_label`, `advisor` y `stages`.
- **Si la radicación (`TAREA-radicacion.md`) ya está fusionada**, se usa también `latest_bank_update`. Si no, esa tarjeta se omite y se anota.

## Cómo corres el entorno
- **Backend:** `docker compose up -d postgres backend`, desde la carpeta principal. Sin el contenedor `frontend`.
- **Front:** `pnpm install` y `pnpm dev` en `wt-front-portal\frontend` (puerto 3000).
- **Entrar al portal:** un enlace de comprador nuevo, creado como asesor (`POST /applications/{id}/buyer-access-links`) o con el que imprime `seed_demo_data`. Cada enlace sirve una sola vez.

## Reglas de trabajo
- Git solo en lectura. Carlos hace todos los commits y push, sin `Co-Authored-By` ni firmas.
- **No se presentan dudas.** Lo que esta spec no cubra lo decides tú con la opción más simple, lo anotas en "Precisiones acordadas" y sigues. Solo te detienes si necesitas un dato que la API no da (lo anotas en "Brechas" y lo dejas fuera), si cambia el alcance o si exige tocar un `.env`.
- Cada parte se hace de corrido. Al cerrarla entregas: verificaciones en verde (`lint`, `format:check`, `typecheck`, tests con cobertura ≥ 70 % y `build`), las decisiones que tomaste y el mensaje de commit. Esperas el "listo" de Carlos.
- **Reglas de F0 vigentes:**
  - cero listas o textos de negocio en el código;
  - etiquetas y estados de la API;
  - `toneFor`, `Money` y `lib/format`;
  - errores por el `MutationCache` global;
  - `If-Match` y `expected_version`.
- **Validación:** el front solo valida formato (requerido, correo, número ≥ 0, longitudes del contrato). **Las reglas de negocio las valida la API.** Un campo que depende de un código de catálogo se muestra siempre (opcional) y la API responde con `details[].field`, que va al campo.
- **Solo tocas tus rutas:** `acceso`, `(portal)/portal/**`, `features/buyer-portal`, `features/buyer-documents` y `e2e/portal`. Lo compartido, en un commit aparte (`refactor(ui)` o `fix(ui)`).
- **Accesibilidad:** objetivos táctiles ≥ 44 px, `aria-describedby` en los errores, foco visible, estado nunca solo por color y `axe` sin violaciones serias.

## Parte 1. Acceso, sesión y estructura del portal
- **`/acceso?token=…`:**
  - `POST /buyer-access/consume`;
  - **borra el token de la URL con `history.replaceState` antes de cualquier otra cosa**;
  - si sale bien, va a `/portal`.
  - Errores: una pantalla por código `MAGIC_LINK_EXPIRED`, `MAGIC_LINK_CONSUMED`, `MAGIC_LINK_REVOKED` y `MAGIC_LINK_INVALID`, con el `message` de la API y la frase "Pídele un enlace nuevo a tu asesor". `429`: "Demasiados intentos, espera N minutos".
- **Layout de `(portal)`:**
  - guarda con `GET /buyer/session`;
  - `401` u otro error de sesión lleva a la pantalla "Tu acceso venció" (de F0, con el manejador inyectable de `SESSION_EXPIRED`), sin datos de la solicitud.
  - Mientras carga, un esqueleto.
- **Encabezado:** logo, nombre (`buyer.display_name`), código de la solicitud, avatar con iniciales, `ThemeToggle` y un menú con "Salir" (`POST /buyer/session/logout` y la pantalla "Saliste del portal").
- **Navegación:**
  - en móvil, una barra inferior fija con Inicio y Documentos (con el número de documentos con `needs_action`);
  - en escritorio, la misma navegación arriba.
  - **"Avisos" se quita:** no hay endpoint de notificaciones del comprador (módulo 13). Va a "Brechas".
- **Aviso de vencimiento:** "Tu acceso vence en N horas. Si se vence, pide un enlace nuevo a tu asesor", calculado con `session.expires_at` y actualizado cada minuto.
- **Consentimientos primero:** si `pending_consents` no está vacío, todas las rutas del portal redirigen a `/portal/consentimientos`. Lo mismo ante un `403 CONSENT_REQUIRED` (manejador de F0).
- **`/portal/consentimientos`:**
  - `GET /consents`;
  - cada uno con su título, el texto (`body`, plegable), si es obligatorio y su estado;
  - "Acepto" llama a `POST` con `ACCEPTED`. Un consentimiento opcional aceptado se puede retirar (`WITHDRAWN`, con confirmación);
  - al quedar sin pendientes obligatorios, el botón "Continuar" va a `/portal`.
- **Solicitud cerrada o no editable** (`is_closed` o `!is_editable`): una franja arriba ("Tu solicitud ya no admite cambios" o "Tu solicitud está cerrada", con `public_status_label`), y todos los formularios en solo lectura. Los `409` de solo lectura usan `isReadOnlyError`.

**Pruebas:**
- consumo correcto y borrado del token;
- cada error del enlace;
- sesión vencida;
- redirección a consentimientos y aceptación;
- retiro de un consentimiento opcional;
- logout;
- franja de solo lectura.

**Commit:** `feat(frontend): add buyer access, portal session, layout and consents`

## Parte 2. Inicio del portal (`/portal`)
Datos: `GET /buyer/applications/{id}` y `GET /buyer/applications/{id}/document-slots`.

- **Saludo:** "Hola, <primer nombre>" y "Tu crédito de <finalidad> con <banco> · <código>". Sin banco, la frase se omite.
- **Estado:** `public_status_label` como título y `next_action` como texto.
- **Progreso:** "Documentos listos X de Y" (`progress.documents_completed_total` / `documents_required_total`) con barra, y "N te tocan a ti · M los está revisando tu asesor" (conteos de slots con `needs_action` y con `public_status` = `IN_REVIEW`).
- **Etapas:** `stages` como lista vertical, con `label` y `state_label` y el estado marcado con ícono y texto, no solo con color. Si viene vacía, no se muestra.
- **Respuesta del banco** (si existe `latest_bank_update`): tarjeta con la etiqueta, la fecha y `public_message`.
- **"Lo que necesitamos de ti":** hasta 3 slots con `needs_action`. Cada uno con:
  - etiqueta y titular (`participant.full_name` y `role_label`);
  - motivo y mensaje del rechazo, si existen;
  - el botón "Subir documento" o "Reemplazar documento", que abre la hoja de carga (Parte 4).

  Debajo, "Ver todos mis documentos".
- **"Tu solicitud":** filas con enlace a su página:
  - tus datos personales;
  - ingresos y gastos (suma mensual de los participantes que aportan ingresos);
  - cada participante adicional, con su nombre y `role_label`;
  - el inmueble (proyecto o dirección);
  - la financiación (banco, monto y plazo);
  - los documentos ("X de Y listos").

  Encima, "Lo que falta": los `progress.items` con `complete=false`, con su `message`.
- **Tu asesor** (si existe `advisor`): iniciales, nombre, "Tu asesor de crédito", "Correo" (`mailto:`) y "WhatsApp" (`https://wa.me/<dígitos>`; si `phone` tiene 10 dígitos y empieza por 3, se antepone 57). Sin `phone`, solo correo.
- **"Ya no quiero continuar con la solicitud"** (solo si no está cerrada): modal con:
  - el motivo (catálogo `application_withdrawal_reason` del endpoint de catálogos del comprador);
  - un comentario opcional;
  - la confirmación explícita "Entiendo que mi solicitud se cerrará".

  Envía `POST /withdrawals` con `expected_version`. Al terminar, se recarga y queda en solo lectura.

**Pruebas:** cada tarjeta con datos completos, vacíos y nulos; WhatsApp con y sin teléfono; desistimiento; sin etapas; sin banco.

**Commit:** `feat(frontend): add the buyer portal home with progress, pending documents and withdrawal`

## Parte 3. Formularios de datos
Patrón común:
- React Hook Form + Zod, solo con validaciones de formato;
- "Guardar" con `If-Match` (versión del `ETag`);
- toast de éxito;
- los errores de campo de la API van a cada campo.
- Los selectores se llenan con `GET /buyer/metadata/catalogs/{code}` (TanStack Query, `staleTime` largo).
- Ciudad: un selector de departamento y otro de municipio filtrado con `parent_code`.

### Páginas
- **`/portal/datos`** (`GET`/`PATCH /profile`):
  - **Solo lectura:** nombres, apellidos, tipo y número de documento (enmascarado como lo entrega la API).
  - **Editables:** correo, teléfono, fecha de nacimiento y direcciones.
  - **Direcciones:** lista con tipo, ciudad, línea 1 y 2, código postal y "principal". Se agregan, editan y quitan, y se envían completas en el `PATCH`.
- **`/portal/ingresos`** (participantes con `GET /participants`): una sección por participante que aporta ingresos, con su nombre y `role_label`.
  - **Perfil financiero** (`GET`/`PUT /buyer/participants/{id}/financial-profile`): perfil laboral, tipo de contrato, empresa, cargo, fecha de ingreso, ingreso mensual, gastos, activos, pasivos y origen de los fondos. Montos con `MoneyInput`.
  - **Fuentes de ingreso** (`GET`/`POST /financial-profiles/{id}/income-sources`, `PATCH`/`DELETE /income-sources/{id}`): lista con tipo, pagador, monto mensual, fecha de inicio y "principal". Se agregan, editan y eliminan (con confirmación).
  - **"Confirmar mis datos"** (`POST …/confirmation` con `If-Match`): muestra "Confirmados el <fecha>" si existe `data_confirmed_at`. Un cambio posterior la borra (lo hace la API): se recarga y se muestra otra vez el botón.
- **`/portal/inmueble`** (`GET`/`PUT /property`): proyecto (solo lectura, si viene), tipo, condición, ciudad, dirección, unidad, valor estimado y "¿Ya es tuyo?" (sí, no o sin respuesta).
- **`/portal/financiacion`** (`GET`/`PUT /financing` y `GET /eligible-bank-products`):
  - modalidad (`financing_mode`);
  - **productos disponibles** como tarjetas con banco, nombre, rangos de monto y plazo (si existen) y la marca "Disponible" o "No disponible para tu caso" según `eligible`. Uno no elegible no se puede elegir;
  - monto solicitado, plazo en meses, moneda, amortización, recursos propios, "¿Usarás tus cesantías?" (con el monto de cesantías solo si se marca) y monto aprobado por otra entidad (opcional).
- Todas: botón "Volver al inicio" y, en móvil, "Guardar" fijo abajo.

**Pruebas:** por cada formulario, carga, guardado con `If-Match`, error de campo de la API, `409 STALE_VERSION` y solo lectura. Además: direcciones, fuentes de ingreso, confirmación, departamento → municipio y producto no elegible deshabilitado.

**Commit:** `feat(frontend): add buyer data, income, property and financing forms`

## Parte 4. Documentos (`/portal/documentos`) y hoja de carga
- **Encabezado:** "Tus documentos", el resumen "Te faltan N documentos. Tu asesor revisa los demás." y la barra "Documentos listos X de Y".
- **Pestañas:**
  - "Todos";
  - una por cada `public_status` presente en los slots, con su `public_status_label` y su número, en el orden en que aparecen al ordenar la lista con `needs_action` primero.
  - No se escriben estados en el código.
- **Lista:** agrupada por participante (nombre y `role_label`). Cada slot muestra:
  - etiqueta y descripción del tipo documental;
  - `public_status_label` con su tono;
  - el archivo vigente (nombre y fecha);
  - el motivo y el mensaje del rechazo;
  - las acciones: "Subir" o "Reemplazar" (solo con `can_upload`), "Ver" (el visor con `GET /buyer/document-files/{id}/download`) y "Versiones" (`GET /versions`, cada una con su estado y "Ver").
- **Hoja de carga** (como el mockup: hoja inferior en móvil y modal en escritorio):
  - título, titular y tipos y tamaño máximo legibles, calculados con `allowed_mime_types` y `max_size_bytes` (PDF, JPG o PNG, de hasta 10 MB);
  - la descripción del tipo documental como ayuda;
  - "Tomar foto" (`accept="image/*"` con `capture="environment"`) y "Elegir archivo" (con los tipos permitidos), usando el `DocumentUploader` de F0;
  - **validación local** de tipo y tamaño antes de enviar, con el texto del error en línea;
  - "Fecha del documento" opcional, si el slot tiene `validity_days`;
  - envío con `uploadFile` (de F0) a `POST /buyer/document-slots/{id}/uploads`, con progreso y "Cancelar";
  - errores de la API: `422 UNSUPPORTED_FILE_TYPE` o `FILE_TOO_LARGE`, `413`, `409 DOCUMENT_LOCKED` o `DOCUMENT_NOT_REJECTED` y `503`, cada uno con su `message`.
  - Al terminar: toast, se recargan los slots y el detalle, y se cierra la hoja.

**Pruebas:**
- pestañas dinámicas;
- validación local de tipo y tamaño;
- carga con progreso;
- cancelar;
- cada error de la API;
- versiones;
- visor;
- slot sin `can_upload` sin botón;
- teclado y foco en la hoja.

**Commit:** `feat(frontend): add buyer documents with the upload sheet, versions and viewer`

## Parte 5. E2E, accesibilidad y cierre
- **Playwright** (`e2e/portal`):
  - el *global setup* entra como el asesor de prueba (`.env.local`), busca una solicitud de demo en `waiting` y crea un enlace nuevo por API;
  - el flujo: abrir el enlace → aceptar los consentimientos → guardar un dato de contacto → subir un PDF pequeño → verlo "En revisión".
  - **Viewport móvil** (390 px) y escritorio.
  - `axe` en cada pantalla, en claro y oscuro.
  - Sin datos de demo, se salta con un mensaje claro.
- **Capturas** a 390, 1280 y 1440 px, en claro y oscuro, del inicio, los documentos, la hoja de carga y un formulario, en `frontend/test-results/` (no se commitean). Reporta qué difiere del mockup.
- **`specs/TAREA-frontend-base.md`, "Brechas":** agrega las de esta fase ("Avisos" y lo que encuentres).
- Trae `master` antes de entregar (Carlos hace el merge) y corre `pnpm api:gen`.
- Entregas el **título y la descripción del PR**, en español, sin firmas.

**Commit:** `test(frontend): add buyer portal end-to-end and accessibility checks`

## Precisiones acordadas

### Parte 1
**Acceso (`/acceso`):**
- El token se lee y se borra de la URL en el primer efecto del cliente; queda solo en memoria. La página lleva `referrer: no-referrer`.
- Sin `token` en la URL: pantalla "Este enlace no es válido", sin llamar a la API.
- Título de cada error del enlace (texto de interfaz, no de negocio): `MAGIC_LINK_EXPIRED` "Este enlace venció", `MAGIC_LINK_CONSUMED` "Este enlace ya se usó", `MAGIC_LINK_REVOKED` "Este enlace ya no sirve" y `MAGIC_LINK_INVALID` "Este enlace no es válido". Debajo, el `message` de la API y "Pídele un enlace nuevo a tu asesor." Un código desconocido: "No pudimos abrir tu acceso".
- `429`: el título es "Demasiados intentos, espera N minutos" (N desde `Retry-After`, mínimo 1) y debajo el `message`.
- Error de red o `5xx`: "No pudimos abrir tu acceso" con "Reintentar", que reenvía el mismo token (el enlace no se gastó).

**Sesión y marco:**
- `401` o `403` de `GET /buyer/session` → "Tu acceso venció". La red y los `5xx` muestran "No pudimos cargar tu solicitud" con "Reintentar".
- Un `401 SESSION_EXPIRED` de cualquier petición del portal (manejador de F0) y la llegada de `expires_at` (temporizador) llevan a "Tu acceso venció" y borran de la caché todo lo del portal (`["buyer"]`).
- "Tu acceso venció" y "Saliste del portal" son pantallas propias del portal (F0 dejó solo el manejador), sin datos de la solicitud.
- Salir: con `204` (o `401`, ya sin sesión) muestra "Saliste del portal" y borra la caché; con otro error, toast y se queda.
- Menú de la cuenta: el avatar es un botón ("Cuenta de <nombre>") que abre un menú con el nombre y el código arriba y "Salir". En escritorio, el nombre y el código también van junto al avatar, como en el mockup.
- Marco desde 900 px como el mockup: navegación arriba y sin barra inferior. El conteo de Documentos es el número de slots con `needs_action`, con "pendientes" como texto oculto. El logo del portal es una variante local sobre fondo claro (no se tocó `LogoMark`).
- Aviso de vencimiento: va en la tarjeta de estado del inicio (README: "lo urgente va arriba, en la tarjeta de estado"). Horas completas; en la última hora, minutos.

**Consentimientos:**
- Con `pending_consents`, se oculta la navegación y no se piden los slots; las demás rutas redirigen a `/portal/consentimientos`.
- `BuyerConsent` no trae etiqueta de estado (ver "Brechas"): cada tarjeta dice "Obligatorio" u "Opcional" y, si está aceptado, "Aceptado el <fecha>" (`accepted_at`). No se escriben los estados.
- Solo un opcional aceptado se puede retirar (con confirmación). Con la solicitud cerrada (`is_closed`), los botones quedan deshabilitados (la API responde `409 APPLICATION_CLOSED`).
- "Continuar" queda deshabilitado con la razón visible mientras falten obligatorios; al pulsarlo, se espera la sesión actualizada antes de ir a `/portal`.

**Rutas provisionales:** `/portal` (saludo, estado y vencimiento) y `/portal/documentos` (solo el título) existen desde la Parte 1 para que la navegación funcione; se completan en las partes 2 y 4.

**E2E (adelanto de la Parte 5):** `e2e/portal` con un *setup* que, como el asesor de prueba, crea un enlace en una solicitud `waiting` elegida al azar por cada proyecto (`portal-mobile` a 390 px y `portal-desktop` a 1280 px). `POST /buyer-access/consume` admite 5 intentos por hora por IP: cada corrida gasta 2. Estos archivos y el cambio de `playwright.config.ts` van en el commit de la Parte 5.

### Parte 2
- **Saludo:** la etiqueta de la finalidad va en minúscula inicial dentro de la frase ("Tu crédito de vivienda…"). Sin banco se omite solo "con <banco>"; el código siempre va. El banco se muestra con `short_name` (o `name`).
- **Progreso:** sin documentos exigidos (`documents_required_total = 0`) no se muestra la barra. En "N te tocan a ti · M los está revisando tu asesor" se omiten las partes en cero y se usa el singular cuando toca.
- **Etapas:** el ícono sale de `state` (`done`, `current`, `pending`, del contrato) y siempre va con `label` y `state_label`; la actual lleva `aria-current="step"`.
- **Respuesta del banco:** título `response_type_label`, arriba "Respuesta del banco · <fecha y hora>" y debajo `public_message`.
- **"Lo que necesitamos de ti":** el número es el total de slots con `needs_action`; se muestran los 3 primeros en el orden de la API. Cada uno lleva su `public_status_label` además del titular, y el tono del ícono sale de `toneFor("documentSlot", status)`: un pendiente es `neutral` (el mockup lo pinta `warning`) y un rechazado `danger`. El primer botón es el primario. Sin pendientes: "Por ahora no necesitamos ningún documento de ti."
- **Botón "Subir/Reemplazar documento" (provisional):** hasta la Parte 4 lleva a `/portal/documentos?slot=<id>`; con la hoja de carga se abre en el mismo inicio.
- **"Tu solicitud":**
  - "Tus datos personales" lleva debajo el nombre del titular.
  - "Ingresos y gastos": suma de `monthly_income_cop` de los participantes con `contributes_income`, pidiendo el perfil financiero de cada uno (un `404` es "sin perfil"). Sin ningún perfil: "Sin datos todavía".
  - Participantes adicionales: todos menos el primero de `participants`, con `role_label` como título y el nombre debajo; enlazan a `/portal/ingresos#participante-<id>`.
  - Inmueble: el proyecto o, sin proyecto, la dirección, más la unidad. Financiación: "<banco> · <monto> a <plazo>", con el plazo en años si son completos y si no en meses.
  - Documentos: "X de Y listos" y, si hay, "N pendientes" con tono `warning`.
  - Sin datos de una sección: "Sin datos todavía".
- **Asesor:** WhatsApp abre en otra pestaña.
- **Desistimiento:**
  - Modal "¿Ya no quieres continuar?" con el botón `danger` "Cerrar mi solicitud".
  - Motivo, comentario opcional (se envía recortado, vacío si no hay) y la casilla "Entiendo que mi solicitud se cerrará", obligatoria en el cliente.
  - `expected_version` sale del `ETag` del detalle.
  - Al terminar: toast "Cerramos tu solicitud" y se recarga todo `["buyer"]`, así aparece la franja y desaparece el enlace.
  - Los errores con campo van al campo; los demás, al toast.
- **Compartido:** `FormField` y `useFormErrorHandler` pasan de `features/applications` a `components/ui/form-field.tsx` (commit aparte `refactor(ui)`), para usarlos en el portal.

### Brechas encontradas
- **Avisos:** no hay endpoint de notificaciones del comprador (módulo 13). Se quitó de la navegación.
- **`BuyerConsent` sin `status_label`:** el estado del consentimiento (`PENDING`, `ACCEPTED`, `WITHDRAWN`) llega solo como código.
- **Ingreso mensual en el inicio:** el detalle del comprador no trae ingresos; la suma de "Ingresos y gastos" pide un perfil financiero por cada participante que aporta ingresos.
- **Mensaje del `429` de `/buyer-access/consume`:** es el texto por defecto de DRF ("Solicitud fue regulada (throttled). Se espera que esté disponible en 3450 segundos."). El portal lo muestra debajo de su propio título.
