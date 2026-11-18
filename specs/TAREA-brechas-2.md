# TAREA — Brechas de backend 2 (contrato para los fronts)

**Agente:** backend-b. **Worktree:** `wt-back-gaps`, rama `feat/backend-gaps`, desde `origin/master`. Base de pruebas `mvp_credit_b`.
**Origen:** las secciones "Brechas que dejó la F1/F2/F3/F4" de `specs/TAREA-frontend-base.md` y lo que dejaron los módulos 11 a 16.
**Regla de oro:** **solo se agrega al contrato**; nada que ya existe cambia de forma ni de nombre (los fronts ya lo usan). Si algo no se puede hacer sin romper, anótalo y sigue.

## Reglas
- Git solo lectura. No leas ni edites `.env*`. No preguntes: decide lo más simple, anótalo en "Precisiones acordadas" y en el reporte.
- Pruebas acotadas; siempre `ruff`, `mypy .`, `makemigrations --check`, `spectacular --validate --fail-on-warn` y **regenerar `schema.d.ts`** (`npx --yes openapi-typescript@7.13.0 ../contracts/openapi.json -o src/lib/api/schema.d.ts` en `frontend/`).
- Etiquetas siempre con `ChoiceLabelField` / del catálogo, como en el resto del proyecto. Enums nuevos con nombre fijo en `ENUM_NAME_OVERRIDES` y en `tests/test_contract_names.py`.
- Cada punto con su prueba. Las consultas no crecen con las filas (si agregas un campo a un listado, prueba el número de consultas).

## Parte 1 — Oportunidades y clientes (las necesita el front 2 ya)
1. **`OpportunityDetail.available_actions`** pasa a lista de objetos con la misma forma que `AvailableAction` de solicitudes: `[{code, label, kind, target_status, target_status_label, reason_required}]`. **Esto sí cambia la forma de un campo existente**: es la única excepción permitida, porque hoy ningún front lo usa (la F4 lo dejó fuera a propósito). Etiquetas y destino salen de `WorkflowTransition` filtrado por rol; `kind`: la conversión es `primary`, perder y cancelar son `destructive`, el resto `secondary`. `reason_required` = la transición exige motivo (`opportunity_lost_reason`).
2. **`reason_required`** también en `AvailableAction` de **solicitudes** (campo nuevo; brecha F1).
3. **`Opportunity` y `OpportunityDetail`**: `status_label` (catálogo `opportunity_status`).
4. **`OpportunityDetail.assignments`** tipado en el contrato (un serializer con nombre: `id`, `advisor {id, name}`, `assigned_by {id, name}`, `reason`, `created_at`, `ended_at`).
5. **`notes` en `POST /opportunities`**: opcional, hasta 2000 caracteres; se guarda como la primera nota o donde ya viva el texto de la oportunidad (revisa el modelo; si no hay campo, crea una nota de actividad). API §14 ya lo documenta.
6. **Auto-asignación al crear** (decidido): si quien crea la oportunidad tiene rol `ADVISOR`, queda asignada a él y pasa a `ASSIGNED` en la misma transacción, con su registro en `opportunity_assignments` y en el historial. Si la crea un broker o el admin, queda como hoy (`NEW`, sin asesor).
7. **`Client.applications_count`** en el listado y el detalle (anotación, sin consultas por fila).
8. **Contrato del broker**: `GET /clients` y `GET /clients/{id}` documentan las dos formas (`Client` y `BrokerClient`) con `oneOf` o, si `spectacular` no lo deja limpio, con un serializer de respuesta por rol documentado en la descripción. Lo importante: que `openapi.json` describa lo que de verdad responde al broker.
9. **`409 DUPLICATE_CLIENT_DOCUMENT`**: el contrato describe `details[].resource_id` (solo cuando el usuario puede ver el cliente).

