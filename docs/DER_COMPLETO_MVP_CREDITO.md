# Diagrama entidad-relación completo

## MVP de gestión de crédito de vivienda

Este documento representa visualmente las 58 tablas definidas en [`ESQUEMA_POSTGRESQL_MVP_CREDITO.sql`](./ESQUEMA_POSTGRESQL_MVP_CREDITO.sql). Se divide por módulos para que las relaciones sean legibles. Cuando una tabla aparece en más de un diagrama, sigue siendo la misma tabla de PostgreSQL; se repite únicamente como referencia visual.

## 1. Cómo leer las relaciones

| Símbolo Mermaid | Significado | Ejemplo |
| --- | --- | --- |
| `||--o{` | Uno a cero o muchos | Un usuario puede tener muchas sesiones. |
| `||--|{` | Uno a uno o muchos, mínimo uno | Una solicitud debe tener participantes. |
| `||--o|` | Uno a cero o uno | Un enlace puede producir una sesión. |
| `||--||` | Uno a uno obligatorio | Una solicitud tiene una configuración financiera. |

La tabla que contiene el campo terminado en `_id` es la tabla hija. Por ejemplo, `auth_sessions.user_id` significa que muchas sesiones pueden apuntar a un mismo usuario.

## 2. Mapa maestro del recorrido de los datos

```mermaid
flowchart LR
    U["Usuarios internos"] --> CRM["Clientes y oportunidades"]
    P["Partners y proyectos"] --> CRM
    CRM --> APP["Solicitud de crédito"]
    APP --> FIN["Participantes, finanzas e inmueble"]
    CFG["Catálogos, bancos y reglas"] --> APP
    CFG --> DOC["Checklist documental"]
    APP --> BUYER["Enlace y sesión del comprador"]
    BUYER --> DOC
    DOC --> PACKAGE["Paquete documental"]
    PACKAGE --> FILING["Radicación manual"]
    FILING --> RESPONSE["Respuesta y observaciones"]
    RESPONSE --> APP
    RESPONSE --> NOTIFY["Actividad y notificaciones"]
    APP --> REPORTS["Dashboard y reportes"]
    U --> AUDIT["Auditoría"]
    BUYER --> AUDIT
```

## 3. Identidad, roles e invitaciones internas

```mermaid
erDiagram
    USERS ||--o{ USER_ROLES : recibe
    ROLES ||--o{ USER_ROLES : asignado_en
    USERS o|--o{ USER_ROLES : asigna
    ROLES ||--o{ ROLE_PERMISSIONS : agrupa
    PERMISSIONS ||--o{ ROLE_PERMISSIONS : habilita
    USERS ||--o{ AUTH_SESSIONS : inicia
    AUTH_SESSIONS o|--o| AUTH_SESSIONS : rota_desde
    USERS ||--o{ PASSWORD_RESET_TOKENS : solicita
    ROLES ||--o{ INTERNAL_INVITATIONS : preasigna
    PARTNERS o|--o{ INTERNAL_INVITATIONS : invita_para
    USERS o|--o{ INTERNAL_INVITATIONS : envia
    USERS ||--o{ PARTNER_MEMBERSHIPS : integra
    PARTNERS ||--o{ PARTNER_MEMBERSHIPS : tiene

    USERS {
        uuid id PK
        citext email UK
        varchar password_hash
        boolean is_active
    }
    ROLES {
        uuid id PK
        varchar code UK
        varchar name
    }
    PERMISSIONS {
        uuid id PK
        varchar code UK
        varchar module
    }
    USER_ROLES {
        uuid id PK
        uuid user_id FK
        uuid role_id FK
        uuid assigned_by_id FK
    }
    ROLE_PERMISSIONS {
        uuid id PK
        uuid role_id FK
        uuid permission_id FK
    }
    AUTH_SESSIONS {
        uuid id PK
        uuid user_id FK
        char refresh_token_hash UK
        uuid rotated_from_id FK
    }
    PASSWORD_RESET_TOKENS {
        uuid id PK
        uuid user_id FK
        char token_hash UK
    }
    INTERNAL_INVITATIONS {
        uuid id PK
        citext email
        uuid role_id FK
        uuid partner_id FK
        uuid invited_by_id FK
    }
    PARTNER_MEMBERSHIPS {
        uuid id PK
        uuid partner_id FK
        uuid user_id FK
        varchar status
    }
    PARTNERS {
        uuid id PK
        varchar tax_id UK
        varchar legal_name
    }
```

Lectura sencilla:

- `user_roles` convierte usuarios y roles en una relación muchos-a-muchos.
- `role_permissions` convierte roles y permisos en otra relación muchos-a-muchos.
- Una sesión o token siempre pertenece a un usuario, pero un usuario puede acumular varios registros históricos.
- La invitación interna permite que un asesor, broker o miembro de constructora cree su propia contraseña.

