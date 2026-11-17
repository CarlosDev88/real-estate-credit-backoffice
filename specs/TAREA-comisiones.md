# Tarea: módulo de comisiones (`commissions`, paso 16)

> ## Precisiones del orquestador (2026-11-17) — MANDAN sobre el resto de esta spec
> Esta spec se escribió antes de construir los módulos 11 a 14. Donde choque con lo de abajo, gana esto:
>
> 1. **No hay outbox.** El proyecto usa señales de Django que se envían después del commit. El disparo automático es un receptor de `filing_response_recorded` (`apps/filings/signals.py`) cuando `response` es de tipo `DISBURSED` (la solicitud pasa a `DISBURSED` en ese mismo registro). Base = `response.disbursed_amount_cop`; fecha = `response.received_at` (fecha de Bogotá). No crees un evento `APPLICATION_DISBURSED` ni una tabla de eventos.
> 2. **Sin plan vigente:** el receptor no lanza error (la respuesta del banco ya quedó guardada): registra una actividad visible para el admin con `record_activity` (`apps/activity/services.py`) y un `logger.warning` sin datos personales. El admin crea el plan y liquida con el endpoint manual, que sí responde `422 COMMISSION_PLAN_NOT_FOUND`.
> 3. **Corrección del desembolso:** la corrección llega como otra `FilingResponse` con `corrects_response` apuntando a la anterior, por la misma señal. Si la respuesta corregida tenía una liquidación `ACTIVE` → regla de "Corrección del desembolso". `filing_response_id` de la liquidación nueva = la respuesta que corrige.
> 4. **Idempotency-Key:** usa el decorador `@idempotent` del #23 en los tres POST (liquidar, anular y pagar), **opcional como en el resto de la API** (no obligatorio). Además, la lógica es idempotente por sí misma (liquidación única `ACTIVE`, pagar una parte ya `PAID` → `409 COMMISSION_SHARE_NOT_PAYABLE`).
> 5. **Auditoría (módulo 14, ya en master):** usa el mismo mecanismo que dejó el módulo 14: atributos `audit_actions` en las vistas y, si emites señales nuevas (`commission_settled`, `commission_settlement_voided`, `commission_share_paid`), un receptor en `apps/audit/receivers.py`. Agrega las acciones nuevas al enum de auditoría. Nunca guardes montos en `metadata`, solo ids y códigos.
> 6. **`If-Match`** en `PATCH /commission-plans/{id}` con el helper de ETag del proyecto (`config/openapi.py`, `etag_response_headers`), igual que en `banking`.
> 7. **Etiquetas:** todo `status` sale con su `status_label` (`ChoiceLabelField`), también `beneficiary_role_label` y `lead_origin_label`.
> 8. **Demo:** `seed_demo_data` crea un plan vigente por cada producto de demo (`rate_pct = 1.0000`, asesor 70 / broker 30, vigente desde el 1 de enero de 2026) y, si hay solicitudes de demo en `DISBURSED`, las liquida. Idempotente, como el resto del seed.
> 9. **Alcance de `/me/commissions`:** paginado, filtros `status` y `date_from`/`date_to` (fecha de desembolso). Para el broker, cada fila trae **solo**: código de la solicitud, nombre del cliente, fecha de desembolso, `share_pct`, `amount_cop`, `status`, `status_label` y `paid_at`.
> 10. **Reglas de trabajo** (reemplazan "Reglas para el agente" del final): git solo lectura; **no preguntes**: si algo es ambiguo, decide lo más simple, anótalo en "Precisiones acordadas" de esta spec y en el reporte; pruebas **acotadas** (`tests/commissions/` y lo que toques), la suite completa la corre el CI; siempre `ruff`, `mypy .`, `makemigrations --check` y `spectacular --validate --fail-on-warn`; `DATABASE_NAME=mvp_credit_a`.
>
> ### Partes
> - **Parte 1 — Planes:** app `apps.commissions`, las 3 tablas con sus `CHECK` e índices, permisos (migración), CRUD de planes con solapamiento (bloqueo de los planes del producto), cierre e "en uso". Pruebas de planes.
> - **Parte 2 — Liquidación:** `settle_application`, cálculo y redondeo, reparto por origen, receptor de la señal, endpoint manual, corrección del desembolso, anulación, casos borde, actividad. Pruebas de cálculo, idempotencia, corrección y anulación.
> - **Parte 3 — Pagos, consulta y cierre:** pagar una parte, listados y detalle de liquidaciones, `/me/commissions`, matriz de permisos completa, auditoría, demo, contrato y docs (lista del final), brecha de pantalla de comisiones en `TAREA-frontend-base.md`, título y descripción del PR.

