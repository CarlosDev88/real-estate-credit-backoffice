# Tarea: datos que le faltan al listado de solicitudes

## Objetivo
Que `GET /applications` entregue lo que muestra el mockup `design/screens/solicitudes.html`, para que el frontend no tenga que hacer una petición por fila ni definir agrupaciones de estados por su cuenta (REQ §8.5).

## Cuándo
- Después del merge de la fase 10 y del monorepo. Antes de que el agente A del frontend conecte el listado con la API real.
- Rama: `feat/applications-list-fields`.

## Reglas de trabajo
Las mismas de siempre:
- Git solo en lectura; Carlos hace los commits de cada parte.
- Sin `Co-Authored-By`.
- Primero, las ambigüedades una por una con su recomendación; después se implementa.
- OpenAPI con `--fail-on-warn` y `contracts/openapi.json` actualizado.
- Cobertura ≥ 95 %.

## Lo que existe hoy (verificado)
- `GET /applications` filtra por `status`, `bank_id`, `product_id`, `purpose`, `advisor_id`, `project_id` y `origin`.
- Busca por código, nombres y documento del cliente.
- Ordena por `created_at`, `updated_at`, `status` y `code`.
- Serializer interno: `ApplicationSerializer`, con `bank_product` como referencia (`BankProductRefSerializer`). El broker recibe `ApplicationSummarySerializer`.
- `BankProduct.product_type_item` apunta al catálogo `bank_product_type` (`MORTGAGE`, `HOUSING_LEASING`).
- El monto está en `FinancingPreference.requested_amount_cop` (`application.financing`).
- La completitud se calcula en `services.completeness(application)`.

## Qué agregar

| # | Qué | Para qué | Nota |
| --- | --- | --- | --- |
| 1 | `product_type` (`{code, label}`) dentro de la referencia de `bank_product` | Columna "Tipo de crédito". | |
| 2 | Filtro `product_type`, con el código del catálogo `bank_product_type` | Filtro "Tipo de crédito". | Un código desconocido responde `400`, como `purpose`. |
| 3 | `requested_amount_cop` en cada fila (`null` si no hay financiación) | Columna "Monto". | |
| 4 | `completeness_pct` en cada fila | Barra "Expediente". | Ver ambigüedad A. |
| 5 | `participants_summary`, con la cantidad de co-solicitantes y de deudores solidarios activos | Texto "+ 1 co-solicitante" bajo el titular. | Con `annotate`, sin consultas por fila. |
| 6 | `status_label` en `ApplicationSerializer` | Ya está en el resumen del broker; el asesor también la necesita. | |
| 7 | Orden por `requested_amount`, nombre del banco y nombre del titular | Columnas ordenables del mockup. | Lista permitida, como hoy. |
| 8 | Pestañas rápidas: endpoint con `code`, `label`, `count` y los estados que agrupa; más un filtro `quick_filter=<code>` en el listado | "Todas 48 · Esperando al comprador 14 · …". El frontend no puede decidir qué estados forman cada pestaña. | Ver ambigüedad B. |

## Ambigüedades a resolver antes de implementar
- **A. Costo de la completitud en el listado.** Calcularla por fila puede ser caro con 100 filas. Opciones:
  1. Calcularla en el listado con `prefetch` y medir las consultas.
  2. Guardar un valor desnormalizado que se actualiza cuando cambian los datos o los documentos.
  3. Quitar la columna del listado.

  El agente mide la opción 1 con una prueba de número de consultas y recomienda.
- **B. Dónde viven las pestañas.** ¿Son un catálogo administrable (`application_quick_filter`, con sus estados) o una configuración fija en el backend? Debe respetar el alcance: los conteos solo cuentan lo que el actor puede ver.
- **C. Aviso "sin actividad del comprador".** El mockup marca con ⚠ las solicitudes que esperan al comprador hace más de 3 días. ¿Se agrega `last_buyer_activity_at` ahora o se deja para el módulo de tareas (paso 12)?

## Pruebas mínimas
- Cada campo nuevo aparece con el valor correcto, y en `null` cuando no aplica.
- Los filtros `product_type` y `quick_filter`, con valores válidos e inválidos.
- Los conteos respetan el alcance: el asesor solo ve lo asignado.
- El número de consultas del listado no crece con las filas (`django_assert_max_num_queries`).
- El broker sigue sin ver montos ni datos financieros: su resumen no cambia salvo que se acuerde.

## Precisiones acordadas
_(se completan al resolver las ambigüedades)_
