# Tarea: solicitudes de crédito (`applications`, paso 8)

## Objetivo
Construir el expediente central del crédito: la solicitud, sus asignaciones, participantes, perfiles financieros, fuentes de ingreso, inmueble, preferencias de financiación, evaluaciones de reglas bancarias e historial de estados (DER §6 y §7.5; API §16 a §18; REQUERIMIENTOS §5.4).

Incluye los pendientes de pasos anteriores:

- **CRM:** `GET /clients/{id}/applications` y la conversión de la oportunidad a `CONVERTED` al crear su solicitud. **Hecho (Parte 2).**
- **Banking:** `GET /applications/{id}/eligible-bank-products` y el contexto real de la solicitud para el evaluador de reglas, con la lista blanca de `apps/banking/rule_fields.py` ajustada. **Hecho (Parte 5).**

## Cuándo se construye
Paso 8 del orden de construcción (DER §15), después de `documents` (configuración, 7). Rama: `feat/applications`, creada desde `master`, con un PR en Draft abierto (el CI corre en cada push).

**Fuera de alcance:** acceso del comprador (paso 9), slots del expediente (paso 10), radicaciones (paso 11), tareas y actividad (paso 12), notificaciones e idempotencia (paso 13).

---

## Avance

| Parte | Contenido | Estado | Commit |
| ---: | --- | --- | --- |
| 1 | Modelos, migraciones y semillas | Hecha | `c40c916` |
| 2 | Núcleo de la solicitud y `/clients/{id}/applications` | Hecha | `3dc9758` |
| 3 | Participantes, perfil financiero e ingresos (API §17) | Hecha | `765b660` |
| 4 | Inmueble, financiación e `include` del detalle (API §18.1 y §18.2) | Hecha | `7a9a96f` |
| 5 | Integración con banking: contexto, lista blanca, evaluaciones y `eligible-bank-products` | Hecha | `9244984` |
| 6 | Estados, desistimiento, historial, acciones, completitud, README y documentación de la API | Hecha | (pendiente de commit) |

Al cerrar la Parte 2: 791 tests en verde, 97 % de cobertura total y el esquema OpenAPI con 1 aviso, el mismo que ya había en `master` (`RoleEnum`).

Al cerrar la Parte 3: 845 tests en verde, 97 % de cobertura total y el esquema OpenAPI **sin avisos**. El aviso previo (`RoleEnum`) venía de que `apps/documents/serializers.py` usa las opciones de `ParticipantRole` en dos campos (`participant_role` y `role`). La Parte 3 agregó `ParticipantRoleEnum` a `ENUM_NAME_OVERRIDES`, y ahora los tres campos comparten el componente `ParticipantRoleEnum` (el componente `RoleEnum` ya no existe).

Al cerrar la Parte 4: 896 tests en verde, 98 % de cobertura total (`views.py` 100 %; `services.py` y `serializers.py` 99 %, con las líneas sin cubrir en código de la Parte 2) y el esquema OpenAPI sin avisos (`spectacular --validate --fail-on-warn`).

Al cerrar la Parte 5: 938 tests en verde, 98 % de cobertura total (`bank_evaluation.py`, `rule_context.py` y `views.py` 100 %; las líneas sin cubrir de `services.py`, `serializers.py` y `rule_engine.py` son anteriores) y el esquema OpenAPI sin avisos.

Al cerrar la Parte 6 (fin del paso 8): 982 tests en verde, 98 % de cobertura total (`views.py`, `bank_evaluation.py` y `rule_context.py` 100 %; `services.py` y `serializers.py` 99 %, con las líneas sin cubrir en código anterior; en la migración `0003` solo queda sin cubrir el `unseed`) y el esquema OpenAPI sin avisos.

---

## Cómo retomar en una sesión nueva

### Reglas de trabajo (las fija el usuario)
- Antes de programar una parte, confirmar el alcance si surge una ambigüedad nueva. Cada parte es un commit con sus tests.
- **Correr los 5 checks en verde antes de proponer un commit**: `ruff check .`, `ruff format --check .`, `mypy .`, `python manage.py makemigrations --check --dry-run` y `pytest --cov=apps --cov-report=term-missing` (los mismos pasos de `.github/workflows/backend.yml`).
- Todo con anotaciones de tipos. Nada de `type: ignore` ni `noqa` sin justificar.
- **Git solo en modo lectura.** El usuario hace los commits y los pushes.
- Las propuestas de commit van **sin `Co-Authored-By` ni firma**. Mensajes cortos, en inglés, con el estilo `feat(applications): ...`.

### Entorno local
- El contenedor `backend` no arranca: en `.env` la línea de `AUTH_JWT_SIGNING_KEY` empieza con espacios y django-environ la descarta (`Invalid line`). No leer ni editar `.env`; el usuario decide si la corrige. Mientras tanto, los checks se corren en un contenedor efímero con una clave ficticia:

  ```bash
  docker compose run --rm --no-deps -e AUTH_JWT_SIGNING_KEY=local-dev-only-not-a-secret backend sh -c '
    ruff check . && ruff format --check . && mypy . &&
    python manage.py makemigrations --check --dry-run &&
    pytest --cov=apps --cov-report=term-missing'
  ```

- Validar también el esquema: `python manage.py spectacular --validate --file /tmp/s.yml` debe seguir **sin avisos** (desde la Parte 3). Dos serializers con el mismo nombre en distintos módulos generan avisos de componentes duplicados: reutilizar los de CRM (`UserRefSerializer`, `AssignmentCreateSerializer`) o poner un nombre único.
- **`config/settings/base.py` usa CRLF** (el repo es mayoritariamente LF). Editarlo con la herramienta de edición, nunca con `sed -i`, que convierte el archivo entero a LF.

### Mapa del código ya escrito (`apps/applications`)