## Objetivo
Calcular automáticamente la comisión de cada crédito desembolsado, repartirla entre asesor y broker, y registrar el pago de cada parte con trazabilidad.

## Cuándo se construye
Paso 16 del orden de construcción (DER §15), después de `filings` (11), `notifications`/outbox (13) y `audit` (14). Rama: `feat/commissions`, creada desde `master`.

## Reglas de negocio (decididas)
1. La comisión **solo se genera cuando la solicitud llega a `DISBURSED`**. Una aprobación no genera comisión: el crédito todavía puede caerse en legalización.
2. **Base:** `disbursed_amount_cop` de la respuesta bancaria de desembolso (`filing_responses`).
3. **Comisión total** = base × `rate_pct` del plan vigente del producto bancario en la fecha de desembolso (`filing_responses.received_at`).
4. **Reparto según el origen de la oportunidad** (catálogo `lead_origin`):
   - `BROKER`: el asesor recibe `advisor_share_pct` y el broker (`opportunities.origin_user_id`) recibe `broker_share_pct`. El asesor siempre lleva la porción mayor.
   - `PARTNER_PROJECT`, `DIRECT` o `REFERRAL`: el asesor recibe el 100%. **La constructora no recibe comisión**; su beneficio es vender el inmueble.
5. **Asesor beneficiario:** `credit_applications.assigned_advisor_id` en el momento del desembolso.
6. **Una sola liquidación vigente por solicitud.**
7. **Instantánea:** base, tasa y porcentajes se copian a la liquidación. Cambiar o cerrar un plan nunca altera liquidaciones existentes.
8. **Pago por partes:** el admin marca como pagada cada parte (asesor y broker) por separado, con fecha y referencia de pago.

## Modelo de datos (3 tablas)
Convenciones del modelo: dinero COP en `BIGINT`, porcentajes en `NUMERIC(8,4)`, estados estructurales en `VARCHAR` con `CHECK`.

### `commission_plans`
Porcentaje de comisión y reparto por producto bancario, con vigencia.

| Campo | Tipo | Nulo | Regla/uso |
| --- | --- | --- | --- |
| `id` | `UUID` | No | PK. |
| `created_at`, `updated_at` | `TIMESTAMPTZ` | No | Convención común. |
| `bank_product_id` | `UUID` | No | FK `bank_products`, `RESTRICT`. |
| `rate_pct` | `NUMERIC(8,4)` | No | `> 0` y `<= 100`. Porcentaje sobre el monto desembolsado. |
| `advisor_share_pct` | `NUMERIC(8,4)` | No | Porción del asesor cuando hay broker. |
| `broker_share_pct` | `NUMERIC(8,4)` | No | Porción del broker. `CHECK advisor_share_pct + broker_share_pct = 100` y `CHECK advisor_share_pct > broker_share_pct`. |
| `valid_from` | `DATE` | No | Inicio de vigencia. |
| `valid_until` | `DATE` | Sí | Fin de vigencia (exclusivo). `CHECK valid_until > valid_from`. Nulo = vigente sin fin. |
| `notes` | `VARCHAR(255)` | Sí | Nota interna. |
| `created_by_id` | `UUID` | No | FK `users`, `RESTRICT`. |

- No puede haber dos planes con vigencias solapadas para el mismo producto. Se valida en el servicio dentro de la transacción (con bloqueo sobre los planes del producto) y se prueba.
- Un plan usado por alguna liquidación no se edita: se cierra (`valid_until`) y se crea uno nuevo.
- Índice: (`bank_product_id`, `valid_from DESC`).

### `commission_settlements`
Liquidación de la comisión de una solicitud desembolsada.

