# Especificación de API REST

## MVP: Gestión de crédito de vivienda

| Campo | Valor |
| --- | --- |
| Estado | Contrato funcional para revisión |
| Versión del documento | 1.0 |
| Versión de API | `v1` |
| Inventario | 208 operaciones REST documentadas |
| Backend propuesto | Django + Django REST Framework |
| Formato | JSON; `multipart/form-data` únicamente para archivos |
| Fuente funcional | `REQUERIMIENTOS_MVP_CREDITO.md` versión 1.1 |
| Alcance | Operación interna, brokers, constructoras partner y autogestión passwordless |

## 1. Propósito

Este documento define el contrato completo de la API REST del MVP. Es la referencia para backend, frontend Next.js, pruebas y documentación OpenAPI. Incluye rutas, permisos, entradas, respuestas, errores y reglas de negocio.

La API permite:

- captar clientes y oportunidades;
- crear y gestionar solicitudes de crédito;
- entregar acceso passwordless al comprador;
- recopilar y revisar documentos;
- evaluar reglas operativas configurables por banco;
- preparar y registrar radicaciones manuales;
- registrar respuestas bancarias y notificar al comprador;
- administrar proyectos, partners, usuarios y catálogos;
- alimentar Dashboard, Mi día y reportes.

No incluye integración directa con bancos, DataCrédito, seguros ni decisión automática de aprobación.

## 2. URL, versionado y medios

```text
Producción: https://api.example.com/api/v1
Staging:    https://api-staging.example.com/api/v1
Local:      http://localhost:8000/api/v1
```

- Todas las rutas funcionales usan `/api/v1`.
- JSON usa `Content-Type: application/json`.
- Cargas usan `multipart/form-data`.
- Descargas responden con el MIME real o una URL firmada temporal.
- Fechas se envían como ISO-8601 UTC: `2026-08-24T15:30:00Z`.
- Montos COP se representan como enteros de pesos: `294000000`; nunca `float`.
- Identificadores son UUID. Los códigos como `SOL-250184` son legibles, pero no autorizan acceso.
- Un cambio incompatible requiere `/api/v2`. Agregar campos opcionales no rompe `/api/v1`.

## 3. Actores y códigos de acceso

| Código | Actor | Autenticación | Alcance resumido |
| --- | --- | --- | --- |
| `ADMIN` | Administrador | JWT interno + refresh opaco | Acceso completo. |
| `ADVISOR` | Asesor | JWT interno + refresh opaco | Solicitudes asignadas, documentos y radicación. |
| `INDEPENDENT_BROKER` | Broker | JWT interno + refresh opaco | Prospectos propios/asignados, resumen y creación de enlace mágico. |
| `CONSTRUCTION_PARTNER` | Usuario de constructora | JWT interno + refresh opaco | Proyectos de su partner. |
| `BUYER` | Comprador | Sesión opaca creada desde enlace mágico | Un único cliente y expediente. |
| `PUBLIC` | Sin sesión | Ninguna | Salud, consumo de enlace y recuperación de acceso. |

Los filtros de alcance se aplican antes de consultar el objeto. Un UUID válido fuera del alcance responde `404 RESOURCE_NOT_FOUND`, para no confirmar su existencia.

## 4. Cookies, cabeceras y CSRF

### 4.1 Cookies

| Cookie | Actor | Uso | Duración inicial |
| --- | --- | --- | --- |
| `__Host-app_access` | Usuario interno | JWT de acceso | 15 minutos |
| `__Host-app_refresh` | Usuario interno | Refresh opaco rotativo | 8 horas |
| `__Host-buyer_session` | Comprador | Sesión passwordless opaca | 24 horas |
| `app_csrf` | Ambos | Token CSRF legible por Next.js | Igual a la sesión |

Las cookies de sesión usan `HttpOnly`, `Secure`, `SameSite=Lax` y `Path=/`. La cookie CSRF no es `HttpOnly` porque el cliente debe enviarla en la cabecera, pero no contiene credenciales.

### 4.2 Cabeceras

| Cabecera | Obligatoria | Uso |
| --- | --- | --- |
| `X-CSRFToken` | En `POST`, `PUT`, `PATCH`, `DELETE` autenticados | Protección CSRF. |
| `X-Request-ID` | Opcional; la API lo genera si falta | Correlación de logs y tareas. |
| `Idempotency-Key` | En mutaciones críticas indicadas | Evitar duplicados por reintentos. |
| `If-Match` | En edición concurrente de solicitudes y configuraciones versionadas | Contiene la versión esperada, por ejemplo `"7"`. |
| `Accept-Language` | Opcional | Inicialmente `es-CO`. |

## 5. Formatos comunes

### 5.1 Recurso individual

```json
{
  "id": "c73f2f02-0cc9-4fd5-90f7-8dd7aacfb146",
  "code": "SOL-250184",
  "created_at": "2026-08-22T20:10:00Z",
  "updated_at": "2026-08-24T13:34:00Z",
  "version": 7
}
```

### 5.2 Lista paginada

```json
{
  "items": [],
  "page": 1,
  "page_size": 25,
  "total": 128,
  "next": "/api/v1/applications?page=2&page_size=25",
  "previous": null
}
```

- `page_size` por defecto: `25`.
- Máximo: `100`.
- Los filtros y campos de ordenamiento usan lista permitida.
- Orden por defecto: `-created_at`.

### 5.3 Error

```json
{
  "code": "APPLICATION_NOT_READY",
  "message": "La solicitud todavía no cumple los requisitos para radicar.",
  "details": [
    {
      "field": "documents",
      "code": "MISSING_REQUIRED_DOCUMENTS",
      "message": "Faltan 2 documentos obligatorios aprobados o exonerados."
    }
  ],
  "request_id": "d1f98a64-bf42-4b93-a952-754eb5cb98a2"
}
```

### 5.4 Códigos HTTP

| Código | Uso |
| --- | --- |
| `200` | Consulta o mutación exitosa. |
| `201` | Recurso creado. |
| `202` | Trabajo asíncrono aceptado. |
| `204` | Operación exitosa sin cuerpo. |
| `400` | JSON o parámetros inválidos. |
| `401` | No autenticado, sesión vencida o enlace inválido. |
| `403` | Autenticado sin permiso para la acción. |
| `404` | Recurso inexistente o fuera del alcance. |
| `409` | Conflicto de estado, versión o duplicidad. |
| `413` | Archivo supera el tamaño permitido. |
| `415` | MIME o extensión no permitida. |
| `422` | Regla de negocio o idempotencia inválida. |
| `428` | Falta `If-Match` en una edición que lo exige (`PRECONDITION_REQUIRED`). |
| `429` | Rate limit excedido. |
| `500` | Error interno no controlado. |
| `503` | Dependencia temporalmente no disponible. |

### 5.5 Errores estables de negocio

| Código | Significado |
| --- | --- |
| `INVALID_CREDENTIALS` | Credenciales internas inválidas. |
| `USER_INACTIVE` | Usuario interno desactivado. |
| `RATE_LIMITED` | Límite de consumo superado. |
| `SESSION_EXPIRED` | Sesión interna o del comprador vencida. |
| `MAGIC_LINK_EXPIRED` | Enlace mágico vencido. |
| `MAGIC_LINK_CONSUMED` | Enlace ya utilizado. |
| `MAGIC_LINK_REVOKED` | Enlace revocado. |
| `OUT_OF_SCOPE` | Actor fuera del alcance del recurso. |
| `STALE_VERSION` | `If-Match` (o `expected_version`) no coincide con la versión actual. |
| `PRECONDITION_REQUIRED` | Falta `If-Match` en un `PUT`/`PATCH` que lo exige (`428`). |
| `INVALID_STATE_TRANSITION` | Transición no permitida. |
| `APPLICATION_ALREADY_OPEN` | La oportunidad ya tiene una solicitud en curso (`409`). |
| `APPLICATION_NOT_EDITABLE` | Los datos del expediente solo se editan antes de `FILED` (`409`). |
| `APPLICATION_CLOSED` | La solicitud ya terminó: no admite transiciones, desistimiento ni reasignación (`409`). |
| `PARTICIPANT_INACTIVE` | Edición de un participante retirado; hay que agregarlo de nuevo (`409`). |
| `APPLICATION_NOT_READY` | No cumple `READY_TO_FILE` (`422`); `details` trae `BANK_PRODUCT_REQUIRED`, `BANK_RULE_BLOCKED` y `DOCUMENTS_NOT_VERIFIED` según el caso. |
| `BANK_RULE_BLOCKED` | Regla bancaria bloqueante incumplida o sin datos para decidir. |
| `BANK_PRODUCT_REQUIRED` | Evaluar reglas bancarias sin producto elegido (`422`). |
| `FINANCING_MODE_MISMATCH` | Cierre `OWN_FUNDS` o `EXTERNAL_CREDIT_APPROVED` sin la modalidad de financiación correspondiente (`422`). |
| `DOCUMENT_LOCKED` | Documento no modificable en la etapa actual. |
| `DOCUMENT_NOT_REJECTED` | Reemplazo posterior a radicación sin observación. |
| `FILE_NOT_CLEAN` | Archivo sin análisis limpio. |
| `IDEMPOTENCY_CONFLICT` | Misma clave con cuerpo diferente. |
| `DUPLICATE_CLIENT_DOCUMENT` | Documento de identidad ya registrado. |
| `PROJECT_NOT_ACTIVE` | Proyecto borrador/archivado no asociable. |
| `COMMISSION_PLAN_NOT_FOUND` | No hay plan de comisión vigente para el producto en la fecha de desembolso. |
| `COMMISSION_PLAN_OVERLAP` | La vigencia se solapa con otro plan del mismo producto. |
| `COMMISSION_PLAN_IN_USE` | El plan ya fue usado por una liquidación. |
| `APPLICATION_NOT_DISBURSED` | La solicitud no está desembolsada. |
| `COMMISSION_SETTLEMENT_HAS_PAYMENTS` | La liquidación tiene partes pagadas y no se puede anular. |
| `COMMISSION_SHARE_NOT_PAYABLE` | La parte de la comisión no está pendiente de pago. |

## 6. Idempotencia y concurrencia

- `POST` de radicación, respuesta bancaria, transición de estado, generación de paquete y creación de enlace mágico requieren `Idempotency-Key`.
- La clave se conserva 24 horas, asociada a actor, método, ruta y hash del cuerpo.
- Mismo cuerpo y clave: devuelve la respuesta original.
- Cuerpo distinto con la misma clave: `422 IDEMPOTENCY_CONFLICT`.
- `PATCH`/`PUT` sobre solicitudes, bancos, productos, reglas y requisitos usa `If-Match`.
- Versión obsoleta: `409 STALE_VERSION`, con la versión actual en `details[0].current_version`.

Concurrencia de la solicitud de crédito:

- Toda respuesta del expediente (solicitud, participantes, perfiles, ingresos, inmueble, financiación, evaluaciones, historial, acciones y completitud), incluidos los `204`, lleva `ETag: "<version>"` con la versión vigente de la solicitud. La cabecera se expone por CORS.
- Todo cambio del expediente aumenta `version`. Un `PUT`/`PATCH` sin cambios reales no la aumenta.
- Todo `PUT`/`PATCH` que modifica el expediente exige `If-Match`, que acepta `"3"`, `3` o `W/"3"`. Sin la cabecera: `428 PRECONDITION_REQUIRED`.
- Los `POST` que crean subrecursos y los `DELETE` no exigen `If-Match`, pero aumentan la versión.
- `POST /status-transitions` y `POST /withdrawals` llevan `expected_version` en el cuerpo en lugar de `If-Match`.

**Estado de implementación.** `Idempotency-Key` se exigirá cuando exista `idempotency_keys` (notificaciones). Mientras tanto, la creación de solicitudes se protege con la restricción de una sola solicitud no terminal por oportunidad (`409 APPLICATION_ALREADY_OPEN`) y las transiciones con `expected_version`.

## 7. Autenticación interna