| Archivo | Contenido reutilizable |
| --- | --- |
| `models/application.py` | `CreditApplication`, `ApplicationAssignment` y `ApplicationStatusHistory`; las constantes `TERMINAL_APPLICATION_STATUSES`, `FAILED_APPLICATION_STATUSES` y `EDITABLE_APPLICATION_STATUSES` (pre-`FILED`); `next_application_code()`; y las propiedades `is_terminal` e `is_editable`. |
| `models/participant.py` | `ApplicationParticipant` (relación inversa `application.participants`), `FinancialProfile` (`participant.financial_profile`) e `IncomeSource` (`financial_profile.income_sources`). `ParticipantRole` viene de `apps.documents.models`. |
| `models/property.py` | `Property` (relación inversa **`application.financed_property`**) y `FinancingPreference` (`application.financing`). |
| `models/evaluation.py` | `BankRuleEvaluation` (`application.rule_evaluations`, de la más reciente a la más antigua). |
| `concurrency.py` | `expected_version(request)` lee `If-Match` (`428`/`400`); `ensure_version(current, expected)` (`409 STALE_VERSION`); `with_etag(response, version)`. |
| `services.py` | `applications_visible_to(user)`, `applications_queryset()`, `application_detail(user, id, include)` (precarga los bloques de `include`), `get_application_scope(user)` (es `CrmScope`; `is_restricted` = broker), `client_applications`, `resolve_visible_opportunity`, `resolve_property_project`, `resolve_bank_product`, `_ensure_product_available(product, purpose, field)`, `property_errors(purpose_code, values)`, `property_values(prop)`, **`lock_for_edit(application, expected_version)`** y **`bump_version(locked, fields)`**, `create_application`, `update_application` (con `_ensure_product_fits_financing`), `assign_application`, los servicios de participantes, perfiles e ingresos, `put_property`, `financing_errors(mode_code, values, product)`, `put_financing`, `evaluate_application(actor, application)`, `latest_evaluation(application)`, `eligible_products_queryset(application)`, `preview_products(application, products)`, `transition_application`, `withdraw_application` (los dos devuelven `StatusChange`), `documents_verified(application)` (hoy `False`: punto de enganche del paso 10), `available_actions(user, application)`, `status_history_queryset(application)` y `completeness(application)` → `Completeness`. Constantes `BANK_CREDIT`, `OWN_FUNDS`, `EXTERNAL_CREDIT`, `READY_TO_FILE_GUARD`, `REASON_REQUIRED_STATUSES`, `CLOSING_FINANCING_MODES` y `DOCUMENTS_NOT_VERIFIED_MESSAGE`. |
| `serializers.py` | `PropertyInputSerializer` + `property_model_values(data)`, `ApplicationPropertyInputSerializer` (con `project_id`), `PropertySerializer`, `FinancingSerializer`/`FinancingInputSerializer` (`model_values()` sin `bank_product_id`), `ApplicationSerializer`, `ApplicationDetailSerializer` (bloques opcionales según `context["include"]`; al final del archivo), `DETAIL_INCLUDES`, `ApplicationSummarySerializer` (la vista del broker) y `ApplicationCreateSerializer`/`ApplicationUpdateSerializer`. `ApplicationDetailSerializer` exige `context["available_actions"]` (lista de `WorkflowTransition`), serializada con `AvailableActionSerializer`. Al final: `BankRuleEvaluationSerializer`, `EligibleBankProductSerializer`, `StatusTransitionSerializer`, `WithdrawalSerializer`, `StatusChangeSerializer`, `StatusHistorySerializer` y `CompletenessSerializer`. |
| `views.py` | Base `ApplicationView` (`actor`, `scope`, `get_application` → 404 fuera de alcance, `list_serializer_class`), `_include_param(request)` y `_detail_response(view, id, include)`, que pone `ETag`. `ExpedienteView` (broker `403`) y `_application_etag`. `ApplicationPropertyView` y `ApplicationFinancingView`. `ApplicationRuleEvaluationView`, `ApplicationLatestRuleEvaluationView` y `EligibleBankProductsView`. `ApplicationStatusTransitionView`, `ApplicationWithdrawalView`, `ApplicationStatusHistoryView`, `ApplicationAvailableActionsView` y `ApplicationCompletenessView` (todas `ExpedienteView`). |
| `rule_context.py` | `build_rule_context(application, on=None)`: contexto con todos los campos de `RULE_FIELDS` (los que faltan, `None`), leído de la base y validado con `validate_context`. `full_months_between(start, end)`. |
| `bank_evaluation.py` | `evaluate_product(product, context, purpose=)` → filas del snapshot (reglas configuradas por código y después las del sistema), `summarize(rows)` → `EvaluationSummary`, `blocking_rows`/`warning_rows`, `issue(row)` (ítem de la respuesta), `is_current(evaluation, application)` y **`save_evaluation(actor, locked)`** (dentro de una transacción, con la solicitud bloqueada y con producto). Constantes `PRODUCT_AMOUNT_RANGE`, `PRODUCT_TERM_RANGE`, `SOURCE_RULE` y `SOURCE_SYSTEM`. |
| `exceptions.py` | `APPLICATION_ALREADY_OPEN`, `APPLICATION_NOT_EDITABLE`, `APPLICATION_CLOSED` y `STALE_VERSION` (`409`), `PRECONDITION_REQUIRED` (`428`), y `BANK_PRODUCT_REQUIRED`, `APPLICATION_NOT_READY` y `FINANCING_MODE_MISMATCH` (`422`). |
| `signals.py` | `application_created`, `application_updated` (`fields`), `application_assigned`, `participant_added`, `participant_removed` y `application_status_changed` (`from_status`, `to_status`, `transition_code`, `reason_code`, `comment`; también la envía el desistimiento). |
| `migrations/0003_seed_closing_reasons.py` | Motivos de cierre de `application_transition_reason`, con `OTHER` al final. |
| `tests/applications/conftest.py` | Usuarios y clientes HTTP (`admin`, `advisor`, `other_advisor`, `broker`, `partner`), `make_client`, `make_opportunity` (`ASSIGNED` con asesor), `make_application` (crea también el `PRIMARY`), `application`, `primary`, `make_project`/`active_project`, `new_home_only_product`, `seeded_product()`, `application_url()` y `catalog_item()`. |

Fuera del módulo:

