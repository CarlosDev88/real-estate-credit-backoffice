# Tarea: brechas del backend que necesita el frontend

## Objetivo
Cerrar lo que el frontend no puede hacer por su cuenta, porque REQ §8.5 prohíbe que defina textos, listas o agrupaciones de negocio: etiquetas que faltan, catálogos para el portal del comprador, datos del asesor y etapas del portal, y la cabecera `ETag` en el contrato. Desbloquea la F2 del frontend (portal del comprador) y completa lo que usa la F1 (backoffice).

## Cuándo y dónde
- **Agente:** backend A, en la carpeta principal (`real-estate-credit-backoffice`).
- **Rama:** `feat/frontend-gaps`, desde `master` al día (después del merge del PR #16).
- **En paralelo:** el backend B trabaja en `TAREA-radicacion.md` (app nueva `filings`) en otro worktree. **No toques nada de radicación.** Si necesitas algo de ese lado, anótalo y sigue.

## Reglas de trabajo
- Git solo en lectura. Carlos hace todos los commits y push, sin `Co-Authored-By` ni firmas.
- **No se presentan dudas.** Lo que esta spec no cubra lo decides tú con la opción más simple, lo anotas en "Precisiones acordadas" y sigues. Solo te detienes si la decisión rompe un contrato ya publicado (quitar o renombrar campos), cambia el alcance, borra o altera datos existentes, o exige tocar un `.env`.
- Cada parte se hace de corrido. Al cerrarla entregas: verificaciones en verde, la lista corta de decisiones que tomaste y el mensaje de commit. Esperas el "listo" de Carlos para la siguiente.
- **Solo se agregan campos** a las respuestas. No se quita ni se renombra nada: el frontend ya consume el contrato.
- Toda etiqueta visible vive en el backend (catálogo, `TextChoices` o una constante única) y se prueba.
- **Contrato y tipos del front:** al cerrar cada parte, regeneras `contracts/openapi.json` (`--validate --fail-on-warn`) y también los tipos del front, desde `frontend/`:
  ```
  npx --yes openapi-typescript@7.13.0 ../contracts/openapi.json -o src/lib/api/schema.d.ts
  ```
  Es la misma versión de `package.json`; el CI del front falla si este archivo queda viejo.
- CI en verde, cobertura ≥ 95 %. El backend de `:8000` sigue sano (lo usa el front): las migraciones se aplican con `migrate` en el contenedor apenas se crean.

## Parte 0. Datos de demo (va primero)
Los agentes del front necesitan datos reales en `:8000` para ver sus pantallas, y la demo final del proyecto también.

### El comando `seed_demo_data` (`apps/core` o la app que ya tenga comandos generales; anótalo)
- **Solo con `DEBUG=True`.** Sin `DEBUG`, termina con error y no escribe nada.
- **Idempotente:** si ya existen los datos de demo (marcados por un prefijo fijo en el correo o el documento de los clientes de demo), no crea nada e imprime "Los datos de demo ya existen".
- **No borra nada, nunca.**
- **Crea todo usando los servicios del dominio, no inserts directos.** Así quedan bien el historial, los slots, la completitud guardada y las evaluaciones.

### Qué crea
- **Usuarios:** un administrador, dos asesores y un broker, con correos `@demo.local`. La contraseña es una constante del comando (`DemoUmbral2026!`), y el README advierte que es solo para local. Si se pasa `--advisor-email asesor.e2e@example.com`, ese asesor existente también recibe solicitudes.
- **Unas 30 solicitudes** repartidas entre las pestañas `draft`, `waiting`, `review` y `ready`, con:
  - titular, y en algunas co-solicitante o deudor solidario;
  - perfil financiero con ingresos, inmueble y financiación, con banco y producto variados (Bancolombia, FNA y Banco de Bogotá; hipotecario y leasing);
  - en `review`, documentos cargados por revisar, unos aprobados y uno rechazado;
  - en `ready`, al menos una con `ready_to_file_blocked=true` (un documento vencido o rechazado después);
  - en `waiting`, al menos una con `buyer_inactive=true`.
- **Archivos:** PDF y PNG pequeños generados en el momento (sin datos reales), guardados con el almacenamiento configurado (disco en el modo local simple).
- **Un enlace de acceso del comprador vigente** para una solicitud en `waiting`. El comando imprime la URL (`http://localhost:3000/acceso?token=…`) para probar el portal.
- Corre `refresh_application_completeness` al final.

### README y pruebas
- **README del backend:** sección "Demo data", con el comando, los usuarios y la advertencia.
- **Pruebas:**
  - crea los datos;
  - una segunda corrida no duplica nada;
  - sin `DEBUG`, falla sin escribir;
  - los conteos por pestaña son mayores que cero.
- Al terminar, **lo corres en el contenedor de `:8000`** con `--advisor-email asesor.e2e@example.com`, y en el reporte pegas la URL del portal que imprimió.

**Commit:** `feat(demo): add a demo data command for local runs`

## Parte 1. Catálogos y etiquetas para el comprador

### 1.1 Catálogos del portal
Hoy `/metadata/bootstrap` y `/metadata/catalogs/{code}` exigen sesión interna. El comprador no tiene cómo llenar los selectores de sus formularios.
- **Nuevo** `GET /api/v1/buyer/metadata/catalogs/{catalog_code}`, con sesión de comprador (`buyerSession`).
- **Misma respuesta, filtros (`parent_code`, `parent_id`), `ETag` e `If-None-Match`** que `GET /metadata/catalogs/{catalog_code}`. Reutiliza su lógica; no la copies.
- **Lista permitida** (constante única, con prueba), con los códigos que usan los formularios del comprador:
  - `address_type`, `municipality` y su catálogo padre (el de departamentos, el que use hoy `municipality` como padre);
  - `employment_profile`, `contract_type`, `funds_origin` e `income_source_type`;
  - `property_type` y `property_condition`;
  - `financing_mode`, `currency_mode` y `amortization_mode`;
  - `application_withdrawal_reason`.

  Verifica con `grep` que esos sean los códigos que validan los serializers del comprador. Si alguno usa otro código, agrégalo y anótalo.
- Un código fuera de la lista o inexistente responde `404 NOT_FOUND`, igual que un recurso que no existe: no se revela qué catálogos hay.
- Mismo límite de consumo que los demás `GET` del comprador.

### 1.2 Estado público de cada documento del comprador
En `BuyerDocumentSlot` (lista, detalle y respuesta de la carga), sin quitar `status`:
- `public_status` y `public_status_label`:

  | `status` del slot | `public_status` | `public_status_label` |
  | --- | --- | --- |
  | `PENDING` | `TO_UPLOAD` | Te falta |
  | `REJECTED` | `TO_FIX` | Corrígelo |
  | `UPLOADED` | `IN_REVIEW` | En revisión |
  | `APPROVED` | `DONE` | Listo |
  | `WAIVED` | `NOT_APPLICABLE` | No aplica |

- `needs_action` (bool): `true` si `can_upload` es verdadero y `public_status` es `TO_UPLOAD` o `TO_FIX`. Es lo que arma la tarjeta "Lo que necesitamos de ti".
- La tabla vive en una sola constante del módulo `documents`, con prueba de que cubre todos los estados.

### 1.3 Etiqueta del rol del participante
`role_label` junto a cada `role` de participante: Titular (`PRIMARY`), Co-solicitante (`CO_APPLICANT`) y Deudor solidario (`SOLIDARY_DEBTOR`).
- Va en los DTO del comprador (`BuyerParticipant`, `BuyerParticipantSummary` y `BuyerSlotParticipant`) y en los internos que exponen el rol del participante (participantes del expediente y slots internos).
- Las etiquetas salen de las `TextChoices` del modelo.

**Pruebas de la Parte 1:**
- Catálogo permitido: `200`, `ETag` y `304`.
- Catálogo no permitido o inexistente: `404`.
- Sin sesión: `401`.
- `municipality` filtrado por `parent_code`.
- Los cinco estados públicos y `needs_action`.
- `role_label` en cada DTO.

**Commit:** `feat(buyer): add buyer catalogs, public document status and participant role labels`

## Parte 2. Datos del portal: asesor, etapas y rol interno

### 2.1 Asesor en el detalle del comprador
En `GET /buyer/applications/{id}` (`BuyerApplicationDetail`): `advisor`, nulo si la solicitud no tiene asesor asignado.
- Lleva `{ full_name, email, phone }`; `phone` es `null` si el usuario no tiene teléfono.
- Solo esos tres campos: nada de id, roles ni otros datos del usuario.
- El front arma el enlace de WhatsApp con `phone`.
- Esto cambia una regla de API §8 ("el comprador no ve… el asesor"): ahora ve solo el nombre, el correo y el teléfono de contacto, por decisión de Carlos. Actualiza esa línea.

### 2.2 Etapas del portal
En `BuyerApplicationDetail`: `stages`, una lista con 4 etapas fijas, en este orden:

| `code` | `label` |
| --- | --- |
| `DATA` | Tus datos |
| `DOCUMENTS` | Documentos |
| `FILING` | Radicación en el banco |
| `BANK_RESPONSE` | Respuesta del banco |

- Cada etapa lleva `{ code, label, state, state_label }`, con `state` en `done`, `current` o `pending` y `state_label` en "Listo", "En curso" o "Pendiente".
- **Etapa actual según el estado de la solicitud:**
  - `DRAFT` y `WAITING_BUYER_DATA`: `DATA`;
  - `WAITING_DOCUMENTS`, `DOCUMENTS_REVIEW` y `BANK_OBSERVATION`: `DOCUMENTS`;
  - `READY_TO_FILE`, `FILED` y `FILING_VALIDATION`: `FILING`;
  - `CREDIT_ANALYSIS`, `APPROVED`, `LEGALIZATION` y `REJECTED`: `BANK_RESPONSE`.

  Las anteriores a la actual van `done` y las siguientes `pending`.
- `DISBURSED`: las cuatro `done`.
- `WITHDRAWN`, `CANCELLED`, `OWN_FUNDS` y `EXTERNAL_CREDIT_APPROVED`: lista vacía (el front oculta las etapas).
- La configuración vive en una constante única. Una prueba verifica que cada estado de `ApplicationStatus` tiene regla.

### 2.3 Etapas del expediente interno
En `ApplicationDetail` (`GET /applications/{id}`, interno): `progress_stages`, con 8 etapas fijas y la misma forma que `stages` del comprador (`code`, `label`, `state` y `state_label`):

| `code` | `label` | Estados que la hacen actual |
| --- | --- | --- |
| `BUYER_DATA` | Datos del comprador | `DRAFT`, `WAITING_BUYER_DATA` |
| `DOCUMENT_UPLOAD` | Carga de documentos | `WAITING_DOCUMENTS` |
| `DOCUMENT_REVIEW` | Revisión documental | `DOCUMENTS_REVIEW` |
| `READY_TO_FILE` | Lista para radicar | `READY_TO_FILE` |
| `FILED` | Radicada | `FILED`, `FILING_VALIDATION` |
| `BANK_ANALYSIS` | Análisis del banco | `CREDIT_ANALYSIS`, `BANK_OBSERVATION` |
| `APPROVED` | Aprobada | `APPROVED`, `LEGALIZATION` |
| `DISBURSED` | Desembolsada | `DISBURSED` (todas `done`) |

- `REJECTED`: las etapas hasta `BANK_ANALYSIS` van `done` y las demás `pending`.
- `WITHDRAWN`, `CANCELLED`, `OWN_FUNDS` y `EXTERNAL_CREDIT_APPROVED`: lista vacía.
- Comparte con `stages` del comprador la misma función y el mismo tipo de respuesta. Prueba de cobertura de estados.

### 2.4 Etiqueta del rol en `/auth/me`
- `role_label`: el `name` del rol principal (`role`), o `null` si no hay. Va bajo el nombre del usuario en el shell.

**Pruebas de la Parte 2:**
- `advisor` con y sin teléfono, y sin asesor.
- `stages` y `progress_stages` para cada grupo de estados.
- `role_label` en `/auth/me`.
- El broker y la sesión interna no ven nada nuevo del comprador.

**Commit:** `feat(applications): add advisor contact and progress stages for the portal and the backoffice`

## Parte 3. `ETag` en el contrato y etiquetas faltantes del backoffice

### 3.1 `ETag` declarado en el contrato
El backend ya envía `ETag` en las respuestas del expediente (API §6), pero el contrato no lo declara en ninguna.
- Un helper único (por ejemplo, `etag_response_headers`) que agrega `headers: {ETag: string}` a las respuestas `2xx` de `extend_schema`.
- Se aplica a todas las vistas que hoy ponen `ETag`, internas y del comprador. Las encuentras con `grep` sobre donde se arma la cabecera.
- Una prueba recorre el esquema generado y verifica que cada operación que exige `If-Match` declara `ETag` en su respuesta `2xx`.

### 3.2 Etiquetas que le faltan al backoffice (F1)
Revisa los DTO internos que usa la F1:
- detalle de la solicitud;
- participantes;
- perfil financiero e ingresos;
- inmueble y financiación;
- evaluación bancaria;
- slots y versiones de documentos;
- revisiones;
- historial de estados;
- acciones disponibles.

Todo campo que sea un código de estado o de tipo y que la pantalla muestre debe traer su `*_label`. Agrega los que falten (por ejemplo, `status_label` del slot y de la versión del archivo, o `decision_label` de la revisión) y lista en el reporte cuáles agregaste.

**Commit:** `feat(api): declare ETag in the contract and add missing labels for the backoffice`

## Cierre
- Todo en verde, contrato y `schema.d.ts` regenerados y commiteados.
- **Docs:** API §8 (catálogos y DTO del comprador), §7 (`/auth/me`), §6 (`ETag` en el contrato) y §19 (estado público del slot).
- En `specs/TAREA-frontend-base.md`, sección "Brechas del backend", marca como resueltas las que cierra esta tarea, con el número de PR por definir.
- Entregas el **título y la descripción del PR**, en español, sin firmas.

## Precisiones acordadas
_(las agrega el agente)_

### Parte 0
- **P0.1 Dónde vive.** No hay `apps/core`; el comando va en `apps/applications` (ya tiene `refresh_application_completeness` y es la app que orquesta el expediente). La lógica está en `apps/applications/demo_data.py` y el comando (`seed_demo_data`) solo valida `DEBUG`, el asesor extra y la existencia, y después imprime.
- **P0.2 Marca de la demo.** Los clientes de demo llevan documento `9900NNNNNN` (constante `DEMO_DOCUMENT_PREFIX`) y correo `@demo.local`. Si existe alguno, el comando imprime "Los datos de demo ya existen" y no crea nada (tampoco con `--advisor-email`).
- **P0.3 Sin una transacción común.** El análisis antivirus y la completitud guardada corren al confirmar cada operación, así que la siembra no va en un solo `atomic`. Si fallara a medias, los usuarios de demo se reutilizan, pero los clientes ya creados hacen que la siguiente corrida diga que la demo existe (no se borra nada para reintentar). Los usuarios sí se crean en una transacción.
- **P0.4 Análisis inmediato.** Después de cada carga, la demo llama a `scan_document_file` (el mismo servicio de la tarea, idempotente) para poder revisar enseguida; el que se encola al confirmar no hace nada. Así también funciona dentro de las pruebas, donde los `on_commit` no corren.
- **P0.5 Usuarios.** El primer administrador se crea con `User.objects.create_user` y su `UserRole`, como el usuario de prueba del README (no hay quién lo cree); los demás, con `identity.users.create_user` (actor: ese admin), sin invitación, y después se les fija la contraseña de demo. `asesor.andres@demo.local` no tiene teléfono, para probar `advisor.phone = null` de la Parte 2. `--advisor-email` debe ser un asesor activo existente; si no, `CommandError` antes de escribir.
- **P0.6 Leasing.** No había productos de leasing sembrados: la demo crea "Leasing habitacional" (`HOUSING_LEASING`) en Bancolombia y Banco de Bogotá con `banking.services.create_product`, si no existen. Solo el hipotecario de Bancolombia tiene requisitos documentales sembrados, así que las solicitudes con documentos (`waiting` con cargas, `review` y `ready`) usan ese producto; las de otros productos no tienen slots.
- **P0.7 Reparto.** 30 solicitudes: 7 `draft`, 9 `waiting` (4 `WAITING_BUYER_DATA` y 5 `WAITING_DOCUMENTS`), 8 `review` y 6 `ready`. Cada una recorre el camino de estados desde `DRAFT` con `transition_application`. Los asesores se asignan en rueda (dos de demo más el de `--advisor-email`), así que cada uno tiene solicitudes en todas las pestañas. Tres oportunidades las origina el broker (origen `BROKER`).
- **P0.8 Cargas.** El comprador entra como en el portal: se emite un enlace, se consume y se aceptan los consentimientos vigentes; después carga. En un grupo alternativo solo carga el primer tipo (el certificado de ingresos y retenciones), que cumple el grupo. El documento de identidad va en PNG y los demás en PDF, generados en el momento.
- **P0.9 Bloqueada e inactiva.** `ready_to_file_blocked`: la última lista, ya en `READY_TO_FILE`, recibe el rechazo de un documento aprobado (motivo `OUTDATED`). `buyer_inactive`: lo único que no pasa por un servicio es mover al pasado (5 días) el `current_stage_started_at` de una solicitud en `WAITING_BUYER_DATA` cuyo comprador nunca entró; es un `update` de esa fecha, no un insert.
- **P0.10 Evaluación final.** Cada cambio de estado sube la versión y deja vieja la última evaluación bancaria; al final la demo vuelve a evaluar (`evaluate_application`) cada solicitud con producto, para que las listas sin bloqueo muestren 100 %.
- **P0.11 Enlace impreso.** Se emite al final (72 h, canal `COPY_LINK`) para una solicitud `WAITING_DOCUMENTS` de Bancolombia sin cargas, para que el portal muestre los documentos por cargar y pida los consentimientos.
- **P0.12 Inactiva por asesor (corrección pedida al cerrar la Parte 1).** Antes solo una solicitud quedaba inactiva, y era de un único asesor: el e2e y los demás no veían ninguna en su pestaña `waiting`. Ahora la primera solicitud `WAITING_BUYER_DATA` de cada asesor queda inactiva (`_mark_buyer_inactive`), y la prueba entra con la sesión de cada asesor. En la base de `:8000`, que ya tenía la demo, se movieron al pasado con la misma función SOL-000009 (asesor e2e) y SOL-000010 (Lucía), solo datos de demo; `seed_demo_data` sigue respondiendo "Los datos de demo ya existen".

### Parte 1
- **P1.1 Dónde vive la lista.** `BUYER_CATALOG_CODES` está en `apps/identity/buyer_portal.py`. Los códigos coinciden exactamente con los que validan los serializers del comprador (perfil y direcciones, ingresos, inmueble, financiación y desistimiento), más `department`, el padre de `municipality`. No apareció ningún código distinto de los de la spec. Una prueba relee esos serializers con una expresión regular y compara.
- **P1.2 Lógica compartida.** `metadata_catalog_response` en `apps/catalogs/views.py` hace la búsqueda, los filtros (`parent_code`, `parent_id`), el `ETag` y el `304`; la usan la vista interna y la del comprador. La descripción, los parámetros y las respuestas del esquema también son constantes compartidas.
- **P1.3 Código del 404.** El sistema responde `404` con `RESOURCE_NOT_FOUND` (no existe un `NOT_FOUND`); se usa ese, igual que el catálogo interno inexistente.
- **P1.4 Caché.** Las vistas del comprador ponen `Cache-Control: no-store`; la de catálogos conserva `private, no-cache`, como la interna, porque no lleva datos personales y así el navegador revalida con `If-None-Match`.
- **P1.5 Límite de consumo.** Hoy ningún `GET` del comprador tiene límite (solo el consumo del enlace, la carga y la descarga); la vista nueva hereda lo mismo que las demás: ninguno.
- **P1.6 Sesión.** Como el resto de `/buyer/*`, solo acepta la cookie del comprador: sin sesión o con la sesión interna responde `401`. Las lecturas no exigen consentimientos ni solicitud abierta.
- **P1.7 Estado público.** `PublicSlotStatus` (TextChoices con las etiquetas) y `PUBLIC_SLOT_STATUS` viven en `apps/documents/models/slot.py`, junto a `SlotStatus`; `ACTIONABLE_PUBLIC_STATUSES` son `TO_UPLOAD` y `TO_FIX`. `public_status`, `public_status_label` y `needs_action` salen del mismo `BuyerDocumentSlotSerializer`, así que llegan en la lista, el detalle y la respuesta de la carga.
- **P1.8 `role_label`.** Sale de `get_role_display` (las `TextChoices` de `ParticipantRole`) en `BuyerParticipant`, `BuyerParticipantSummary`, `BuyerSlotParticipant`, `ApplicationParticipant` y `SlotParticipant`. No se tocaron `PreviewParticipantResult` (la simulación de la lista documental, no un participante real) ni `PackageHolder` (ya trae `role_name`).

### Parte 2
- **P2.1 Asesor nulo.** `assigned_advisor` es obligatorio en el modelo, así que una solicitud siempre tiene asesor. `advisor` es `null` cuando ese asesor ya no puede entrar (desactivado o borrado): mostrar el contacto de alguien que ya no atiende confundiría al comprador. La regla está en `buyer_portal.buyer_advisor`.
- **P2.2 Forma del asesor.** `BuyerAdvisor` lleva solo `full_name` (`get_full_name`), `email` y `phone`; un teléfono vacío sale `null`.
- **P2.3 Etapas.** `apps/applications/stages.py` tiene las dos listas (`BUYER_STAGES` e `INTERNAL_STAGES`), cada una con una regla por estado (`CURRENT`, `DONE_THROUGH`, `ALL_DONE` u `HIDDEN`), y una sola función `progress_stages(track, status)`. El tipo de respuesta es el componente `ProgressStage` (`code`, `label`, `state`, `state_label`), compartido por `stages` y `progress_stages`; `state` es el enum `StateEnum` (`done`, `current`, `pending`) y sus etiquetas viven en `StageState` (TextChoices). `REJECTED` en el expediente interno es `DONE_THROUGH BANK_ANALYSIS`: sin etapa en curso.
- **P2.4 Broker.** Recibe el resumen (`ApplicationSummary`), que no cambia: no ve `progress_stages`, `stages` ni `advisor`. La sesión interna no entra a `/buyer/*` (`401`).
- **P2.5 `role_label` en `/auth/me`.** Es el `name` del rol del primer `UserRole` activo, el mismo que decide `role`; se calcula en `get_access_profile` (`AccessProfile.role_label`) y solo se agrega a `/auth/me`, no al login.

### Parte 3
- **P3.1 Helper y dónde vive.** `etag_response_headers(*codes, description=...)` está en `config/openapi.py`, porque lo usan `applications`, `identity` y `catalogs`. Devuelve un `OpenApiParameter` de cabecera con `response=[códigos]`, que drf-spectacular publica como `headers.ETag` (string, obligatoria) solo en esas respuestas, sin agregarlo a la petición.
- **P3.2 Qué vistas.** La lista no salió solo de un `grep`, porque varias vistas ponen el `ETag` a través de helpers (`_detail_response`, `self.etag`, `_status_change_response`, etc.). Corrí la suite con un plugin temporal de pytest (fuera del repo) que registró cada vista, método y código que respondió con `ETag`: son 56 respuestas (internas y del comprador), y esas mismas declara el contrato. Se declaran los códigos que de verdad la llevan, incluidos los `201` y los `204` de los `DELETE`; el `204` de la reasignación que deja al actor sin acceso no la lleva y no se declara.
- **P3.3 Catálogos.** `/metadata/bootstrap`, `/metadata/catalogs/{code}` y `/buyer/metadata/catalogs/{code}` usan otro `ETag` (la huella del contenido), con otra descripción (`CONTENT_ETAG`). Se declara en el `200` y también en el `304`, que también lo envía.
- **P3.4 Pruebas del contrato.** `tests/test_etag_contract.py` genera el esquema y exige que: toda operación con `If-Match` declare `ETag` en todos sus `2xx`; el `GET` del mismo recurso también lo declare (de ahí sale el valor para `If-Match`); `ETag` nunca sea un parámetro de la petición; y los tres catálogos lo declaren en `200` y `304`.
- **P3.5 Etiquetas: una sola fuente.** `ChoiceLabelField` (`config/serializers.py`) entrega la etiqueta de un código a partir de su `TextChoices` o de un mapa único; un código nulo da `null`. Etiquetas agregadas:
  - expediente documental: `status_label` en `DocumentSlot` (y `DocumentSlotDetail`), `CurrentFile`, `DocumentFile` (versiones) y `DocumentFileScanStatus`; `scan_status_label` en `CurrentFile`, `FileMetadata` y `DocumentFileScanStatus`; `decision_label` en `DocumentReview` y `SlotDecision` (`waiver_history`); `holder_scope_label` en `SlotDocumentType`; `status_label` en `CompletenessDocumentSlot`;
  - estados: `from_status_label` (nulo en el registro de creación) y `to_status_label` en `StatusHistory`; `target_status_label` en `AvailableAction`; `previous_status_label` y `status_label` en `StatusChange`;
  - bancos: `outcome_label` en `RuleIssue` (`blocking` y `warnings` de la evaluación) y `product_type_label` en `EligibleBankProduct` (la etiqueta del catálogo `bank_product_type`).
- **P3.6 `Outcome` sin etiquetas.** `Outcome` es un `StrEnum` del motor de reglas, sin texto. Las etiquetas van en una constante única, `OUTCOME_LABELS` en `apps/banking/rule_engine.py` (Cumple, No cumple, Faltan datos), con una prueba de que cubre todos los resultados.
- **P3.7 `RuleIssue` en tiempo de ejecución.** `blocking` y `warnings` devolvían los diccionarios de `issue()` sin pasar por `RuleIssueSerializer`, que solo documentaba el esquema. Ahora pasan por el serializer (`_issues`), para que el `outcome_label` del contrato llegue de verdad. La forma de los demás campos no cambia.
- **P3.8 Lo que no lleva etiqueta.** `CompletenessItem.code` ya trae `message`, que es el texto que se muestra. Las reglas y requisitos de configuración (`BankPolicyRule.severity`, `DocumentRequirement.participant_role`) son de administración y no están en la F1. `PackageHolder` ya trae `role_name`.
- **P3.9 Nombres estables de enums.** Los enums nuevos de las Partes 1 y 2 salían como `PublicStatusEnum` y `StateEnum`, nombres que drf-spectacular cambia si otro campo coincide. En `ENUM_NAME_OVERRIDES` quedan como `PublicSlotStatusEnum` y `ProgressStageStateEnum`. Todavía no están en `master`, así que no se rompe ningún contrato publicado.

### Cierre
- **C.1 Brechas.** En `TAREA-frontend-base.md` se marcaron como resueltas las tres que cierra esta tarea: el estado público del documento, `role_label` en `/auth/me` y `ETag` en el contrato. Las cuatro del listado las resolvió el PR #16 (ya en `master`), pero la línea 516 de esa spec pide marcarlas al agente del frontend y su worktree edita el mismo archivo; se dejan sin tocar para no chocar. La de `BuyerSlotDocumentType` (formatos y tamaño) ya está cubierta a nivel del slot (`BuyerDocumentSlot.allowed_mime_types` y `max_size_bytes`); se anota en el reporte y no se toca.
- **C.2 Base de pruebas compartida.** backend-b corre su suite contra la misma base de pruebas (`test_mvp_credit`) en el mismo Postgres. Esta tarea corrió sus pruebas con `DATABASE_NAME=mvp_credit_brechas` (base de pruebas `test_mvp_credit_brechas`), sin tocar ningún `.env`.