### Resumen de endpoints

| Método | Ruta | Actor | Entrada | Respuesta |
| --- | --- | --- | --- | --- |
| `POST` | `/auth/login` | `PUBLIC` | Correo, contraseña | Usuario, permisos y cookies de sesión. |
| `POST` | `/auth/refresh` | Sesión interna | Cookie refresh | Nuevo access y refresh rotado. |
| `POST` | `/auth/logout` | Usuario interno | Sin cuerpo | `204`; revoca sesión actual. |
| `GET` | `/auth/me` | Usuario interno | — | Perfil, rol, permisos y alcance. |
| `POST` | `/auth/password-reset-requests` | `PUBLIC` | Correo | `202` uniforme. |
| `POST` | `/auth/password-resets/confirm` | `PUBLIC` | Token y nueva contraseña | `204`; revoca sesiones. |
| `POST` | `/auth/change-password` | Usuario interno | Contraseña actual y nueva | `204`; revoca otras sesiones. |

### `POST /auth/login`

Rate limit: 5 intentos por correo e IP cada 15 minutos.

```json
{
  "email": "asesor@example.com",
  "password": "••••••••"
}
```

Respuesta `200`:

```json
{
  "user": {
    "id": "uuid",
    "name": "Andrea García",
    "email": "asesor@example.com",
    "role": "ADVISOR"
  },
  "permissions": [
    "applications.read_assigned",
    "documents.review",
    "filings.manage"
  ],
  "session_expires_at": "2026-08-24T23:00:00Z"
}
```

Errores: `INVALID_CREDENTIALS`, `USER_INACTIVE`, `RATE_LIMITED`.

### `GET /auth/me`

La respuesta es la fuente de verdad para ocultar funciones del panel. Next.js no deduce permisos únicamente desde el nombre del rol.

```json
{
  "id": "uuid",
  "name": "Andrea García",
  "role": "ADVISOR",
  "permissions": ["applications.read_assigned", "documents.review", "filings.manage"],
  "scope": {
    "assigned_applications_only": true,
    "partner_id": null
  }
}
```

## 8. Acceso passwordless del comprador

| Método | Ruta | Actor | Entrada | Respuesta |
| --- | --- | --- | --- | --- |
| `POST` | `/applications/{application_id}/buyer-access-links` | `ADMIN`, `ADVISOR`, broker dentro de alcance | Canal y vencimiento opcional | Enlace creado y fecha de vencimiento. |
| `GET` | `/applications/{application_id}/buyer-access-links` | `ADMIN`, `ADVISOR`, broker dentro de alcance | Estado opcional | Historial sin token. |
| `DELETE` | `/buyer-access-links/{link_id}` | `ADMIN`, `ADVISOR`, emisor dentro de alcance | — | `204`; revoca enlace. |
| `POST` | `/buyer-access/consume` | `PUBLIC` | Token mágico | Cookie de comprador y resumen público. |
| `GET` | `/buyer/session` | `BUYER` | — | Sesión, cliente y expediente permitido. |
| `POST` | `/buyer/session/logout` | `BUYER` | — | `204`; revoca sesión temporal. |

### `POST /applications/{application_id}/buyer-access-links`

Requiere `Idempotency-Key`. Crear un nuevo enlace revoca los enlaces pendientes anteriores de la misma solicitud.

```json
{
  "delivery_channel": "COPY_LINK",
  "expires_in_hours": 72
}
```

Respuesta `201`:

```json
{
  "id": "uuid",
  "application_id": "uuid",
  "url": "https://compradores.example.com/acceso?token=token-de-un-solo-uso",
  "expires_at": "2026-08-27T23:00:00Z",
  "status": "PENDING"
}
```

El campo `url` solo se devuelve en la creación. Nunca aparece en listados, logs ni auditoría.

### `POST /buyer-access/consume`

Rate limit: 5 intentos por IP por hora.

```json
{
  "token": "token-recibido-en-la-url"
}
```

Respuesta `200`:

```json
{
  "buyer": { "display_name": "Laura Gómez" },
  "application": {
    "id": "uuid",
    "code": "SOL-250184",
    "public_status": "DOCUMENTS_REVIEW"
  },
  "session_expires_at": "2026-08-25T14:00:00Z"
}
```

El frontend elimina el token de la URL inmediatamente después del consumo.

### Portal del comprador durante la sesión temporal

Estos endpoints usan DTO exclusivos del portal. Aunque internamente consulten los mismos agregados, nunca reutilizan el serializer administrativo ni aceptan un `client_id` como autorización.

| Método | Ruta | Actor | Descripción |
| --- | --- | --- | --- |
| `GET` | `/buyer/processes` | `BUYER` | Devuelve únicamente el proceso asociado a la sesión vigente. |
| `GET` | `/buyer/applications/{application_id}` | `BUYER` | Estado público, progreso, siguiente acción y datos editables. |
| `PATCH` | `/buyer/applications/{application_id}/profile` | `BUYER` | Actualiza datos personales permitidos antes de radicar. |
| `PATCH` | `/buyer/applications/{application_id}/financial-profile` | `BUYER` | Actualiza ocupación, ingresos, gastos, activos y pasivos permitidos. |
| `POST` | `/buyer/applications/{application_id}/withdrawals` | `BUYER` | Registra desistimiento con motivo y cierra el flujo. |

El `application_id` de la ruta debe coincidir con el de la sesión. Un ID válido de otro expediente responde `404`. Tras `FILED`, los endpoints `PATCH` retornan `409 DOCUMENT_LOCKED`; solo permanece habilitada la carga de slots expresamente observados.

## 9. Metadatos públicos para el frontend

| Método | Ruta | Actor | Descripción |
| --- | --- | --- | --- |
| `GET` | `/metadata/bootstrap` | Usuario interno o `BUYER` | Catálogos mínimos, permisos, configuración pública y versión. |
| `GET` | `/metadata/catalogs/{catalog_code}` | Usuario interno o `BUYER` según catálogo | Ítems activos aplicables al actor. |
| `GET` | `/metadata/form-schemas/{form_code}` | Usuario interno o `BUYER` | Campos, tipos, dependencias y validaciones de presentación. |
| `GET` | `/applications/{application_id}/available-actions` | `applications.read` (no broker) | Transiciones que el actor puede ejecutar desde el estado actual, según rol y permiso: `[{code, label, target_status, guard_code}]`. La guarda se evalúa al ejecutarla. Ver §16.3. |

### `GET /metadata/bootstrap`

Soporta `If-None-Match`; puede devolver `304`.

```json
{
  "metadata_version": 18,
  "actor": "ADVISOR",
  "permissions": ["applications.read_assigned", "documents.review"],
  "catalogs": {
    "loan_purpose": [
      { "id": "uuid", "code": "PURCHASE_NEW", "label": "Vivienda nueva", "order": 1 }
    ],
    "application_status": []
  },
  "features": {
    "manual_filing": true,
    "buyer_magic_link": true
  }
}
```

Los endpoints de metadatos no reemplazan las validaciones de backend.

## 10. Usuarios internos, roles e invitaciones

### 10.1 Usuarios

| Método | Ruta | Permiso | Entrada / filtros | Respuesta |
| --- | --- | --- | --- | --- |
| `GET` | `/users` | `users.read` | `role`, `status`, `search`, paginación | Usuarios internos. |
| `POST` | `/users` | `users.create` | Datos básicos y rol | Usuario creado; puede quedar pendiente de invitación. |
| `GET` | `/users/{user_id}` | `users.read` | — | Detalle sin hash ni tokens. |
| `PATCH` | `/users/{user_id}` | `users.update` | Nombre, teléfono y campos permitidos | Usuario actualizado. |
| `POST` | `/users/{user_id}/activate` | `users.manage_status` | Motivo opcional | Usuario activo. |
| `POST` | `/users/{user_id}/deactivate` | `users.manage_status` | Motivo obligatorio | Usuario inactivo y sesiones revocadas. |
| `PUT` | `/users/{user_id}/roles` | `roles.assign` | Lista de roles | Roles reemplazados. |
| `GET` | `/roles` | `roles.read` | — | Roles y permisos disponibles. |

`POST /users`:

```json
{
  "name": "Andrea García",
  "email": "andrea@example.com",
  "phone": "+573001112233",
  "role_codes": ["ADVISOR"],
  "send_invitation": true
}
```

Reglas:

- correo normalizado único;
- un usuario de constructora requiere membresía partner;
- desactivar revoca `auth_sessions`;
- el comprador no se crea en `/users`.

### 10.2 Invitaciones internas

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/invitations` | `invitations.read` | Lista invitaciones internas por correo, rol y estado. |
| `POST` | `/invitations` | `invitations.create` | Crea invitación de usuario interno. |
| `POST` | `/invitations/{invitation_id}/resend` | `invitations.create` | Revoca token anterior y reenvía. |
| `DELETE` | `/invitations/{invitation_id}` | `invitations.revoke` | Revoca invitación pendiente. |
| `POST` | `/invitations/accept` | `PUBLIC` | Consume token y establece contraseña interna. |

`POST /invitations/accept`:

```json
{
  "token": "token-interno",
  "password": "contraseña-segura",
  "password_confirmation": "contraseña-segura"
}
```

## 11. Partners y membresías

### 11.1 Partners

| Método | Ruta | Permiso | Entrada / filtros | Respuesta |
| --- | --- | --- | --- | --- |
| `GET` | `/partners` | `partners.read` | `status`, `city_code`, `search` | Partners visibles. |
| `POST` | `/partners` | `partners.create` | Razón social, NIT, contacto | Partner creado. |
| `GET` | `/partners/{partner_id}` | `partners.read` | — | Detalle y métricas básicas. |
| `PATCH` | `/partners/{partner_id}` | `partners.update` | Datos de contacto permitidos | Partner actualizado. |
| `POST` | `/partners/{partner_id}/activate` | `partners.manage_status` | — | Partner activo. |
| `POST` | `/partners/{partner_id}/deactivate` | `partners.manage_status` | Motivo | Partner inactivo; no crea proyectos. |

### 11.2 Membresías partner

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/partners/{partner_id}/members` | `partner_members.read` | Usuarios de la constructora. |
| `POST` | `/partners/{partner_id}/members` | `partner_members.create` | Agrega usuario existente o crea invitación. |
| `GET` | `/partner-memberships/{membership_id}` | `partner_members.read` | Detalle de membresía. |
| `PATCH` | `/partner-memberships/{membership_id}` | `partner_members.update` | Cargo, estado o datos permitidos. |
| `DELETE` | `/partner-memberships/{membership_id}` | `partner_members.remove` | Finaliza membresía; no borra historial. |

`CONSTRUCTION_PARTNER` solo puede consultar su propia membresía y partner. En el MVP no puede pertenecer simultáneamente a dos partners activos.

## 12. Proyectos inmobiliarios

| Método | Ruta | Permiso | Entrada / filtros | Respuesta |
| --- | --- | --- | --- | --- |
| `GET` | `/projects` | `projects.read` | `status`, `partner_id`, `city_code`, `search` | Proyectos dentro del alcance. |
| `POST` | `/projects` | `projects.create` | Datos del proyecto | Proyecto `DRAFT`. |
| `GET` | `/projects/{project_id}` | `projects.read` | — | Detalle del proyecto. |
| `PATCH` | `/projects/{project_id}` | `projects.update` | Campos editables | Proyecto actualizado. |
| `POST` | `/projects/{project_id}/submit` | `projects.submit` | Nota opcional | Envía a validación. |
| `POST` | `/projects/{project_id}/activate` | `projects.approve` | Comentario opcional | Proyecto `ACTIVE`. |
| `POST` | `/projects/{project_id}/reject` | `projects.approve` | Motivo obligatorio | Regresa a `DRAFT`. |
| `POST` | `/projects/{project_id}/archive` | `projects.archive` | Motivo | Proyecto `ARCHIVED`. |
| `GET` | `/projects/{project_id}/summary` | `projects.read` | — | Conteos de oportunidades y solicitudes, sin PII para partner. |

