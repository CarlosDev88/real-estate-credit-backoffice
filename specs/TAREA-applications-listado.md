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
| 9 | Marca de "ya no cumple" en las filas `READY_TO_FILE` | Aviso en el listado cuando una solicitud lista para radicar dejó de cumplir (documento rechazado, reabierto, vencido o versión nueva). Viene de la fase 10: la solicitud sigue en `READY_TO_FILE` y `/completeness` trae `ready_to_file_problems`. | Debe salir sin consultas por fila. Ver ambigüedad A. |
| 10 | `short_name` en `banks` (opcional, editable) y en la referencia del banco | La columna "Banco" muestra "FNA" en lugar de "Fondo Nacional del Ahorro" truncado. Si viene vacío, el front usa `name`. | Cambio de modelo: migración, DER, SQL y API §23.2. |

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

### 0. Verificación inicial
- Lo de "Lo que existe hoy" coincide con el repo. Matices:
  - La marca "ya no cumple" (punto 9) sale de `ready_to_file_problems`, que cuesta lo mismo que la completitud.
  - La evaluación bancaria solo es vigente para la versión con que se hizo (`is_current`): cualquier edición de datos la vence, y la completitud recalcula las reglas en memoria.
  - El filtro `purpose` hoy **no** valida el código (un código desconocido devuelve una lista vacía, no `400`), y `origin` tampoco. Se alinean en la Parte 1: `purpose`, `origin` y `product_type` validan el código contra su catálogo (`loan_purpose`, `lead_origin` y `bank_product_type`) y responden `400` si no existe. Hay pruebas de los tres.
  - Paginación: 25 por defecto, máximo 100.

### A. Completitud y "ya no cumple": valor guardado
- Medición de la opción 1 (`completeness()` por fila, con los fixtures reales): 6 consultas y 13 ms por fila con la evaluación vigente; 10 consultas y 22 ms con la evaluación vencida. Con 25 filas, de 150 a 250 consultas; con 100, de 600 a 1000. Se descarta.
- Campos nuevos en `credit_applications`: `completeness_pct` (0 a 100), `ready_to_file_ok` (bool) y `completeness_refreshed_at`. La migración los deja nulos y el comando los llena.
- `refresh_completeness(application)` guarda lo que devuelve `completeness()`: una sola regla, nunca distinta de `/completeness`. Corre en `transaction.on_commit` después de:
  - cualquier edición de datos (todas pasan por `bump_version()`);
  - los cambios del expediente, que no suben la versión: carga, resultado del análisis, revisión, exoneración, reapertura y recálculo de slots.
- Comando `refresh_application_completeness`: recalcula las solicitudes abiertas y las que tengan el valor nulo (vencimiento de documentos por fecha, cambios de reglas o de requisitos). Corre al arrancar el backend (en el `command` del compose) y el README dice que en un entorno real se correría a diario. Un error en una solicitud se registra y el comando sigue.
- En el listado: `completeness_pct` (`null` si nunca se calculó; el front muestra "—") y `ready_to_file_blocked`: `true` si la solicitud está en `READY_TO_FILE` y `ready_to_file_ok` es falso, `false` si está en `READY_TO_FILE` y cumple, `null` en los demás estados o sin valor calculado.
- `/completeness` sigue calculando en vivo.
- Pruebas: después de cada punto de enganche (edición de datos, carga, resultado del análisis, revisión, exoneración, reapertura y recálculo de slots), el valor guardado es igual a `completeness()`. El listado hace el mismo número de consultas con 1 y con 25 filas.

### B. Pestañas: configuración fija en el backend
- Las pestañas son una configuración fija en el código, no un catálogo. Una prueba verifica que cada estado está en exactamente una pestaña (sin contar `all`), así que la suma de las pestañas es igual a "Todas".

| `code` | Etiqueta | Estados |
| --- | --- | --- |
| `all` | Todas | Todos |
| `draft` | Borradores | `DRAFT` |
| `waiting` | Esperando al comprador | `WAITING_BUYER_DATA`, `WAITING_DOCUMENTS` |
| `review` | En revisión | `DOCUMENTS_REVIEW` |
| `ready` | Listas para radicar | `READY_TO_FILE` |
| `bank` | En el banco | `FILED`, `FILING_VALIDATION`, `CREDIT_ANALYSIS`, `BANK_OBSERVATION`, `APPROVED`, `LEGALIZATION` |
| `closed` | Cerradas | `DISBURSED`, `REJECTED`, `EXTERNAL_CREDIT_APPROVED`, `OWN_FUNDS`, `WITHDRAWN`, `CANCELLED` |

- `GET /applications/quick-filters` devuelve `[{code, label, statuses, count}]` en ese orden, con los conteos en una sola consulta (`Count(filter=…)`) sobre el mismo queryset del listado: respeta el alcance (asesor: lo asignado; broker: lo que originó; administrador: todo) y acepta los mismos filtros del listado, salvo `status` y `quick_filter`, que ignora.
- `quick_filter=<code>` en el listado: `all` no filtra; un código desconocido responde `400`; junto con `status` se aplican los dos.

### C. Sin actividad del comprador: ahora
- `last_buyer_activity_at`: el `last_seen_at` más reciente de las sesiones del comprador en esa solicitud (subconsulta, sin consultas por fila); `null` si nunca entró.
- `buyer_inactive`: `true` si la solicitud está en la pestaña `waiting` y la última actividad (o, si nunca entró, `current_stage_started_at`) tiene más de `BUYER_INACTIVITY_DAYS` días (`3` por defecto, en settings); `false` si está en `waiting` y hay actividad reciente; `null` fuera de esa pestaña.
- El front arma el texto del aviso con `last_buyer_activity_at`.
- Pendiente para el paso 12: "Mi día" y la "atención pendiente" (RF-22) pueden reutilizar o reemplazar esta regla.

### D. Broker
- El resumen del broker (`ApplicationSummarySerializer`) no cambia: ni montos, ni completitud, ni `last_buyer_activity_at`, ni `buyer_inactive`. Una prueba lo verifica. El broker sí puede usar `quick_filter` y `/applications/quick-filters`, dentro de su alcance (solo conteos).

### Detalles de implementación
- `bank_product.product_type` es `{code, label}`, como las demás referencias de catálogo.
- `participants_summary` es `{co_applicants, solidary_debtors}`, con los participantes activos, calculado con subconsultas de conteo (sin consultas por fila ni filas duplicadas).
- `status_label` se agrega a `ApplicationSerializer` (y, por herencia, al detalle).
- Nombres de orden: `requested_amount`, `bank_name` y `applicant_name` (nombres y apellidos del titular), más los de hoy. Los nulos van al final en los dos sentidos.
- `banks.short_name`: opcional (`max_length=30`, puede quedar vacío), editable en `POST`/`PATCH /banks`, y en las referencias del banco (`bank_product.bank.short_name` en el listado). Se actualizan el DER, el SQL y la API §23.2.
- Cada migración se aplica al backend en marcha con `migrate` (sin reiniciar contenedores) apenas se crea: el front lo usa en `:8000`.