- **`apps/crm/services.py`:** `convert_opportunity(actor, opportunity)` (fila bloqueada, evento en `on_commit`) y `ensure_advisor(user)`, ahora pública. `transition_opportunity` rechaza `CONVERTED`.
- **`config/serializers.py`:** `ErrorDetailSerializer.current_version`.
- **`config/settings/base.py`:** `ApplicationStatusEnum` en `ENUM_NAME_OVERRIDES` y `ETag` en `CORS_EXPOSE_HEADERS`.
- **`apps/banking/rule_engine.py`:** `referenced_fields(condition)` (campos citados, en orden de lectura). `banking.services.RuleResult` trae ahora `fields` con esos campos.
- **`tests/catalogs/test_workflow.py`:** un fixture que retira las transiciones `APPLICATION` sembradas, porque esos tests prueban el motor genérico sobre un flujo vacío.

---

## Decisiones (acordadas con el usuario)

1. **`actor_buyer_session_id` se omite.** Apunta a `buyer_sessions`, que nace en el paso 9. Ver pendientes.
2. **`Idempotency-Key` se aplaza al paso 13**, dueño de `idempotency_keys`. Mientras tanto:
   - las transiciones se protegen con `expected_version`;
   - la creación se protege con una restricción de PostgreSQL: como máximo una solicitud no terminal por oportunidad (`uq_credit_applications_open_opportunity`).
3. **Conversión de la oportunidad.** Crear la solicitud pasa la oportunidad a `CONVERTED` en la misma transacción, mediante las transiciones `CONVERT_*` del flujo `OPPORTUNITY` (desde `ASSIGNED`, `CONTACTED` e `IN_PROGRESS`). Una oportunidad `NEW` (sin asesor) se rechaza. Sobre una oportunidad ya `CONVERTED` se admite un nuevo intento solo si todas sus solicitudes anteriores terminaron en `REJECTED`, `WITHDRAWN` o `CANCELLED`.
4. **Quién crea y quién ve.**
   - `applications.create`: `ADMIN` y `ADVISOR`.
   - `INDEPENDENT_BROKER`: solo el resumen de las solicitudes de oportunidades que originó; nunca datos financieros, participantes en detalle, inmueble, financiación ni productos elegibles.
   - `CONSTRUCTION_PARTNER`: sin acceso. API §27.4 ("un miembro registra cliente, oportunidad y solicitud") **contradice** REQUERIMIENTOS §3 ("no crea ni consulta expedientes de compradores"). **Manda REQUERIMIENTOS §3.**
5. **Transiciones sembradas (flujo `APPLICATION`), solo hasta antes de radicar:**
   - `DRAFT → WAITING_BUYER_DATA → WAITING_DOCUMENTS → DOCUMENTS_REVIEW → READY_TO_FILE` (esta última, `MARK_READY_TO_FILE`, con la guarda `APPLICATION_READY_TO_FILE`);
   - saltos `DRAFT → WAITING_DOCUMENTS` y `DOCUMENTS_REVIEW → WAITING_DOCUMENTS`, y reapertura `READY_TO_FILE → DOCUMENTS_REVIEW` (`REOPEN_REVIEW`, agregada en la implementación);
   - salidas a `CANCELLED`, `OWN_FUNDS` y `EXTERNAL_CREDIT_APPROVED` desde los cinco estados previos a la radicación;
   - `WITHDRAWN` desde todo estado no terminal (incluidos los posteriores a `FILED`), con el permiso `applications.withdraw`, ejecutable solo por `/withdrawals`;
   - de `FILED` en adelante, las agrega el paso 11 (`filings`).
6. **Guarda `APPLICATION_READY_TO_FILE`.** La parte bancaria se implementa ya: producto elegido y última evaluación de la versión actual sin bloqueos. La parte documental falla cerrada (`422 APPLICATION_NOT_READY`) hasta el paso 10.
7. **Concurrencia.** Todo cambio del expediente incrementa `credit_applications.version` (solicitud, participantes, perfiles, ingresos, inmueble y financiación). Siguiendo API §6, **todo `PUT`/`PATCH` que modifique el expediente exige `If-Match`** (`409 STALE_VERSION` con la versión actual en `details`). Los `POST` que crean subrecursos nuevos y los `DELETE` no lo exigen, pero incrementan la versión.
8. **Participantes.** `POST` acepta `client_id` de un cliente visible o el bloque de identidad, que crea el cliente (o `409 DUPLICATE_CLIENT_DOCUMENT`). `relationship_code` del ejemplo de API §17.1 se descarta: no tiene columna en el DER. Retirar un participante lo marca `is_active = false`. El `PRIMARY` es el cliente de la oportunidad y se crea con la solicitud.
9. **Cruces entre API y esquema.**
   - `PUT /financing` exige `financing_mode_code` (la columna es obligatoria); `bank_product_id` es obligatorio solo con el modo de crédito bancario (`BANK_CREDIT`) y se guarda en `credit_applications`.
   - `PATCH /applications` solo edita `purpose_code` y `bank_product_id`; montos, plazo y modalidades van por `/financing`.
   - El perfil financiero usa `employment_profile_code` (catálogo `employment_profile`), no `employment_type_code`.
10. **`eligible-bank-products`.** Productos disponibles hoy para la finalidad, cada uno con una evaluación **no persistida** (`eligible`, `blocking_count`, `warning_count`). Lo usan `ADMIN` y `ADVISOR` (y el comprador desde el paso 9); **el broker no tiene acceso**. Solo `POST /bank-rule-evaluations` guarda resultados, y la selección de producto dispara una evaluación persistida.
11. **Lista blanca de campos.** Se agregan `property.is_owned_by_applicant`, `property.has_project`, `financing.financing_mode_code`, `financing.amortization_mode_code`, `financing.external_approved_amount_cop`, `applicant.contract_type_code`, `applicant.employment_months`, `household.monthly_expenses_cop`, `household.liabilities_cop` y `application.participant_count`. `application.is_joint` es "hay un `CO_APPLICANT` activo". `household.monthly_income_cop` usa `income_share_cop` cuando está informado y, si no, el ingreso del perfil.
12. **Catálogos nuevos** (propuesta inicial editable, como en CRM):
    - `contract_type`, `funds_origin`, `income_source_type`, `financing_mode` (`BANK_CREDIT`, `OWN_FUNDS`, `EXTERNAL_CREDIT`), `amortization_mode` (`FIXED_PAYMENT`, `FIXED_PRINCIPAL`) y `application_withdrawal_reason`, todos públicos;
    - `application_transition_reason`, interno.

