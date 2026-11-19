# TAREA — Brechas de backend 3 (contrato de F6/F7) y datos de demo completos

> Spec cerrada. Todas las decisiones están tomadas. **No preguntes:** si algo no cuadra con el código, decide lo más simple, anótalo en "Precisiones acordadas" (al final) y en el reporte, y sigue.

**Agente:** "backend-gaps". **Worktree:** `C:\Users\ASUS\Documents\programacion\mvp-backoffice\wt-back-gaps3`, rama `feat/backend-gaps-3`, desde `origin/master`. Copia de esta spec en `specs/TAREA-brechas-3-demo.md`. Buzón `.buzon/` como siempre.
**Origen:** lo que dejaron como brecha los fronts de F6 (administración) y F7 (comisiones, broker, expediente), y el pedido de Carlos de una demo donde el admin vea **todo** el producto con datos.
**Regla de oro:** **solo se agrega al contrato**; nada que ya existe cambia de forma ni de nombre (los fronts ya lo usan). Si algo no se puede hacer sin romper, anótalo y sigue.

**En paralelo** trabaja el agente de seguridad (`specs/TAREA-seguridad-fase-b.md`, rama `fix/security-phase-b`). Los dos tocan `contracts/openapi.json`, `frontend/src/lib/api/schema.d.ts` y `backend/tests/security/access_matrix.py`: no edites a mano lo del otro. El que entre segundo trae `master` (lo hace Carlos) y regenera esos archivos.

## Reglas
- Git solo lectura. No leas ni edites `.env*`. Nada secreto en reportes ni pruebas (solo la contraseña de demo `DemoUmbral2026!`).
- **Base de pruebas propia** `mvp_credit_b` (la de siempre de este carril) y, para la demo, una base nueva y vacía `mvp_credit_demo`. No toques `mvp_credit` (la de Carlos) ni `mvp_credit_secb`.
- Pruebas acotadas; siempre `ruff`, `mypy .`, `makemigrations --check`, `spectacular --validate --fail-on-warn` y **regenerar `schema.d.ts`** (`npx --yes openapi-typescript@7.13.0 ../contracts/openapi.json -o src/lib/api/schema.d.ts` en `frontend/`) y confirmar `corepack pnpm typecheck` en `frontend/`.
- Etiquetas siempre con `ChoiceLabelField` / del catálogo. Enums nuevos con nombre fijo en `ENUM_NAME_OVERRIDES` y en `tests/test_contract_names.py`.
- Cada punto con su prueba. Las consultas no crecen con las filas (si agregas un campo a un listado, prueba el número de consultas).
- **Endpoint nuevo:** su fila en `backend/tests/security/access_matrix.py` (patrón de 9 letras A/U/F/H para los 9 actores) y `python security/render_matrix.py`; si no, el CI falla. **Operación idempotente nueva:** a la lista de `tests/applications/idempotency/test_idempotency.py`.

## Parte 1 — Brechas de contrato (F6 y F7)
1. **`status_label`** en `User`, `Invitation`, `Partner` y `Membership` (listados y detalles).
2. **`ProjectDetail.available_actions`**: cada acción con `label` (y la forma de `AvailableAction` de solicitudes si encaja: `code, label, kind, target_status, target_status_label, reason_required`). Si hoy es una lista de códigos, agrega un campo nuevo `available_action_details` con los objetos en vez de cambiar el existente.
3. **Broker en solicitudes:** `GET /applications` y `GET /applications/{id}` documentan las dos formas (`oneOf` de la forma interna y `ApplicationSummary`, la que recibe el broker), igual que se hizo con `/clients` en `TAREA-brechas-2.md`. Lo importante: que el contrato describa lo que de verdad responde al broker.
4. **`BrokerOpportunity.status_label`** (catálogo `opportunity_status`).
5. **Catálogo de papeles de participante** (`RoleCodeEnum`: titular, cotitular, codeudor…) en el bootstrap de catálogos, con `code` y `label`, para que el front quite su constante.
6. **Reglas bancarias:**
   - `GET /bank-policy-rules/fields` (o el nombre que encaje con las rutas vecinas): la lista de campos permitidos en una regla, con `code`, `label`, tipo (`number`, `money`, `percent`, `boolean`, `choice`) y, para `choice`, sus opciones. Una sola fuente: se genera desde donde el backend ya valida los campos permitidos, no se copia a mano. Permiso: el mismo de leer reglas.
   - `status_label` y `severity_label` en la regla;
   - `outcome_label` en la respuesta de `POST /bank-policy-rules/{id}/test`.
