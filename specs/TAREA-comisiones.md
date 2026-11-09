# Tarea: módulo de comisiones (`commissions`, paso 16)

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