## Parte 2 — Etiquetas y datos que faltan en expediente, documentos y radicación
1. `status_label` en: `BuyerConsent`, `BuyerDocumentVersion`, `DocumentPackageJob`, `BuyerAccessLink`. `scan_status_label` en `Evidence`.
2. **`CurrentFile`** (en la lista de slots, interna): `size_bytes`, `detected_mime_type` y `last_buyer_comment` — así el front deja de pedir 16 `GET /document-files/{id}`.
3. **`DocumentFile.uploaded_by`**: `{type: "buyer"|"user", name}` (para el usuario interno, su nombre; para el comprador, "Comprador"). Nunca correo ni documento.
4. **`participants_summary`** del listado: agrega `roles: [{code, label, count}]` (sin quitar los conteos actuales).
5. **Detalle de la solicitud**: `origin_user_name` (nombre del broker u usuario que originó la oportunidad; nulo si no hay) y `consents: {required, accepted}` (conteos de consentimientos obligatorios del comprador titular).
6. **Paquetes de una solicitud**: `GET /applications/{id}/document-package-jobs` (paginado, más nuevo primero, mismo permiso que el `POST`).
7. **`FilingDocumentSnapshot`**: `document_type_label` y `slot_label` (copiados o resueltos al leer; si se resuelven al leer, sin consultas por fila).
8. **`Filing.is_response_overdue`**: verdadero si pasó `target_response_at` y no hay respuestas.
9. **Campos por tipo de respuesta del banco**: los ítems del catálogo de tipos de respuesta exponen en `metadata` `{fields: [...], required: [...]}` sacados de `RULES` de `filings/responses.py` (una sola fuente: genera la metadata desde `RULES`, no la copies a mano). Así el front puede quitar su constante `RESPONSE_FORMS`.
10. **Corregir una respuesta `DISBURSED`** (decidido): se permite, solo al admin, solo sobre la última respuesta, con el mismo mecanismo de corrección que ya existe (`corrects_response`); puede cambiar `disbursed_amount_cop`, `received_at`, referencia y comentarios; **no** cambia el estado de la solicitud. Comisiones ya reacciona a la corrección (su receptor lo maneja): agrega la prueba de punta a punta (desembolso → liquidación → corrección → anulación y nueva liquidación; con una parte pagada → `needs_review`).
11. **Ingresos del comprador** en `GET /buyer/applications/{id}`: `income_summary: {participants_with_income, total_monthly_income_cop}` solo de lo que el propio comprador cargó (nunca de otro participante que no sea de su solicitud).

## Parte 3 — Límites, mensajes y comodidad local
1. **Texto del `429` en español** para todos los throttles: "Hiciste demasiados intentos. Vuelve a intentarlo en N minutos." (`N` redondeado hacia arriba; segundos si es menos de 1 minuto), con `code: "RATE_LIMITED"` y `Retry-After` como hoy. Un solo lugar (el manejador de excepciones o una clase base de throttle).
2. **Límites flojos solo en local** (decidido): setting `AUTH_RATE_LIMIT_MULTIPLIER` (por defecto 1). Si `DEBUG=True` **y** la variable de entorno `AUTH_RATE_LIMIT_MULTIPLIER` está puesta, cada cupo de `AUTH_RATE_LIMITS` y `REPORTS_RATE_LIMIT` se multiplica por ese número. Con `DEBUG=False` se ignora siempre (prueba explícita). Documenta en `backend/README.md` que para los E2E locales se usa `AUTH_RATE_LIMIT_MULTIPLIER=20` en `.env` (eso lo pone el orquestador en el `.env`, tú no).
3. **Docs**: API §5/§8/§13/§14/§19/§21 donde cambió algo, y la lista de brechas resueltas en `specs/TAREA-frontend-base.md` (marca cada una como "Resuelta en `TAREA-brechas-2.md`").

## Fuera de esta tarea (decidido)
- Notificaciones internas del backoffice (la campana): fuera del MVP.
- "Deshacer" una aprobación de documento: se mantiene como está (se decide otra vez sobre la versión vigente).

## Entregas
| Parte | Commit propuesto |
| --- | --- |
| 1 | `feat(crm): add opportunity actions, labels, typed assignments and auto-assignment for advisors` |
| 2 | `feat(api): add the missing labels, file details, package list and disbursement corrections` |
| 3 | `feat(api): translate rate-limit errors and allow looser limits only in local debug` |
Al cerrar: título y descripción del PR (en español) en el reporte.