`POST /projects`:

```json
{
  "name": "Verona 118",
  "partner_id": "uuid",
  "city_code": "11001",
  "address": "Carrera 11 # 118-40",
  "description": "Proyecto de vivienda nueva",
  "estimated_delivery_date": "2027-06-30"
}
```

Reglas:

- para `CONSTRUCTION_PARTNER`, `partner_id` se ignora y se deriva de la membresía;
- un proyecto nuevo siempre inicia `DRAFT`;
- solo `ACTIVE` puede asociarse a nuevas oportunidades;
- archivar no elimina asociaciones históricas.

## 13. Clientes

| Método | Ruta | Permiso | Entrada / filtros | Respuesta |
| --- | --- | --- | --- | --- |
| `GET` | `/clients` | `clients.read` | `search`, `document_type`, `origin`, `status` | Clientes dentro del alcance. |
| `POST` | `/clients` | `clients.create` | Identidad y contacto mínimo | Cliente creado. |
| `GET` | `/clients/{client_id}` | `clients.read` | — | Detalle según rol. |
| `PATCH` | `/clients/{client_id}` | `clients.update` | Campos permitidos | Cliente actualizado. |
| `GET` | `/clients/{client_id}/opportunities` | `clients.read` | Estado, proyecto | Oportunidades del cliente. |
| `GET` | `/clients/{client_id}/applications` | `applications.read` | Estado | Solicitudes visibles. |
| `GET` | `/clients/{client_id}/activity` | `activity.read` | Visibilidad, paginación | Actividad permitida. |
| `POST` | `/clients/{client_id}/notes` | `activity.create_internal` | Texto interno | Nota creada. |

`POST /clients`:

```json
{
  "document_type_code": "CC",
  "document_number": "1032445908",
  "first_names": "Laura",
  "last_names": "Gómez Vélez",
  "email": "laura.gomez@email.com",
  "phone": "+573104458821",
  "origin_type": "BROKER"
}
```

Responde `409 DUPLICATE_CLIENT_DOCUMENT` si existe la combinación documento/tipo. Un broker solo obtiene campos de contacto y resumen; nunca perfiles financieros ni documentos.

## 14. Oportunidades comerciales

| Método | Ruta | Permiso | Entrada / filtros | Respuesta |
| --- | --- | --- | --- | --- |
| `GET` | `/opportunities` | `opportunities.read` | `status`, `broker_id`, `advisor_id`, `project_id`, `search` | Oportunidades según alcance. |
| `POST` | `/opportunities` | `opportunities.create` | Cliente, origen y proyecto opcional | Oportunidad `NEW`. |
| `GET` | `/opportunities/{opportunity_id}` | `opportunities.read` | — | Detalle permitido. |
| `PATCH` | `/opportunities/{opportunity_id}` | `opportunities.update` | Campos comerciales | Oportunidad actualizada. |
| `POST` | `/opportunities/{opportunity_id}/assignments` | `opportunities.assign` | Asesor responsable | Asignación auditada. |
| `POST` | `/opportunities/{opportunity_id}/transitions` | `opportunities.transition` | Estado destino y motivo | Estado cambiado. |
| `GET` | `/opportunities/{opportunity_id}/activity` | `activity.read` | — | Línea de tiempo permitida. |
| `POST` | `/opportunities/{opportunity_id}/notes` | `activity.create_internal` | Nota | Nota interna. |
| `GET` | `/broker/opportunities` | `INDEPENDENT_BROKER` | Estado, atención, paginación | Resumen de prospectos propios/asignados. |

`POST /opportunities`:

```json
{
  "client_id": "uuid",
  "origin_type": "BROKER",
  "project_id": null,
  "notes": "Cliente interesado en vivienda nueva"
}
```

Si existe `project_id`, debe estar `ACTIVE`. El partner no usa estos endpoints en el MVP.

## 15. Mi día y tareas

### 15.1 Mi día

| Método | Ruta | Permiso | Filtros | Respuesta |
| --- | --- | --- | --- | --- |
| `GET` | `/workday/applications` | `ADMIN`, `ADVISOR` | `stage`, `bank_id`, `purpose`, `attention`, `search`, paginación | Solicitudes asignadas al asesor autenticado. |
| `GET` | `/workday/summary` | `ADMIN`, `ADVISOR` | Mismos filtros | Conteos por segmento. |

Para `ADVISOR`, la API siempre aplica `assigned_advisor_id=request.user.id`. No acepta otro asesor desde query. Para `ADMIN`, puede recibir `advisor_id` explícito.

Respuesta reducida:

```json
{
  "items": [
    {
      "id": "uuid",
      "code": "SOL-250184",
      "client_display_name": "Laura Gómez",
      "bank": "Bancolombia",
      "product": "Crédito hipotecario",
      "stage": "DOCUMENTS_REVIEW",
      "next_action": "REVIEW_DOCUMENTS",
      "days_in_stage": 2,
      "updated_at": "2026-08-24T13:34:00Z"
    }
  ],
  "page": 1,
  "page_size": 25,
  "total": 24
}
```

### 15.2 Tareas

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/tasks` | `tasks.read` | Lista tareas dentro del alcance. |
| `POST` | `/tasks` | `tasks.create` | Crea tarea manual. |
| `GET` | `/tasks/{task_id}` | `tasks.read` | Detalle. |
| `PATCH` | `/tasks/{task_id}` | `tasks.update` | Edita título, responsable, fecha o prioridad. |
| `POST` | `/tasks/{task_id}/complete` | `tasks.complete` | Completa tarea. |
| `POST` | `/tasks/{task_id}/cancel` | `tasks.cancel` | Cancela con motivo. |

```json
{
  "title": "Revisar extractos corregidos",
  "application_id": "uuid",
  "assigned_to_id": "uuid",
  "due_at": "2026-08-25T17:00:00Z",
  "priority_code": "HIGH"
}
```

## 16. Solicitudes de crédito

### 16.1 Solicitud principal

| Método | Ruta | Permiso | Entrada / filtros | Respuesta |
| --- | --- | --- | --- | --- |
| `GET` | `/applications` | `applications.read` | `status`, `bank_id`, `product_id`, `purpose`, `advisor_id`, `project_id`, `origin`, `search` | Solicitudes según alcance. |
| `POST` | `/applications` | `applications.create` | Oportunidad, finalidad, asesor e inmueble inicial | Solicitud `DRAFT`. |
| `GET` | `/applications/{application_id}` | `applications.read` | `include` permitido | Expediente según rol. |
| `PATCH` | `/applications/{application_id}` | `applications.update` | Campos editables no relacionados con estado | Solicitud actualizada. |
| `GET` | `/applications/{application_id}/summary` | `applications.read_summary` | — | Resumen operativo o público según actor. |
| `GET` | `/applications/{application_id}/completeness` | `applications.read` (no broker) | — | Porcentaje, ítems de datos y estado documental. |
| `GET` | `/applications/{application_id}/status-history` | `applications.read_history` | Paginación | Historial de estados, de la más reciente a la más antigua. |
| `GET` | `/applications/{application_id}/available-actions` | `applications.read` (no broker) | — | Transiciones ejecutables ahora. |
| `POST` | `/applications/{application_id}/status-transitions` | `applications.transition` | Estado destino, motivo y versión | Transición atómica. |
| `POST` | `/applications/{application_id}/withdrawals` | `applications.withdraw` | Motivo y versión | Solicitud `WITHDRAWN`. |
| `POST` | `/applications/{application_id}/assignments` | `applications.assign` | Asesor | Reasignación auditada. |

`POST /applications` requiere `Idempotency-Key`:

```json
{
  "opportunity_id": "uuid",
  "purpose_code": "PURCHASE_NEW",
  "assigned_advisor_id": "uuid",
  "project_id": "uuid",
  "property": {
    "property_type_code": "APARTMENT",
    "condition_code": "NEW",
    "city_code": "11001",
    "estimated_value_cop": 420000000
  }
}
```

Respuesta `201`:

```json
{
  "id": "uuid",
  "code": "SOL-250184",
  "status": "DRAFT",
  "purpose": { "code": "PURCHASE_NEW", "label": "Vivienda nueva" },
  "assigned_advisor": { "id": "uuid", "name": "Andrea García" },
  "version": 1,
  "created_at": "2026-08-24T13:00:00Z"
}
```

Reglas de creación:

- `property` es opcional: el inmueble puede registrarse después con `PUT /property`. `project_id` va fuera de `property` y exige `property`.
- Sin `assigned_advisor_id` se usa el asesor de la oportunidad. Una oportunidad `NEW` (sin asesor) se rechaza.
- Crear la solicitud convierte la oportunidad a `CONVERTED` en la misma transacción. Sobre una oportunidad ya convertida solo se admite un nuevo intento si todas sus solicitudes anteriores terminaron en `REJECTED`, `WITHDRAWN` o `CANCELLED`.
- La creación registra el titular (`PRIMARY`), la asignación inicial y la primera fila del historial (`from_status` nulo).

Detalle (`GET /applications/{application_id}`):

- `property`, `assignments` y `available_actions` salen siempre.
- `include` agrega bloques opcionales separados por comas (se toleran espacios): `participants` (solo vigentes) y `financing` (`null` si no existe). `property` se admite sin efecto. Un valor desconocido responde `400` en el campo `include`.
- El broker recibe el resumen e `include` se ignora. Solo el `GET` admite `include`.

### 16.2 Edición y concurrencia

`PATCH /applications/{application_id}` exige `If-Match`.

Campos internos editables antes de `FILED`:

- `purpose_code`;
- `bank_product_id`.

Montos, plazo y modalidades van por `PUT /financing` (§18.2), y el asesor, por `/assignments`. El producto debe estar activo, vigente y admitir la finalidad. Con una financiación registrada, el producto debe cuadrar con su modalidad: solo `BANK_CREDIT` lleva producto, y con `BANK_CREDIT` no se puede dejar sin él (`400`). Cambiar la finalidad exige que el producto elegido y el inmueble registrado la admitan. Elegir un producto guarda una evaluación de sus reglas (§18.2).

El estado nunca se cambia por `PATCH`; se usa `/status-transitions`.

### 16.3 Transición de estado

```json
{
  "target_status": "READY_TO_FILE",
  "reason_code": "CHECKLIST_APPROVED",
  "comment": "Todos los requisitos fueron revisados.",
  "expected_version": 7
}
```

Respuesta `200`:

```json
{
  "application_id": "uuid",
  "previous_status": "DOCUMENTS_REVIEW",
  "status": "READY_TO_FILE",
  "version": 8,
  "transitioned_at": "2026-08-24T15:30:00Z"
}
```

La operación crea en una transacción: estado, `application_status_history`, `activity_logs` y tareas automáticas aplicables.

Reglas:

- `expected_version` es obligatorio (no se usa `If-Match`); si no coincide, `409 STALE_VERSION`. La respuesta lleva `ETag`.
- Sobre una solicitud terminada: `409 APPLICATION_CLOSED`. Sin transición configurada entre los dos estados: `409 INVALID_STATE_TRANSITION`.
- `WITHDRAWN` no se acepta aquí (`400`): va por `/withdrawals`.
- `reason_code` (catálogo `application_transition_reason`) es obligatorio al pasar a `CANCELLED`, `OWN_FUNDS` y `EXTERNAL_CREDIT_APPROVED`, y opcional en las demás. Debe ser un ítem activo. `comment` admite hasta 2000 caracteres.
- `OWN_FUNDS` exige una financiación registrada con modalidad `OWN_FUNDS`, y `EXTERNAL_CREDIT_APPROVED`, con `EXTERNAL_CREDIT`. Si no: `422 FINANCING_MODE_MISMATCH` (`details` en `financing_mode_code`).
- Cada transición pone `current_stage_started_at` en el momento del cambio y aumenta `version`. Llegar a `READY_TO_FILE` fija `ready_to_file_at`; volver a `DOCUMENTS_REVIEW` lo limpia, y se conserva al avanzar o al cerrar. Un estado terminal fija `closed_at`.

Guarda `APPLICATION_READY_TO_FILE` (transición a `READY_TO_FILE`):

- Exige producto elegido y una evaluación bancaria vigente sin bloqueos. Si la última evaluación no corresponde a la versión y al producto actuales, la transición evalúa y la guarda; esa evaluación se conserva aunque la transición se rechace.
- Exige también los documentos obligatorios aprobados o exonerados. Hasta que exista el expediente documental (§19), esta parte falla cerrada: `READY_TO_FILE` no se puede alcanzar.
- Si no la cumple: `422 APPLICATION_NOT_READY` con todos los motivos en `details`:

```json
{
  "code": "APPLICATION_NOT_READY",
  "message": "La solicitud todavía no cumple las condiciones para radicar.",
  "details": [
    {
      "field": "financing.requested_amount_cop",
      "code": "BANK_RULE_BLOCKED",
      "message": "El monto no puede superar el 70% del valor del inmueble."
    },
    {
      "field": "documents",
      "code": "DOCUMENTS_NOT_VERIFIED",
      "message": "Los documentos obligatorios todavía no se pueden verificar: el expediente documental aún no está disponible."
    }
  ],
  "request_id": "req_01J..."
}
```

Sin producto, el primer motivo es `BANK_PRODUCT_REQUIRED` (campo `bank_product_id`).

Transiciones configuradas hoy (flujo `APPLICATION`), solo hasta antes de radicar:

- `DRAFT → WAITING_BUYER_DATA → WAITING_DOCUMENTS → DOCUMENTS_REVIEW → READY_TO_FILE`, con los saltos `DRAFT → WAITING_DOCUMENTS` y `DOCUMENTS_REVIEW → WAITING_DOCUMENTS`, y la reapertura `READY_TO_FILE → DOCUMENTS_REVIEW`;
- `CANCELLED`, `OWN_FUNDS` y `EXTERNAL_CREDIT_APPROVED` desde los cinco estados previos a la radicación;
- `WITHDRAWN` desde todo estado no terminal, solo por `/withdrawals`.

Las transiciones de `FILED` en adelante llegan con la radicación (§20).

#### Desistimiento

`POST /applications/{application_id}/withdrawals`:

```json
{
  "reason_code": "OTHER_FINANCING",
  "comment": "Compró con otra entidad.",
  "expected_version": 9
}
```

- `reason_code` (catálogo `application_withdrawal_reason`) y `expected_version` son obligatorios.
- Se admite desde cualquier estado no terminal, también después de `FILED`. En una solicitud terminada: `409 APPLICATION_CLOSED`.
- Fija `withdrawn_at`, `withdrawal_reason` y `closed_at`, y usa la transición `WITHDRAW_<estado>`. Responde con la misma forma que la transición.

#### Historial de estados

`GET /applications/{application_id}/status-history` es una lista paginada, de la más reciente a la más antigua, que incluye el registro de creación (`from_status` nulo):

```json
{
  "id": "uuid",
  "from_status": "DOCUMENTS_REVIEW",
  "to_status": "CANCELLED",
  "transition_code": "CANCEL_DOCUMENTS_REVIEW",
  "reason": { "code": "CLIENT_UNREACHABLE", "label": "No fue posible contactar al cliente" },
  "comment": "",
  "actor": { "id": "uuid", "name": "Andrea García" },
  "application_version": 8,
  "created_at": "2026-08-24T15:30:00Z"
}
```

#### Acciones disponibles

`available_actions` del detalle y `GET /applications/{application_id}/available-actions` devuelven las transiciones que el actor puede ejecutar desde el estado actual según su rol y permiso. La guarda no se evalúa aquí, sino al ejecutar la transición. Incluyen `WITHDRAW_*`, que se ejecuta por `/withdrawals`.

```json
[
  {
    "code": "MARK_READY_TO_FILE",
    "label": "Marcar lista para radicar",
    "target_status": "READY_TO_FILE",
    "guard_code": "APPLICATION_READY_TO_FILE"
  }
]
```

#### Completitud

`GET /applications/{application_id}/completeness`:

```json
{
  "percentage": 60,
  "ready_to_file": false,
  "items": [
    { "code": "property", "complete": true, "message": "Inmueble registrado.", "participant_id": null },
    { "code": "financial_profile", "complete": false, "message": "Registra el perfil financiero de Mateo Vargas León.", "participant_id": "uuid" }
  ],
  "documents": {
    "verified": false,
    "message": "Los documentos obligatorios todavía no se pueden verificar: el expediente documental aún no está disponible."
  }
}
```

- Ítems de datos: `property`, `financing`, `bank_product` y `bank_evaluation` (vigente y elegible; estos dos solo sin financiación registrada o con `BANK_CREDIT`), y `financial_profile` por cada participante activo que aporta ingresos.
- `percentage` = ítems completos / total, entero hacia abajo. Los documentos todavía no cuentan, y `ready_to_file` es `false` hasta que exista el expediente documental (§19).

## 17. Participantes, finanzas e ingresos

### 17.1 Participantes

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/applications/{application_id}/participants` | `applications.read` o comprador del expediente | Lista solicitante principal y adicionales. |
| `POST` | `/applications/{application_id}/participants` | `applications.update` o comprador antes de `FILED` | Agrega co-solicitante/deudor. |
| `GET` | `/application-participants/{participant_id}` | Actor con alcance | Detalle permitido. |
| `PATCH` | `/application-participants/{participant_id}` | Actor con alcance, antes de `FILED` | Actualiza datos. |
| `DELETE` | `/application-participants/{participant_id}` | `applications.update`, antes de `FILED` | Retira participante no principal. |

