# Documento de Requerimientos de Software (DRS)

## MVP: Gestión de crédito y Portal de Compradores

| Campo | Valor |
| --- | --- |
| Estado | Versión pública para revisión y modelado |
| Versión | 1.1 |
| Audiencia | Negocio, producto, UX, desarrollo y QA |
| Alcance organizacional | Una sola operación interna; sin multi-tenant |

## 1. Objetivo

Construir una plataforma para gestionar clientes y solicitudes de crédito inmobiliario. La plataforma debe permitir a los asesores realizar seguimiento operativo, revisar documentos y radicar expedientes manualmente ante los bancos. A la vez, debe ofrecer un portal de autogestión para que los compradores completen sus datos, seleccionen una alternativa de financiación, carguen documentos y consulten el avance.

El producto tiene dos interfaces conectadas por la misma base de datos:

```text
Backoffice interno -> gestiona y radica -> Banco (proceso manual)
       ^                                      |
       |                                      v
Portal de compradores <- ve avance y corrige documentos
```

## 2. Alcance del MVP

### Incluido

- Autenticación con contraseña para usuarios internos y acceso passwordless por enlace mágico para compradores.
- Roles `ADMIN`, `ADVISOR`, `INDEPENDENT_BROKER`, `CONSTRUCTION_PARTNER` y `BUYER`.
- Clientes, oportunidades comerciales, tareas y la bandeja "Mi día".
- Proyectos inmobiliarios creados por constructoras partner y validados por operación.
- Solicitudes de crédito y segundo solicitante.
- Datos financieros básicos.
- Bancos, productos y requisitos documentales configurables.
- Portal de compradores con carga documental y seguimiento mediante enlace de autogestión enviado por el broker.
- Revisión de documentos por un asesor.
- Preparación, descarga y registro de radicación manual.
- Registro manual de la respuesta bancaria, avance de etapa y notificación al comprador por portal y correo.
- Dashboard operativo y exportación CSV básica.
- Historial de estados y actividades relevantes.
- Cálculo, reparto y registro del pago de comisiones sobre créditos desembolsados.

### Fuera de alcance

- Multi-tenant comercial: no habrá facturación, configuración ni bases de datos separadas por aliado. Sí habrá aislamiento de acceso por partner y proyecto para proteger los expedientes.
- Consulta DataCrédito, score, reglas automáticas de riesgo o simulación real.
- Integración con portales, APIs o correos de los bancos.
- Seguros, SOAT, bots, calendario, Power BI y firma electrónica.
- Retenciones, impuestos y facturación de comisiones.
- Aplicación móvil nativa.

### Decisiones adoptadas para el MVP

| Decisión | Definición acordada |
| --- | --- |
| País y moneda | Colombia y pesos colombianos (COP). |
| Bancos de prueba | Bancolombia, Fondo Nacional del Ahorro (FNA) y Banco de Bogotá. |
| Producto inicial | Bancolombia: crédito hipotecario. FNA: crédito hipotecario. Banco de Bogotá: crédito de vivienda. Las tres operaciones se gestionan por radicación manual en el MVP. |
| Finalidades iniciales | Compra de vivienda nueva (incluye sobre planos), compra de vivienda usada y remodelación/mejora de vivienda. Los productos y documentos aplicables se configuran por finalidad. |
| Propiedad e inmuebles | Cada solicitud tiene un inmueble. Para vivienda nueva puede estar vinculado a un proyecto; para usada y remodelación se registra directamente. |
| Partners | Una constructora partner crea y edita sus proyectos en estado borrador. No gestiona expedientes ni documentos de compradores en este MVP. Un broker independiente solo ve el resumen de los prospectos y expedientes que capta o le asignan. |
| Carga documental | Solo el comprador carga o reemplaza sus documentos desde el portal de autogestión. El broker genera o comparte el enlace de invitación; no accede ni carga archivos. |
| Catálogos y tipificaciones | Todas las opciones funcionales, documentos y requisitos se administran en backend. El frontend nunca contiene listas ni enums de negocio; las consulta por API. |
| Estilo de API | API REST versionada; GraphQL no forma parte de este proyecto. |
| Reglas bancarias | Cada banco/producto/finalidad se configura desde backend: disponibilidad, rangos operativos, documentación y validaciones previas. No se calculan scores ni se toma una decisión automática de crédito. |
| Responsable de radicación | Todo expediente con banco seleccionado —provenga de broker o de proyecto de constructora— se asigna a un asesor. El asesor prepara, radica manualmente y registra la respuesta del banco. |
| Regla de expediente listo | Una solicitud está `READY_TO_FILE` si tiene banco/producto seleccionado y todos los documentos obligatorios están `APPROVED` o `WAIVED`. |
| Cambios tras radicación | Desde `FILED`, el comprador solo puede reemplazar documentos que el asesor haya rechazado por observación. |
| Respuesta del banco | El asesor registra manualmente cada respuesta. Una devolución, rechazo o aprobación debe incluir tipificación y mensaje visible para el comprador; la nota interna se conserva separada. |
| Comisiones | Solo se generan al desembolso, sobre el monto desembolsado y con el plan vigente del producto bancario. Si el cliente lo captó un broker, se reparte entre el asesor (porción mayor) y el broker; en cualquier otro origen, incluida la constructora, el 100% es del asesor. La constructora no recibe comisión: su beneficio es vender el inmueble. |
| Notificación inicial | Toda respuesta bancaria relevante crea una notificación en el portal y un correo transaccional. WhatsApp queda para una fase posterior. |

### Flujo operativo completo del MVP

```text
Broker capta cliente y comparte invitación
-> comprador completa autogestión y carga documentos
-> asesor revisa y deja el expediente READY_TO_FILE
-> asesor descarga ZIP y radica manualmente en el banco
-> asesor registra respuesta del banco
   -> devuelto/observado: motivo visible, notificación y corrección documental
   -> en análisis: se actualiza seguimiento
   -> rechazado: motivo visible, notificación y cierre del proceso
   -> aprobado: notificación y avance a legalización/desembolso
```

La plataforma no afirma que una radicación fue recibida ni que un crédito fue aprobado hasta que el asesor registre la evidencia o respuesta del banco. La respuesta bancaria es manual en este MVP, pero queda trazada, notificada y asociada a la radicación correcta.

## 3. Actores y permisos

| Actor | Capacidades |
| --- | --- |
| Administrador | Acceso completo; administra usuarios, partners, proyectos, bancos, productos y requisitos documentales. |
| Asesor (`ADVISOR`) | Gestiona clientes y solicitudes asignadas, tareas, documentos, radicaciones y la validación de proyectos partner. |
| Broker independiente (`INDEPENDENT_BROKER`) | Capta el cliente, crea el contacto y oportunidad inicial, envía la invitación de autogestión y consulta el resumen de estado de sus expedientes. No ve archivos ni datos financieros detallados, no carga documentos, no radica, no aprueba ni modifica catálogos. |
| Usuario de constructora (`CONSTRUCTION_PARTNER`) | Crea y edita proyectos de su constructora. No crea ni consulta expedientes de compradores, no accede a documentos, no radica ni administra catálogos. |
| Comprador (`BUYER`) | Accede únicamente a sus propios procesos, datos, documentos y estados públicos. Puede cargar documentos propios conforme a las reglas de bloqueo. |

El sistema debe aplicar las autorizaciones en el servidor. Ocultar una acción en la interfaz no es suficiente para autorizarla.

## 4. Estados de negocio

### 4.1 Oportunidad comercial

`NEW -> ASSIGNED -> CONTACTED -> IN_PROGRESS -> CONVERTED`

Estados de salida: `LOST` y `CANCELLED`.

### 4.2 Solicitud de crédito

`DRAFT -> WAITING_BUYER_DATA -> WAITING_DOCUMENTS -> DOCUMENTS_REVIEW -> READY_TO_FILE -> FILED -> FILING_VALIDATION -> CREDIT_ANALYSIS -> APPROVED -> LEGALIZATION -> DISBURSED`

Estados alternativos: `BANK_OBSERVATION`, `REJECTED`, `EXTERNAL_CREDIT_APPROVED`, `OWN_FUNDS`, `WITHDRAWN` y `CANCELLED`.

### 4.3 Documento

`PENDING -> UPLOADED -> APPROVED`

Un documento también puede estar en `REJECTED` o `WAIVED`. Un documento rechazado exige comentario.

### 4.4 Reglas de transición

- Solo el comprador puede cargar y reemplazar documentos desde el portal de autogestión; no puede aprobarlos.
- Solo el asesor o administrador puede marcar una solicitud como `READY_TO_FILE`.
- Para llegar a `READY_TO_FILE`, todos los documentos obligatorios deben estar `APPROVED` o `WAIVED`.
- Cada cambio de estado debe generar un registro de historial y una actividad en una única transacción.
- Una solicitud puede tener varias radicaciones; cada intento es un registro independiente.
- Después de `FILED`, el comprador no puede modificar datos financieros, banco, producto ni modalidad de pago. Solo puede reemplazar un documento con estado `REJECTED` por observación. El asesor conserva la facultad de gestión.

### 4.5 Respuesta bancaria y notificación

Cada respuesta se registra contra un `filing` y usa una tipificación administrada por backend: `RECEIVED`, `RETURNED`, `IN_ANALYSIS`, `APPROVED`, `REJECTED` o `OTHER`.