## 4. Partners, proyectos, clientes y oportunidades

```mermaid
erDiagram
    PARTNERS ||--o{ PROJECTS : posee
    USERS ||--o{ PROJECTS : crea
    USERS o|--o{ PROJECTS : valida
    CATALOG_ITEMS ||--o{ PROJECTS : define_ciudad
    CATALOGS ||--o{ CATALOG_ITEMS : contiene
    CATALOG_ITEMS o|--o{ CATALOG_ITEMS : padre_de
    CATALOG_ITEMS ||--o{ CLIENTS : define_documento
    CATALOG_ITEMS o|--o{ CLIENTS : define_origen
    USERS o|--o{ CLIENTS : registra
    CLIENTS ||--o{ CLIENT_ADDRESSES : tiene
    CATALOG_ITEMS ||--o{ CLIENT_ADDRESSES : define_tipo
    CATALOG_ITEMS ||--o{ CLIENT_ADDRESSES : define_ciudad
    CLIENTS ||--o{ OPPORTUNITIES : genera
    PROJECTS o|--o{ OPPORTUNITIES : interesa
    USERS o|--o{ OPPORTUNITIES : origina
    USERS o|--o{ OPPORTUNITIES : atiende
    CATALOG_ITEMS ||--o{ OPPORTUNITIES : define_origen
    CATALOG_ITEMS o|--o{ OPPORTUNITIES : explica_perdida
    OPPORTUNITIES ||--o{ OPPORTUNITY_ASSIGNMENTS : asigna
    USERS ||--o{ OPPORTUNITY_ASSIGNMENTS : responsable
    USERS o|--o{ OPPORTUNITY_ASSIGNMENTS : asignador

    PARTNERS {
        uuid id PK
        varchar legal_name
        varchar tax_id UK
    }
    PROJECTS {
        uuid id PK
        uuid partner_id FK
        uuid city_item_id FK
        uuid created_by_id FK
        uuid validated_by_id FK
    }
    CATALOGS {
        uuid id PK
        varchar code UK
        int version
    }
    CATALOG_ITEMS {
        uuid id PK
        uuid catalog_id FK
        uuid parent_item_id FK
        varchar code
        varchar label
    }
    USERS {
        uuid id PK
    }
    CLIENTS {
        uuid id PK
        uuid document_type_item_id FK
        varchar document_number
        uuid origin_item_id FK
        uuid created_by_id FK
    }
    CLIENT_ADDRESSES {
        uuid id PK
        uuid client_id FK
        uuid address_type_item_id FK
        uuid city_item_id FK
    }
    OPPORTUNITIES {
        uuid id PK
        uuid client_id FK
        uuid project_id FK
        uuid origin_user_id FK
        uuid assigned_advisor_id FK
        uuid origin_item_id FK
        uuid lost_reason_item_id FK
    }
    OPPORTUNITY_ASSIGNMENTS {
        uuid id PK
        uuid opportunity_id FK
        uuid advisor_id FK
        uuid assigned_by_id FK
    }
```

Lectura sencilla:

- Un cliente existe una sola vez y puede generar varias oportunidades.
- Una oportunidad puede señalar un proyecto o existir sin proyecto.
- `assigned_advisor_id` guarda el asesor actual; `opportunity_assignments` conserva todos los asesores anteriores.
- `catalog_items` ofrece valores compartidos como ciudad, tipo de documento, origen y motivo de pérdida.

## 5. Bancos, productos, reglas y flujos