```json
{
  "role_code": "CO_APPLICANT",
  "document_type_code": "CC",
  "document_number": "1015882421",
  "first_names": "Mateo",
  "last_names": "Vargas León",
  "contributes_income": true
}
```

El cuerpo lleva `client_id` de un cliente visible o el bloque de identidad plano (`document_type_code`, `document_number`, `first_names`, `last_names`, `birth_date`, `email`, `phone`), nunca ambos. El bloque crea el cliente con las mismas reglas que `POST /clients` (`409 DUPLICATE_CLIENT_DOCUMENT` si el documento ya existe). `role_code` admite `CO_APPLICANT` o `SOLIDARY_DEBTOR`. `income_share_cop` (aporte declarado al hogar) exige `contributes_income = true`. El modelo de datos no tiene relación de parentesco.

Reglas:

- exactamente un `PRIMARY` por solicitud;
- `PRIMARY` no se elimina;
- cada participante que aporta ingresos requiere perfil financiero y documentos aplicables;
- no se agregan ni retiran después de `FILED`;
- la lista muestra los vigentes; `?include_inactive=true` agrega los retirados;
- `PATCH` cambia `role_code`, `contributes_income` e `income_share_cop` (exige `If-Match`); los datos personales se corrigen en `/clients/{client_id}`;
- `DELETE` marca el participante como retirado (`is_active = false`); repetirlo responde `204`;
- editar un participante retirado, su perfil o sus fuentes responde `409 PARTICIPANT_INACTIVE`; volver a agregar el mismo cliente lo reactiva en su fila.

### 17.2 Perfil financiero

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/application-participants/{participant_id}/financial-profile` | Actor con alcance | Perfil financiero. |
| `PUT` | `/application-participants/{participant_id}/financial-profile` | Actor editable antes de `FILED` | Crea o reemplaza campos permitidos. |
| `GET` | `/financial-profiles/{profile_id}/income-sources` | Actor con alcance | Fuentes de ingreso. |
| `POST` | `/financial-profiles/{profile_id}/income-sources` | Actor editable | Agrega fuente. |
| `PATCH` | `/income-sources/{income_source_id}` | Actor editable | Actualiza fuente. |
| `DELETE` | `/income-sources/{income_source_id}` | Actor editable | Retira fuente. |

`PUT /application-participants/{participant_id}/financial-profile`:

```json
{
  "employment_profile_code": "EMPLOYEE",
  "contract_type_code": "INDEFINITE",
  "employer_name": "Tecnología Andina SAS",
  "employment_start_date": "2022-02-01",
  "monthly_income_cop": 7800000,
  "monthly_expenses_cop": 2450000,
  "assets_cop": 96000000,
  "liabilities_cop": 18200000,
  "funds_origin_code": "SALARY"
}
```

La API recalcula requisitos documentales si cambia el perfil laboral, pero conserva el historial de slots previos.

Reglas:

- `PUT` exige `If-Match` y hace un reemplazo completo: lo que no llega vuelve a su valor por omisión. Responde `201` si crea el perfil y `200` si lo reemplaza.
- `employment_profile_code` (catálogo `employment_profile`) es obligatorio; `employment_start_date` no puede ser futura; `data_confirmed_at` no se acepta.
- El detalle expone `income_sources_total_cop` (suma de las fuentes) junto a `monthly_income_cop`, solo como información: la suma no se valida.
- Como máximo una fuente `is_primary` por perfil: marcar una nueva desmarca la anterior. `PATCH` de una fuente exige `If-Match`; `DELETE` la borra.

## 18. Inmueble y financiación

### 18.1 Inmueble

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/applications/{application_id}/property` | Actor con alcance | Inmueble de la solicitud. |
| `PUT` | `/applications/{application_id}/property` | Actor editable antes de `FILED` | Crea o reemplaza datos del inmueble. |

```json
{
  "property_type_code": "APARTMENT",
  "condition_code": "NEW",
  "project_id": "uuid",
  "unit_reference": "Torre 2 · Apto 803",
  "city_code": "11001",
  "address": "Carrera 11 # 118-40",
  "estimated_value_cop": 420000000,
  "is_owned_by_applicant": false
}
```

Reglas por finalidad:

- `PURCHASE_NEW`: permite `project_id`; proyecto debe estar `ACTIVE`.
- `PURCHASE_USED`: exige ciudad, dirección y valor; proyecto no es obligatorio.
- `HOME_IMPROVEMENT`: exige inmueble existente y declaración de propiedad/relación; los soportes dependen del banco.

`PUT` exige `If-Match` y hace un reemplazo completo (`201` si crea, `200` si reemplaza). `project_id` va dentro del cuerpo; un proyecto que no está `ACTIVE` responde `422 PROJECT_NOT_ACTIVE`. El `GET` responde `404` mientras no haya inmueble. Las reglas por finalidad también se aplican al crear la solicitud y al cambiar su finalidad.