## Decididas en la implementación

### Parte 1
- **Relación del inmueble.** La relación inversa es `application.financed_property`, no `application.property`: ese nombre tapaba el decorador `@property` dentro de `CreditApplication`.
- **Conversión solo desde applications.** `POST /opportunities/{id}/transitions` rechaza `CONVERTED` (`400`, campo `target_status`), igual que `ASSIGNED`; las transiciones `CONVERT_*` solo las ejecuta `applications`. Siguen apareciendo en `available_actions` de la oportunidad, para que el frontend ofrezca "Convertir en solicitud".
- **Códigos `SOL-000001`.** Salen de la secuencia `credit_application_code_seq` (migración `0001`) y nunca se reutilizan, aunque falle la transacción que pidió el número.
- **`ParticipantRole`** se reutiliza desde `apps.documents.models`, para que los requisitos documentales y los participantes no puedan divergir.
- **Permisos sembrados:**
  - `applications.read` y `applications.read_summary`: `ADMIN`, `ADVISOR` e `INDEPENDENT_BROKER`;
  - `applications.read_history`, `.create`, `.update`, `.transition`, `.assign` y `.withdraw`: `ADMIN` y `ADVISOR`.

### Parte 2
- **Alcance.** El asesor ve las solicitudes donde es `assigned_advisor`, no las de oportunidades que solo originó. El broker ve las de oportunidades con `origin_user` = él, siempre como resumen (lista, detalle y `/clients/{id}/applications`) y con el documento enmascarado.
- **Concurrencia.**
  - Las respuestas de la solicitud llevan `ETag: "<version>"`, expuesto por CORS.
  - `If-Match` acepta `"3"`, `3` o `W/"3"`.
  - Sin la cabecera: `428 PRECONDITION_REQUIRED`. Versión obsoleta: `409 STALE_VERSION` con `details[0].current_version`.
  - Un `PATCH` sin cambios reales no aumenta la versión.
- **Creación.**
  - `property` es opcional: se puede registrar después con `PUT /property`.
  - `project_id` va fuera de `property`, como en el ejemplo de API §16.1, y exige `property`.
  - Sin `assigned_advisor_id` se usa el asesor de la oportunidad.
  - Las reglas por finalidad del inmueble (API §18.1, `property_errors`) ya se aplican al crear y al cambiar la finalidad: proyecto solo en `PURCHASE_NEW`, dirección en `PURCHASE_USED` y `HOME_IMPROVEMENT`, y `is_owned_by_applicant` en `HOME_IMPROVEMENT`.
  - La respuesta `201` trae el detalle aunque el creador no quede como asesor asignado.
- **Conversión.** Desde `NEW`, `LOST` o `CANCELLED` responde `409 INVALID_STATE_TRANSITION`, porque no existe `CONVERT_*`. Un nuevo intento sobre una oportunidad `CONVERTED` con una solicitud exitosa responde lo mismo. El evento `opportunity_status_changed` sale al confirmar la transacción (`on_commit`).
- **`PATCH`.** El producto debe estar activo, vigente y admitir la finalidad. Cambiar la finalidad exige que el producto elegido y el inmueble registrado la admitan.
- **Reasignación.** No cambia `version`. Se permite después de `FILED`; en una solicitud terminada responde `409 APPLICATION_CLOSED`. Si quien reasigna pierde el acceso, `204`.
- **`include` del detalle** (API §16.1) se aplaza a la Parte 4. Hoy el detalle ya trae `property` y `assignments`.

### Parte 3
- **Endpoints** (tag `Application participants`): `GET`/`POST /applications/{id}/participants`; `GET`/`PATCH`/`DELETE /application-participants/{id}`; `GET`/`PUT /application-participants/{id}/financial-profile`; `GET`/`POST /financial-profiles/{id}/income-sources`; `PATCH`/`DELETE /income-sources/{id}`. Las listas van paginadas (`items`).
- **Acceso.** Lectura con `applications.read` y escritura con `applications.update`. El broker recibe `403` en todos (`ExpedienteView`). Un subrecurso de una solicitud fuera del alcance responde `404`.
- **Concurrencia.** `lock_for_edit(application | id, expected_version: int | None)`, donde `None` no compara la versión. `PATCH` de participante, `PUT` de perfil y `PATCH` de fuente exigen `If-Match`. `POST` y `DELETE` no lo exigen, pero aumentan la versión. Todas las respuestas, incluidos los `204`, llevan `ETag` con la versión vigente de la solicitud. Un `PATCH`/`PUT` sin cambios reales no aumenta la versión.
- **Alta de participantes.**
  - `role_code` admite solo `CO_APPLICANT` o `SOLIDARY_DEBTOR`.
  - Llega `client_id` (cliente visible; si no, `400` en `client_id`) o el bloque de identidad plano, como el ejemplo de API §17.1 (`document_type_code`, `document_number`, `first_names`, `last_names`, `birth_date`, `email`, `phone`), nunca ambos. El bloque se valida con `ClientCreateSerializer` (mismas reglas que `POST /clients`) y el cliente se crea en la misma transacción.
  - Un cliente que ya participa activo responde `400` en `client_id`. Uno retirado se reactiva en su fila (mismo `id`) con el papel y los ingresos nuevos.
  - `income_share_cop` exige `contributes_income = true`.