```mermaid
erDiagram
    BANKS ||--o{ BANK_PRODUCTS : ofrece
    CATALOG_ITEMS ||--o{ BANK_PRODUCTS : tipifica
    BANK_PRODUCTS ||--o{ BANK_PRODUCT_PURPOSES : admite
    CATALOG_ITEMS ||--o{ BANK_PRODUCT_PURPOSES : finalidad
    BANK_PRODUCTS ||--o{ BANK_POLICY_RULES : configura
    CATALOG_ITEMS o|--o{ BANK_POLICY_RULES : limita_finalidad
    USERS ||--o{ BANK_POLICY_RULES : crea
    BANK_PRODUCTS ||--o{ DOCUMENT_REQUIREMENTS : exige
    DOCUMENT_TYPES ||--o{ DOCUMENT_REQUIREMENTS : solicita
    CATALOG_ITEMS o|--o{ DOCUMENT_REQUIREMENTS : finalidad
    CATALOG_ITEMS o|--o{ DOCUMENT_REQUIREMENTS : perfil_laboral
    CATALOG_ITEMS o|--o{ DOCUMENT_REQUIREMENTS : condicion_inmueble
    PERMISSIONS o|--o{ WORKFLOW_TRANSITIONS : requiere
    WORKFLOW_TRANSITIONS ||--o{ WORKFLOW_TRANSITION_ROLES : autoriza
    ROLES ||--o{ WORKFLOW_TRANSITION_ROLES : ejecuta

    BANKS {
        uuid id PK
        varchar code UK
        varchar name
        varchar short_name
        smallint filing_response_days
    }
    BANK_PRODUCTS {
        uuid id PK
        uuid bank_id FK
        uuid product_type_item_id FK
        varchar code
    }
    BANK_PRODUCT_PURPOSES {
        uuid id PK
        uuid bank_product_id FK
        uuid purpose_item_id FK
    }
    BANK_POLICY_RULES {
        uuid id PK
        uuid bank_product_id FK
        uuid purpose_item_id FK
        uuid created_by_id FK
        jsonb condition
    }
    DOCUMENT_TYPES {
        uuid id PK
        varchar code UK
        text_array allowed_mime_types
    }
    DOCUMENT_REQUIREMENTS {
        uuid id PK
        uuid bank_product_id FK
        uuid document_type_id FK
        uuid purpose_item_id FK
        uuid employment_profile_item_id FK
        uuid property_condition_item_id FK
    }
    WORKFLOW_TRANSITIONS {
        uuid id PK
        uuid required_permission_id FK
        varchar from_status
        varchar to_status
    }
    WORKFLOW_TRANSITION_ROLES {
        uuid id PK
        uuid transition_id FK
        uuid role_id FK
    }
    CATALOG_ITEMS {
        uuid id PK
    }
    USERS {
        uuid id PK
    }
    ROLES {
        uuid id PK
    }
    PERMISSIONS {
        uuid id PK
    }
```

`bank_product_purposes` es la tabla intermedia N:M entre productos y finalidades. `workflow_transition_roles` hace lo mismo entre transiciones y roles.

## 6. Solicitud, participantes, finanzas e inmueble

```mermaid
erDiagram
    OPPORTUNITIES ||--o{ CREDIT_APPLICATIONS : convierte
    CATALOG_ITEMS ||--o{ CREDIT_APPLICATIONS : finalidad
    BANK_PRODUCTS o|--o{ CREDIT_APPLICATIONS : producto
    USERS ||--o{ CREDIT_APPLICATIONS : gestiona
    CREDIT_APPLICATIONS ||--o{ APPLICATION_ASSIGNMENTS : reasigna
    USERS ||--o{ APPLICATION_ASSIGNMENTS : asesor
    USERS o|--o{ APPLICATION_ASSIGNMENTS : asignador
    CREDIT_APPLICATIONS ||--|{ APPLICATION_PARTICIPANTS : incluye
    CLIENTS ||--o{ APPLICATION_PARTICIPANTS : participa
    APPLICATION_PARTICIPANTS ||--o| FINANCIAL_PROFILES : declara
    CATALOG_ITEMS ||--o{ FINANCIAL_PROFILES : perfil_laboral
    CATALOG_ITEMS o|--o{ FINANCIAL_PROFILES : contrato
    CATALOG_ITEMS o|--o{ FINANCIAL_PROFILES : origen_fondos
    FINANCIAL_PROFILES ||--o{ INCOME_SOURCES : detalla
    CATALOG_ITEMS ||--o{ INCOME_SOURCES : tipo_ingreso
    CREDIT_APPLICATIONS ||--o| PROPERTIES : financia
    PROJECTS o|--o{ PROPERTIES : contiene
    CATALOG_ITEMS ||--o{ PROPERTIES : tipo
    CATALOG_ITEMS ||--o{ PROPERTIES : condicion
    CATALOG_ITEMS ||--o{ PROPERTIES : ciudad
    CREDIT_APPLICATIONS ||--o| FINANCING_PREFERENCES : configura
    CATALOG_ITEMS ||--o{ FINANCING_PREFERENCES : modalidad
    CATALOG_ITEMS o|--o{ FINANCING_PREFERENCES : moneda
    CATALOG_ITEMS o|--o{ FINANCING_PREFERENCES : amortizacion
    CREDIT_APPLICATIONS ||--o{ BANK_RULE_EVALUATIONS : evalua
    BANK_PRODUCTS ||--o{ BANK_RULE_EVALUATIONS : usa
    USERS o|--o{ BANK_RULE_EVALUATIONS : ejecuta
    CREDIT_APPLICATIONS ||--o{ APPLICATION_STATUS_HISTORY : recorre
    WORKFLOW_TRANSITIONS o|--o{ APPLICATION_STATUS_HISTORY : produce
    CATALOG_ITEMS o|--o{ APPLICATION_STATUS_HISTORY : motivo
    USERS o|--o{ APPLICATION_STATUS_HISTORY : cambia
    BUYER_SESSIONS o|--o{ APPLICATION_STATUS_HISTORY : desiste

    CREDIT_APPLICATIONS {
        uuid id PK
        uuid opportunity_id FK
        uuid purpose_item_id FK
        uuid bank_product_id FK
        uuid assigned_advisor_id FK
        varchar status
        int version
        smallint completeness_pct
        boolean ready_to_file_ok
        timestamptz completeness_refreshed_at
    }
    APPLICATION_ASSIGNMENTS {
        uuid id PK
        uuid application_id FK
        uuid advisor_id FK
        uuid assigned_by_id FK
    }
    APPLICATION_PARTICIPANTS {
        uuid id PK
        uuid application_id FK
        uuid client_id FK
        varchar role
    }
    FINANCIAL_PROFILES {
        uuid id PK
        uuid participant_id FK
        uuid employment_profile_item_id FK
    }
    INCOME_SOURCES {
        uuid id PK
        uuid financial_profile_id FK
        uuid source_type_item_id FK
    }
    PROPERTIES {
        uuid id PK
        uuid application_id FK
        uuid project_id FK
        uuid property_type_item_id FK
    }
    FINANCING_PREFERENCES {
        uuid id PK
        uuid application_id FK
        uuid financing_mode_item_id FK
    }
    BANK_RULE_EVALUATIONS {
        uuid id PK
        uuid application_id FK
        uuid bank_product_id FK
        uuid evaluated_by_id FK
    }
    APPLICATION_STATUS_HISTORY {
        uuid id PK
        uuid application_id FK
        uuid transition_id FK
        uuid actor_user_id FK
        uuid actor_buyer_session_id FK
    }
    OPPORTUNITIES {
        uuid id PK
    }
    CLIENTS {
        uuid id PK
    }
    USERS {
        uuid id PK
    }
    BANK_PRODUCTS {
        uuid id PK
    }
    PROJECTS {
        uuid id PK
    }
    CATALOG_ITEMS {
        uuid id PK
    }
    WORKFLOW_TRANSITIONS {
        uuid id PK
    }
    BUYER_SESSIONS {
        uuid id PK
    }
```