### 18.2 Preferencias de financiación

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/applications/{application_id}/financing` | Actor con alcance | Preferencia actual. |
| `PUT` | `/applications/{application_id}/financing` | Actor editable antes de `FILED` | Selecciona banco/producto y valores. |
| `GET` | `/applications/{application_id}/eligible-bank-products` | `applications.read` (no broker) o comprador | Productos disponibles para la finalidad, con evaluación no guardada. |
| `POST` | `/applications/{application_id}/bank-rule-evaluations` | `applications.update` (no broker) o comprador | Evalúa reglas sin cambiar estado. |
| `GET` | `/applications/{application_id}/bank-rule-evaluations/latest` | `applications.read` (no broker) | Último resultado. |

`PUT /applications/{application_id}/financing`:

```json
{
  "financing_mode_code": "BANK_CREDIT",
  "bank_product_id": "uuid",
  "requested_amount_cop": 294000000,
  "term_months": 240,
  "currency_mode_code": "COP",
  "amortization_mode_code": "FIXED_PAYMENT",
  "own_resources_cop": 126000000,
  "uses_severance_funds": true,
  "severance_funds_cop": 30000000
}
```

Reglas del `PUT /financing` (exige `If-Match`, reemplazo completo, `201`/`200`):

- `financing_mode_code` (catálogo `financing_mode`) es obligatorio.
- `BANK_CREDIT` exige `bank_product_id` (activo, vigente y que admita la finalidad) y `requested_amount_cop`. El producto se guarda en la solicitud.
- `OWN_FUNDS` y `EXTERNAL_CREDIT` no llevan producto (se limpia el de la solicitud) y `requested_amount_cop` queda en 0: puede omitirse o llegar en 0.
- `external_approved_amount_cop` es obligatorio con `EXTERNAL_CREDIT` y no se acepta en los otros modos.
- Sin `uses_severance_funds`, `severance_funds_cop` debe ser 0.
- Los rangos de monto y plazo del producto no se validan al guardar: los verifica la evaluación de reglas.

`POST /applications/{application_id}/bank-rule-evaluations` responde `201`:

```json
{
  "id": "uuid",
  "bank_product_id": "uuid",
  "application_version": 7,
  "is_current": true,
  "eligible": false,
  "blocking": [
    {
      "rule_code": "MAX_LTV",
      "outcome": "FAILED",
      "message": "El monto solicitado supera el 70% configurado del valor del inmueble.",
      "field": "financing.requested_amount_cop",
      "unresolved_fields": []
    }
  ],
  "warnings": [],
  "evaluated_at": "2026-08-24T15:10:00Z"
}
```

Evaluación de reglas:

- Exige producto elegido (`422 BANK_PRODUCT_REQUIRED`) y solo se admite antes de `FILED` (`409 APPLICATION_NOT_EDITABLE`). No exige `If-Match` ni cambia la versión.
- Aplica las reglas publicadas y vigentes del producto (§23.3) y dos reglas del sistema, siempre `BLOCKING`: `PRODUCT_AMOUNT_RANGE` (`requested_amount_cop` contra `min/max_amount_cop`) y `PRODUCT_TERM_RANGE` (`term_months` contra `min/max_term_months`). Si el producto no define el rango, esa regla no aparece; si falta el dato, da `MISSING_DATA`.
- Falla cerrada: una regla `BLOCKING` con `FAILED` o `MISSING_DATA` deja `eligible = false`. Las `WARNING` van a `warnings` y no afectan la elegibilidad. Las reglas que se cumplen no aparecen en la respuesta.
- Cada ítem trae `outcome` (`FAILED` o `MISSING_DATA`) y `field`, la ruta completa del campo de la lista segura: el primero que falta o, si se incumple, el primero que cita la condición. Con `MISSING_DATA`, `message` es del sistema ("Faltan datos para evaluar la regla: …") y `unresolved_fields` lista los campos.
- El resultado guarda la versión exacta de cada regla y el contexto evaluado, y la respuesta se reconstruye siempre desde ese registro.
- Elegir un producto con `PATCH /applications` o `PUT /financing` guarda una evaluación en la misma transacción. Los demás cambios dejan la última con `is_current = false`.

`GET .../bank-rule-evaluations/latest` devuelve la más reciente con la misma forma, aunque la solicitud haya cambiado después: `is_current` es verdadero si la versión y el producto coinciden con los actuales. Responde `404` solo si nunca se evaluó.

`GET /applications/{application_id}/eligible-bank-products` es una lista paginada de los productos activos y vigentes (con banco activo) que admiten la finalidad, ordenada por banco y producto. Cada uno trae una evaluación **no guardada** con los datos actuales, incluidas las reglas del sistema. Se listan aunque la modalidad registrada no sea `BANK_CREDIT`:

```json
{
  "id": "uuid",
  "code": "MORTGAGE",
  "name": "Crédito hipotecario",
  "bank": { "id": "uuid", "code": "BANCOLOMBIA", "name": "Bancolombia" },
  "product_type_code": "MORTGAGE",
  "min_amount_cop": 50000000,
  "max_amount_cop": 800000000,
  "min_term_months": 60,
  "max_term_months": 360,
  "evaluation": { "eligible": true, "blocking_count": 0, "warning_count": 1 }
}
```

Estas reglas validan preparación operativa; no aprueban ni rechazan el crédito.

## 19. Expediente documental

El expediente se modela como una lista de requisitos (`document slots`). Cada slot representa un documento esperado y conserva todas sus versiones. Los archivos no se reemplazan físicamente ni se eliminan: una nueva carga crea una nueva versión.

### 19.1 Lista de documentos y vigencia de requisitos

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/applications/{application_id}/document-slots` | `ADMIN`, asesor asignado o comprador | Lista de chequeo, estado, obligatoriedad y versión vigente. |
| `POST` | `/applications/{application_id}/document-slots/refresh` | `ADMIN` o asesor asignado con `documents.manage_requirements` | Recalcula requisitos según banco, finalidad, participantes y perfil laboral. |
| `GET` | `/document-slots/{slot_id}` | `ADMIN`, asesor asignado o comprador | Detalle del requisito. |
| `GET` | `/document-slots/{slot_id}/versions` | `ADMIN`, asesor asignado o comprador | Historial de versiones del documento. |
| `POST` | `/document-slots/{slot_id}/uploads` | Comprador del expediente | Carga una nueva versión con `multipart/form-data`. |
| `PATCH` | `/document-slots/{slot_id}/review` | `ADMIN` o asesor asignado con `documents.review` | Aprueba, rechaza o exonera el requisito. |
| `GET` | `/document-files/{file_id}` | `ADMIN`, asesor asignado o comprador | Metadatos de una versión, filtrados por rol. |
| `GET` | `/document-files/{file_id}/download` | `ADMIN`, asesor asignado o comprador | Obtiene URL firmada de descarga con vigencia corta. |
| `GET` | `/document-files/{file_id}/scan-status` | `ADMIN` o asesor asignado | Consulta validación antivirus y técnica. |

Filtros de la lista: `status`, `participant_id`, `document_type_code`, `required=true|false`.

Estados de un slot: `MISSING`, `UPLOADED`, `IN_REVIEW`, `APPROVED`, `REJECTED`, `WAIVED`. Estados técnicos del archivo: `PENDING_SCAN`, `CLEAN`, `INFECTED`, `INVALID`.

Carga de archivo:

```http
POST /api/v1/document-slots/00e6.../uploads
Content-Type: multipart/form-data

file=<archivo>
client_filename=certificacion_laboral.pdf
```

```json
{
  "data": {
    "id": "uuid",
    "slot_id": "uuid",
    "version": 2,
    "filename": "certificacion_laboral.pdf",
    "mime_type": "application/pdf",
    "size_bytes": 483220,
    "scan_status": "PENDING_SCAN",
    "slot_status": "UPLOADED",
    "uploaded_at": "2026-08-24T16:00:00Z"
  }
}
```

Revisión:

```json
{
  "decision": "REJECTED",
  "reason_code": "OUTDATED",
  "buyer_comment": "La certificación laboral debe tener menos de 30 días.",
  "internal_comment": "Fecha de expedición: 2 de junio."
}
```

Reglas:

- `APPROVED` exige una versión `CLEAN`; `WAIVED` exige motivo y permiso específico.
- Un archivo `INFECTED` o `INVALID` no puede descargarse ni aprobarse.
- El comprador puede cargar documentos mientras la solicitud no esté radicada.
- Broker y partner solo reciben avance/resumen del expediente; no pueden cargar, listar versiones ni descargar archivos.
- Después de `FILED`, solo puede cargar una nueva versión en un slot `REJECTED` por observación.
- La respuesta nunca expone la clave real del almacenamiento; la descarga usa URL firmada y auditada.
- Cambiar banco, producto, finalidad, participantes o perfil laboral vuelve a evaluar los requisitos sin borrar el historial.

### 19.2 Paquete para radicación

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `POST` | `/applications/{application_id}/document-package-jobs` | `ADMIN` o asesor asignado con `filings.prepare` | Genera de forma asíncrona el paquete ZIP/PDF para el banco. |
| `GET` | `/document-package-jobs/{job_id}` | `ADMIN` o asesor asignado que inició el trabajo | Consulta progreso, errores y vencimiento. |
| `GET` | `/document-package-jobs/{job_id}/download` | `ADMIN` o asesor asignado con `filings.prepare` | Descarga el paquete terminado mediante URL firmada. |

La creación requiere `Idempotency-Key`. Si falta un documento obligatorio aprobado o exonerado, retorna `409 APPLICATION_NOT_READY` con la lista de bloqueos. El paquete incluye manifiesto, versiones aprobadas y hash SHA-256 de cada archivo.

## 20. Radicación manual y respuestas del banco

La radicación del MVP se registra después de que el asesor descargue el paquete y lo entregue por el canal externo definido por el banco. La API no se comunica con ninguna entidad financiera.

### 20.1 Radicaciones

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/applications/{application_id}/filings` | Actor con alcance | Historial de radicaciones y re-radicaciones. |
| `POST` | `/applications/{application_id}/filings` | `filings.create` | Registra la entrega manual al banco. |
| `GET` | `/filings/{filing_id}` | Actor con alcance | Detalle y estado de la radicación. |
| `PATCH` | `/filings/{filing_id}` | `filings.update` | Corrige referencia o comentario, sin alterar evidencias históricas. |
| `GET` | `/filings/{filing_id}/document-snapshots` | `ADMIN` o asesor asignado | Versiones exactas que conformaron la radicación. |

`POST /applications/{application_id}/filings`:

```json
{
  "bank_product_id": "uuid",
  "package_job_id": "uuid",
  "external_reference": "RAD-2026-008154",
  "filed_at": "2026-08-25T14:30:00Z",
  "channel_code": "BANK_PORTAL",
  "comment": "Radicada manualmente por el asesor."
}
```

Respuesta resumida:

```json
{
  "data": {
    "id": "uuid",
    "sequence": 1,
    "status": "FILED",
    "external_reference": "RAD-2026-008154",
    "application_status": "FILED",
    "filed_by": { "id": "uuid", "name": "Ana Gómez" },
    "filed_at": "2026-08-25T14:30:00Z"
  }
}
```

Precondiciones:

- La solicitud tiene banco y producto seleccionados.
- Todos los documentos obligatorios están `APPROVED` o `WAIVED`.
- La evaluación operativa de reglas no tiene bloqueos.
- El asesor autenticado está asignado a la solicitud.
- El paquete corresponde a la versión actual del expediente.
- La operación exige `Idempotency-Key` e `If-Match`.

Al crearla, la API cambia la solicitud a `FILED`, bloquea la edición ordinaria, guarda el snapshot documental y crea el evento de auditoría.

### 20.2 Respuestas y observaciones del banco

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/filings/{filing_id}/responses` | Actor con alcance | Historial cronológico de respuestas. |
| `POST` | `/filings/{filing_id}/responses` | `filings.record_response` | Registra una respuesta recibida manualmente. |
| `GET` | `/filing-responses/{response_id}` | Actor con alcance | Detalle de la respuesta y sus motivos. |
| `GET` | `/filing-responses/{response_id}/evidence/download` | `ADMIN` o asesor asignado | Descarga evidencia adjunta, si existe. |

Tipos admitidos:

| `response_type` | Nuevo estado de solicitud | Datos obligatorios |
| --- | --- | --- |
| `UNDER_REVIEW` | `UNDER_BANK_REVIEW` | Fecha de respuesta. |
| `RETURNED` | `RETURNED` | Motivo, mensaje para comprador y slots observados. |
| `APPROVED` | `APPROVED` | Monto aprobado, plazo, vigencia y condiciones conocidas. |
| `REJECTED` | `REJECTED` | Código de motivo y explicación visible para el comprador. |
| `DISBURSED` | `DISBURSED` | Fecha y monto desembolsado. |

Ejemplo de devolución:

```json
{
  "response_type": "RETURNED",
  "received_at": "2026-08-29T19:10:00Z",
  "reason_code": "DOCUMENT_CORRECTION",
  "buyer_message": "El banco solicita actualizar dos documentos.",
  "internal_comment": "Respuesta recibida por correo.",
  "observations": [
    {
      "document_slot_id": "uuid",
      "reason_code": "OUTDATED",
      "message": "Cargar certificación laboral expedida hace menos de 30 días."
    },
    {
      "document_slot_id": "uuid",
      "reason_code": "ILLEGIBLE",
      "message": "Volver a cargar el desprendible de nómina de julio."
    }
  ],
  "evidence_file_id": "uuid"
}
```