| Campo | Tipo | Nulo | Regla/uso |
| --- | --- | --- | --- |
| `id` | `UUID` | No | PK. |
| `created_at`, `updated_at` | `TIMESTAMPTZ` | No | Convención común. |
| `application_id` | `UUID` | No | FK `credit_applications`, `RESTRICT`. |
| `filing_response_id` | `UUID` | No | FK `filing_responses`, `RESTRICT`; respuesta de desembolso usada. UQ. |
| `plan_id` | `UUID` | No | FK `commission_plans`, `RESTRICT`. |
| `lead_origin_code` | `VARCHAR(50)` | No | Instantánea del origen (`BROKER`, `PARTNER_PROJECT`, `DIRECT`, `REFERRAL`). |
| `base_amount_cop` | `BIGINT` | No | `> 0`. Monto desembolsado. |
| `rate_pct` | `NUMERIC(8,4)` | No | Instantánea de la tasa. |
| `total_amount_cop` | `BIGINT` | No | `>= 0`. Comisión total. |
| `status` | `VARCHAR(20)` | No | `ACTIVE`, `VOIDED`. |
| `needs_review` | `BOOLEAN` | No | `DEFAULT FALSE`. Ver "Corrección del desembolso" y "Casos borde". |
| `voided_at` | `TIMESTAMPTZ` | Sí | Obligatorio si `VOIDED`. |
| `voided_by_id` | `UUID` | Sí | FK `users`, `SET NULL`. |
| `void_reason` | `VARCHAR(255)` | Sí | Obligatorio si `VOIDED`. |

- Índice único parcial: (`application_id`) `WHERE status = 'ACTIVE'`.
- Índice: (`status`, `created_at DESC`).

### `commission_shares`
Parte de la comisión de cada beneficiario y su pago.

| Campo | Tipo | Nulo | Regla/uso |
| --- | --- | --- | --- |
| `id` | `UUID` | No | PK. |
| `created_at`, `updated_at` | `TIMESTAMPTZ` | No | Convención común. |
| `settlement_id` | `UUID` | No | FK `commission_settlements`, `CASCADE`. |
| `beneficiary_user_id` | `UUID` | No | FK `users`, `RESTRICT`. |
| `beneficiary_role` | `VARCHAR(40)` | No | `ADVISOR`, `INDEPENDENT_BROKER`. UQ (`settlement_id`, `beneficiary_role`). |
| `share_pct` | `NUMERIC(8,4)` | No | `> 0` y `<= 100`. |
| `amount_cop` | `BIGINT` | No | `>= 0`. |
| `status` | `VARCHAR(20)` | No | `PENDING`, `PAID`, `VOIDED`. |
| `paid_at` | `DATE` | Sí | Obligatorio si `PAID`. |
| `paid_by_id` | `UUID` | Sí | FK `users`, `SET NULL`. |
| `payment_reference` | `VARCHAR(100)` | Sí | Referencia del pago. |

- Índice: (`beneficiary_user_id`, `status`, `created_at DESC`) para "mis comisiones".

## Cálculo y redondeo
- Siempre con `Decimal`, nunca `float`. Redondeo `ROUND_HALF_UP` al peso.
- `total = round(base × rate_pct / 100)`.
- Con broker: `broker = round(total × broker_share_pct / 100)` y `advisor = total − broker`. Así la suma siempre cuadra exacta.
- Sin broker: una sola parte del asesor con `share_pct = 100` y `amount_cop = total`.

## Disparo
- Un único servicio de dominio `settle_application(application_id)` hace todo el cálculo dentro de una transacción.
- Lo invocan:
  1. El handler del evento outbox `APPLICATION_DISBURSED`, que `filings` emite en la misma transacción en que registra la respuesta de desembolso. Si el paso 11 aún no lo emite, se agrega en esta tarea.
  2. El endpoint manual `POST /applications/{application_id}/commission-settlement` (admin).
- **Idempotente:** si ya existe una liquidación `ACTIVE` para la solicitud, la devuelve sin crear otra. Un evento duplicado nunca genera doble comisión.
- **Sin plan vigente** para el producto en la fecha de desembolso: no crea nada, el evento queda `FAILED` con `COMMISSION_PLAN_NOT_FOUND` y se registra una actividad visible para el admin. El admin crea el plan y usa el endpoint manual.

## Corrección del desembolso
Si la respuesta de desembolso se corrige (`filing_responses.corrects_response_id`):
- **Ninguna parte pagada:** se anula la liquidación (`VOIDED`, partes `VOIDED`) y se crea una nueva con el monto corregido, en la misma transacción.
- **Alguna parte pagada:** no se toca; se marca `needs_review = true` para manejo manual (ajustes fuera de la v1).

## Casos borde
- Origen `BROKER` pero sin `origin_user_id` (broker eliminado o dato faltante): 100% al asesor y `needs_review = true`.
- Anular una liquidación con alguna parte `PAID`: `409 COMMISSION_SETTLEMENT_HAS_PAYMENTS`.
- Pagar una parte ya pagada con la misma `Idempotency-Key`: devuelve la respuesta original.