El estado y asesor actuales viven en `credit_applications` para consultar rápido. Sus historiales viven en `application_status_history` y `application_assignments`.

## 7. Acceso del comprador y consentimientos

```mermaid
erDiagram
    CLIENTS ||--o{ BUYER_ACCESS_LINKS : recibe
    CREDIT_APPLICATIONS ||--o{ BUYER_ACCESS_LINKS : limita
    USERS o|--o{ BUYER_ACCESS_LINKS : genera
    CATALOG_ITEMS o|--o{ BUYER_ACCESS_LINKS : canal
    BUYER_ACCESS_LINKS ||--o| BUYER_SESSIONS : consume_en
    CLIENTS ||--o{ BUYER_SESSIONS : navega
    CREDIT_APPLICATIONS ||--o{ BUYER_SESSIONS : habilita
    CONSENT_DEFINITIONS ||--o{ CONSENT_RECORDS : version_aceptada
    CLIENTS o|--o{ CONSENT_RECORDS : acepta
    USERS o|--o{ CONSENT_RECORDS : acepta
    CREDIT_APPLICATIONS o|--o{ CONSENT_RECORDS : contextualiza
    BUYER_SESSIONS o|--o{ CONSENT_RECORDS : evidencia

    CLIENTS {
        uuid id PK
    }
    CREDIT_APPLICATIONS {
        uuid id PK
    }
    USERS {
        uuid id PK
    }
    CATALOG_ITEMS {
        uuid id PK
    }
    BUYER_ACCESS_LINKS {
        uuid id PK
        uuid client_id FK
        uuid application_id FK
        uuid created_by_id FK
        uuid delivery_channel_item_id FK
        char token_hash UK
    }
    BUYER_SESSIONS {
        uuid id PK
        uuid access_link_id FK, UK
        uuid client_id FK
        uuid application_id FK
        char session_token_hash UK
    }
    CONSENT_DEFINITIONS {
        uuid id PK
        varchar code
        int version
        char content_hash
    }
    CONSENT_RECORDS {
        uuid id PK
        uuid consent_definition_id FK
        uuid client_id FK
        uuid user_id FK
        uuid application_id FK
        uuid buyer_session_id FK
    }
```

El comprador no se conecta con `users`: está representado por `clients`. El único vínculo del usuario interno con el enlace es `created_by_id`, que identifica quién lo generó.

## 8. Expediente documental