Ejemplo de aprobación:

```json
{
  "response_type": "APPROVED",
  "received_at": "2026-09-03T13:00:00Z",
  "approved_amount_cop": 285000000,
  "approved_term_months": 240,
  "valid_until": "2026-12-03",
  "buyer_message": "Tu crédito fue aprobado. Tu asesor se comunicará contigo para continuar.",
  "conditions": "Sujeto a legalización del inmueble."
}
```

Cada respuesta es inmutable. Una corrección se registra como una nueva respuesta vinculada a la anterior. `RETURNED`, `APPROVED` y `REJECTED` generan una notificación al comprador; una devolución marca únicamente los slots observados como `REJECTED`. Una nueva radicación se crea después de corregir y aprobar esos documentos.

## 21. Actividad, notas, consentimientos y notificaciones

### 21.1 Trazabilidad funcional

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/applications/{application_id}/activity` | Actor con alcance o comprador | Línea de tiempo filtrada según actor. |
| `GET` | `/applications/{application_id}/notes` | Actor interno con alcance | Notas internas paginadas. |
| `POST` | `/applications/{application_id}/notes` | `applications.add_note` | Agrega nota interna. |
| `GET` | `/applications/{application_id}/consents` | Actor con alcance | Evidencias de tratamientos y declaraciones. |
| `POST` | `/buyer/applications/{application_id}/consents` | Comprador | Acepta una versión vigente del consentimiento. |

El comprador nunca recibe notas internas, comentarios de evaluación, identidades técnicas ni eventos de auditoría. Un consentimiento guarda tipo, versión del texto, fecha, IP, agente de usuario y huella de la sesión.

### 21.2 Notificaciones del comprador

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/buyer/notifications` | Comprador | Notificaciones de su expediente. |
| `PATCH` | `/buyer/notifications/{notification_id}/read` | Comprador | Marca una notificación como leída. |
| `POST` | `/buyer/notifications/read-all` | Comprador | Marca todas como leídas. |

Eventos mínimos: invitación, documento rechazado, expediente listo, radicación, devolución, aprobación, rechazo y desembolso. La notificación en la aplicación es la fuente de verdad; el correo es un canal de entrega y sus fallos no revierten la operación principal.

## 22. Dashboard, Mi día y reportes

Los resultados siempre respetan el alcance del usuario: el asesor ve asignaciones propias; el broker, sus clientes; el partner, sus proyectos y solicitudes; el administrador, toda la operación.

### 22.1 Dashboard

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/dashboard/summary` | `dashboard.read` | Indicadores principales por periodo. |
| `GET` | `/dashboard/funnel` | `dashboard.read` | Solicitudes por etapa y conversión. |
| `GET` | `/dashboard/workload` | `dashboard.read` | Carga por asesor, vencimientos y pendientes. |
| `GET` | `/dashboard/bank-results` | `dashboard.read` | Radicaciones, devoluciones, aprobaciones y rechazos por banco. |

Parámetros comunes: `date_from`, `date_to`, `advisor_id`, `partner_id`, `project_id`, `bank_id`, `purpose_code`. Los filtros fuera del alcance del usuario retornan `403`, no resultados vacíos engañosos.

### 22.2 Reportes operativos

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/reports/funnel` | `reports.read` | Embudo reportable por periodo y filtros. |
| `GET` | `/reports/applications` | `reports.read` | Reporte paginado de solicitudes. |
| `GET` | `/reports/applications.csv` | `reports.export` | Exportación CSV directa para resultados pequeños. |
| `GET` | `/reports/applications/export-jobs` | `reports.export` | Lista de exportaciones solicitadas. |
| `POST` | `/reports/applications/export-jobs` | `reports.export` | Genera CSV/XLSX asíncrono con los filtros actuales. |
| `GET` | `/report-export-jobs/{job_id}` | Propietario o `reports.manage` | Consulta el estado de la exportación. |
| `GET` | `/report-export-jobs/{job_id}/download` | Propietario o `reports.manage` | Descarga el archivo mediante URL firmada. |
| `GET` | `/reports/advisors` | `reports.read` | Productividad y carga de asesores. |
| `GET` | `/reports/banks` | `reports.read` | Resultado y tiempos por banco/producto. |
| `GET` | `/reports/document-quality` | `reports.read` | Rechazos, recargas y tiempos de aprobación documental. |

Las exportaciones contienen solo campos autorizados para el rol, registran auditoría y vencen. Los campos personales sensibles se enmascaran cuando el permiso no exige verlos completos.

## 23. Administración y parametrización

Los recursos de esta sección son administrados por API y consumidos por el frontend como datos. En el cliente web no se duplican listas de bancos, notarías, finalidades, estados, tipos documentales ni reglas de transición.

### 23.1 Catálogos y tipificaciones

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/catalogs` | `catalogs.read` | Lista de catálogos configurables. |
| `POST` | `/catalogs` | `catalogs.create` | Crea un catálogo. |
| `GET` | `/catalogs/{catalog_id}` | `catalogs.read` | Detalle y versión. |
| `PATCH` | `/catalogs/{catalog_id}` | `catalogs.update` | Actualiza metadatos. |
| `GET` | `/catalogs/{catalog_id}/items` | `catalogs.read` | Lista valores, filtros y orden. |
| `POST` | `/catalogs/{catalog_id}/items` | `catalogs.create` | Crea un valor. |
| `PUT` | `/catalogs/{catalog_id}/items/order` | `catalogs.update` | Reordena valores. |
| `GET` | `/catalog-items/{item_id}` | `catalogs.read` | Detalle del valor. |
| `PATCH` | `/catalog-items/{item_id}` | `catalogs.update` | Cambia etiqueta, metadatos o vigencia. |
| `POST` | `/catalog-items/{item_id}/activate` | `catalogs.update` | Activa el valor. |
| `POST` | `/catalog-items/{item_id}/deactivate` | `catalogs.update` | Desactiva sin afectar datos históricos. |

Cada elemento tiene `code` estable, `label`, `description`, `sort_order`, `active`, `valid_from`, `valid_to` y `metadata`. Ejemplos de catálogos: departamentos, municipios, tipos de documento, parentescos, perfiles laborales, finalidades, motivos de devolución/rechazo, canales de radicación y notarías.

Los códigos usados históricamente no se renombran ni eliminan. Si dejan de aplicar, se desactivan y se conserva su etiqueta para lectura de expedientes anteriores.

### 23.2 Bancos y productos

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/banks` | `banks.read` | Lista bancos y filtros. |
| `POST` | `/banks` | `banks.create` | Crea banco. |
| `GET` | `/banks/{bank_id}` | `banks.read` | Detalle y productos. |
| `PATCH` | `/banks/{bank_id}` | `banks.update` | Actualiza datos operativos. |
| `POST` | `/banks/{bank_id}/activate` | `banks.update` | Habilita para nuevas solicitudes. |
| `POST` | `/banks/{bank_id}/deactivate` | `banks.update` | Deshabilita sin alterar historial. |
| `GET` | `/bank-products` | `banks.read` | Lista productos; `available=true` deja solo los elegibles hoy. |
| `POST` | `/bank-products` | `banks.create` | Crea producto de crédito. |
| `GET` | `/bank-products/{product_id}` | `banks.read` | Condiciones, rangos y finalidades activas. |
| `PATCH` | `/bank-products/{product_id}` | `banks.update` | Actualiza producto. |
| `POST` | `/bank-products/{product_id}/activate` | `banks.update` | Activa producto. |
| `POST` | `/bank-products/{product_id}/deactivate` | `banks.update` | Desactiva producto. |
| `PUT` | `/bank-products/{product_id}/purposes` | `banks.update` | Define finalidades admitidas. |

Para el MVP existen tres bancos de prueba —Bancolombia, Fondo Nacional del Ahorro y Banco de Bogotá— y un producto hipotecario configurable por banco. Ningún campo o endpoint presume comunicación automática con ellos.

Semilla inicial (paso 6): cada banco tiene un producto `MORTGAGE` activo —"Crédito hipotecario" en Bancolombia y FNA, "Crédito de vivienda" en Banco de Bogotá— que admite `PURCHASE_NEW`, `PURCHASE_USED` y `HOME_IMPROVEMENT`, sin montos ni plazos y vigente desde `2026-01-01`. No se siembran reglas.

Acceso (decisión del paso 6, alineada con la matriz 8.6 de requerimientos): `banks.read` y `bank_rules.read` son de `ADMIN` y `ADVISOR`; crear, editar, activar y desactivar bancos, productos y reglas es solo de `ADMIN`. `INDEPENDENT_BROKER` y `CONSTRUCTION_PARTNER` reciben `403` en `/banks`, `/bank-products` y `/bank-policy-rules`.

Un producto es elegible en una fecha si el banco y el producto están `ACTIVE`, la fecha está dentro de su vigencia (`valid_from`–`valid_to`) y, para una finalidad, esa finalidad está activa en el producto. `PUT /bank-products/{product_id}/purposes` reemplaza la lista: las finalidades que salen se desactivan, no se borran.

> **Pendiente del paso 8.** La elección de banco dentro de una solicitud no pasa por `/banks` ni `/bank-products`: se resuelve en `GET /applications/{application_id}/eligible-bank-products` (sección 18.2), que combinará los productos elegibles para la finalidad e inmueble de la solicitud con la evaluación de sus reglas. Ese endpoint define qué ve cada actor con alcance sobre la solicitud, incluido el comprador.

### 23.3 Reglas operativas por banco

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/bank-policy-rules` | `bank_rules.read` | Lista reglas, versiones y filtros. |
| `POST` | `/bank-policy-rules` | `bank_rules.create` | Crea una regla inicialmente inactiva. |
| `GET` | `/bank-policy-rules/{rule_id}` | `bank_rules.read` | Detalle de expresión, alcance y versión. |
| `PATCH` | `/bank-policy-rules/{rule_id}` | `bank_rules.update` | Crea/edita borrador de una regla. |
| `POST` | `/bank-policy-rules/{rule_id}/activate` | `bank_rules.publish` | Publica la versión tras validación. |
| `POST` | `/bank-policy-rules/{rule_id}/deactivate` | `bank_rules.publish` | Detiene su aplicación futura. |
| `POST` | `/bank-policy-rules/{rule_id}/test` | `bank_rules.update` | Ejecuta casos de prueba sin afectar solicitudes. |
| `GET` | `/bank-policy-rules/{rule_id}/versions` | `bank_rules.read` | Historial inmutable de versiones. |

Una regla define banco/producto, finalidad, perfil del solicitante, severidad (`BLOCKING` o `WARNING`), condición declarativa, mensaje y vigencia. No se admite código Python/JavaScript enviado por usuarios. El motor solo interpreta operadores permitidos (`eq`, `in`, `gte`, `lte`, `and`, `or`, `sum`, `ratio`) sobre campos incluidos en una lista segura.

Ejemplo conceptual:

```json
{
  "code": "MAX_LTV_NEW_HOME",
  "bank_product_id": "uuid",
  "purpose_code": "PURCHASE_NEW",
  "severity": "BLOCKING",
  "condition": {
    "operator": "lte",
    "left": {
      "operator": "ratio",
      "numerator_field": "financing.requested_amount_cop",
      "denominator_field": "property.estimated_value_cop"
    },
    "right": 0.7
  },
  "message": "El monto solicitado no puede superar el 70% del valor del inmueble."
}
```

Las evaluaciones guardan la versión exacta de las reglas aplicadas. Cambiar una regla no modifica retrospectivamente el resultado histórico.

#### Gramática de la condición

El backend interpreta la condición con un intérprete propio de operadores: recorre el JSON y solo reconoce los nodos de esta gramática. No usa `eval` ni nada que ejecute código; un operador o un campo desconocido se rechaza.

```text
condición   := comparación | pertenencia | lógica
comparación := {"operator": "eq" | "gte" | "lte", "left": valor, "right": valor}
pertenencia := {"operator": "in", "left": valor, "right": [literal, ...]}
lógica      := {"operator": "and" | "or", "conditions": [condición, ...]}
valor       := literal | campo | suma | razón
campo       := {"field": "<campo permitido>"}
suma        := {"operator": "sum", "fields": ["<campo numérico>", ...]}       (2 o más)
razón       := {"operator": "ratio", "numerator_field": "<campo numérico>",
                "denominator_field": "<campo numérico>"}
