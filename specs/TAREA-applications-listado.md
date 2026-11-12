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
- **No se presentan dudas.** Lo que esta spec no cubra lo decide el agente con la opción más simple, lo anota en "Precisiones acordadas" y sigue. Solo se detiene si la decisión rompe el contrato de la API ya acordado, cambia el alcance, borra o altera datos existentes, o exige tocar el `.env`.
- Cada parte se hace de corrido. Al cerrarla, el agente entrega: verificaciones en verde, la lista corta de decisiones que tomó por su cuenta y el mensaje de commit. Espera el "listo" de Carlos para la siguiente.
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

### Parte 3: decisiones de implementación
- **Orden de la migración:** primero `migrate` (tres columnas nulas, más `ck_credit_applications_completeness_pct`: nulo o ≤ 100) y después el modelo y el código. Así el backend en marcha nunca lee columnas que no existen.
- **Enganches extra**, además de los 6 del plan:
  - `save_evaluation`: una evaluación bancaria nueva cambia el ítem `bank_evaluation` sin subir la versión;
  - `create_application`: si a la solicitud no le aplica ningún requisito, `sync_slots` no cambia nada y no refresca. Sin este enganche, una solicitud nueva saldría con "—" hasta el próximo cambio o arranque.
- **Cambio de estado:** pasa por `bump_version()` (en `_apply_status_change`), así que no necesita enganche propio. Tiene su prueba.
- **Búsqueda de otros `save()`/`update()`:** los demás (reasignación de asesor, oportunidades, enlaces del comprador y ZIP de paquetes) no afectan la completitud.
- **Sin deduplicar dentro de la transacción:** Django no expone los `on_commit` pendientes sin usar internos, y el cálculo es idempotente. Una petición puede recalcular dos o tres veces la misma solicitud (unos milisegundos cada vez).
- **`refresh_completeness_safely`:** envuelve a `refresh_completeness`, registra el error con el id y devuelve `False`. La usan el `on_commit` y el comando. Una solicitud que ya no existe no es un error: no hace nada.
- **Imports locales de `schedule_completeness_refresh`** en `documents` (carga, análisis, revisión y slots) y en `bank_evaluation`: `services` importa esos módulos al cargarse.
- **Prueba existente ajustada:** `test_a_clean_scan_leaves_the_version_in_review` contaba exactamente un `on_commit` en la carga. Ahora comprueba que el análisis se encola una sola vez; los demás `on_commit` son los refrescos.

### Parte 4: decisiones de implementación
- **Forma de `/applications/quick-filters`:** un arreglo JSON plano, como `/available-actions` (la convención del proyecto para listas sin paginar), con `pagination_class = None`. Sin eso, el OpenAPI lo documentaba como `PaginatedQuickFilterList`.
- **Filtros compartidos:** `_filtered_applications` aplica el alcance y los filtros por id y por catálogo, y la búsqueda la agrega `SearchFilter` con los mismos `search_fields`. Así el listado y las pestañas no pueden divergir. El listado suma encima `status` y `quick_filter`. Los parámetros del OpenAPI también se comparten (`LIST_FILTER_PARAMETERS`).
- **Conteos:** un solo `aggregate` sobre `CreditApplication.objects.filter(pk__in=<filtradas>)`. Así no arrastra las anotaciones del listado y sigue siendo una sola consulta.
- **`quick_filter` inválido:** usa el mismo `_choice_param` que `status`, con el mensaje "Valor no permitido. Opciones: …".
- **`last_buyer_activity_at`:** es una anotación de `applications_queryset()`, así que sale también en el detalle y en la lista del cliente. Si la instancia no la trae, se consulta. Se serializa con `DateTimeField`, con el mismo formato y la misma zona horaria que las demás fechas.
- **`buyer_inactive`:** "más de 3 días" es estricto: con exactamente 3 días es `false`. Las sesiones que nunca se usaron (`last_seen_at` nulo) no cuentan como actividad.
- **`WAITING_STATUSES`** sale de la misma tabla de pestañas: si la pestaña `waiting` cambia, el aviso la sigue.