```mermaid
erDiagram
    CREDIT_APPLICATIONS ||--o{ APPLICATION_DOCUMENT_SLOTS : exige
    APPLICATION_PARTICIPANTS o|--o{ APPLICATION_DOCUMENT_SLOTS : aporta
    DOCUMENT_TYPES ||--o{ APPLICATION_DOCUMENT_SLOTS : tipifica
    DOCUMENT_REQUIREMENTS o|--o{ APPLICATION_DOCUMENT_SLOTS : origina
    CATALOG_ITEMS o|--o{ APPLICATION_DOCUMENT_SLOTS : exonera
    APPLICATION_DOCUMENT_SLOTS ||--o{ DOCUMENT_FILES : versiona
    FILE_OBJECTS ||--o| DOCUMENT_FILES : almacena
    BUYER_SESSIONS ||--o{ DOCUMENT_FILES : carga
    DOCUMENT_FILES o|--o| APPLICATION_DOCUMENT_SLOTS : vigente
    APPLICATION_DOCUMENT_SLOTS ||--o{ DOCUMENT_REVIEWS : decide
    DOCUMENT_FILES o|--o{ DOCUMENT_REVIEWS : revisa
    USERS ||--o{ DOCUMENT_REVIEWS : decide
    CATALOG_ITEMS o|--o{ DOCUMENT_REVIEWS : motivo
    CREDIT_APPLICATIONS ||--o{ DOCUMENT_PACKAGE_JOBS : prepara
    USERS ||--o{ DOCUMENT_PACKAGE_JOBS : solicita
    FILE_OBJECTS o|--o| DOCUMENT_PACKAGE_JOBS : produce

    APPLICATION_DOCUMENT_SLOTS {
        uuid id PK
        uuid application_id FK
        uuid participant_id FK
        uuid document_type_id FK
        uuid requirement_id FK
        uuid waiver_reason_item_id FK
        uuid current_file_id FK
        varchar status
    }
    DOCUMENT_FILES {
        uuid id PK
        uuid slot_id FK
        uuid file_object_id FK, UK
        uuid uploaded_by_buyer_session_id FK
        int version_number
    }
    DOCUMENT_REVIEWS {
        uuid id PK
        uuid slot_id FK
        uuid document_file_id FK
        uuid reviewer_id FK
        uuid reason_item_id FK
        varchar decision
        uuid decision_batch_id
    }
    FILE_OBJECTS {
        uuid id PK
        varchar object_key UK
        char sha256
        varchar scan_status
    }
    DOCUMENT_PACKAGE_JOBS {
        uuid id PK
        uuid application_id FK
        uuid requested_by_id FK
        uuid output_file_object_id FK, UK
    }
    CREDIT_APPLICATIONS {
        uuid id PK
    }
    APPLICATION_PARTICIPANTS {
        uuid id PK
    }
    DOCUMENT_TYPES {
        uuid id PK
    }
    DOCUMENT_REQUIREMENTS {
        uuid id PK
    }
    BUYER_SESSIONS {
        uuid id PK
    }
    USERS {
        uuid id PK
    }
    CATALOG_ITEMS {
        uuid id PK
    }
```

Hay cuatro conceptos distintos:

1. `document_requirements`: plantilla general.
2. `application_document_slots`: documento concreto esperado en una solicitud.
3. `document_files`: cada versión cargada.
4. `document_reviews`: decisiones sobre un slot: aprobar o rechazar una versión, exonerar y reabrir (desvío del paso 10, ver MODELO §8.4).

`file_objects` solo describe dónde está el archivo físico y su estado antivirus.

## 9. Radicación manual y respuestas