- **Edición de participantes.** `PATCH` cambia `role_code`, `contributes_income` e `income_share_cop`. Los datos personales se corrigen en `/clients/{id}`. El `PRIMARY` no cambia de papel ni se retira (`400`).
- **Retiro.** `DELETE` marca `is_active = false` y repetirlo responde `204` sin aumentar la versión. La lista muestra solo los activos; `?include_inactive=true` agrega los retirados. Cada fila trae `is_active` y `financial_profile_id`.
- **Participante retirado.** El `GET` del participante, de su perfil y de sus fuentes sigue funcionando. Editarlo (`PATCH`, `PUT` del perfil o cambios en sus fuentes) responde `409 PARTICIPANT_INACTIVE` ("agrégalo de nuevo").
- **Perfil financiero.** `PUT` hace un reemplazo completo: lo que no llega vuelve a su valor por omisión. Responde `201` si lo crea y `200` si lo reemplaza. `employment_profile_code` es obligatorio, `employment_start_date` no puede ser futura y `data_confirmed_at` no se acepta (`400`, campo no permitido). El detalle expone `income_sources_total_cop` (suma de las fuentes) junto a `monthly_income_cop`, solo como información.
- **Fuentes de ingreso.** Como máximo una `is_primary` por perfil: marcar una nueva desmarca la anterior (al crear y al editar). La suma no se valida contra `monthly_income_cop`. `DELETE` borra la fila, porque la tabla no tiene `is_active`. La lista trae la principal primero.
- **Visibilidad en CRM.** `clients_visible_to` agrega, para el asesor, los clientes que participan (activos o retirados) en solicitudes que tiene asignadas, también tras una reasignación. El modelo se resuelve con `apps.get_model` para no crear un ciclo de imports. El broker no gana visibilidad por participación.
- **Eventos.** `participant_added` (`participant`, `reactivated`) y `participant_removed`. Los cambios de participante, perfil y fuentes salen por `application_updated` con `fields` = `["participants"]`, `["financial_profile"]` o `["income_sources"]`.
- **OpenAPI.** `ParticipantRoleEnum` en `ENUM_NAME_OVERRIDES` (ver "Avance"). La entrada `role_code` genera `RoleCodeEnum` (dos valores).

### Parte 4
- **Endpoints** (tag `Application property and financing`): `GET`/`PUT /applications/{id}/property` y `GET`/`PUT /applications/{id}/financing`. Lectura con `applications.read` y escritura con `applications.update`. El broker recibe `403` (`ExpedienteView`) y una solicitud fuera del alcance responde `404`. El `GET` responde `404` mientras el subrecurso no exista.
- **Concurrencia.** Los dos `PUT` exigen `If-Match`, hacen un reemplazo completo (lo que no llega vuelve a su valor por omisión) y responden `201` si crean y `200` si reemplazan. Un `PUT` sin cambios reales no aumenta la versión. Todas las respuestas llevan `ETag`. Después de `FILED`: `409 APPLICATION_NOT_EDITABLE`.
- **Inmueble.** `project_id` va dentro del cuerpo (API §18.1). Se reutilizan `PropertyInputSerializer`, `property_errors` y `resolve_property_project` (proyecto visible y `ACTIVE`; si no, `422 PROJECT_NOT_ACTIVE`). Las reglas por finalidad se comprueban con la solicitud bloqueada. Evento `application_updated` con `fields = ["property"]`.
- **Financiación: modos (estricto).**
  - `BANK_CREDIT` exige `bank_product_id` (activo, vigente y que admita la finalidad) y `requested_amount_cop`. El producto se guarda en `credit_applications.bank_product`.
  - Con `OWN_FUNDS` o `EXTERNAL_CREDIT`, `bank_product_id` debe ir vacío (`400`) y se limpia el producto de la solicitud. `requested_amount_cop` queda en 0: puede omitirse o llegar en 0, y otro valor responde `400`.
  - `external_approved_amount_cop` es obligatorio con `EXTERNAL_CREDIT` y se rechaza en los otros modos (`400`).
  - Sin `uses_severance_funds`, `severance_funds_cop` debe ser 0 (`400` antes del CHECK).
  - Las reglas que cruzan campos viven en `services.financing_errors` y se reportan juntas, por campo.
- **Rangos del producto.** `min/max_amount_cop` y `min/max_term_months` **no se validan al guardar**. Los verifica la evaluación de la Parte 5.
- **Evento.** `application_updated` con `fields` = `["financing"]`, `["bank_product"]` o `["bank_product", "financing"]`, según lo que cambió.
- **`PATCH /applications` frente a la modalidad.** Si hay financiación registrada con un modo distinto de `BANK_CREDIT`, un `bank_product_id` no nulo responde `400`. Con `BANK_CREDIT`, dejar el producto en `null` responde `400`. Sin financiación registrada, el `PATCH` se comporta como en la Parte 2. Cambiar solo la finalidad no mira la modalidad.
- **`include` del detalle.** `GET /applications/{id}?include=participants,financing` (separados por comas, con espacios tolerados). `property` y `assignments` salen siempre; `property` se acepta en `include` sin efecto. Un valor desconocido (también en mayúsculas) responde `400` en el campo `include`.
  - `participants` trae solo los vigentes y `financing` es `null` si no existe. Sin `include`, esas claves no aparecen.
  - Para el broker, `include` se ignora por completo, incluso si es inválido, y recibe su resumen.
  - Solo el `GET` admite `include`; las respuestas de `PATCH`, `POST` y `/assignments` siguen sin bloques opcionales.
- **OpenAPI.** Los bloques opcionales del detalle se declaran como campos no de solo lectura (`required=False`) para que el esquema no los marque obligatorios. `ApplicationDetailSerializer` quedó al final de `serializers.py` porque usa los serializers de participantes y financiación.