| Respuesta bancaria | Cambio de solicitud | Obligatorio | Comunicación al comprador |
| --- | --- | --- | --- |
| `RECEIVED` | `FILED` o `FILING_VALIDATION` | Fecha y referencia si existe. | Confirmación de que se registró la recepción reportada por el banco. |
| `RETURNED` | `BANK_OBSERVATION` y luego `WAITING_DOCUMENTS` cuando requiere corrección. | Motivo tipificado y mensaje público de corrección. | Notificación y tarea/documento a corregir. |
| `IN_ANALYSIS` | `CREDIT_ANALYSIS` | Fecha de respuesta. | Actualización de avance. |
| `APPROVED` | `APPROVED` | Condiciones ofrecidas o evidencia disponible. | Notificación de aprobación y siguiente paso de legalización. |
| `REJECTED` | `REJECTED` | Motivo tipificado y mensaje público. | Notificación de rechazo, motivo comunicado y cierre o alternativa comercial. |
| `OTHER` | No cambia automáticamente. | Explicación interna y decisión del asesor. | Solo se notifica si el asesor define mensaje público. |

El asesor puede conservar una nota interna con el texto completo del banco. Para proteger al comprador, el `buyer_reason_text` se redacta explícitamente y no se expone la nota interna ni información sensible de terceros. Toda respuesta que cambie el estado crea una actividad, historial de estado, tarea si aplica y notificación dentro de una única operación de dominio.

## 5. Requerimientos funcionales

### 5.1 Acceso y usuarios

| ID | Requerimiento | Criterio de aceptación |
| --- | --- | --- |
| RF-01 | El usuario interno debe iniciar sesión con correo y contraseña. | Con credenciales válidas accede a la interfaz correspondiente a su rol. |
| RF-02 | El comprador debe poder abrir un enlace mágico, completar el formulario de autogestión y cargar documentos sin crear cuenta ni contraseña. | El enlace contiene un token de un solo uso, vence, inicia una sesión temporal revocable y queda asociado exclusivamente a su expediente. |
| RF-03 | Debe existir recuperación de contraseña para usuarios internos. | El enlace de recuperación tiene vencimiento y permite definir una nueva contraseña. No aplica al comprador. |
| RF-04 | El administrador debe crear, activar, desactivar y asignar rol a usuarios internos. | Un usuario desactivado no puede iniciar sesión. |

### 5.2 Clientes y oportunidades

| ID | Requerimiento | Criterio de aceptación |
| --- | --- | --- |
| RF-10 | Un asesor debe crear y editar clientes. | Se valida que tipo y número de documento no se dupliquen. |
| RF-11 | El sistema debe permitir asignar un asesor a un cliente y su oportunidad. | La reasignación queda registrada en la bitácora. |
| RF-12 | Un cliente puede estar relacionado con uno o más proyectos. | Cada relación se representa como una oportunidad independiente. |
| RF-13 | El asesor debe registrar notas y actividades. | Las notas internas no se exponen al portal del comprador. |
| RF-14 | Un broker puede crear el contacto y la oportunidad inicial dentro de su propio alcance. | No puede consultar ni modificar registros de otro broker salvo que un administrador o asesor se los asigne; solo recibe un resumen, no documentos ni datos financieros detallados. |
| RF-15 | Un usuario de constructora puede crear y editar únicamente proyectos de su partner. | La API deriva el partner de su membresía y rechaza cualquier intento de usar un `partner_id` ajeno. |

### 5.2.1 Partners y proyectos

| ID | Requerimiento | Criterio de aceptación |
| --- | --- | --- |
| RF-16 | El administrador debe crear y activar constructoras partner y sus usuarios. | Un usuario partner pertenece a una única constructora activa en el MVP. |
| RF-17 | La constructora partner debe crear y editar sus proyectos en estado `DRAFT`. | Un asesor o administrador debe aprobarlos para que puedan ser asociados a nuevas oportunidades. |
| RF-18 | Todo proyecto debe guardar partner propietario, nombre, ciudad/municipio DANE, dirección o ubicación, estado y fechas relevantes. | El sistema mantiene quién creó, validó, modificó o archivó el proyecto. |

### 5.3 Mi día y tareas

| ID | Requerimiento | Criterio de aceptación |
| --- | --- | --- |
| RF-20 | El asesor debe crear tareas relacionadas con una oportunidad o solicitud. | La tarea tiene responsable, fecha, prioridad y estado; apoya el seguimiento, pero no define la bandeja principal. |
| RF-21 | "Mi día" debe mostrar exclusivamente las solicitudes de crédito asignadas al asesor autenticado. | Cada fila muestra código, cliente, banco/producto, etapa actual, siguiente acción, fecha de actualización y días en etapa. |
| RF-22 | "Mi día" debe permitir filtrar las solicitudes asignadas por etapa, banco, finalidad y atención pendiente. | Incluye como segmentos: documentos por revisar, listas para radicar, radicadas, en análisis y observadas; cada fila enlaza al expediente. |

### 5.4 Solicitudes de crédito

| ID | Requerimiento | Criterio de aceptación |
| --- | --- | --- |
| RF-30 | El asesor debe crear una solicitud a partir de un cliente y una oportunidad. | La solicitud obtiene un código único y estado inicial. |
| RF-31 | Se deben registrar monto solicitado, valor del inmueble, banco/producto, asesor y modalidad de pago. | Los cambios quedan auditados. |
| RF-32 | La solicitud debe soportar un segundo solicitante y su información financiera. | El segundo solicitante puede crearse, actualizarse o eliminarse antes de radicar. |
| RF-33 | Se debe poder registrar recursos propios o crédito externo aprobado. | Estas modalidades no exigen radicación bancaria dentro de la plataforma. |
| RF-34 | La solicitud debe registrar la finalidad `PURCHASE_NEW`, `PURCHASE_USED` o `HOME_IMPROVEMENT` y un inmueble asociado. | Para compra nueva se permite asociar un proyecto; para usada y remodelación se exige la información directa del inmueble. |
| RF-35 | La disponibilidad de banco/producto y los documentos exigidos deben evaluarse por finalidad, perfil de solicitante y condición del inmueble. | Un requisito no aplicable no bloquea la regla de expediente listo. |

### 5.5 Portal de compradores

| ID | Requerimiento | Criterio de aceptación |
| --- | --- | --- |
| RF-40 | El comprador debe consultar sus procesos activos. | Solo ve oportunidades y solicitudes asociadas a su cuenta. |
| RF-41 | El comprador debe actualizar sus datos personales y financieros. | El asesor puede consultar los cambios desde el backoffice. |
| RF-42 | El comprador debe seleccionar modalidad de financiación y, si aplica, un banco/producto habilitado. | La selección actualiza la solicitud y genera actividad. |
| RF-43 | El comprador debe cargar y reemplazar documentos solicitados. | El portal muestra cuáles faltan, fueron aprobados o necesitan corrección. |
| RF-44 | El comprador debe consultar el estado público y la siguiente acción. | No se muestran notas internas ni datos de otros clientes. |
| RF-45 | El comprador debe poder registrar un desistimiento y su motivo. | La solicitud cambia a `WITHDRAWN` y se registra la actividad. |
| RF-46 | Después de la radicación, el comprador solo puede reemplazar documentos rechazados por observación. | Los demás datos y documentos quedan bloqueados para el comprador; el asesor conserva la facultad de gestionarlos. |
| RF-47 | Solo el comprador autorizado puede cargar documentos desde su portal. | El sistema registra el comprador y la versión cargada; broker y partner no reciben endpoints de carga ni descarga. |

### 5.6 Documentos

| ID | Requerimiento | Criterio de aceptación |
| --- | --- | --- |
| RF-50 | El administrador debe administrar los tipos de documento y requisitos por banco/producto. | Un requisito puede ser obligatorio u opcional y ordenarse para el portal. |
| RF-51 | El asesor debe aprobar, rechazar o exonerar documentos. | Un rechazo requiere comentario visible para el comprador. |
| RF-52 | El asesor debe descargar un documento individual o el expediente completo. | El expediente ZIP contiene los documentos aprobados de la solicitud. |
| RF-53 | El sistema debe conservar las versiones de un documento reemplazado y la decisión de revisión sobre cada versión. | La versión previa no se elimina ni puede incluirse accidentalmente en una nueva radicación. |

### 5.7 Radicación manual

| ID | Requerimiento | Criterio de aceptación |
| --- | --- | --- |
| RF-60 | El asesor debe preparar una solicitud lista para radicar. | El sistema bloquea esta transición si faltan documentos obligatorios aprobados. |
| RF-61 | El asesor debe descargar un ZIP del expediente. | La descarga queda registrada en la bitácora. |
| RF-62 | El asesor debe registrar una radicación manual. | Guarda banco/producto, canal, fecha, responsable y número de referencia si existe. |
| RF-63 | El asesor debe registrar una o varias respuestas de una radicación. | Guarda tipificación, fecha, referencia, motivo interno, motivo visible y evidencia cuando exista. |
| RF-64 | Una devolución bancaria debe crear el motivo visible, la tarea de corrección y el cambio de etapa correspondiente. | El comprador recibe notificación en portal y correo; solo puede corregir los documentos observados. |
| RF-65 | Un rechazo o aprobación bancaria debe avanzar/cerrar la solicitud con trazabilidad. | La notificación al comprador incluye resultado y mensaje público; la nota interna no se expone. |