```mermaid
erDiagram
    CREDIT_APPLICATIONS ||--o{ FILINGS : radica
    BANK_PRODUCTS ||--o{ FILINGS : recibe
    DOCUMENT_PACKAGE_JOBS ||--o| FILINGS : respalda
    CATALOG_ITEMS ||--o{ FILINGS : canal
    USERS ||--o{ FILINGS : registra
    FILINGS ||--|{ FILING_DOCUMENT_SNAPSHOTS : congela
    DOCUMENT_FILES ||--o{ FILING_DOCUMENT_SNAPSHOTS : incluye
    FILE_OBJECTS ||--o{ FILING_DOCUMENT_SNAPSHOTS : verifica
    FILINGS ||--o{ FILING_RESPONSES : recibe
    CATALOG_ITEMS ||--o{ FILING_RESPONSES : tipo
    CATALOG_ITEMS o|--o{ FILING_RESPONSES : motivo
    FILE_OBJECTS o|--o{ FILING_RESPONSES : evidencia
    USERS ||--o{ FILING_RESPONSES : registra
    FILING_RESPONSES o|--o| FILING_RESPONSES : corrige
    FILING_RESPONSES ||--o{ FILING_RESPONSE_OBSERVATIONS : detalla
    APPLICATION_DOCUMENT_SLOTS ||--o{ FILING_RESPONSE_OBSERVATIONS : observa
    CATALOG_ITEMS ||--o{ FILING_RESPONSE_OBSERVATIONS : motivo
    DOCUMENT_FILES o|--o{ FILING_RESPONSE_OBSERVATIONS : resuelve

    FILINGS {
        uuid id PK
        uuid application_id FK
        uuid bank_product_id FK
        uuid package_job_id FK, UK
        uuid channel_item_id FK
        uuid filed_by_id FK
        int sequence_number
        varchar status
        timestamptz target_response_at
    }
    FILING_DOCUMENT_SNAPSHOTS {
        uuid id PK
        uuid filing_id FK
        uuid document_file_id FK
        uuid file_object_id FK
        char sha256
    }
    FILING_RESPONSES {
        uuid id PK
        uuid filing_id FK
        uuid response_type_item_id FK
        uuid reason_item_id FK
        uuid evidence_file_object_id FK
        uuid recorded_by_id FK
        uuid corrects_response_id FK
    }
    FILING_RESPONSE_OBSERVATIONS {
        uuid id PK
        uuid filing_response_id FK
        uuid document_slot_id FK
        uuid reason_item_id FK
        uuid resolved_by_file_id FK
    }
    CREDIT_APPLICATIONS {
        uuid id PK
    }
    BANK_PRODUCTS {
        uuid id PK
    }
    DOCUMENT_PACKAGE_JOBS {
        uuid id PK
    }
    DOCUMENT_FILES {
        uuid id PK
    }
    APPLICATION_DOCUMENT_SLOTS {
        uuid id PK
    }
    FILE_OBJECTS {
        uuid id PK
    }
    CATALOG_ITEMS {
        uuid id PK
    }
    USERS {
        uuid id PK
    }
```

`filing_document_snapshots` es la tabla intermedia N:M entre radicaciones y versiones documentales. Conserva la evidencia exacta de lo enviado. Una observación señala únicamente el slot que el comprador puede corregir después de radicar.

Catálogos de la radicación: `filing_channel` (canal de entrega), `filing_response_type` (incluye `DISBURSED`), `filing_return_reason` y `filing_rejection_reason` (motivo de la respuesta), y `document_rejection_reason` (motivo de cada observación). `banks.filing_response_days` calcula `filings.target_response_at`. Las transiciones `FILE` y `BANK_*` son de sistema (`workflow_transitions.system_only`).

## 10. Tareas, actividad, notificaciones y plataforma

```mermaid
erDiagram
    OPPORTUNITIES o|--o{ TASKS : genera
    CREDIT_APPLICATIONS o|--o{ TASKS : genera
    USERS ||--o{ TASKS : responsable
    USERS o|--o{ TASKS : crea
    CATALOG_ITEMS ||--o{ TASKS : prioridad
    CLIENTS o|--o{ ACTIVITY_LOGS : registra
    OPPORTUNITIES o|--o{ ACTIVITY_LOGS : registra
    CREDIT_APPLICATIONS o|--o{ ACTIVITY_LOGS : registra
    USERS o|--o{ ACTIVITY_LOGS : actua
    BUYER_SESSIONS o|--o{ ACTIVITY_LOGS : actua
    CLIENTS o|--o{ NOTIFICATIONS : recibe
    USERS o|--o{ NOTIFICATIONS : recibe
    CREDIT_APPLICATIONS o|--o{ NOTIFICATIONS : contextualiza
    NOTIFICATIONS ||--o{ NOTIFICATION_DELIVERIES : entrega
    USERS o|--o{ IDEMPOTENCY_KEYS : ejecuta
    BUYER_SESSIONS o|--o{ IDEMPOTENCY_KEYS : ejecuta
    USERS o|--o{ AUDIT_EVENTS : actua
    BUYER_SESSIONS o|--o{ AUDIT_EVENTS : actua
    USERS ||--o{ REPORT_EXPORT_JOBS : solicita
    FILE_OBJECTS o|--o| REPORT_EXPORT_JOBS : produce

    TASKS {
        uuid id PK
        uuid opportunity_id FK
        uuid application_id FK
        uuid assigned_to_id FK
        uuid created_by_id FK
        uuid priority_item_id FK
    }
    ACTIVITY_LOGS {
        uuid id PK
        uuid client_id FK
        uuid opportunity_id FK
        uuid application_id FK
        uuid actor_user_id FK
        uuid actor_buyer_session_id FK
    }
    NOTIFICATIONS {
        uuid id PK
        uuid client_id FK
        uuid user_id FK
        uuid application_id FK
        varchar deduplication_key UK
    }
    NOTIFICATION_DELIVERIES {
        uuid id PK
        uuid notification_id FK
        varchar channel
        varchar status
    }
    IDEMPOTENCY_KEYS {
        uuid id PK
        uuid user_id FK
        uuid buyer_session_id FK
        varchar key
    }
    AUDIT_EVENTS {
        uuid id PK
        uuid actor_user_id FK
        uuid actor_buyer_session_id FK
        uuid request_id
    }
    OUTBOX_EVENTS {
        uuid id PK
        varchar aggregate_type
        uuid aggregate_id
        jsonb payload
        varchar status
    }
    REPORT_EXPORT_JOBS {
        uuid id PK
        uuid requested_by_id FK
        uuid output_file_object_id FK, UK
    }
    CLIENTS {
        uuid id PK
    }
    OPPORTUNITIES {
        uuid id PK
    }
    CREDIT_APPLICATIONS {
        uuid id PK
    }
    USERS {
        uuid id PK
    }
    BUYER_SESSIONS {
        uuid id PK
    }
    CATALOG_ITEMS {
        uuid id PK
    }
    FILE_OBJECTS {
        uuid id PK
    }
```