## API
Todas bajo `/api/v1`, con los formatos comunes de la API (§5) y `If-Match` en `PATCH`.

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| `GET` | `/commission-plans` | `commission_plans.read` | Lista planes; filtros `bank_product_id`, `vigente_en` (fecha). |
| `POST` | `/commission-plans` | `commission_plans.manage` | Crea plan. Valida porcentajes y solapamiento. |
| `GET` | `/commission-plans/{plan_id}` | `commission_plans.read` | Detalle. |
| `PATCH` | `/commission-plans/{plan_id}` | `commission_plans.manage` | Solo si ninguna liquidación lo usa. |
| `POST` | `/commission-plans/{plan_id}/close` | `commission_plans.manage` | Fija `valid_until`. |
| `GET` | `/commission-settlements` | `commissions.read` | Lista; filtros estado, banco, asesor, broker, fechas, `needs_review`. |
| `GET` | `/commission-settlements/{settlement_id}` | `commissions.read` | Detalle con sus partes. |
| `POST` | `/applications/{application_id}/commission-settlement` | `commissions.manage` | Liquida manualmente. Requiere `Idempotency-Key`. Idempotente. |
| `POST` | `/commission-settlements/{settlement_id}/void` | `commissions.manage` | Anula con motivo obligatorio. Requiere `Idempotency-Key`. |
| `POST` | `/commission-shares/{share_id}/pay` | `commissions.manage` | Marca pagada con `paid_at` y `payment_reference`. Requiere `Idempotency-Key`. |
| `GET` | `/me/commissions` | `commissions.read_own` | Partes propias del usuario autenticado. |

## Permisos y visibilidad
| Permiso | ADMIN | ADVISOR | INDEPENDENT_BROKER | CONSTRUCTION_PARTNER | BUYER |
| --- | --- | --- | --- | --- | --- |
| `commission_plans.read` | Sí | No | No | No | No |
| `commission_plans.manage` | Sí | No | No | No | No |
| `commissions.read` | Sí | No | No | No | No |
| `commissions.manage` | Sí | No | No | No | No |
| `commissions.read_own` | — | Sí | Sí | No | No |

- `/me/commissions` devuelve **solo la parte propia**: código de la solicitud, fecha de desembolso, porcentaje propio, monto propio, estado y fecha de pago.
- El broker **no** ve la base, la tasa, la comisión total ni la parte del asesor (no accede a datos financieros detallados, REQUERIMIENTOS §3). El asesor tampoco ve la parte del broker.
- Los permisos se siembran con una migración de datos, igual que en `crm` y `banking`.

## Errores nuevos
| Código | HTTP | Significado |
| --- | --- | --- |
| `COMMISSION_PLAN_NOT_FOUND` | 422 | No hay plan vigente para el producto en la fecha de desembolso. |
| `COMMISSION_PLAN_OVERLAP` | 409 | La vigencia se solapa con otro plan del mismo producto. |
| `COMMISSION_PLAN_IN_USE` | 409 | El plan ya fue usado por una liquidación y no se puede editar. |
| `APPLICATION_NOT_DISBURSED` | 409 | La solicitud no está en `DISBURSED`. |
| `COMMISSION_SETTLEMENT_HAS_PAYMENTS` | 409 | No se puede anular: tiene partes pagadas. |
| `COMMISSION_SHARE_NOT_PAYABLE` | 409 | La parte no está `PENDING`. |

## Auditoría y trazabilidad
- Crear, editar o cerrar planes, liquidar, anular y pagar generan `audit_events`.
- Liquidar, anular y pagar agregan un evento a la actividad de la solicitud.

## Fuera de alcance (v1)
- Retenciones, impuestos y facturación de comisiones.
- Pagos parciales de una parte y ajustes manuales de montos.
- Comisión para referidos o constructoras.
- Recálculo retroactivo al cambiar planes.
- Exportación CSV de comisiones (iría en `reporting` si se pide).

## Pruebas mínimas
- Reparto con broker y sin broker (los 3 orígenes restantes dan 100% al asesor).
- Redondeo: la suma de las partes siempre es igual al total (incluye casos con decimales .5).
- Idempotencia: el evento `APPLICATION_DISBURSED` dos veces crea una sola liquidación.
- Selección del plan por fecha de desembolso (antes, dentro y al borde de la vigencia).
- Solapamiento de planes rechazado; plan en uso no editable.
- Sin plan vigente: no crea liquidación y el error es `COMMISSION_PLAN_NOT_FOUND`.
- Corrección del desembolso con y sin partes pagadas.
- Anulación con y sin pagos; pago de parte no `PENDING`.
- Matriz de permisos: cada endpoint con todos los roles; en `/me/commissions` cada usuario ve solo su parte y el broker no ve base, tasa, total ni la parte del asesor.