### 5.8 Dashboard y reportes

| ID | Requerimiento | Criterio de aceptación |
| --- | --- | --- |
| RF-70 | El dashboard debe mostrar el embudo operativo. | Incluye clientes, documentos completos, listos para radicar, radicados, aprobados y desembolsados. |
| RF-71 | El dashboard debe mostrar tareas vencidas y para hoy. | Los valores cambian según el rol y alcance del usuario. |
| RF-72 | El usuario debe filtrar reportes por fechas, asesor, banco y estado. | Los resultados se pueden exportar a CSV. |
| RF-73 | El comprador debe consultar sus notificaciones y marcar las leídas. | Ve resultado bancario, siguiente acción y fecha, sin notas internas. |

### 5.9 Comisiones

| ID | Requerimiento | Criterio de aceptación |
| --- | --- | --- |
| RF-80 | El administrador debe configurar planes de comisión por producto bancario. | Cada plan define porcentaje sobre el monto desembolsado, reparto asesor/broker y vigencia; no se permiten vigencias solapadas para el mismo producto. |
| RF-81 | El sistema debe liquidar la comisión cuando la solicitud pasa a `DISBURSED`. | Usa el monto desembolsado y el plan vigente en la fecha de desembolso; una aprobación sin desembolso no genera comisión. |
| RF-82 | La comisión debe repartirse según el origen de la oportunidad. | Origen broker: asesor (porción mayor) y broker según el plan. Cualquier otro origen, incluida la constructora: 100% al asesor. |
| RF-83 | La liquidación debe ser única e inmutable. | Un evento repetido no genera doble comisión; base, tasa y porcentajes se copian a la liquidación y no cambian si el plan cambia. |
| RF-84 | El administrador debe registrar el pago de cada parte por separado. | Guarda fecha, referencia y responsable; queda en auditoría. |
| RF-85 | Una corrección del desembolso debe reflejarse en la comisión. | Sin pagos: se anula y se recalcula. Con algún pago: se marca para revisión manual. |
| RF-86 | Asesores y brokers deben consultar solo sus propias comisiones. | El broker no ve monto base, tasa, total ni la parte del asesor. |

## 6. Vistas del producto

### Operación, brokers y partners: 14 vistas

1. Login interno.
2. Dashboard.
3. Mi día.
4. Listado de clientes.
5. Crear/editar cliente.
6. Detalle de cliente.
7. Listado de solicitudes.
8. Espacio de trabajo de solicitud: datos, financiación, documentos, actividad y estados.
9. Radicación manual.
10. Reportes.
11. Administración de usuarios.
12. Listado y detalle de proyectos.
13. Administración de partners y usuarios partner.
14. Catálogos: bancos, productos y requisitos documentales.

Las vistas son una misma aplicación Next.js con navegación condicionada por rol. Broker y partner no requieren un tercer frontend: el broker recibe su bandeja de prospectos, enlace de invitación y resumen de estados; la constructora recibe la administración de sus proyectos. La creación de proyecto aparece solo para `CONSTRUCTION_PARTNER`, asesor y administrador; la aprobación del proyecto solo para asesor y administrador. El detalle financiero, los archivos y la radicación se reservan para comprador, asesor y administrador según la acción.

### Portal de compradores: 8 vistas

1. Acceso por enlace mágico vencible y formulario de autogestión.
2. Mis procesos.
3. Tablero del proceso.
4. Datos financieros.
5. Segundo solicitante.
6. Financiación.
7. Documentos.
8. Seguimiento, notificaciones, desistimiento y contacto.

## 7. Modelo de datos inicial

El modelo se ajusta a **41 tablas de dominio, catálogo y seguridad**. No cuenta las tablas técnicas que Django cree para migraciones, permisos y administración; estas deben permanecer bajo control de las migraciones. `users` representa únicamente usuarios internos; el comprador es un `client` que accede con enlace mágico y sesión temporal, sin cuenta ni contraseña.

| Grupo | Tabla | Responsabilidad y campos clave |
| --- | --- | --- |
| Identidad | `users` | Usuario interno autenticable: correo único normalizado, hash de contraseña, activo, nombre, teléfono, último acceso. |
| Identidad | `roles` / `user_roles` | RBAC explícito para usuarios internos: `ADMIN`, `ADVISOR`, `INDEPENDENT_BROKER`, `CONSTRUCTION_PARTNER`. |
| Identidad | `auth_sessions` | Refresh token hasheado para usuarios internos: usuario, expiración, revocación, IP y dispositivo resumido. |
| Identidad | `invitations` | Invitación a usuario interno, por ejemplo de partner; token hasheado, rol, destinatario, vencimiento y uso único. |
| Identidad | `buyer_access_links` | Enlace mágico: cliente, expediente, token hasheado, vencimiento, consumo, emisor y revocación. No contiene contraseña. |
| Identidad | `buyer_sessions` | Sesión temporal revocable creada al consumir un enlace mágico: cliente, expediente, token hasheado, expiración, IP y dispositivo resumido. |
| Identidad | `password_reset_tokens` | Token hasheado, usuario, vencimiento, consumo y auditoría del restablecimiento. |
| Identidad | `consent_records` | Tratamiento de datos y consentimientos: texto/versión, actor, IP, fecha, evidencia y retiro cuando aplique. |
| Partners | `partners` | Constructora partner: razón social, NIT, estado, datos de contacto. No es un tenant. |
| Partners | `partner_memberships` | Usuario partner, partner, estado y fechas; MVP: una membresía activa por usuario partner. |
| Comercial | `projects` | Proyecto: partner propietario, nombre, estado `DRAFT/ACTIVE/ARCHIVED`, ubicación, municipio DANE, creador y validador. |
| Comercial | `clients` | Persona interesada: identidad, nombres, datos de contacto y consentimiento. No requiere usuario ni contraseña para autogestionarse. |
| Comercial | `client_addresses` | Dirección normalizada del cliente y del inmueble cuando aplique, con código municipal/DANE configurable. |
| Comercial | `opportunities` | Relación comercial cliente-proyecto opcional, broker/origen, asesor asignado, estado y fecha de conversión. |
| Crédito | `credit_applications` | Expediente: código legible, oportunidad, finalidad, banco/producto, asesor, estado, versión de concurrencia y fechas. |
| Crédito | `application_participants` | Personas de la solicitud: `PRIMARY`, `CO_APPLICANT` o `SOLIDARY_DEBTOR`, aporte de ingresos y estado. Sustituye una tabla rígida de segundo solicitante. |
| Crédito | `financial_profiles` | Perfil financiero por participante y solicitud: empleo, contrato, antigüedad, ingresos, gastos, activos, pasivos y origen de fondos. |
| Crédito | `income_sources` | Fuentes de ingreso por perfil; permite varios empleos/ingresos sin columnas repetidas. |
| Crédito | `properties` | Inmueble de la solicitud: tipo, condición nueva/usada/sobre planos, ubicación, valor, proyecto opcional, unidad y datos de propiedad/remodelación. |
| Crédito | `financing_preferences` | Monto, plazo, moneda, amortización, cesantías, aporte propio y modalidad de financiación. |
| Catálogos | `banks` | Entidades financieras disponibles y estado. |
| Catálogos | `bank_products` | Producto por banco, estado y reglas de disponibilidad. |
| Catálogos | `bank_product_purposes` | Finalidades admitidas por producto: nueva, usada o remodelación. |
| Catálogos | `bank_policy_rules` | Reglas configurables y versionadas por banco/producto/finalidad: requisito de datos, rango, condición del inmueble o advertencia/bloqueo. El backend solo permite tipos de regla previamente soportados. |
| Catálogos | `catalogs` | Definición de cada tipificación: código técnico, nombre, descripción, alcance, si es administrable y versión. |
| Catálogos | `catalog_items` | Ítem configurable: código estable, etiqueta, descripción, orden, activo, metadatos y dependencias. Contiene finalidades, estados visibles, tipos de inmueble, perfiles laborales, prioridades, canales, motivos y demás opciones de negocio. |
| Catálogos | `workflow_transitions` | Acción/transición permitida: tipo de flujo, estado origen/destino, roles autorizados, condición y etiqueta a mostrar. |
| Catálogos | `document_types` | Tipo documental configurable desde backend: código, etiqueta, formato permitido, tamaño máximo y estado. |
| Catálogos | `document_requirements` | Regla versionada por banco/producto/finalidad/perfil: obligatoriedad, grupo alternativo, mínimo, vigencia y orden. |
| Expediente | `application_document_slots` | Instantánea de cada requisito al crearse/actualizarse el checklist: estado, regla origen/versionada, exención, observación y revisor. |
| Expediente | `document_files` | Cada archivo/version: slot, objeto privado, hash SHA-256, tamaño, MIME detectado, resultado antivirus, cargador, fecha y estado. |
| Operación | `tasks` | Trabajo asociado a oportunidad o solicitud: responsable, vencimiento, prioridad, estado y origen. |
| Operación | `activity_logs` | Línea de tiempo de negocio, notas internas/públicas y actor. |
| Operación | `application_status_history` | Transición inmutable: estado anterior/nuevo, actor, motivo y marca de tiempo. |
| Radicación | `filings` | Intento manual: solicitud, banco/producto, canal, responsable, referencia, estado, fechas objetivo y reales. |
| Radicación | `filing_responses` | Cada respuesta manual del banco: tipo, fecha, referencia, motivo tipificado, mensaje interno, mensaje público, actor y evidencia opcional. |
| Radicación | `filing_document_snapshots` | Evidencia exacta de los archivos/versiones aprobados incluidos en cada paquete radicado. |
| Plataforma | `idempotency_keys` | Clave, usuario, endpoint, hash de petición, respuesta y vencimiento para POST críticos. |
| Plataforma | `notifications` | Notificación de dominio: destinatario, tipo, canal, título, mensaje público, recurso relacionado, estado de lectura/envío y fechas. |
| Plataforma | `audit_events` | Registro técnico inmutable de accesos y mutaciones sensibles: actor, recurso, IP, `request_id`, resultado y metadatos minimizados. |