### Parte 5
- **Endpoints** (tag `Application bank rules`): `POST /applications/{id}/bank-rule-evaluations` (`applications.update`), `GET /applications/{id}/bank-rule-evaluations/latest` y `GET /applications/{id}/eligible-bank-products` (`applications.read`). Los tres son `ExpedienteView`: broker `403`, fuera del alcance `404`, y todos responden `ETag`.
- **Lista blanca.** Se agregaron los diez campos de la decisión 11; no se retiró ninguno, así que ninguna regla publicada se invalida. `application.participant_count` cuenta los participantes activos de todos los roles, incluido el titular.
- **Contexto.** Siempre trae todos los campos de la lista blanca (un grupo sin datos va con sus campos en `None`, no ausente), así el snapshot tiene una forma estable. Lo arma el sistema, por eso `validate_context` falla con excepción, no con `400`. `applicant.employment_months` es `None` sin `employment_start_date`; una fecha futura da 0. `property.has_project` es `None` sin inmueble.
- **Snapshot.** `result_snapshot = {"rules": [...], "context": {...}}`. Cada fila: `rule_id`, `code`, `version`, `severity`, `message` (el de la regla o el del rango, nunca el de `MISSING_DATA`), `outcome`, `unresolved_fields`, `field` y `source`. Las `PASSED` también se guardan. La respuesta (también la de `latest`) se reconstruye desde las filas.
- **Mensajes de los rangos.** "El monto solicitado debe estar entre $50.000.000 y $250.000.000 para este producto." (o "ser de al menos" / "ser como máximo de") y lo mismo para "El plazo … meses".
- **Orden.** Reglas configuradas por código y después `PRODUCT_AMOUNT_RANGE` y `PRODUCT_TERM_RANGE`.
- **Evaluación automática.** `update_application` y `put_financing` llaman a `save_evaluation` dentro de su transacción, después de `bump_version`, solo si el producto cambió a uno no nulo. No envía evento propio.
- **`eligible-bank-products`.** Evalúa solo los productos de la página pedida, con un único contexto. No guarda nada.

### Parte 6
- **Endpoints** (tag `Applications`): `POST /applications/{id}/status-transitions` (`applications.transition`), `POST /applications/{id}/withdrawals` (`applications.withdraw`), `GET /applications/{id}/status-history` (`applications.read_history`), `GET /applications/{id}/available-actions` y `GET /applications/{id}/completeness` (`applications.read`). Todos son `ExpedienteView`: broker `403`, fuera del alcance `404`, y todos responden `ETag`.
- **Orden de las comprobaciones de una transición.** `WITHDRAWN` (`400`) y el motivo obligatorio (`400`) se validan antes de bloquear la fila; después, solicitud terminada (`409 APPLICATION_CLOSED`), versión (`409 STALE_VERSION`), transición (`409 INVALID_STATE_TRANSITION` o `403` si existe pero el actor no tiene rol o permiso), modalidad de los cierres (`422 FINANCING_MODE_MISMATCH`) y, por último, la guarda.
- **Guarda.** Se evalúa cuando la transición tiene `guard_code = APPLICATION_READY_TO_FILE`, sea cual sea su destino; el catálogo de guardas (`TRANSITION_GUARDS`) solo admite esa en el flujo `APPLICATION`. Los motivos se calculan dentro de la transacción y el error se lanza fuera del bloque, para confirmar la evaluación guardada. El mensaje de cada `BANK_RULE_BLOCKED` es el del ítem de la evaluación (el del sistema con `MISSING_DATA`).
- **Documentos.** `services.documents_verified(application)` devuelve `False` y lo usan la guarda y la completitud. El paso 10 solo tiene que implementarlo. Los tests simulan el paso 10 con `monkeypatch` para cubrir el camino feliz de `READY_TO_FILE` y `ready_to_file = true`.
- **`ready_to_file_at`.** Se limpia al pasar de `READY_TO_FILE` a cualquier estado previo a la radicación (hoy solo `REOPEN_REVIEW`).
- **Desistimiento.** `closed_at` y `withdrawn_at` comparten el mismo instante. El historial guarda el motivo de desistimiento en `reason_item`.
- **Acciones.** Ordenadas por código (`available_transitions`). El detalle las calcula también en la respuesta `201` de la creación y en la del `PATCH`.
- **Completitud.** El mensaje de `financial_profile` usa el nombre del participante. `bank_evaluation` explica el motivo: sin producto, sin evaluación, desactualizada o con bloqueos.
- **Motivos de cierre.** Migración `0003_seed_closing_reasons`: los siete motivos nuevos se ordenan después de los existentes y `OTHER` se mueve al final.
- **Documentación.** Se aplicó la lista "Documentación pendiente de actualizar" en `docs/API_REST_MVP_CREDITO.md`, y además §6 (concurrencia de la solicitud y el aplazamiento de `Idempotency-Key`), §9, §16.1 a §16.3 (reglas de creación, detalle, transiciones, desistimiento, historial, acciones y completitud) y la nota de §27.4. En el README: la sección "Credit Applications" y "Current Status" con los pasos 5 a 8 (antes solo listaba hasta el 4).

---

## Plan de las partes pendientes

Todas las partes están hechas; este plan queda como registro de lo acordado. Lo que se decidió al implementar está en "Decididas en la implementación".

### Parte 5. Integración con banking