## Precisiones acordadas

### Parte 1 (backend-b, 2026-11-18)
- **`ActionKind` compartido:** el enum pasa a `apps/catalogs/workflow.py` y `apps.applications.actions` lo reexporta; `ENUM_NAME_OVERRIDES` apunta ahí y el nombre `AvailableActionKindEnum` no cambia. `crm` no importa `applications`.
- **Acciones de la oportunidad:** `OpportunityAvailableAction` = `AvailableAction` sin `guard_code` (el flujo de la oportunidad no tiene guardas). Salen ordenadas como las de la solicitud: `primary`, `secondary`, `destructive` y, dentro, por código. Reglas en `apps/crm/actions.py`.
- **`reason_required` en solicitudes:** `true` para `CANCELLED`, `OWN_FUNDS`, `EXTERNAL_CREDIT_APPROVED` (los cierres que hoy exigen `reason_code`) y `WITHDRAWN` (su `reason_code` es obligatorio en `/withdrawals`). `REASON_REQUIRED_STATUSES` se movió a `apps/applications/actions.py` (una sola fuente para la validación y el campo).
- **`status_label` de la oportunidad:** `ChoiceLabelField(OpportunityStatus)`, sin consulta. Las etiquetas del catálogo `opportunity_status` son las mismas; una prueba lo exige.
- **`assignments`:** el serializer se renombra a `OpportunityAssignmentSerializer` (componente `OpportunityAssignment`); antes no salía en el contrato.
- **`notes`:** la oportunidad no tiene campo de texto. Va a la actividad como una fila `NOTE_ADDED` interna con `opportunity` y `client`: `crm` emite la señal nueva `opportunity_created` y `apps/activity/receivers.py` la registra (sin migración). Si la nota falla, se registra en el log y la oportunidad queda (como todo suscriptor de actividad).
- **Auto-asignación:** decide el rol `ADVISOR` del actor (si además es `ADMIN`, también se asigna). Usa la transición `NEW → ASSIGNED` (`ASSIGN`) con `resolve_transition`; si no está activa o el asesor no la puede ejecutar, responde `409`/`403` y no se crea nada. El registro de `opportunity_assignments` lleva `reason` "Asignación automática: la creó el asesor."; salen `opportunity_assigned` y `opportunity_status_changed` como en `assign_advisor`.
- **`applications_count`:** cuenta las solicitudes **visibles para el usuario** en las que el cliente participa con un papel vigente: el mismo número que `GET /clients/{id}/applications`. La regla de alcance de solicitudes pasa a `crm.services.application_scope_condition` y `applications` la usa (una sola fuente). En el contrato es **opcional**: `Client` también va dentro de `ApplicationParticipant.client`, donde no se calcula; viene siempre en `/clients` (listado, detalle, `POST`, `PATCH`) para internos. El broker no lo recibe.
- **Contrato del broker:** `oneOf` sin discriminador. Componentes nuevos `ClientByRole` (`POST`), `ClientDetailByRole` (`GET`/`PATCH` detalle), `PaginatedClientListByRole` y `PaginatedBrokerClientList` (listado) y `BrokerClient`. `Client`, `ClientDetail` y `PaginatedClientList` conservan nombre y forma (la página se arma con `config.api.paginated_serializer`; pierde solo los `example` de `page`, `page_size`, `total`, `next` y `previous`). Como la respuesta ya no es "lista" para drf-spectacular, los filtros (`filters=True`) y la paginación se declaran a mano; los parámetros publicados no cambian.
- **`409 DUPLICATE_CLIENT_DOCUMENT`:** se describe en `POST` y `PATCH /clients` (`details[0]` = `{field, code: "EXISTING_CLIENT", resource_id}` solo si el usuario ve el cliente). `ErrorDetail.resource_id` ya existía.
- **Docs:** API §13, §14 y "Acciones disponibles" (§16) se actualizaron en esta parte; las marcas de `TAREA-frontend-base.md` quedan para la Parte 3.