### Relaciones y restricciones críticas

```text
partner -> project -> opportunity -> credit_application -> property
user (broker/partner/advisor) -> opportunity/application según asignación
client -> opportunity; credit_application -> application_participants -> financial_profile -> income_sources
credit_application -> document_slots -> document_files
bank -> bank_product -> bank_product_purposes + bank_policy_rules + document_requirements -> document_slots (instantánea)
catalogs -> catalog_items; workflow_transitions -> catalog_items de estados y acciones
credit_application -> filings -> filing_document_snapshots
filing -> filing_responses -> notifications (portal y correo)
client -> buyer_access_links -> buyer_sessions; partner user -> partner_membership -> partner -> project
```

- Una solicitud tiene exactamente un inmueble y al menos un participante `PRIMARY`.
- `PURCHASE_NEW` permite proyecto y unidad; `PURCHASE_USED` no exige proyecto; `HOME_IMPROVEMENT` exige dirección/propiedad del inmueble y presupuesto/soportes solo cuando la regla bancaria los solicite.
- Un partner no puede tener relaciones de datos que apunten a proyectos de otro partner. Esta restricción se verifica tanto en servicio de dominio como en filtros de consulta.
- Las tipificaciones de negocio se referencian por `catalog_items`, no mediante enums del frontend ni listas codificadas en componentes. Los códigos estables sirven para reglas del backend; la etiqueta, orden y visibilidad son datos administrables.
- `bank_policy_rules` permite configurar solo reglas predefinidas por el backend (por ejemplo, finalidad admitida, rango de monto/plazo, condición de inmueble o dato/documento requerido). No admite fórmulas arbitrarias ni reemplaza la decisión crediticia del banco.
- `document_requirements` es una plantilla. La aplicación nunca debe reevaluar reglas históricas directamente desde la plantilla: usa `application_document_slots` para preservar qué se exigía al momento de radicar.
- Un reemplazo crea un nuevo `document_files`; no sobrescribe, borra ni modifica la versión previa. Solo la versión limpia y aprobada puede entrar a un `filing_document_snapshot`.
- Una respuesta bancaria no se sobrescribe: cada comunicación se agrega en `filing_responses`. El mensaje al comprador se conserva en `notifications`, aun si el correo falla y debe reintentarse.
- Todas las tablas tienen UUID, `created_at`, `updated_at`; las entidades de negocio relevantes usan `deleted_at` cuando el borrado lógico sea válido. Los eventos, estados, archivos y radicaciones no se borran lógicamente ni físicamente desde la aplicación.
- Las restricciones únicas deben incluir como mínimo: correo normalizado de usuario, número de documento de cliente según tipo, código de solicitud, referencia de radicación cuando el banco la suministre y una clave de idempotencia por usuario/endpoint.

## 7.1 Configuración bancaria inicial: Bancolombia y FNA

Esta sección transforma la información recibida en reglas iniciales del MVP. No debe interpretarse como una política crediticia definitiva: los documentos, condiciones y tiempos deben validarse con la entidad o con el convenio comercial vigente antes de operar en producción.

### Reglas bancarias configurables desde el inicio

Sí conviene crearlas desde este MVP. No para predecir una aprobación, sino para impedir que operación prepare un expediente incompatible o incompleto. Cada regla pertenece a banco, producto y finalidad, tiene vigencia, estado y severidad `WARNING` o `BLOCKING`.

| Tipo de regla permitida | Ejemplo de uso |
| --- | --- |
| Finalidad y condición de inmueble | Determinar que un producto admite vivienda nueva, usada o remodelación. |
| Rango operativo | Validar monto solicitado, valor de inmueble o plazo dentro de los rangos publicados/configurados. |
| Datos requeridos | Exigir ciudad, valor de inmueble, modalidad de pago o perfil laboral antes de preparar el expediente. |
| Documento requerido | Activar documentos por banco/producto/finalidad/perfil mediante `document_requirements`. |
| Observación operativa | Mostrar advertencia al asesor sin bloquear la radicación, por ejemplo una vigencia próxima a vencer. |

La evaluación se ejecuta al seleccionar banco/producto y de nuevo antes de `READY_TO_FILE`. El resultado devuelve bloqueos y advertencias a la interfaz, pero no sustituye el análisis ni la decisión final del banco. Agregar un banco nuevo implica crear su banco, producto, reglas y documentos desde backend; no cambiar enums ni desplegar el frontend.

### Datos de vivienda y financiación requeridos

La solicitud debe capturar los siguientes datos adicionales:

| Dato | Valores iniciales |
| --- | --- |
| Tipo de inmueble | Casa, apartamento. |
| Estado del inmueble | Nueva, usada, sobre planos. |
| Finalidad | `PURCHASE_NEW`, `PURCHASE_USED`, `HOME_IMPROVEMENT`. Compra nueva admite sobre planos. Compra de cartera y construcción en sitio propio quedan fuera del MVP. |
| Producto | Crédito hipotecario o leasing habitacional. |
| Modalidad monetaria | Pesos o UVR. |
| Modalidad de amortización | Catálogo configurable. |
| Uso de cesantías | Sí/No y valor estimado. |
| Solicitud conjunta | Sí/No; si es sí, se exige al menos un segundo solicitante con soportes de ingreso. |

### Checklist documental inicial para Bancolombia

| Perfil | Documentos requeridos o alternativos |
| --- | --- |
| Todos | Copia de documento de identidad; la operación debe permitir marcar si requiere huella y firma física. |
| Todos | Certificado de ingresos y retenciones **o** declaración de renta del último año gravable, cuando aplique. |
| Empleado | Certificación laboral con salario, fecha de ingreso, cargo y tipo de contrato; vigencia inicial máxima: 30 días. |
| Empleado | Tres comprobantes o desprendibles de nómina. |
| Independiente | Extractos bancarios de los últimos tres meses y soportes de actividad/ingresos. |
| Pensionado | Certificación de pensión y tres comprobantes de pago. |

El número de documentos, vigencias y alternativas debe quedar configurado en `document_requirements`, no codificado en la interfaz.

### Catálogo documental inicial del MVP

El siguiente es el catálogo de 17 tipos documentales que se debe sembrar inicialmente. Una fila marcada como "configurable" existe en el sistema, pero no debe bloquear la radicación hasta recibir el anexo oficial aplicable del banco y producto.

`INCOME_TAX_PROOF` no es un tipo documental: es el `alternative_group_code` que comparten los requisitos de `INCOME_RETENTION_CERTIFICATE` e `INCOME_TAX_RETURN`. Basta con aportar uno de los dos, y el grupo es exonerable (`is_waivable = true`) para cubrir el "cuando aplique".