7. **Comisiones:** filtro `application_id` en `GET /commission-settlements` y catálogos de estado de liquidación y de estado de parte en el bootstrap (`code`, `label`).
8. Lo que haya quedado anotado como "brecha para el backend" en los reportes de `wt-front-f7/.buzon/reportes/` (léelos: solo lectura) que no esté arriba: si es pequeño y solo agrega, hazlo; si no, anótalo en el reporte.
9. **Docs:** API §… donde cambió algo, y marca como resueltas las brechas en `specs/TAREA-front-admin.md` y `specs/TAREA-front-cierre-vistas.md` ("Resuelta en `TAREA-brechas-3-demo.md`").

**Commit:** `feat(api): add the labels, rule fields and filters the admin and broker screens need`

## Parte 2 — Datos de demo completos
**Objetivo (pedido de Carlos):** entrar como admin y que **cada pantalla** tenga datos reales y variados, y poder recorrer el producto con un usuario de cada uno de los 5 roles.

### Cómo se carga (decidido)
- Sigue siendo `python manage.py seed_demo_data`, **solo con `DEBUG`**, **nunca borra**.
- Hoy, si los datos de demo ya existen, no hace nada. Cambia eso: **cada bloque es idempotente por su cuenta** (marca propia: un código, un correo o un nombre fijo). Así, en la base de Carlos (que ya tiene la demo vieja) el comando **agrega solo lo que falta**, y correrlo dos veces seguidas no duplica nada.
- Fechas reales hacia atrás: los registros se crean y después se retroceden sus fechas (`created_at`, historial de estados, auditoría, respuestas del banco…) con `update()`, de forma coherente (un desembolso nunca antes de su radicación).
- Repartido entre los asesores de demo, con el broker originando una parte.

### Qué debe quedar
1. **Usuarios de demo, los 5 roles** (contraseña de demo): `admin@`, `asesora.lucia@`, `asesor.andres@`, `broker@` y **nuevo `constructora@demo.local`** (`CONSTRUCTION_PARTNER`) con su constructora y al menos un proyecto activo. Más un usuario **inactivo**.
2. **Solicitudes repartidas en los últimos 6 meses** y en **todos los estados** del flujo, para que el dashboard, el embudo por cohorte, "Mi día" y los reportes tengan historia (al menos 60 en total contando las que ya existen).
3. **Radicaciones con cada tipo de respuesta del banco:** recibida, en análisis, devuelta y corregida, aprobada, rechazada y desembolsada (y una vencida sin respuesta, `is_response_overdue`).
4. **Comisiones:** liquidaciones pendiente, pagada, anulada y con revisión pendiente; con broker (70/30) y directas (100 %); al menos una con una parte pagada.
5. **Tareas** vencidas, de hoy, próximas, completadas y canceladas, para los dos asesores.
6. **Notas y actividad** en clientes, oportunidades y solicitudes.
7. **Avisos del comprador** (leídos y sin leer) y **entregas de correo** (enviada y fallida con reintento).
8. **Exportaciones de reportes:** una terminada y una vencida.
9. **Constructoras y proyectos en cada estado** (borrador, en validación, activo, rechazado, archivado) y **membresías**.
10. **Invitaciones** pendiente, aceptada, vencida y revocada.
11. **Bancos, productos y reglas** con más de una versión de regla.
12. **Auditoría:** logins correctos y fallidos, un `403`, descargas de documentos y una exportación.
13. **Oportunidades** en todos sus estados (nueva, asignada, convertida, perdida, cancelada).

### Salida del comando (la usará el `demo.ps1` de la documentación)
Al final imprime, en este orden:
- un resumen por bloque (`creados` / `ya existían`);
- **una tabla de usuarios por rol** (rol, correo, para qué sirve en una línea) y la contraseña de demo;
- **el enlace del portal del comprador** (un solo uso, como hoy) y el código de la solicitud a la que pertenece.

### Verificación
- En `mvp_credit_demo` vacía: `migrate`, `seed_demo_data`, y **otra vez** `seed_demo_data` → la segunda corrida dice "ya existían" en todo y los conteos no cambian (pega los conteos por tabla de las dos corridas).
- En una copia con la demo vieja (crea `mvp_credit_demo_old`, corre el `seed_demo_data` de `master` y después el tuyo) → agrega solo lo nuevo.
- Prueba automática: un test que corre el seed dos veces y compara conteos, y que verifica que cada estado de la lista de arriba existe al menos una vez.
- Tiempo del seed completo en el reporte (si pasa de 60 s, anótalo).
- Arranca un servidor propio en el **8012** con `mvp_credit_demo` y entra como cada uno de los 5 usuarios (`POST /api/v1/auth/login` y `GET /auth/me`): todos `200`.

**Commit:** `feat(demo): seed six months of varied demo data and a demo user for every role`

## Parte 3 — Cierre
- `backend/README.md`: sección de datos de demo actualizada (qué crea, los 5 usuarios, que se puede correr varias veces).
- Reporte final con lo hecho, números, archivos tocados y **título y descripción del PR en español** (sin firmas ni `Co-Authored-By`).
**PR:** `feat(api): close the admin and broker contract gaps and seed complete demo data`