literal     := número | texto | booleano
```

- Tipos: `gte` y `lte` comparan números; `eq` compara valores del mismo tipo; `in` compara un número o un texto con una lista no vacía de literales del mismo tipo.
- Cada objeto lleva exactamente sus claves; una clave de más es un error.
- Límites: 6 niveles de profundidad, 60 nodos, 50 elementos por lista y 200 caracteres por texto.
- Los números se evalúan como decimales exactos (`0.1 + 0.2 = 0.3`).
- Una condición no válida responde `400 VALIDATION_ERROR` y `details[].field` señala el nodo, por ejemplo `condition.conditions.1.left.field`.

La condición describe lo que **debe cumplirse**. Cada evaluación devuelve:

| Resultado | Significado |
| --- | --- |
| `PASSED` | Se cumple. |
| `FAILED` | No se cumple: la regla aplica su severidad (`BLOCKING` o `WARNING`) y su mensaje. |
| `MISSING_DATA` | Falta un dato o un denominador vale cero; `unresolved_fields` lista los campos. |

`and` y `or` usan lógica de tres valores: `and` es falso si alguna parte es falsa aunque falten datos en otra; `or` es verdadero si alguna parte lo es.

#### Campos permitidos

La lista segura vive en un solo lugar del backend, `apps/banking/rule_fields.py`. La solicitud construye el contexto de evaluación con esta forma; cada campo aparece siempre y un dato que la solicitud todavía no tiene llega como `null` (`MISSING_DATA`):

| Grupo | Campos |
| --- | --- |
| `application` | `purpose_code` (texto), `is_joint` (booleano: hay un `CO_APPLICANT` activo), `participant_count` (participantes activos, incluido el titular) |
| `applicant` (titular) | `employment_profile_code` y `contract_type_code` (textos), `employment_months` (meses completos desde el inicio del empleo), `monthly_income_cop`, `monthly_expenses_cop`, `assets_cop`, `liabilities_cop` |
| `household` | `monthly_income_cop`, `monthly_expenses_cop` y `liabilities_cop`: sumas de los participantes activos que aportan ingresos. En el ingreso se usa `income_share_cop` si está informado y, si no, el del perfil; si a uno le falta el perfil, gastos y pasivos son `null` |
| `property` | `property_type_code`, `condition_code` y `city_code` (textos), `estimated_value_cop`, `is_owned_by_applicant` y `has_project` (booleanos) |
| `financing` | `financing_mode_code`, `currency_mode_code` y `amortization_mode_code` (textos), `requested_amount_cop`, `term_months`, `own_resources_cop`, `severance_funds_cop`, `external_approved_amount_cop`, `uses_severance_funds` (booleano) |

Los campos sin tipo indicado son números. Además de las reglas configuradas, cada evaluación aplica los rangos de monto y plazo del producto como reglas del sistema (`PRODUCT_AMOUNT_RANGE` y `PRODUCT_TERM_RANGE`, §18.2). El "perfil del solicitante" no tiene columna propia en `bank_policy_rules`: se expresa en la condición, por ejemplo `{"operator": "in", "left": {"field": "applicant.employment_profile_code"}, "right": ["EMPLOYEE"]}`. Un `purpose_code` vacío significa que la regla aplica a todas las finalidades.

#### Versionado y publicación

Una regla lógica es el par (producto, `code`); cada fila de `bank_policy_rules` es una versión.

- `POST` crea la versión 1 en `DRAFT`. Si el código ya existe en el producto, responde `409 DUPLICATE_CODE`: los cambios se hacen con `PATCH`.
- `PATCH` sobre un `DRAFT` lo edita en el sitio (`200`).
- `PATCH` sobre una versión `ACTIVE` o `INACTIVE` no la modifica: crea un `DRAFT` con `version + 1` (la siguiente a la mayor existente) que copia lo que no cambia (`201`).
- Solo existe un `DRAFT` por regla. Si ya hay uno, el `PATCH` sobre la versión publicada responde `409 RULE_DRAFT_EXISTS` con el id del borrador en `details[0].resource_id`, para editarlo.
- `activate` publica la versión (`DRAFT` o `INACTIVE`) y la `ACTIVE` anterior de la misma regla pasa a `INACTIVE` en la misma transacción. Antes vuelve a validar la condición con la lista segura vigente (`422 RULE_CONDITION_INVALID`) y rechaza una vigencia ya vencida (`422 RULE_EXPIRED`).
- `deactivate` pasa la versión `ACTIVE` a `INACTIVE`; sobre un `DRAFT` responde `409 INVALID_STATE_TRANSITION`.
- Producto, código y versión no se editan. El historial (`/versions`) es inmutable: de una versión solo cambia su estado, nunca su contenido.
- Al evaluar, aplican las versiones `ACTIVE` del producto vigentes en ese momento, sin finalidad o con la finalidad de la solicitud.

#### Casos de prueba

`POST /bank-policy-rules/{rule_id}/test` evalúa la versión indicada, en cualquier estado, sin modificarla ni tocar solicitudes:

```json
{
  "cases": [
    {
      "name": "Supera el 70%",
      "context": {
        "financing": {"requested_amount_cop": 250000000},
        "property": {"estimated_value_cop": 300000000}
      },
      "expected": "FAILED"
    }
  ]
}
```

Acepta de 1 a 20 casos. El `context` solo admite campos de la lista segura con su tipo; un campo puede faltar o ser `null`. La respuesta trae, por caso, `outcome`, `unresolved_fields`, `expected` y `matches_expected`.

### 23.4 Tipos y requisitos documentales

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/document-types` | Usuario interno | Lista tipos documentales. |
| `POST` | `/document-types` | `document_requirements.create` | Crea tipo documental. |
| `GET` | `/document-types/{document_type_id}` | Usuario interno | Detalle y restricciones técnicas. |
| `PATCH` | `/document-types/{document_type_id}` | `document_requirements.update` | Actualiza metadatos. |
| `POST` | `/document-types/{document_type_id}/activate` | `document_requirements.publish` | Activa el tipo. |
| `POST` | `/document-types/{document_type_id}/deactivate` | `document_requirements.publish` | Desactiva el tipo. |
| `GET` | `/document-requirements` | `document_requirements.read` | Reglas de documentos obligatorios/opcionales. |
| `POST` | `/document-requirements` | `document_requirements.create` | Crea requisito en borrador. |
| `GET` | `/document-requirements/{requirement_id}` | `document_requirements.read` | Detalle y alcance. |
| `PATCH` | `/document-requirements/{requirement_id}` | `document_requirements.update` | Actualiza borrador. |
| `POST` | `/document-requirements/{requirement_id}/activate` | `document_requirements.publish` | Publica el requisito. |
| `POST` | `/document-requirements/{requirement_id}/deactivate` | `document_requirements.publish` | Lo desactiva para casos futuros. |
| `POST` | `/document-requirements/preview` | `document_requirements.read` | Simula la lista documental con un caso de prueba. |

Un tipo documental define formatos MIME, tamaño máximo, titular posible y vigencia sugerida. Un requisito combina banco/producto, finalidad, condición del inmueble, tipo de participante y perfil de ingreso; además indica si es obligatorio, repetible y exonerable.

Documentos base contemplados por las reglas del MVP:

- Identificación por ambas caras; firma/huella cuando el formato operativo del banco lo exija.
- Autorización de tratamiento de datos y declaraciones requeridas.
- Empleado: certificación laboral vigente, comprobantes de nómina y certificado de ingresos y retenciones o declaración de renta, según aplique.
- Independiente: extractos bancarios recientes, declaración de renta o certificado de no declarante y soportes de actividad/ingresos.
- Pensionado: certificación de pensión y desprendibles de pago recientes.
- Compra nueva: separación/promesa o documento del proyecto/unidad, según etapa.
- Compra usada: promesa de compraventa y soportes disponibles del inmueble.
- Remodelación: evidencia de propiedad o relación con el inmueble, presupuesto y soportes de la intervención.
- Participante adicional/deudor solidario: identificación e ingresos con las mismas reglas de su perfil.

La cantidad exacta de meses, vigencia y obligatoriedad se parametriza por producto; no se codifica en el frontend.

### 23.5 Flujo de estados

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/workflow-transitions` | `workflow.read` | Transiciones configuradas y filtros. |
| `POST` | `/workflow-transitions` | `workflow.create` | Crea transición inactiva. |
| `GET` | `/workflow-transitions/{transition_id}` | `workflow.read` | Detalle, guardas y permiso requerido. |
| `PATCH` | `/workflow-transitions/{transition_id}` | `workflow.update` | Actualiza una transición inactiva. |
| `POST` | `/workflow-transitions/{transition_id}/activate` | `workflow.publish` | Habilita la transición. |
| `POST` | `/workflow-transitions/{transition_id}/deactivate` | `workflow.publish` | Deshabilita para operaciones futuras. |

Aunque las transiciones se consultan por API, los estados estructurales del dominio se mantienen como constantes del backend para proteger invariantes. La configuración decide qué transición está disponible, para quién y bajo qué guardas; no puede crear un salto que viole reglas como radicar sin documentos completos.

### 23.6 Comisiones

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/commission-plans` | `commission_plans.read` | Lista planes; filtros por producto y fecha de vigencia. |
| `POST` | `/commission-plans` | `commission_plans.manage` | Crea plan; valida porcentajes y solapamiento de vigencias. |
| `GET` | `/commission-plans/{plan_id}` | `commission_plans.read` | Detalle. |
| `PATCH` | `/commission-plans/{plan_id}` | `commission_plans.manage` | Edita solo si ninguna liquidación lo usa. |
| `POST` | `/commission-plans/{plan_id}/close` | `commission_plans.manage` | Fija el fin de vigencia. |
| `GET` | `/commission-settlements` | `commissions.read` | Lista liquidaciones; filtros por estado, banco, asesor, broker, fechas y revisión pendiente. |
| `GET` | `/commission-settlements/{settlement_id}` | `commissions.read` | Detalle con sus partes. |
| `POST` | `/applications/{application_id}/commission-settlement` | `commissions.manage` | Liquida manualmente una solicitud `DISBURSED`; idempotente. |
| `POST` | `/commission-settlements/{settlement_id}/void` | `commissions.manage` | Anula con motivo, si ninguna parte está pagada. |
| `POST` | `/commission-shares/{share_id}/pay` | `commissions.manage` | Registra el pago de una parte con fecha y referencia. |
| `GET` | `/me/commissions` | `commissions.read_own` | Partes propias del asesor o broker autenticado. |

La liquidación se crea automáticamente al procesar el evento `APPLICATION_DISBURSED`, que se emite en la misma transacción que la respuesta bancaria de desembolso. Usa el monto desembolsado y el plan vigente del producto en la fecha de desembolso. Con origen broker, la comisión se reparte entre asesor y broker según el plan; con cualquier otro origen, el 100% es del asesor. Los `POST` de liquidación, anulación y pago requieren `Idempotency-Key`. En `/me/commissions` cada usuario ve solo su parte; el broker no ve monto base, tasa, total ni la parte del asesor. Detalle completo en `specs/TAREA-comisiones.md`.

## 24. Auditoría y operación técnica