| Código | Documento o evidencia | Aplica a | Regla inicial |
| --- | --- | --- | --- |
| `IDENTITY_DOCUMENT` | Copia del documento de identidad | Todos los solicitantes; Bancolombia | Obligatorio. El formulario debe permitir registrar si la copia requiere huella y firma física. |
| `INCOME_RETENTION_CERTIFICATE` | Certificado de ingresos y retenciones del último año gravable | Todos los solicitantes; Bancolombia | Grupo alternativo `INCOME_TAX_PROOF` con `INCOME_TAX_RETURN`: basta uno. Exonerable cuando no aplique. |
| `INCOME_TAX_RETURN` | Declaración de renta del último año gravable | Todos los solicitantes; Bancolombia | Grupo alternativo `INCOME_TAX_PROOF` con `INCOME_RETENTION_CERTIFICATE`: basta uno. Exonerable cuando no aplique. |
| `EMPLOYMENT_CERTIFICATE` | Certificación laboral | Asalariado; Bancolombia | Obligatorio. Debe indicar salario, cargo, fecha de ingreso y tipo de contrato. Vigencia inicial máxima: 30 días. |
| `PAYROLL_SLIP` | Desprendible o comprobante de nómina | Asalariado; Bancolombia | Obligatorio. Mínimo tres documentos. |
| `BANK_STATEMENT` | Extracto bancario | Independiente; Bancolombia | Obligatorio. Mínimo tres meses. |
| `INDEPENDENT_INCOME_SUPPORT` | Soporte de actividad e ingresos | Independiente; Bancolombia | Obligatorio. Puede ser contrato, certificación o soporte equivalente validado por el asesor. |
| `PENSION_CERTIFICATE` | Certificación de entidad pagadora de pensión | Pensionado; Bancolombia | Obligatorio. |
| `PENSION_PAYMENT_SLIP` | Comprobante de pago de pensión | Pensionado; Bancolombia | Obligatorio. Mínimo tres documentos. |
| `CO_APPLICANT_INCOME_SUPPORT` | Soportes de ingresos del segundo solicitante | Solicitud conjunta; FNA y Bancolombia | Obligatorio para cada solicitante que aporta ingresos. |
| `EXTERNAL_APPROVAL_LETTER` | Carta de aprobación externa | Modalidad `EXTERNAL_CREDIT_APPROVED` | Obligatorio para finalizar esa modalidad. |
| `PROPERTY_ANALYSIS_DOCUMENTS` | Soportes del inmueble para análisis/legalización | FNA | Configurable. El FNA informa requisitos por finalidad: vivienda nueva/usada, leasing, construcción, mejora o compra de cartera. Se activa al recibir el anexo oficial aplicable. |
| `TITLE_STUDY_DOCUMENTS` | Documentos para estudio de títulos | FNA | Configurable; corresponde a la etapa de legalización. |
| `DEED_SIGNATURE_DOCUMENTS` | Documentos para firma de escritura | FNA | Configurable; corresponde a la etapa de legalización. |
| `REGISTRATION_DOCUMENTS` | Escritura registrada y soportes de registro | FNA | Configurable; se exige antes de desembolso cuando aplique. |
| `PROPERTY_OWNERSHIP_DOCUMENT` | Documento de propiedad o soporte equivalente | Remodelación | Configurable por banco/producto; se exige cuando la regla aplicable lo indique. |
| `REMODELING_BUDGET` | Presupuesto, cotización o soporte técnico de la obra | Remodelación | Configurable por banco/producto; no se presume obligatorio para todos los bancos. |

### Etapas operativas iniciales del FNA

| Estado del sistema | Etapa FNA de referencia | Tiempo de referencia |
| --- | --- | --- |
| `WAITING_DOCUMENTS` / `DOCUMENTS_REVIEW` | Asesoría y recepción de soportes | 1 hora de asesoría |
| `FILED` / `FILING_VALIDATION` | Radicación y validación de formulario/documentos | 7 días |
| `CREDIT_ANALYSIS` | Análisis y oferta de crédito o leasing | 6 días |
| `LEGALIZATION` | Avalúo, estudio de títulos, notaría y registro | 84 días |
| `DISBURSED` | Giro del crédito | 3 días |

Los tiempos son referencias de seguimiento, no compromisos del sistema. Cada radicación debe poder guardar una fecha objetivo calculada y una fecha real de respuesta.