- **Contexto.** `apps/applications/rule_context.py`: `build_rule_context(application) -> dict` con la forma de `RULE_FIELDS` (`application.*`, `applicant.*` = `PRIMARY`, `household.*`, `property.*` y `financing.*`), validado con `apps.banking.rule_engine.validate_context`. Los datos que falten van como `None` (resultado `MISSING_DATA`).
- **Lista blanca.** Ajustar `apps/banking/rule_fields.py` según la decisión 11 y actualizar la tabla de API §23.3. `applicant.employment_months` son los meses completos desde `employment_start_date` hasta hoy.
- **Hogar (acordado).** `household.monthly_income_cop`, `household.monthly_expenses_cop` y `household.liabilities_cop` suman los mismos participantes: los activos con `contributes_income`. En el ingreso, `income_share_cop` (si está informado) reemplaza al del perfil. En gastos y pasivos, si a uno de esos participantes le falta el perfil financiero, la suma es `null` (`MISSING_DATA`); en el ingreso, solo si además le falta `income_share_cop`.
- **`POST /applications/{id}/bank-rule-evaluations`** (`applications.update`; broker `403`):
  - **(acordado)** Sin producto elegido: `422 BANK_PRODUCT_REQUIRED` (código nuevo).
  - **(acordado)** Solo antes de `FILED`; después, `409 APPLICATION_NOT_EDITABLE`. No exige `If-Match`, no cambia la versión y bloquea la fila (`select_for_update`) para leer un contexto coherente. Responde `201` con `ETag`.
  - Llama a `banking.services.evaluate_rules(product, context, purpose=...)` y guarda un `BankRuleEvaluation` con `application_version`, contadores, `evaluated_by` y `result_snapshot`: por regla, `rule_id`, `code`, `version`, `severity`, `message`, `outcome`, `unresolved_fields` y `source` (`RULE` o `SYSTEM`), más el contexto evaluado.
  - **Elegibilidad (acordado): falla cerrada.** Cualquier regla `BLOCKING` (configurada o del sistema) con `FAILED` o `MISSING_DATA` deja la evaluación no elegible y cuenta en `blocking_count`. Las `WARNING` con `FAILED` o `MISSING_DATA` van a `warnings` (`warning_count`) y no afectan la elegibilidad. Las `PASSED` no aparecen en la respuesta, pero sí en el snapshot.
  - **Rangos del producto (acordado).** Además de las reglas configuradas, la evaluación verifica siempre `min/max_amount_cop` (contra `requested_amount_cop`) y `min/max_term_months` (contra `term_months`) cuando el producto los tiene definidos. Es una validación **bloqueante del sistema**: no depende de que el administrador cree una regla. Fuera de rango, la solicitud no puede pasar a `READY_TO_FILE`.
    - Dos reglas del sistema, `PRODUCT_AMOUNT_RANGE` y `PRODUCT_TERM_RANGE`, siempre `BLOCKING`.
    - Monto o plazo vacío, o sin financiación, da `MISSING_DATA` bloqueante.
    - Si el producto no tiene límites de monto (o de plazo), esa regla no aparece.
    - En el snapshot van con `rule_id` y `version` nulos y `source: "SYSTEM"`.
  - **Respuesta (acordado).** Forma de API §18.2: `eligible`, `blocking`, `warnings` y `evaluated_at`. Cada ítem de `blocking`/`warnings` trae `{rule_code, outcome, message, field, unresolved_fields}`:
    - `field` es la ruta completa de la lista blanca (`financing.requested_amount_cop`): el primer campo faltante con `MISSING_DATA`, o el primer campo que cita la condición con `FAILED`.
    - Con `MISSING_DATA`, `message` es del sistema ("Faltan datos para evaluar la regla: …"), no el de la regla, que describe un incumplimiento.
  - **(acordado)** La respuesta del `POST` trae además `id`, `bank_product_id`, `application_version` e `is_current`.
- **`GET .../bank-rule-evaluations/latest` (acordado).** Devuelve siempre la más reciente, con la forma del `POST` (`id`, `bank_product_id`, `application_version` e `is_current`, que es verdadero si la versión y el producto coinciden con los actuales de la solicitud). `404` solo si nunca se evaluó.
- **`GET /applications/{id}/eligible-bank-products` (acordado).** `available_products(purpose=...)` más la evaluación no persistida de cada producto, incluidas las reglas del sistema. Paginada con `items`, ordenada por nombre del banco y del producto. Cada ítem trae el producto (`id`, `code`, `name`, banco `{id, code, name}`, `product_type_code` y rangos de monto y plazo) y `evaluation: {eligible, blocking_count, warning_count}`. Se listan aunque la modalidad registrada no sea `BANK_CREDIT`. Broker `403`.
- **Evaluación automática (acordado).** Solo cuando `PATCH /applications` o `PUT /financing` cambian el producto a uno no nulo: se guarda una evaluación en la misma transacción, con la versión nueva y `evaluated_by` = actor. Los demás cambios dejan la última evaluación con `is_current = false` hasta un nuevo `POST`. Las respuestas del `PATCH`/`PUT` no cambian de forma.

### Parte 6. Estados y cierre (hecha)

- **`POST /applications/{id}/status-transitions`** (`applications.transition`).
  - Cuerpo: `target_status`, `reason_code` (catálogo `application_transition_reason`), `comment` y `expected_version`.
  - **Motivo (acordado).** `reason_code` es obligatorio al pasar a `CANCELLED`, `OWN_FUNDS` y `EXTERNAL_CREDIT_APPROVED` (`400` en `reason_code`) y opcional en las demás. Debe ser un ítem activo del catálogo. `comment` es opcional, hasta 2000 caracteres.
  - **Motivos de cierre sembrados (acordado, editables).** Se agregan a `application_transition_reason`: `CLIENT_UNREACHABLE`, `INSUFFICIENT_CAPACITY`, `CLIENT_DECLINED_PURCHASE`, `BETTER_RATE_ELSEWHERE`, `FASTER_ELSEWHERE`, `EXISTING_BANK_RELATIONSHIP` y `SOLD_OTHER_PROPERTY` (`OTHER` ya existía). Migración nueva, sin tocar la `0002`.
  - Rechaza `WITHDRAWN` con `400` (va por `/withdrawals`).
  - Usa `catalogs.services.resolve_transition` y evalúa la guarda.
  - En una transacción: cambia el estado, pone `current_stage_started_at` en ahora y aumenta `version`; fija `ready_to_file_at` al llegar a `READY_TO_FILE` y `closed_at` al llegar a un estado terminal; crea la fila del historial con `transition`, `reason_item`, `comment`, `actor_user` y `application_version`.
  - **`ready_to_file_at` (acordado).** Se fija en cada llegada a `READY_TO_FILE` y se limpia con `REOPEN_REVIEW`. Se conserva al avanzar (paso 11) o al cerrar.
  - Evento `application_status_changed`.
  - **Versión (acordado).** `expected_version` es obligatorio en el cuerpo (API §16.3), sin `If-Match`. Si no coincide: `409 STALE_VERSION` con `details[0].current_version`. La respuesta tiene la forma de API §16.3 (`application_id`, `previous_status`, `status`, `version`, `transitioned_at`) y lleva `ETag`.
  - **Solicitud terminada (acordado).** `409 APPLICATION_CLOSED`, antes de buscar la transición (como la reasignación).
  - **Modalidad (acordado).** Pasar a `OWN_FUNDS` exige una financiación registrada con modalidad `OWN_FUNDS`, y pasar a `EXTERNAL_CREDIT_APPROVED` exige `EXTERNAL_CREDIT`. Sin financiación o con otra modalidad: `422 FINANCING_MODE_MISMATCH` (código nuevo), con `details` en `financing_mode_code`.