`outbox_events` no usa una FK física porque puede representar eventos de muchas tablas. Guarda `aggregate_type` y `aggregate_id`; su propósito es asegurar que correos, escaneos y trabajos no se pierdan después de guardar el cambio principal.

## 11. Las relaciones N:M del modelo

| Relación conceptual | Tabla intermedia | Restricción que evita duplicados |
| --- | --- | --- |
| Usuarios N:M roles | `user_roles` | (`user_id`, `role_id`) |
| Roles N:M permisos | `role_permissions` | (`role_id`, `permission_id`) |
| Transiciones N:M roles | `workflow_transition_roles` | (`transition_id`, `role_id`) |
| Productos N:M finalidades | `bank_product_purposes` | (`bank_product_id`, `purpose_item_id`) |
| Solicitudes N:M clientes | `application_participants` | (`application_id`, `client_id`) |
| Radicaciones N:M versiones documentales | `filing_document_snapshots` | (`filing_id`, `document_file_id`) |

En el DER físico estas relaciones se dibujan como dos relaciones 1:N hacia la tabla intermedia.

## 12. Relaciones 1:1 o 1:0..1 importantes

| Tabla padre | Tabla hija | Cómo se garantiza |
| --- | --- | --- |
| Participante | Perfil financiero | `financial_profiles.participant_id UNIQUE` |
| Solicitud | Inmueble | `properties.application_id UNIQUE` |
| Solicitud | Preferencia financiera | `financing_preferences.application_id UNIQUE` |
| Enlace mágico | Sesión del comprador | `buyer_sessions.access_link_id UNIQUE` |
| Objeto físico | Versión documental | `document_files.file_object_id UNIQUE` |
| Trabajo de paquete | Radicación | `filings.package_job_id UNIQUE` |
| Objeto físico | Paquete/exportación | FK de salida `UNIQUE` |

## 13. Flujo completo en una frase por etapa

1. Un usuario interno recibe roles y permisos.
2. Un broker o partner registra un cliente y una oportunidad.
3. Un asesor convierte la oportunidad en solicitud.
4. La solicitud reúne participantes, finanzas, inmueble y financiación.
5. Banco, producto y reglas generan los documentos exigidos.
6. Un enlace mágico crea una sesión temporal para el comprador.
7. El comprador carga versiones y el asesor las revisa.
8. Las versiones aprobadas forman un paquete.
9. El asesor registra una radicación manual y congela lo enviado.
10. Cada respuesta bancaria se agrega sin sobrescribir la anterior.
11. Las observaciones habilitan solo los documentos que deben corregirse.
12. Estado, actividad, tareas, notificaciones y auditoría conservan todo el recorrido.

## 14. Fuente física

El diagrama explica las relaciones; el archivo SQL define los detalles ejecutables: tipos, nulabilidad, `ON DELETE`, restricciones únicas, `CHECK` e índices.

- [Esquema PostgreSQL](./ESQUEMA_POSTGRESQL_MVP_CREDITO.sql)
- [Diccionario completo de tablas](./MODELO_DATOS_DER_MVP_CREDITO.md)

## 15. Distribución de tablas por módulo y orden de construcción

Cada tabla tiene un único módulo propietario. Otros módulos pueden consultarla o
referenciarla mediante claves foráneas, pero no deben modificar directamente sus
reglas de negocio. El orden siguiente reduce dependencias y separa las tablas que
solo pueden existir cuando ya están creados sus recursos padre.