### 24.1 Auditoría

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/audit-events` | `audit.read` | Busca eventos por actor, recurso, acción, fecha o request ID. |
| `GET` | `/audit-events/{event_id}` | `audit.read` | Detalle de cambios permitidos y contexto técnico. |

La auditoría es de solo lectura desde la API. Registra autenticación, enlaces mágicos, lectura/descarga de archivos, cambios de datos sensibles, revisiones, asignaciones, transiciones, radicaciones, respuestas bancarias, exportaciones y cambios de configuración. Contraseñas, tokens, archivos y secretos nunca se copian al evento.

### 24.2 Estado del servicio y contrato OpenAPI

| Método | Ruta | Acceso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/health` | Infraestructura | Comprueba que el proceso responde. |
| `GET` | `/ready` | Infraestructura | Comprueba base de datos, caché y almacenamiento. |
| `GET` | `/openapi.json` | Interno/autorizado | Contrato OpenAPI generado y versionado. |
| `GET` | `/docs` | Solo desarrollo o red interna | Interfaz Swagger UI. |

`/health` no consulta dependencias ni revela versiones. `/ready` responde únicamente `ready`/`not_ready`; los detalles técnicos van a logs internos. En producción, la documentación interactiva no debe ser pública.

## 25. Matriz resumida de acceso por módulo

| Módulo | Admin | Asesor | Broker | Partner | Comprador |
| --- | --- | --- | --- | --- | --- |
| Dashboard y reportes | Todo | Propio/asignado | Propio | Propio/proyectos | No |
| Usuarios y roles | Todo | No | No | Miembros propios limitados | No |
| Clientes/oportunidades | Todo | Asignados | Propios | Propios/proyectos | Su expediente |
| Proyectos | Todo | Lectura relacionada | Lectura relacionada | CRUD propio | Lectura del asociado |
| Solicitudes | Todo | Asignadas | Originadas | Originadas | Su solicitud |
| Expediente | Todo | Revisar/descargar asignadas | Solo resumen, sin archivos | Solo resumen, sin archivos | Cargar/ver permitido |
| Radicación/respuestas | Todo | Gestionar asignadas | Solo seguimiento | Solo seguimiento | Estado visible |
| Bancos, reglas y requisitos | CRUD/publicar | Lectura | Lectura pública aplicable | Lectura pública aplicable | Opciones aplicables |
| Auditoría | Todo | No, salvo actividad funcional | No | No | No |
| Comisiones | Planes, liquidación y pagos | Solo su parte | Solo su parte | No | No |

La matriz es orientativa; la autorización real combina permiso, rol, pertenencia al partner, originador, asesor asignado y recurso solicitado. Nunca se autoriza únicamente porque el ID del recurso sea válido.

En bancos y reglas, la configuración (`/banks`, `/bank-products`, `/bank-policy-rules`) solo la consultan `ADMIN` y `ADVISOR` (sección 23.2). La "lectura pública aplicable" de broker, partner y comprador se entregará por solicitud en `GET /applications/{application_id}/eligible-bank-products`, pendiente del paso 8.

## 26. Límites de consumo

| Operación | Límite sugerido | Clave |
| --- | --- | --- |
| Login interno | 5 intentos / 15 min | IP + correo normalizado |
| Solicitud de recuperación | 3 / hora | IP + correo |
| Consumo de enlace mágico | 5 intentos / 15 min | IP + token hash |
| Creación/reenvío de enlace mágico | 5 / hora por solicitud | Usuario + solicitud |
| Carga de documentos | 30 / hora | Sesión + solicitud |
| Descarga de archivos/paquetes | 60 / hora | Usuario/sesión |
| Escrituras generales | 120 / min | Usuario |
| Lecturas generales | 600 / min | Usuario |
| Exportaciones | 5 trabajos / hora | Usuario |

Al superar el límite se retorna `429 RATE_LIMITED` y `Retry-After`. Los números son configuración inicial y deben ajustarse con observabilidad; no sustituyen los límites de tamaño, cuotas de almacenamiento ni protección perimetral.

## 27. Flujos completos consumiendo la API

### 27.1 Broker invita al comprador

1. El broker crea o reutiliza cliente con `POST /clients`.
2. Crea oportunidad con `POST /opportunities`.
3. Crea solicitud con `POST /applications` y queda como originador.
4. El sistema asigna asesor o un administrador usa `PUT /applications/{id}/assignments`.
5. El broker crea el enlace con `POST /applications/{id}/buyer-access-links`.
6. Comparte la URL fuera de la plataforma por el canal acordado.
7. El comprador abre la URL y el frontend consume `POST /buyer-access/consume`.
8. Consulta `GET /buyer/session` y continúa sin cuenta ni contraseña.

### 27.2 Autogestión documental

1. El comprador consulta esquema y opciones en `/metadata/*`.
2. Completa participantes, finanzas, inmueble y financiación en los endpoints de la solicitud.
3. Consulta `GET /applications/{id}/document-slots`.
4. Carga cada archivo con `POST /document-slots/{id}/uploads`.
5. El asesor revisa con `PATCH /document-slots/{id}/review`.
6. Si rechaza, la API notifica y el comprador carga una nueva versión.
7. `GET /applications/{id}/completeness` indica cuándo está lista para radicar.

### 27.3 Radicación, devolución y re-radicación

1. El asesor genera el paquete con `POST /applications/{id}/document-package-jobs`.
2. Consulta el trabajo y descarga el resultado.
3. Entrega manualmente los documentos al banco.
4. Registra la radicación con `POST /applications/{id}/filings`.
5. Registra `RETURNED` en `POST /filings/{id}/responses` y señala los slots observados.
6. El comprador accede con un enlace vigente/nuevo y reemplaza solamente esos documentos.
7. El asesor revisa las nuevas versiones, genera otro paquete y crea una nueva radicación.
8. Cuando llega respuesta, registra `APPROVED` o `REJECTED`; el cliente ve estado y motivo permitido.

### 27.4 Solicitud originada por constructora

> **Nota.** El paso 2 contradice REQUERIMIENTOS §3 ("el usuario de constructora no crea ni consulta expedientes de compradores"), y **manda REQUERIMIENTOS §3**: el usuario `CONSTRUCTION_PARTNER` no tiene acceso a `/applications`. La solicitud asociada al proyecto la crea un asesor o un administrador.

1. El partner crea y publica un proyecto autorizado.
2. Un miembro registra cliente, oportunidad y solicitud asociada al proyecto/unidad.
3. La plataforma asigna un asesor interno.
4. El partner acompaña la captura, pero el asesor revisa y radica manualmente igual que en el flujo de broker.
5. Los permisos impiden que el partner consulte solicitudes de otro proyecto u organización.

## 28. Criterios transversales de implementación

### 28.1 Seguridad

- Contraseñas internas con Argon2id; nunca reversibles ni visibles en logs.
- JWT de acceso corto y refresh rotativo en cookies `HttpOnly`, `Secure` y `SameSite=Lax/Strict` según el despliegue.
- Protección CSRF en toda escritura autenticada por cookie.
- Enlaces mágicos con token aleatorio de alta entropía, un solo uso, expiración y almacenamiento exclusivo de su hash.
- Autorización por objeto en cada consulta y escritura; respuestas `404` cuando revelar existencia facilite enumeración.
- Validación estricta de JSON, listas permitidas, tamaños y MIME real de archivos.
- Antivirus, almacenamiento privado, cifrado en tránsito y en reposo, URLs firmadas breves.
- Cabeceras seguras, CORS por lista explícita, límites de cuerpo, timeouts y rate limiting distribuido.
- Redacción de PII, tokens y secretos en logs; secretos fuera del repositorio y rotación por ambiente.
- Operaciones sensibles auditadas y alertas ante fuerza bruta, descargas anómalas o elevación de privilegios.

### 28.2 Consultas, filtros y paginación

- Listas: `page`, `page_size` (máximo 100), `ordering` y `search` solo en campos permitidos.
- Fechas: `date_from` inclusivo y `date_to` exclusivo, documentado en UTC.
- Los filtros se combinan con el alcance del actor antes de ejecutar la consulta.
- Índices mínimos: estados/fechas de solicitudes, asesor asignado, originador, partner/proyecto, banco, slots por solicitud y eventos por recurso/fecha.
- No se aceptan nombres arbitrarios de campos para ordenar o filtrar.

### 28.3 Tareas asíncronas

Correo, escaneo antivirus, paquetes documentales, exportaciones y notificaciones externas se ejecutan en workers. La escritura principal usa transacción de base de datos y patrón outbox para no perder eventos entre PostgreSQL y la cola. Los trabajos son reintentables e idempotentes; un fallo termina en cola de errores y genera alerta operativa.

### 28.4 Borrado y retención

El MVP utiliza desactivación o archivo lógico en usuarios, partners, proyectos, catálogos, bancos y configuración. Solicitudes, participantes, documentos, radicaciones, respuestas, consentimientos y auditoría no ofrecen `DELETE` público. Una política posterior de retención/anonimización debe implementarse como proceso administrativo auditado, no como eliminación directa desde la interfaz.

## 29. Contrato, pruebas y definición de terminado

La implementación debe publicar un `openapi.json` generado por DRF y validado en integración continua. El contrato es la fuente para generar tipos del frontend Next.js y para pruebas de compatibilidad.

Cada endpoint se considera terminado cuando cumple:

- Serializer de entrada y salida explícito; no expone modelos completos por accidente.
- Autenticación, permiso y alcance por objeto probados.
- Caso exitoso, validaciones `400/422`, no autenticado `401`, prohibido `403/404`, conflicto `409` y rate limit cuando aplique.
- Transacción, idempotencia y control de concurrencia en escrituras críticas.
- Auditoría de la acción y redacción de datos sensibles.
- Prueba de contrato contra OpenAPI.
- Prueba del cliente Next.js para estados de carga, vacío, error, éxito y permisos.
- Documentación con ejemplo realista y código de error estable.

Pruebas de flujo obligatorias:

1. Login, refresh rotativo, logout y revocación.
2. Enlace mágico válido, vencido, reutilizado, revocado y limitado a otro expediente.
3. Broker/partner sin acceso cruzado a clientes, proyectos o solicitudes.
4. Asesor solo ve solicitudes asignadas en `Mi día`.
5. Requisitos cambian al modificar perfil, finalidad, banco o participante.
6. Archivo inválido/infectado no se aprueba ni descarga.
7. No se puede radicar sin banco o con documentos pendientes.
8. Snapshot de radicación conserva las versiones exactas.
9. Tras radicar, el comprador solo reemplaza slots observados.
10. Devolución, aprobación y rechazo actualizan estado, actividad y notificación una sola vez.
11. Dos escrituras con versión antigua producen `409 STALE_VERSION`.
12. Repetir una operación con la misma `Idempotency-Key` no duplica radicaciones, respuestas ni exportaciones.

## 30. Convenciones para la especificación OpenAPI

- `operationId` estable en formato `recurso_accion`, por ejemplo `applications_create`.
- Tags por módulo: `Auth`, `Buyer access`, `Metadata`, `Users`, `Partners`, `Projects`, `Clients`, `Opportunities`, `Workday`, `Applications`, `Documents`, `Filings`, `Notifications`, `Reports`, `Configuration`, `Audit`.
- Todos los esquemas de escritura tienen `additionalProperties: false` salvo metadatos controlados.
- Los enums públicos incluyen descripción, no solo el código.
- Los endpoints mutadores documentan `Idempotency-Key` e `If-Match` cuando aplican.
- Los ejemplos nunca contienen tokens válidos, datos personales reales ni rutas internas de almacenamiento.
- Los cambios incompatibles requieren `/api/v2`; agregar campos opcionales o nuevos valores compatibles mantiene `/api/v1`.

## 31. Fuera del alcance del contrato v1

- Integraciones automáticas con bancos, centrales de riesgo, notarías o aseguradoras.
- Aprobación crediticia automática, scoring financiero o promesa de otorgamiento.
- Venta de seguros.
- Multi-tenant SaaS completo y facturación por organización.
- Firma electrónica avanzada.
- Chat en tiempo real y aplicación móvil nativa.

Estos límites no impiden que el diseño use adaptadores internos, IDs estables y reglas versionadas. La API v1 se concentra en captar, completar, revisar, radicar manualmente y hacer seguimiento trazable a solicitudes de crédito para vivienda nueva, vivienda usada y remodelación.