## Plan detallado de las partes que faltan
Partes 1 y 2 hechas (campos del listado, filtros y `short_name`). Faltan la 3, la 4 y el cierre. Todo lo de abajo ya está decidido: no se pregunta.

### Parte 3. Completitud guardada
**Modelo y migración**
- En `CreditApplication`: `completeness_pct` (`PositiveSmallIntegerField`, nulo, 0 a 100), `ready_to_file_ok` (`BooleanField`, nulo) y `completeness_refreshed_at` (`DateTimeField`, nulo).
- Migración solo de esquema, con los tres campos nulos. Sin migración de datos: los llena el comando.
- El agente **puede aplicar la migración y correr el comando en el contenedor sin preguntar**: solo agregan columnas y valores calculados. Usa `docker compose exec backend python manage.py migrate applications` (sin reiniciar).

**Servicio** (en `apps/applications/services.py`, junto a `completeness()`)
- `refresh_completeness(application_id)`:
  - lee la solicitud de nuevo desde la base, calcula `completeness()` y guarda con `CreditApplication.objects.filter(pk=…).update(...)`;
  - **no** usa `save()`: no sube `version`, no cambia `updated_at`, no dispara señales, eventos ni auditoría. El `ETag` de la solicitud no cambia por esto;
  - si la solicitud no existe, no hace nada.
- `schedule_completeness_refresh(application_id)`: registra `refresh_completeness` en `transaction.on_commit`.
  - Si se programa varias veces la misma solicitud en una transacción, conviene que corra una sola vez. Si deduplicar se complica, se omite y se anota: primero lo correcto.
  - Un error dentro del refresco se registra en el log con el id de la solicitud y **nunca** rompe la petición del usuario.

**Puntos de enganche** (cada uno llama a `schedule_completeness_refresh`)
1. `bump_version()`: cubre todas las ediciones de datos.
2. Carga de una versión de documento (`uploads.upload_document`).
3. Resultado del análisis (`scans._apply`).
4. Revisión: aprobar, rechazar, exonerar y reabrir (`reviews.py`).
5. Recálculo de slots (`slots.sync_slots`), cuando cambió algo.
6. Cambio de estado (`transition_application`), si no pasa ya por `bump_version()`.

El agente busca con `grep` cualquier otro `.save(` sobre `CreditApplication` o sobre slots y documentos fuera de estos puntos. Si encuentra uno que cambie la completitud, lo engancha y lo anota.

**Comando `refresh_application_completeness`** (`apps/applications/management/commands/`)
- Por defecto recalcula las solicitudes abiertas (fuera de `TERMINAL_APPLICATION_STATUSES`) y las que tengan `completeness_refreshed_at` nulo. Con `--all`, todas.
- Recorre con `.iterator(chunk_size=200)`, una solicitud a la vez. Un error se registra y se sigue.
- Al final imprime una línea: "Completitud: N recalculadas, M con error".
- **Siempre termina con código 0**, para que el backend arranque aunque falle una solicitud.
- En `backend/docker-compose.yml` va después de `createcachetable` y antes de `describe_local_services`.
- El README del backend dice que en un entorno real correría a diario (por vencimiento de documentos por fecha).

**API**
- `ApplicationSerializer` (interno): `completeness_pct` (entero o `null`) y `ready_to_file_blocked`:
  - `true` si está en `READY_TO_FILE` y `ready_to_file_ok` es falso;
  - `false` si está en `READY_TO_FILE` y cumple;
  - `null` en otro estado o sin valor calculado.

  Se calcula con los campos de la fila, sin consultas. En el OpenAPI va como booleano nulo (`extend_schema_field`).
- `ApplicationSummarySerializer` (broker): no cambia.
- `/completeness` sigue calculando en vivo.