| Orden | Módulo | Tablas propietarias | Depende principalmente de |
| ---: | --- | --- | --- |
| 1 | `identity` (núcleo) | `users`, `roles`, `permissions`, `user_roles`, `role_permissions`, `auth_sessions`, `password_reset_tokens` | Ningún módulo de negocio. |
| 2 | `catalogs` | `catalogs`, `catalog_items`, `workflow_transitions`, `workflow_transition_roles` | `identity` para permisos y roles de las transiciones. |
| 3 | `partners` | `partners`, `partner_memberships`, `projects` | `identity` para miembros/creadores y `catalogs` para ciudad. |
| 4 | `identity` (invitaciones) | `internal_invitations` | `partners`, porque una invitación puede reservar una membresía de constructora. |
| 5 | `crm` (núcleo) | `clients`, `client_addresses`, `opportunities`, `opportunity_assignments` | `identity`, `catalogs` y `partners` cuando la oportunidad tenga proyecto. |
| 6 | `banking` | `banks`, `bank_products`, `bank_product_purposes`, `bank_policy_rules` | `catalogs` para tipificaciones e `identity` para el creador de reglas. |
| 7 | `documents` (configuración) | `document_types`, `document_requirements` | `banking` y `catalogs`. |
| 8 | `applications` | `credit_applications`, `application_assignments`, `application_participants`, `financial_profiles`, `income_sources`, `properties`, `financing_preferences`, `bank_rule_evaluations`, `application_status_history` | `crm`, `identity`, `catalogs`, `banking` y `partners` para el proyecto opcional del inmueble. |
| 9 | `identity` (acceso comprador) | `consent_definitions`, `buyer_access_links`, `buyer_sessions`, `consent_records` | `crm`, `applications`, `catalogs` e `identity` núcleo. |
| 10 | `documents` (expediente) | `file_objects`, `application_document_slots`, `document_files`, `document_reviews`, `document_package_jobs` | `applications`, acceso comprador, configuración documental, catálogos e identidad. |
| 11 | `filings` | `filings`, `filing_document_snapshots`, `filing_responses`, `filing_response_observations` | `applications`, `banking`, `documents`, `catalogs` e `identity`. |
| 12 | `crm` (operación) | `tasks`, `activity_logs` | `crm` núcleo, `applications`, acceso comprador, catálogos e identidad. |
| 13 | `notifications` | `notifications`, `notification_deliveries`, `idempotency_keys`, `outbox_events` | `identity`, `crm`, `applications` y acceso comprador. |
| 14 | `audit` | `audit_events` | `identity` y acceso comprador. |
| 15 | `reporting` | `report_export_jobs` | `identity` y `documents.file_objects`; consulta, sin ser dueño, los datos de CRM, solicitudes y radicaciones. |
| 16 | `commissions` | `commission_plans`, `commission_settlements`, `commission_shares` | `banking` para el producto, `applications` y `crm` para asesor y origen, `filings` para el desembolso y `notifications` para el evento `APPLICATION_DISBURSED`. |

### Resumen por módulo

| Módulo | Cantidad | Tablas |
| --- | ---: | --- |
| `identity` | 12 | `users`, `roles`, `permissions`, `user_roles`, `role_permissions`, `auth_sessions`, `password_reset_tokens`, `internal_invitations`, `consent_definitions`, `buyer_access_links`, `buyer_sessions`, `consent_records` |
| `partners` | 3 | `partners`, `partner_memberships`, `projects` |
| `catalogs` | 4 | `catalogs`, `catalog_items`, `workflow_transitions`, `workflow_transition_roles` |
| `crm` | 6 | `clients`, `client_addresses`, `opportunities`, `opportunity_assignments`, `tasks`, `activity_logs` |
| `banking` | 4 | `banks`, `bank_products`, `bank_product_purposes`, `bank_policy_rules` |
| `applications` | 9 | `credit_applications`, `application_assignments`, `application_participants`, `financial_profiles`, `income_sources`, `properties`, `financing_preferences`, `bank_rule_evaluations`, `application_status_history` |
| `documents` | 7 | `document_types`, `document_requirements`, `file_objects`, `application_document_slots`, `document_files`, `document_reviews`, `document_package_jobs` |
| `filings` | 4 | `filings`, `filing_document_snapshots`, `filing_responses`, `filing_response_observations` |
| `notifications` | 4 | `notifications`, `notification_deliveries`, `idempotency_keys`, `outbox_events` |
| `reporting` | 1 | `report_export_jobs` |
| `audit` | 1 | `audit_events` |
| `commissions` | 3 | `commission_plans`, `commission_settlements`, `commission_shares` |
| **Total** | **58** | Todas las tablas persistentes de negocio y plataforma del MVP. |