## Precisiones acordadas
(las agrega el agente)

### Parte 1
- **P1.1 `status_label` de usuario, invitación, partner y membresía:** sale de las `TextChoices` (`UserStatus`, `InvitationStatus`, `PartnerStatus`) con `ChoiceLabelField`. Partner y membresía comparten `PartnerStatus` ("Activo" / "Inactivo"). No hay catálogo nuevo para estos estados (no se pidió).
- **P1.2 Acciones del proyecto:** `available_actions` sigue igual (códigos, por código). El campo nuevo `available_action_details` tiene la forma de `OpportunityAvailableAction` (la de la solicitud sin `guard_code`, porque el flujo del proyecto no tiene guardas): `code, label, kind, target_status, target_status_label, reason_required`. `kind` por estado destino (`apps/partners/actions.py`, como `apps/crm/actions.py`): `PENDING_REVIEW` y `ACTIVE` → `primary`, `DRAFT` (`REJECT`) → `secondary`, `ARCHIVED` → `destructive`; ordenado por tipo. `reason_required` es `true` en `/reject` y `/archive`, que ya exigen `reason`. Se calcula con una sola consulta de transiciones para los dos campos.
- **P1.3 `oneOf` del broker en solicitudes:** además de `GET /applications` y `GET /applications/{id}`, también `GET /clients/{id}/applications`, que usa la misma rama del broker (`list_serializer_class`). Componentes nuevos `PaginatedApplicationListByRole`, `PaginatedApplicationSummaryList` y `ApplicationDetailByRole`. `PaginatedApplicationList` mantiene nombre y forma; solo pierde los `example` (igual que `PaginatedClientList` en brechas-2). Los parámetros de paginación del `oneOf` pasan de `apps/crm/views.py` a `config/api.py` (`PAGINATION_PARAMETERS`) para usarlos en los dos módulos. `PATCH /applications/{id}` no cambia: el broker no tiene `applications.update`.
- **P1.4 Front con el `oneOf`:** como en brechas-2, solo se tocan fixtures de pruebas y la afirmación de la forma interna (`as ApplicationPage`, `as ApplicationDetail`, `as Schemas["PaginatedApplicationList"]`) en `features/applications/queries.ts`, `workspace-queries.ts` y `features/clients/detail-queries.ts`. Sin cambios de componentes ni de comportamiento.
- **P1.5 Catálogo de papeles:** código `participant_role`, con los tres valores de `ParticipantRole` (`PRIMARY` "Titular", `CO_APPLICANT` "Co-solicitante", `SOLIDARY_DEBTOR` "Deudor solidario"). El front usa los dos últimos para agregar (`RoleCodeEnum`); el titular va también para mostrar. Sistema (`is_manageable=False`), sembrado en `applications/0006`.
- **P1.6 Catálogos de comisiones:** `commission_settlement_status` (`ACTIVE` "Vigente", `VOIDED` "Anulada") y `commission_share_status` (`PENDING` "Pendiente de pago", `PAID` "Pagada", `VOIDED` "Anulada"), de sistema, en `commissions/0004`. Una prueba exige que coincidan con las `TextChoices`.
- **P1.7 `GET /bank-policy-rules/fields`:** `operation_id` `bank_policy_rules_fields_list`, permiso `bank_rules.read`, sin paginar (lista fija de 28 campos). Una sola fuente: `RULE_FIELDS` gana `label` y `catalog` por campo, y el tipo del editor se deriva del tipo del motor (`string` → `choice`, `boolean` → `boolean`, `number` → `money` si termina en `_cop`, si no `number`). `percent` queda en el enum pero hoy ningún campo lo usa (no hay porcentajes en la lista blanca). Cada campo trae también `description`. `options` son los ítems vigentes del catálogo (una consulta para todos); en `municipality` (bajo demanda, ~1100 ítems) es `null` y se pide en `/metadata/catalogs/municipality`. Enum nuevo `RuleFieldTypeEnum` con override fijo.
- **P1.8 Filtro `application_id`:** devuelve todas las liquidaciones de la solicitud (la vigente y las anuladas); un UUID mal formado responde `400` como los demás filtros.
- **P1.9 Brechas de los reportes de F7:** las cuatro que anotaron (filtro `application_id`, catálogos de comisiones, `oneOf` de solicitudes con `status_label` del broker y catálogo de papeles) ya estaban en los puntos 3, 4, 5 y 7. No quedó ninguna otra.
- **P1.10 `specs/TAREA-front-cierre-vistas.md`:** no existe en esta rama (solo en `wt-front-f7`, que no toco) y no tiene viñetas de brecha: las brechas de F7 están en sus reportes del buzón. Se marcaron las de `specs/TAREA-front-admin.md`.