**Pruebas**
- Después de cada uno de los 6 enganches, el valor guardado es igual a `completeness()`.
- `refresh_completeness` no cambia `version` ni `updated_at`.
- Un error en el refresco no rompe la petición: responde igual y queda en el log.
- Comando: solo abiertas y nulas por defecto, todas con `--all`; con un error en una, las demás se recalculan y el código de salida es 0.
- `ready_to_file_blocked` en sus tres valores.
- Mismo número de consultas con 1 y con 25 filas.
- El broker no ve los campos nuevos.

**Documentación:** DER, SQL, modelo de datos, API (listado) y README del backend (el comando).

**Commit:** `feat(applications): store completeness for the list and refresh it on changes`

### Parte 4. Pestañas e inactividad del comprador
**Pestañas**
- `apps/applications/quick_filters.py`: una tupla fija de `QuickFilter(code, label, statuses)`, con la tabla de la precisión B. Los estados se referencian con `ApplicationStatus`, no como texto suelto.
- Prueba: cada estado está en exactamente una pestaña (sin contar `all`), y no sobra ni falta ninguno.
- **Endpoint** `GET /api/v1/applications/quick-filters`:
  - mismo permiso que el listado (`applications.read`); el broker también puede;
  - se declara en `urls.py` antes de las rutas con `<uuid:…>`;
  - usa el mismo queryset base y los mismos filtros que el listado (alcance, `q`, banco, tipo, finalidad, asesor, etc.). Ignora `status`, `quick_filter`, `page`, `page_size` y `ordering`;
  - los conteos salen en **una sola consulta**, con `aggregate` y `Count(filter=Q(status__in=…))`, más el total de `all`;
  - la forma de la respuesta sigue la convención del proyecto para listas sin paginar. El agente mira cómo responde un endpoint parecido, usa la misma forma y la anota.
- **Filtro `quick_filter`** en el listado:
  - `all` no filtra;
  - un código desconocido responde `400` con el mismo formato de error que `purpose` (`details[].field = "quick_filter"`);
  - junto con `status`, se aplican los dos.

**Inactividad del comprador**
- `last_buyer_activity_at`: anotación con `Subquery` sobre `BuyerSession` (`application=OuterRef("pk")`), con el `last_seen_at` más reciente y los nulos al final. `null` si nunca entró.
- `buyer_inactive`: se calcula en el serializer con la anotación, el estado, `current_stage_started_at` y `timezone.now()`, sin consultas. La regla es la de la precisión C.
- `BUYER_INACTIVITY_DAYS = 3` como constante en `config/settings/base.py`, **sin variable de entorno** (así no se toca el `.env`).
- Solo en `ApplicationSerializer`; el broker no lo ve.

**Pruebas**
- Pestañas: conteos correctos; respetan el alcance (asesor: lo asignado; broker: lo que originó; administrador: todo); aplican los filtros del listado e ignoran `status`.
- El endpoint hace una sola consulta de conteo (`django_assert_num_queries`).
- `quick_filter`: válido, `all`, desconocido (`400`) y combinado con `status`.
- `buyer_inactive`:
  - `true` con actividad vieja;
  - `true` sin actividad y con la etapa vieja;
  - `false` con actividad reciente;
  - `null` fuera de `waiting`.

  Con el tiempo congelado.
- El listado sigue con el mismo número de consultas con 1 y con 25 filas.

**Documentación:** API (listado y endpoint nuevo).

**Commit:** `feat(applications): add quick filter tabs with counts and a buyer inactivity flag`

### Cierre
- Todo en verde:
  - ruff, formato y mypy;
  - `makemigrations --check`;
  - suite completa;
  - cobertura ≥ 95 %;
  - contrato regenerado con `--fail-on-warn` y commiteado;
  - backend de `:8000` sano.
- El agente entrega el **título y la descripción del PR**, en español, sin firmas de Claude. La descripción incluye:
  - qué trae cada parte;
  - los campos nuevos del listado (para el front);
  - los dos comandos/migraciones;
  - cómo probarlo.