Fuentes para validación: [formulario de financiación inmobiliaria de Bancolombia](https://formulariosdigitales.bancolombia.com/content/forms/af/bancolombia/personas-y-pymes/credito-hipotecario/t160612/F-3112.html) y [etapas/condiciones de crédito del FNA](https://www.fna.gov.co/personas/vivienda/herramientas-tramites/condiciones-de-credito).

## 8. Arquitectura y diseño de la API REST

### 8.1 Decisión de arquitectura

El backend es un **monolito modular en Django + Django REST Framework**, con PostgreSQL. Es la decisión adecuada para el MVP porque el riesgo principal está en la consistencia de expedientes, permisos, documentos y auditoría, no en cómputo asíncrono masivo. Los módulos se despliegan juntos, comparten una única transacción de base de datos y se separan por límites de dominio para evitar acoplamiento.

FastAPI no hace parte de este MVP. No se crean microservicios ni conectores bancarios: el alcance termina en la preparación del expediente, la radicación manual y el registro de la respuesta del banco.

### 8.2 Arquitectura lógica y despliegue

```text
Usuarios (admin, asesor, broker, partner, comprador)
                     |
                  Next.js
          Backoffice + portal comprador
                     |
          CDN/WAF + HTTPS + rate limiting perimetral
                     |
         Django REST Framework: /api/v1
   ┌─────────────────┼──────────────────────┐
   │                 │                      │
módulos de       PostgreSQL              Redis
dominio          datos y auditoría       límites, caché y colas
   │                 │                      │
   ├──────── almacenamiento privado de documentos ── antivirus
   ├──────── worker asíncrono: ZIP, correo, exportaciones
```

La API es la única capa que accede a datos y documentos. Next.js nunca recibe secretos, URLs privadas permanentes o permisos de base de datos.

Módulos de backend:

| Módulo | Responsabilidad |
| --- | --- |
| `identity` | Usuarios internos, roles, permisos, sesiones, invitaciones internas, enlaces mágicos de comprador, consentimientos y autorización. |
| `partners` | Constructoras, membresías y proyectos. |
| `crm` | Clientes, direcciones, oportunidades, asignaciones, tareas, notas, actividad funcional y Mi día. |
| `catalogs` | Catálogos y tipificaciones configurables, además de transiciones de flujo reutilizables. |
| `banking` | Bancos, productos, finalidades admitidas, reglas operativas y evaluaciones bancarias. |
| `applications` | Solicitud de crédito, participantes, finanzas, ingresos, inmueble, financiación, asignaciones e historial de estados. |
| `documents` | Tipos y requisitos documentales, plantillas, slots, versiones, análisis de archivos, revisiones y paquetes ZIP. |
| `filings` | Preparación, radicación manual, respuesta y evidencia del expediente enviado. |
| `notifications` | Notificaciones de portal, entregas por correo y eventos outbox para tareas asíncronas. |
| `reporting` | Dashboard, filtros y exportaciones. |
| `audit` | Auditoría técnica inmutable, `request_id`, trazabilidad y retención. |

### 8.3 Principios de dominio que debe imponer la API

1. **Autorización antes de consulta.** Cada queryset nace filtrado por el alcance del actor. No basta verificar permisos después de buscar por UUID.
2. **Servicios de dominio para cambios críticos.** Transiciones, aprobación de documentos, cálculo de checklist y radicación no viven en controladores HTTP ni en componentes Next.js.
3. **Transacciones atómicas.** Un cambio de estado, su historial, actividad y tareas resultantes se persisten juntos o no se persiste ninguno.
4. **Instantáneas inmutables.** El checklist se congela en slots y la radicación conserva las versiones de archivo incluidas.
5. **Idempotencia.** Toda creación que pueda repetirse por reintento de red, especialmente radicaciones y transiciones, requiere `Idempotency-Key`.
6. **Concurrencia explícita.** `credit_applications` usa un entero `version`; `PATCH` y acciones críticas reciben `If-Match` o la versión esperada y devuelven `409 CONFLICT` ante edición obsoleta.
7. **Asincronía solo para tareas no transaccionales.** Escaneo de archivos, creación de ZIP, correos y CSV se encolan después de confirmar la transacción mediante patrón outbox o tarea posterior al commit.

### 8.4 Convenciones REST

- Prefijo obligatorio: `/api/v1`; no se mezclan rutas internas sin versión.
- JSON en solicitudes y respuestas; `multipart/form-data` únicamente para el binario de una carga documental.
- UUID para recursos; códigos humanos de cliente, oportunidad y solicitud son de consulta, nunca autorización.
- Fechas en ISO-8601 UTC; la interfaz convierte a `America/Bogota`. Valores monetarios en COP se expresan como entero de pesos, nunca `float`.
- Paginación por defecto `page=1&page_size=25`, máximo 100. Listas incluyen `items`, `page`, `page_size`, `total` y `next`.
- Filtros y ordenamientos se permiten por lista blanca. Ejemplo: `?status=READY_TO_FILE&bank_id=...&assigned_to=...&ordering=-created_at`.
- `GET` no modifica estado. `PATCH` cambia campos editables; las reglas de negocio se exponen como acciones con verbo explícito (`/review`, `/transitions`, `/validate`).
- Creaciones devuelven `201`; trabajos asíncronos `202` y un recurso consultable; borrados lógicos `204` solo cuando estén permitidos; violaciones de estado o versión `409`; permisos/alcance `403` o `404` según la política de no revelar existencia.
- Error homogéneo: `{ "code": "DOCUMENT_NOT_READY", "message": "...", "details": [...], "request_id": "uuid" }`.
- OpenAPI 3.1 es un artefacto versionado del repositorio. Cada endpoint debe incluir esquema, ejemplos, códigos de error, autenticación y permisos.

### 8.5 Catálogos, tipificaciones y formularios dirigidos por backend

El frontend Next.js **no define enums, listas de selección, requisitos documentales ni transiciones de estados de negocio**. Debe renderizar las opciones que recibe desde la API. Esta regla aplica a finalidad, tipo/condición de inmueble, perfil laboral, tipo de contrato, tipo de ingreso, estados visibles, prioridades, canales, motivos de rechazo/desistimiento, bancos, productos, documentos y demás tipificaciones.

- El administrador crea, activa, ordena, desactiva y versiona los `catalog_items` desde los endpoints administrativos. No se elimina un ítem que tenga expedientes históricos: se marca inactivo.
- Un ítem usa un `code` estable para reglas del backend y una `label`/descripción editable para presentación. El frontend no compara etiquetas ni mantiene equivalentes en TypeScript.
- Las reglas críticas —por ejemplo, que `READY_TO_FILE` requiere slots aprobados— permanecen en servicios de dominio. Hacer configurable una etiqueta no permite debilitar una política de crédito ni autorización.
- `document_types` y `document_requirements` también se administran solo en backend. El portal consulta los `application_document_slots` calculados; no decide qué documento exigir ni qué grupo alternativo está satisfecho.
- `GET /metadata/bootstrap` devuelve los catálogos necesarios para la sesión, permisos funcionales, versión de metadatos y configuración pública. `GET /metadata/catalogs/{catalog_code}` permite cargar catálogos grandes o dependientes bajo demanda.
- Los formularios reciben un esquema de campo desde backend: código, etiqueta, tipo de entrada, obligatorio, catálogo origen, validaciones de presentación y dependencia. La API vuelve a validar todo; el esquema no reemplaza las validaciones de dominio.
- Las respuestas incluyen `ETag` o `metadata_version` para que Next.js pueda cachear y refrescar los catálogos sin desplegar una nueva versión cuando negocio cambie una tipificación.

Ejemplo reducido de metadato que consume el frontend:

```json
{
  "catalog": "loan_purpose",
  "version": 12,
  "items": [
    { "id": "uuid", "code": "PURCHASE_NEW", "label": "Vivienda nueva", "active": true, "order": 1 },
    { "id": "uuid", "code": "HOME_IMPROVEMENT", "label": "Remodelación", "active": true, "order": 3 }
  ]
}
```

### 8.6 Matriz de alcance por actor

| Recurso/acción | Admin | Asesor | Broker | Partner constructor | Comprador |
| --- | --- | --- | --- | --- | --- |
| Usuarios, roles, bancos y requisitos | Administrar | Lectura selectiva | No | No | No |
| Partner y proyectos | Administrar/validar | Validar y consultar | No | Crear/editar propios | Lectura de proyecto relacionado si aplica |
| Clientes y oportunidades | Todo | Asignados | Contactos/prospectos propios y resumen | No | Solo su proceso |
| Solicitud y datos financieros | Todo | Asignadas | Solo resumen de estado de oportunidades propias | No | Solo propia, antes de `FILED` |
| Cargar documento | No | No | No | No | Propio |
| Aprobar/rechazar/exonerar documento | Sí | Sí | No | No | No |
| Crear/actualizar radicación | Sí | Sí | No | No | No |
| Notas internas / auditoría | Sí | Alcance asignado | No | No | No |
| Comisiones | Planes, liquidación y pagos | Solo su parte | Solo su parte | No | No |

El servidor calcula el alcance desde `request.user`, membresía partner, asignaciones y relaciones de expediente. Ningún `partner_id`, `client_id` o `user_id` que venga del frontend amplía privilegios.

### 8.7 Recursos y endpoints principales

| Área | Endpoints representativos |
| --- | --- |
| Sesión interna | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/password-reset-requests`, `POST /auth/password-resets/confirm` |
| Acceso comprador | `POST /buyer-access-links`, `POST /buyer-access/consume`, `POST /buyer-sessions/logout` |
| Invitaciones internas | `POST /invitations`, `POST /invitations/accept` |
| Usuarios y partners | `GET/POST /users`, `GET/PATCH /users/{id}`, `GET/POST /partners`, `GET/PATCH /partners/{id}`, `POST /partners/{id}/members` |
| Proyectos | `GET/POST /projects`, `GET/PATCH /projects/{id}`, `POST /projects/{id}/activate`, `POST /projects/{id}/archive` |
| CRM y broker | `GET/POST /clients`, `GET/PATCH /clients/{id}`, `GET/POST /opportunities`, `POST /opportunities/{id}/assignments`, `GET /broker/opportunities`, `GET/POST /tasks`, `PATCH /tasks/{id}` |
| Operación | `GET /workday/applications?stage=...&bank_id=...&purpose=...&attention=...`; la API siempre filtra por el asesor asignado autenticado. |
| Solicitudes | `GET/POST /applications`, `GET/PATCH /applications/{id}`, `POST /applications/{id}/participants`, `PATCH /application-participants/{id}`, `PUT /applications/{id}/property`, `PUT /applications/{id}/financing`, `POST /applications/{id}/status-transitions` |
| Checklist y archivos | `GET /applications/{id}/document-slots`, `POST /applications/{id}/document-slots/refresh`, `POST /document-slots/{id}/uploads`, `PATCH /document-slots/{id}/review`, `GET /document-files/{id}/download`, `POST /applications/{id}/document-package-jobs` |
| Radicación | `GET/POST /applications/{id}/filings`, `GET/PATCH /filings/{id}`, `GET/POST /filings/{id}/responses` |
| Comprador | `GET /buyer/processes`, `GET /buyer/applications/{id}`, `PATCH /buyer/applications/{id}/profile`, `PATCH /buyer/applications/{id}/financial-profile`, `GET /buyer/notifications`, `PATCH /buyer/notifications/{id}/read`, `POST /buyer/applications/{id}/withdrawals` |
| Metadatos | `GET /metadata/bootstrap`, `GET /metadata/catalogs/{catalog_code}`, `GET /applications/{id}/available-actions`, `GET /applications/{id}/document-slots` |
| Catálogos administrativos/reportes | `GET/POST/PATCH /catalogs`, `/catalog-items`, `/banks`, `/bank-products`, `/bank-policy-rules`, `/document-types`, `/document-requirements`; `GET /reports/funnel`, `GET /reports/applications.csv` |

Los endpoints de comprador derivan cliente y expediente de la `buyer_session` creada por el enlace mágico; no aceptan un `client_id` ni un `application_id` como autorización suficiente. Los endpoints de partner no permiten seleccionar otro partner: se deriva de la membresía activa. El broker no tiene rutas para descargar archivos ni para recibir datos financieros detallados.

### 8.8 Flujos REST críticos

#### Creación y preparación

```text
broker/asesor crea contacto y oportunidad
-> asesor crea o completa la solicitud con finalidad e inmueble
-> broker crea un buyer access link y lo comparte con el comprador
-> comprador consume el enlace mágico; la URL se limpia y se crea sesión temporal
-> API valida banco/producto aplicable
-> genera slots del checklist como instantánea
-> comprador completa datos y carga archivos desde el enlace de autogestión
-> antivirus marca archivo CLEAN
-> asesor aprueba, rechaza o exonera slots
-> servicio de dominio verifica READY_TO_FILE
```

La acción `POST /applications/{id}/status-transitions` recibe `target_status`, `reason` y la `version` esperada. El servidor determina si la transición está permitida; el frontend nunca manda un estado directamente por `PATCH`.

#### Documento y observación

```text
POST /document-slots/{slot_id}/uploads
-> archivo en cuarentena (PENDING_SCAN)
-> worker valida tipo/tamaño, calcula hash y analiza malware
-> CLEAN o REJECTED_BY_SCAN
-> asesor revisa slot: APPROVED / REJECTED / WAIVED
-> si REJECTED, crea observación visible y habilita solo ese slot
```

Tras `FILED`, el endpoint de carga verifica que el slot esté `REJECTED` por una observación abierta y que el actor sea el comprador del expediente. Una carga aceptada no altera la evidencia de una radicación pasada.

#### Radicación manual

```text
POST /applications/{id}/document-package-jobs
-> worker genera ZIP de versiones aprobadas
-> asesor descarga y radica fuera de la plataforma
-> POST /applications/{id}/filings (Idempotency-Key)
-> se guarda canal, referencia, responsable y snapshot de archivos
-> POST /filings/{id}/responses registra respuesta, motivo interno y mensaje público
-> transición de solicitud, tarea siguiente y notificación portal/correo en una transacción
```

No se puede crear `filings` si el servicio de dominio no confirma `READY_TO_FILE`. Si una misma clave de idempotencia llega con un cuerpo distinto, se responde `422`; si es idéntico, se devuelve la respuesta original sin crear otra radicación.

Una respuesta `RETURNED` crea la corrección solicitada y devuelve el expediente a preparación documental; una respuesta `REJECTED` lo lleva a rechazo; una respuesta `APPROVED` lo lleva a aprobación y habilita el seguimiento de legalización. El envío de correo se realiza por worker y es reintentable, pero la notificación de portal se crea antes, en la transacción de la respuesta.

### 8.9 Contratos mínimos a fijar antes de codificar

1. Esquemas OpenAPI para todo endpoint, con DTO distintos de los modelos ORM.
2. Política de campos editables y de serialización por rol; nunca reutilizar el serializador administrativo en el portal.
3. Matriz de transición `estado_actual × rol × estado_destino` como dato probado unitariamente.
4. Catálogo de errores de negocio estable: `APPLICATION_NOT_READY`, `INVALID_STATE_TRANSITION`, `STALE_VERSION`, `OUT_OF_SCOPE`, `DOCUMENT_LOCKED`, `FILE_NOT_CLEAN`, `IDEMPOTENCY_CONFLICT`.
5. Política de compatibilidad: cambios incompatibles entran en `/api/v2`, nunca se rompen silenciosamente clientes de `/api/v1`.

## 9. Seguridad

### 9.1 Autenticación y sesiones

- Las contraseñas aplican solo a usuarios internos y se almacenan exclusivamente con **Argon2id**, con sal única por contraseña y parámetros mínimos de OWASP: 19 MiB de memoria, 2 iteraciones y paralelismo 1. Nunca se cifran para recuperarlas ni se almacenan en texto plano. [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- El acceso interno usa JWT firmado asimétricamente o con una clave de alta entropía administrada por un gestor de secretos. El servidor valida algoritmo permitido, firma, `iss`, `aud`, `exp`, `nbf` y `jti`.
- El access token interno dura 15 minutos y se entrega en cookie `HttpOnly`, `Secure` y `SameSite=Lax`; no se guarda en `localStorage`. El refresh token interno es opaco, rotativo, de un solo uso, se almacena como hash en `auth_sessions` y dura inicialmente 8 horas.
- El comprador no crea contraseña ni recibe refresh token. El enlace mágico tiene token aleatorio hasheado, un solo uso y vencimiento inicial de 72 horas. Al consumirlo se limpia el token de la URL y se crea una `buyer_session` opaca, revocable, limitada al expediente y con duración inicial de 24 horas.
- Cerrar sesión, revocar enlace/sesión o desactivar un usuario interno corta el acceso respectivo. Las operaciones sensibles internas requieren reautenticación.
- Las cookies de sesión exigen protección CSRF para métodos que modifican datos.

### 9.2 Autorización y protección de datos

- Cada endpoint valida rol y autorización sobre el objeto solicitado; un asesor solo consulta solicitudes asignadas y un comprador solo el expediente ligado a su sesión temporal. Esta validación evita BOLA/IDOR.
- Las respuestas se construyen por rol: el comprador no recibe notas internas, información de otros solicitantes ni datos de auditoría operativa.
- Las notificaciones por correo incluyen solo resultado, mensaje público y enlace autenticado al portal; nunca adjuntan documentos, notas internas, números completos de identificación ni información financiera sensible.
- Se usa lista permitida de campos editables por endpoint. No se aceptan objetos completos para evitar mass assignment.
- Todos los datos viajan por HTTPS; se habilitan HSTS, CORS con orígenes explícitos, cabeceras de seguridad y registros sin secretos ni documentos de identidad completos.
- Los archivos se almacenan privados, se verifican por tamaño, extensión, MIME real y análisis antimalware; se sirven mediante URL firmada de corta duración.
- Secretos, claves de firma y credenciales de servicios viven en un gestor de secretos. No se suben al repositorio, no aparecen en logs y no se envían al frontend.

### 9.3 Rate limiting y defensas contra abuso

| Flujo | Límite inicial | Regla adicional |
| --- | --- | --- |
| Login | 5 intentos por correo e IP cada 15 minutos | Demora progresiva; no revelar si el correo existe. |
| Recuperación de contraseña | 3 solicitudes por correo e IP por hora | Respuesta uniforme y token de un solo uso. |
| Consumir enlace mágico | 5 intentos por IP por hora | Token de un solo uso, vencimiento, limpieza de URL y revocación posible. |
| Emitir/reemitir enlace mágico | 3 solicitudes por comprador y emisor por hora | Revoca enlaces activos previos o limita su coexistencia según política configurada. |
| Carga de documentos | 30 solicitudes por sesión de comprador por minuto | Máximo de 10 MB por archivo y cuota configurable por solicitud. |
| API autenticada general | 120 solicitudes por usuario por minuto | Límite inferior para endpoints costosos de reportes/exportación. |
| Cambio de estado / radicación | 20 solicitudes por usuario por minuto | Idempotency key obligatoria para crear radicaciones. |

Los límites se implementan en Redis o equivalente, no en memoria del proceso. Login, recuperación y otros flujos sensibles requieren protección reforzada contra fuerza bruta y credential stuffing. [OWASP API2: Broken Authentication](https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/)

### 9.4 Requerimientos de seguridad verificables

| ID | Requerimiento |
| --- | --- |
| RNF-11 | La API debe rechazar JWT internos vencidos o alterados, enlaces mágicos vencidos/consumidos y sesiones de comprador revocadas o expiradas. |
| RNF-12 | Toda autorización sobre cliente, solicitud, documento y radicación se valida en servidor antes de leer o modificar datos. |
| RNF-13 | Login interno, recuperación, enlaces mágicos, carga de archivos y radicación tienen rate limits configurables y auditables. |
| RNF-14 | La API valida formato, rango, longitud y listas permitidas de todos los datos de entrada. |
| RNF-15 | Los archivos no se exponen mediante rutas públicas permanentes. |
| RNF-16 | Cada solicitud HTTP recibe un `request_id`; los logs estructurados incluyen ese ID sin contener secretos ni PII sensible completa. |

### 9.5 Controles adicionales obligatorios de la plataforma

- **Principio de mínimo privilegio:** la cuenta de base de datos de la API no puede administrar el motor, y el worker de archivos solo accede al bucket/carpeta de cuarentena y objetos que necesita procesar.
- **Protección de archivos:** se permiten únicamente extensiones y MIME definidos por configuración; se limita tamaño, cantidad, profundidad de archivos comprimidos y tiempo de análisis para reducir ZIP bombs. Los archivos ejecutables, con doble extensión o con MIME inconsistente se rechazan. Nunca se renderiza un archivo cargado como HTML en el mismo origen de la aplicación.
- **Cifrado:** HTTPS extremo a extremo; cifrado administrado en base de datos, discos, copias de seguridad y almacenamiento de objetos. Si se cifran campos especialmente sensibles a nivel aplicativo, las claves viven fuera de la base de datos y se rota su material criptográfico.
- **Cabeceras y navegador:** `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `frame-ancestors` restrictivo y cookies con prefijos apropiados. CORS solo acepta los dominios concretos de los dos frontends; nunca `*` con credenciales.
- **Validación de proxy:** solo el proxy/WAF de confianza puede suministrar IP de cliente; la aplicación no debe confiar ciegamente en `X-Forwarded-For` enviado desde internet.
- **Autenticación reforzada:** se deja preparada la activación de MFA para `ADMIN` y `ADVISOR`. Si no entra a la primera entrega, el riesgo residual debe aprobarse explícitamente antes de producción.
- **Dependencias y secretos:** análisis de vulnerabilidades y detección de secretos en CI; versiones corregidas por parche de seguridad; rotación de claves JWT, contraseñas de base de datos y secretos de proveedores mediante procedimiento documentado.
- **Auditoría y privacidad:** se auditan inicios de sesión, fallos, descargas, cambios de permisos, acceso a expedientes y acciones sensibles. La bitácora no puede contener contraseñas, tokens, encabezados `Authorization`, números de documento completos ni URLs firmadas.
- **Respaldo y recuperación:** copias cifradas de PostgreSQL y objetos, con prueba periódica de restauración. Se definen RPO/RTO antes de producción; el backup sin prueba de restauración no se considera control suficiente.

## 10. Estrategia de pruebas

### 10.1 Pirámide de pruebas

```text
             E2E: pocos, flujos de negocio críticos
        Integración: API REST, base de datos y almacenamiento
Unitarias: servicios, validadores, componentes y utilidades
```

### 10.2 Pruebas de backend

| Tipo | Cobertura mínima |
| --- | --- |
| Unitarias | Transiciones de estado, cálculo de `READY_TO_FILE`, validación de checklist, autorización de dominio, creación de radicaciones e idempotencia. |
| Integración | Endpoints REST con base de datos efímera, migraciones, paginación, filtros, permisos, archivos y transacciones. |
| Contrato | Validar respuestas contra OpenAPI; detectar cambios incompatibles antes de desplegar. |
| Seguridad | JWT vencido/alterado, sesión revocada, escalamiento de privilegios, BOLA/IDOR, mass assignment, CSRF, rate limiting, carga de archivo inválida y fuga de datos. |

### 10.3 Pruebas de frontend

| Tipo | Cobertura mínima |
| --- | --- |
| Unitarias de componentes | Formularios financieros, checklist, estados de documento, bloqueo posterior a radicación y validaciones de campos. |
| Integración | Cliente API simulado: errores, carga/reemplazo de documentos, filtros de Mi día y visualización por rol. |
| Accesibilidad | Navegación por teclado, etiquetas de formularios, foco en modales, mensajes de error y contraste. |
| E2E | Navegación completa de asesor y comprador contra un ambiente de prueba. |

### 10.4 Casos E2E obligatorios

1. Administrador crea asesor, banco/producto y requisitos documentales.
2. Asesor crea cliente, oportunidad y solicitud; el broker genera el enlace mágico de autogestión.
3. Comprador consume el enlace mágico, completa datos, selecciona banco y carga documentos sin crear contraseña.
4. Asesor rechaza un documento; comprador solo puede reemplazar ese documento.
5. Asesor aprueba/exonera requisitos y la solicitud pasa a `READY_TO_FILE`.
6. Asesor descarga expediente, crea radicación manual y registra número de referencia.
7. Comprador no puede modificar información financiera ni banco después de `FILED`.
8. Comprador A y asesor B intentan acceder a datos ajenos: la API responde `403` o `404` según política.
9. Reintentar una creación de radicación con la misma idempotency key no crea duplicados.
10. Login repetido excede el rate limit y no revela si un usuario existe.
11. Un broker no accede al expediente de otro broker y una constructora no accede a datos de otro partner, incluso manipulando UUIDs en la URL.
12. Un partner crea un proyecto `DRAFT`; este no permite oportunidades nuevas hasta que asesor o administrador lo active.
13. La misma solicitud se prueba como vivienda nueva, usada y remodelación; el checklist y los campos obligatorios cambian según finalidad.
14. Un archivo reemplazado conserva la versión previa; el ZIP de una radicación histórica contiene exactamente la versión aprobada al radicar.
15. Dos ediciones concurrentes de la solicitud: la segunda con versión obsoleta devuelve `409` y no pierde cambios.
16. El administrador activa un nuevo ítem de catálogo o requisito documental; el frontend lo consulta desde `/metadata` y lo muestra sin desplegar código ni agregar un enum.
17. Un ítem de catálogo con uso histórico se desactiva; no se ofrece para nuevas solicitudes, pero los expedientes existentes conservan su valor y etiqueta histórica.
18. El asesor registra una devolución bancaria con motivo público: la solicitud cambia a observación/documentos, se crea la tarea y el comprador ve la notificación y el correo transaccional pendiente/enviado.
19. El asesor registra un rechazo y luego una aprobación en expedientes distintos: se conserva la respuesta, el motivo visible, la nota interna protegida y la transición correcta para cada caso.
20. Un enlace mágico vencido, ya consumido, revocado o asociado a otro expediente no permite acceso; el comprador requiere un nuevo enlace para retomar el formulario.

### 10.5 Puertas de calidad en CI

- Todas las pruebas unitarias, integración y contrato deben pasar antes de fusionar cambios.
- Cobertura mínima: 80% de servicios de dominio y validadores; 70% de componentes y flujos de frontend; 100% de transiciones de estado y controles de autorización críticos.
- Escaneo de dependencias, linting, análisis estático y migraciones en una base de datos vacía deben ejecutarse en cada pull request.
- Los flujos E2E críticos y pruebas de seguridad se ejecutan antes de cada despliegue a producción.
- Los permisos se prueban como matriz: cada endpoint relevante se ejecuta con todos los roles y con un recurso dentro y fuera de alcance.

## 11. Requerimientos no funcionales

| ID | Requerimiento |
| --- | --- |
| RNF-01 | Todo el tráfico debe usar HTTPS. |
| RNF-02 | Las contraseñas de usuarios internos se almacenan con hash seguro, nunca en texto plano; el comprador no tiene contraseña. |
| RNF-03 | Los archivos deben ser privados y descargables mediante enlaces temporales autorizados. |
| RNF-04 | El sistema debe registrar actor, fecha y acción para cambios de estado, documentos, asignaciones y radicaciones. |
| RNF-05 | Un comprador nunca debe acceder a expedientes de otro comprador. |
| RNF-06 | Las operaciones de transición de estado deben ser atómicas. |
| RNF-07 | Las listas operativas deben paginarse y permitir filtros. |
| RNF-08 | El sistema debe permitir exportar informes sin exponer documentos privados. |
| RNF-09 | Se deben realizar copias de seguridad de la base de datos y de metadatos de archivos. |
| RNF-10 | La aceptación de tratamiento de datos y otros consentimientos debe conservar versión, fecha, actor y evidencia. |
| RNF-17 | Las lecturas normales de listas y detalle deben responder con p95 menor a 800 ms bajo la carga objetivo inicial; generación de ZIP, CSV y análisis de archivos no bloquean la solicitud HTTP. |
| RNF-18 | La aplicación expone `health` y `ready` sin datos sensibles; se monitorean error rate, latencia, colas, uso de almacenamiento, tasa de rechazos de archivos y fallos de tareas. |
| RNF-19 | Las tareas asíncronas son reintentables e idempotentes. Un fallo de correo, ZIP o antivirus nunca debe cambiar silenciosamente el estado de crédito. |
| RNF-20 | La API conserva compatibilidad dentro de `/api/v1`; toda modificación incompatible exige nueva versión, migración y plan de retiro. |
| RNF-21 | Una respuesta bancaria que cambie estado debe persistir la notificación de portal antes de encolar el correo; un fallo de correo es visible y reintentable, sin perder el resultado del banco. |

### 11.1 Operación, observabilidad y recuperación

| Tema | Diseño inicial |
| --- | --- |
| Métricas | Solicitudes por endpoint/estado, p50/p95/p99, 4xx/5xx, bloqueos de rate limit, documentos en cuarentena, longitud/fallos de cola, radicaciones por estado y trabajos vencidos. |
| Logs | Estructurados, con `request_id`, usuario pseudonimizado, endpoint, estado HTTP y duración. La consulta de logs se restringe a operación técnica. |
| Trazas | El `request_id` viaja de Next.js a API y worker; las tareas asíncronas incluyen correlación con solicitud, documento o radicación. |
| Alertas | Error 5xx sostenido, cola detenida, backups fallidos, aumento de archivos maliciosos, falta de capacidad de almacenamiento y fallos de restauración. |
| Backups | Copia diaria como mínimo y retención según decisión de negocio; pruebas de restauración programadas y registradas. |
| Despliegue | Migraciones reversibles cuando sea posible, ambiente de staging con datos sintéticos, smoke test tras despliegue y rollback documentado. |

## 12. Decisiones aún pendientes

Las definiciones de país, moneda, bancos iniciales, finalidades, criterio de `READY_TO_FILE`, bloqueo posterior a radicación y alcance de brokers/constructoras están cerradas. Permanecen estas decisiones, ordenadas para no bloquear la implementación innecesariamente:

| Prioridad | Decisión | Propuesta inicial / impacto |
| --- | --- | --- |
| Antes de producción | Validar con cada banco el checklist, vigencias y condiciones por producto/finalidad. | El modelo ya lo configura; sin esta validación solo debe operarse en pruebas. |
| Antes de producción | Definir responsable de tratamiento, texto de autorizaciones, retención de expedientes y procedimiento de atención de datos personales. | Afecta consentimientos, textos de invitación, archivos, backups y borrado. Requiere validación legal/compliance local. |
| Antes de producción | Definir RPO/RTO, proveedor de almacenamiento, antivirus y proceso de restauración. | Afecta costo, backup, disponibilidad y política de respuesta a incidentes. |
| Antes de producción | Definir dominio final y estrategia de cookies entre Next.js y API. | Debe cerrar CORS, `SameSite`, CSRF y configuración de proxy. |
| Durante diseño UX | Definir el contenido exacto del resumen que ve el broker. | Propuesta: código de solicitud, estado público, siguiente acción y fecha de actualización; excluir documentos, finanzas, observaciones y PII innecesaria. |
| Antes de implementación | Seleccionar proveedor de correo y aprobar las plantillas de devolución, rechazo y aprobación. | Portal + correo ya son el canal inicial acordado; WhatsApp no hace parte del MVP. |
| Durante diseño UX | Definir métricas de dashboard, fórmula de conversión y rangos de fechas. | Evita construir indicadores con definiciones comerciales ambiguas. |
| Durante diseño UX | Definir qué hace un broker cuando registra un cliente cuyo documento ya existe y que creó otro usuario fuera de su alcance. | Hoy `POST /clients` responde `409 DUPLICATE_CLIENT_DOCUMENT` sin `resource_id`, para no revelar el cliente, y el broker no puede crear la oportunidad porque no ve a ese cliente (RF-14). Hay que decidir si el broker pide la vinculación a un asesor o administrador, o si puede abrir la oportunidad sobre el cliente existente sin ver sus datos. |

## 13. Supuestos explícitos de implementación

1. Un usuario partner pertenece a una constructora activa; si después se requiere una misma persona en varias constructoras, `partner_memberships` ya permite ampliar la regla de uno a muchos.
2. Un broker es un usuario individual y no se modela como empresa ni como tenant. Puede tener expedientes propios o asignados.
3. Un proyecto partner comienza en `DRAFT`. Solo `ACTIVE` puede recibir oportunidades; archivar no elimina expedientes históricos.
4. El comprador es el único cargador de documentos. El broker captura el prospecto y comparte la invitación de autogestión; la constructora se limita a sus proyectos.
5. El MVP permite un único inmueble por solicitud y un participante principal con cero o más co-solicitantes/deudores solidarios.
6. El MVP usa radicación manual. La generación de ZIP es asistencia operativa, no evidencia de que el banco recibió la solicitud; la evidencia y cada respuesta del banco se registran en `filings` y `filing_responses`, con notificación al comprador.

## 14. Próximos artefactos de ingeniería

1. ADR-001: Django + DRF como monolito modular, PostgreSQL, Redis, worker y almacenamiento privado.
2. Modelo entidad-relación y diccionario de datos detallado, incluyendo índices, restricciones y migración inicial Django.
3. Diagrama de estados definitivo y matriz `rol × estado actual × acción × estado destino`.
4. Especificación OpenAPI 3.1 inicial y matriz de permisos por endpoint; se debe generar cliente tipado para Next.js.
5. Historias de usuario priorizadas con criterios de aceptación de QA y casos negativos de autorización.
6. Prototipo de navegación y diseño de las 14 vistas operativas y 8 del portal comprador.
7. Diseño de despliegue, selección de almacenamiento/antivirus y runbooks de backup, restauración y rotación de secretos.