## Reglas para el agente
- Antes de proponer commits, corre y deja en verde: `ruff check .`, `ruff format --check .`, `mypy .`, `python manage.py makemigrations --check --dry-run` y `pytest`.
- Todo con anotaciones de tipos. Nada de `type: ignore` ni `noqa` sin justificar.
- Si algo es ambiguo, pregunta antes de decidir.
- **Git solo en modo lectura.** Propón los commits; Carlos hace los commits, el push y el PR.

## Documentación actualizada con esta tarea
- `REQUERIMIENTOS_MVP_CREDITO.md`: alcance, decisión "Comisiones", RF-80 a RF-86 (§5.9) y fila en la matriz §8.6.
- `DER_COMPLETO_MVP_CREDITO.md`: paso 16 en §15 y total de 58 tablas.
- `MODELO_DATOS_DER_MVP_CREDITO.md`: inventario y nueva §14 con las 3 tablas.
- `ESQUEMA_POSTGRESQL_MVP_CREDITO.sql`: 3 tablas e índices.
- `API_REST_MVP_CREDITO.md`: errores §5.5, nueva §23.6 y fila en la matriz §25.

## Precisiones acordadas
_(las agrega el agente)_

### Parte 1
- **P1.1 `version` en los planes.** El `If-Match` del proyecto (`apps/applications/concurrency.py`, API §6) se basa en un entero. Por eso `commission_plans` tiene `version` (desvío del SQL, que se documenta al cierre). Sube con cada edición o cierre, y la responden `ETag` del detalle, la creación, la edición y el cierre. `banking` no usa `If-Match`; se tomó el mecanismo del expediente.
- **P1.2 Bloqueo para el solapamiento.** Se bloquea la fila del producto (`select_for_update` sobre `bank_products`) antes de validar el solapamiento. Bloquear solo los planes existentes no impide que entre uno nuevo en paralelo. Así, dos altas o ediciones del mismo producto se serializan.
- **P1.3 Vigencia.** `[valid_from, valid_until)`: el fin es exclusivo, así que un plan puede empezar el mismo día en que termina otro. `vigente_en` sigue la misma regla.
- **P1.4 Validación.** Las reglas de los `CHECK` responden `400` en su campo, antes de llegar a la base. Con `broker_share_pct` negativo, el error va en `broker_share_pct`; si la suma no da 100 o el asesor no lleva la mayor, en `advisor_share_pct`; con un fin no posterior al inicio, en `valid_until`. Asesor 100 / broker 0 es válido.
- **P1.5 Edición.** `PATCH` admite `rate_pct`, los dos porcentajes, `valid_from`, `valid_until` y `notes`. El producto no cambia (un campo desconocido responde `400`). Se revalida el plan completo, y un `PATCH` vacío no sube la versión.
- **P1.6 "En uso".** Cuenta cualquier liquidación, vigente o anulada: el plan es la instantánea de una liquidación que existió. `in_use` sale en cada plan (anotado, sin consultas por fila).
- **P1.7 Cierre.** `POST /close` con `valid_until` (obligatorio, posterior a `valid_from`). Se permite en un plan en uso. Solo adelanta el fin: alargar un plan ya cerrado podría solaparse, así que responde `400`. Para alargarlo se crea un plan nuevo.
- **P1.8 Textos opcionales.** `notes`, `void_reason` y `payment_reference` son texto vacío en lugar de nulos (convención de Django); el `CHECK` de la anulación exige un `void_reason` no vacío.
- **P1.9 Auditoría.** `COMMISSION_PLAN_CHANGED` para crear, editar y cerrar (por `audit_actions`). Las acciones de las partes 2 y 3 (`COMMISSION_SETTLED`, `COMMISSION_SETTLEMENT_VOIDED` y `COMMISSION_SHARE_PAID`) ya quedaron en el enum, en la misma migración `audit.0004`, para no generar una por parte.
- **P1.10 Permisos.** Los 5 de la spec en una migración: `commission_plans.read` y `.manage` y `commissions.read` y `.manage` para `ADMIN`; `commissions.read_own` para `ADVISOR` e `INDEPENDENT_BROKER`.