- **Guarda `APPLICATION_READY_TO_FILE`.** Producto elegido y última evaluación de la versión actual elegible (incluye los rangos del producto, Parte 5); la parte documental falla cerrada, así que `READY_TO_FILE` no se puede alcanzar hasta el paso 10. Los tests verifican el rechazo y el mensaje.
  - **Reevaluación automática (acordado).** Si la última evaluación no es vigente (`is_current = false`) o no existe, se evalúa y se guarda con la fila bloqueada, antes de aplicar la guarda (reutiliza `save_evaluation`). Si la guarda falla, **la evaluación queda confirmada** y después se responde el error: así `/bank-rule-evaluations/latest` muestra los motivos bancarios.
  - **Error (acordado).** `422 APPLICATION_NOT_READY` con todos los motivos en `details`: `BANK_PRODUCT_REQUIRED` (campo `bank_product_id`) si no hay producto; un `BANK_RULE_BLOCKED` por cada regla bloqueante, con su `field`; y `DOCUMENTS_NOT_VERIFIED` (campo `documents`) mientras no exista el expediente documental (paso 10).
- **`POST /applications/{id}/withdrawals`** (`applications.withdraw`).
  - Cuerpo: `reason_code` (catálogo `application_withdrawal_reason`, obligatorio), `comment` y `expected_version` (obligatorio, acordado; mismas reglas que las transiciones).
  - Fija `withdrawn_at`, `withdrawal_reason_item` y `closed_at`, y usa la transición `WITHDRAW_<estado>`. Se permite también después de `FILED`; en una solicitud terminada, `409 APPLICATION_CLOSED`.
  - Responde la forma de API §16.3 con `ETag`.
- **`GET /applications/{id}/status-history` (acordado).** Paginado (`items`), de la más reciente a la más antigua, incluido el registro de creación (`from_status = null`). Cada fila: `{id, from_status, to_status, transition_code, reason {code, label}, comment, actor {id, name}, application_version, created_at}`. Permiso `applications.read_history`; el broker recibe `403`.
- **Acciones disponibles (acordado).** `available_actions` en el detalle interno y `GET /applications/{id}/available-actions` (REQUERIMIENTOS §8.7; broker `403`). Los dos devuelven objetos `{code, label, target_status, guard_code}` de `catalogs.services.available_transitions` (rol y permiso; la guarda no se evalúa). Incluyen `WITHDRAW_*`, que el frontend ejecuta por `/withdrawals`.
- **`GET /applications/{id}/completeness` (acordado).** Broker `403`.
  - `items` de datos, cada uno `{code, complete, message, participant_id}`: `property`, `financing`, `bank_product` y `bank_evaluation` (vigente y elegible), estos dos últimos solo sin financiación registrada o con `BANK_CREDIT`; y `financial_profile` por cada participante activo que aporta ingresos (con su `participant_id`).
  - `percentage` = completos / total, entero hacia abajo.
  - `documents: {verified: false, message}` no cuenta en el porcentaje, y `ready_to_file` es siempre `false` hasta el paso 10.
- **README.** Agregar `applications` en "Current Status" y la tabla de endpoints de solicitudes.
- **Documentación.** Aplicar lo de "Documentación pendiente de actualizar".

---

## Documentación de la API

Aplicada en la Parte 6 (`docs/API_REST_MVP_CREDITO.md`): §5.4, §5.5, §6, §9, §16.1, §16.2, §16.3, §17.1, §17.2, §18.1, §18.2, §23.3 y §27.4. Los cambios de los pasos siguientes que afecten a solicitudes (comprador, expediente documental, radicación e idempotencia) deben actualizar esas mismas secciones.

## Pendientes para pasos posteriores

1. **Paso 9 (acceso del comprador).** **Hecho** en `feat/buyer-access` (ver `TAREA-buyer-access.md`): la columna y su `CHECK` (Parte 1), el comprador en las cuatro operaciones (Partes 5 y 6), y un cambio real del perfil o de sus ingresos limpia `data_confirmed_at` (decisión 14).
   - Agregar `application_status_history.actor_buyer_session_id`, con FK a `buyer_sessions` (`SET NULL`) y el `CHECK (num_nonnulls(actor_user_id, actor_buyer_session_id) <= 1)` del esquema.
   - Habilitar al comprador en el desistimiento, la edición previa a `FILED`, la confirmación del perfil (`data_confirmed_at`) y `eligible-bank-products`.
   - Decidir si un `PUT` del perfil financiero con cambios reales limpia `data_confirmed_at`. Hoy no lo toca.
2. **Paso 13 (notificaciones).** Exigir `Idempotency-Key` en `POST /applications` y en `POST /applications/{id}/status-transitions` (API §6 y §16.1) cuando exista `idempotency_keys`.
3. **Paso 10 (expediente).** **Hecho** en `feat/document-file` (ver `TAREA-document-file.md`, Partes 3 y 6): la guarda exige los obligatorios aprobados no vencidos o exonerados, con `DOCUMENT_PENDING`, `DOCUMENT_EXPIRED` y `DOCUMENTS_NOT_CONFIGURED` en lugar de `DOCUMENTS_NOT_VERIFIED`; los slots se recalculan en la misma transacción que el cambio de perfil laboral; `/completeness` promedia datos y documentos, y `ready_to_file` usa la misma regla que la guarda.
   - Completar la parte documental de la guarda `APPLICATION_READY_TO_FILE` (una lista vacía tampoco la cumple; ver `TAREA-documents-config.md`) y quitar `DOCUMENTS_NOT_VERIFIED`. Recalcular los requisitos cuando cambie el perfil laboral (API §17.2). En `/completeness`, los documentos pasan a contar en `percentage` y `ready_to_file` se calcula con el expediente real.
4. **Paso 11 (radicación).** Agregar las transiciones desde `READY_TO_FILE → FILED` en adelante.
5. **Paso 12 (actividad).** Suscribirse a `application_created`, `application_updated`, `application_assigned` y, desde la Parte 6, `application_status_changed`.
6. **Mejora futura (CRM).** Alinear `available_actions` de la oportunidad (hoy, una lista de códigos) al formato de objetos de la solicitud: `{code, label, target_status, guard_code}`.
