# TAREA — Módulo 15: dashboard y reportes (`apps.reporting`)

Agente: **backend-b**. Rama `feat/reports` (worktree `wt-back-reports`, desde `origin/master` con el #23).
Fuentes: REQUERIMIENTOS §5.8 (RF-70 a RF-72), §8.7, §9.3 y RNF-08; API §22 y §27.4; MODELO_DATOS §10.7 (`report_export_jobs`).
Todas las decisiones están tomadas. Si algo no cuadra con el código, **no inventes**: anótalo en el reporte como duda y sigue con lo demás.

## Reglas de siempre
- Git en **solo lectura** (nada de commit, add, mv, restore, push). Carlos hace los commits.
- No leas ni edites `.env*`. Si necesitas un setting nuevo, va en `config/settings/base.py` con valor por defecto.
- Pruebas **acotadas** en local (solo `tests/reporting/` y lo que toques); la suite completa la corre el CI.
- Siempre `ruff`, `mypy .` (incluye `tests/`) y `spectacular --validate --fail-on-warn` → `contracts/openapi.json`.
- Base de pruebas propia: `-e DATABASE_NAME=mvp_credit_b` en tu `docker run`.
- Al terminar cada parte: reporte en `.buzon/reportes/AAAA-MM-DD_parte-N.md`, actualiza `ESTADO.md` y dile a Carlos "Parte N lista, reporte en .buzon/…". Espera "listo, lee tu buzón".

## Alcance cerrado (decisión de Carlos: alcance "medio")
**Entra:** 4 endpoints de dashboard, `GET /reports/funnel`, `GET /reports/applications`, `GET /reports/applications.csv` y la exportación asíncrona **solo CSV** (`report_export_jobs`).
**No entra:** XLSX, `/reports/advisors`, `/reports/banks`, `/reports/document-quality` (el dashboard ya cubre carga y bancos). Documenta en `apps/reporting/__init__.py` que quedan fuera por decisión del MVP.

## Decisiones de negocio (cerradas)
1. **Roles y alcance** (REQ §3 manda sobre API §27.4):
   - `ADMIN`: todo; lee y exporta.
   - `ADVISOR`: solo las solicitudes que tiene asignadas (el mismo `_scope_filter` de applications); lee y exporta.
   - `INDEPENDENT_BROKER`: solo **conteos** de las solicitudes de las oportunidades que originó. Nunca montos, nunca datos personales, nunca exportación ni el listado de `/reports/applications`.
   - `CONSTRUCTION_PARTNER` y comprador: nada (403).
   - **Reutiliza** `get_application_scope` / `_scope_filter` de `apps.applications.services` (sácalo a una función pública si hace falta, sin cambiar su comportamiento). No dupliques la lógica de alcance.
2. **Permisos nuevos** (migración de datos, mismo patrón que `apps/tasks/migrations/0003_seed_task_permissions.py`, módulo `reporting`):
   - `dashboard.read` → ADMIN, ADVISOR, INDEPENDENT_BROKER.
   - `reports.read` → ADMIN, ADVISOR.
   - `reports.export` → ADMIN, ADVISOR.
   - `reports.manage` → ADMIN (ver cualquier exportación).
3. **Rango de fechas:** el usuario **escoge** `date_from` y `date_to` (fechas `YYYY-MM-DD`, ambas incluidas, hora de Colombia `America/Bogota`). Si no manda ninguna, por defecto **el mes en curso** (día 1 a hoy). Si manda solo una, la otra se completa (`date_to` = hoy; `date_from` = día 1 del mes de `date_to`). Errores 400 `VALIDATION_ERROR`: `date_from > date_to`, rango > **366 días**, `date_to` en el futuro se recorta a hoy (no es error). La respuesta siempre devuelve el rango efectivo en `period: {date_from, date_to}`.
4. **Filtros comunes:** `date_from`, `date_to`, `advisor_id`, `partner_id`, `project_id`, `bank_id`, `purpose_code`, y en reportes además `status` (multivalor, `status=FILED&status=APPROVED`).
   - Un filtro **fuera del alcance** responde **403 `FILTER_OUT_OF_SCOPE`** (API §22), nunca resultados vacíos: el asesor que manda `advisor_id` de otro asesor, el broker que manda `advisor_id`, `partner_id` o `project_id`. Un id que no existe responde 400 `VALIDATION_ERROR`. El admin puede filtrar por todo.
   - Valores de `status` y `purpose_code` que no existen → 400.
5. **Embudo (cohorte + foto):**
   - Etapas del embudo (RF-70), en este orden: `CREATED` (solicitudes creadas en el periodo), `DOCUMENTS_COMPLETE` (ver nota), `READY_TO_FILE`, `FILED`, `APPROVED`, `DISBURSED`.
     - Nota: "documentos completos" = llegó alguna vez a `DOCUMENTS_REVIEW` **con todos los obligatorios aprobados o dispensados** no es reconstruible del historial; decisión: `DOCUMENTS_COMPLETE` = llegó alguna vez a `DOCUMENTS_REVIEW`. Documéntalo en el docstring.
     - RF-70 menciona "clientes": el resumen trae aparte `clients_created` (clientes creados en el periodo, dentro del alcance; para el asesor, clientes de sus solicitudes u oportunidades asignadas; reutiliza el alcance de CRM).
   - **Cohorte:** de las solicitudes **creadas** en el periodo (y dentro del alcance y filtros), cuántas **llegaron alguna vez** a cada etapa según `ApplicationStatusHistory.to_status` (una solicitud cuenta una vez por etapa aunque pase varias veces). Una solicitud que llegó a `DISBURSED` cuenta también en las anteriores aunque el historial se las salte (orden del embudo = orden de la lista; si llegó a una etapa posterior, cuenta en las previas).
   - **Conversión:** `count / created` con 4 decimales (`"0.4500"`, string decimal; `null` si `created = 0`). Además `step_conversion` = contra la etapa anterior (`null` si la anterior es 0).
   - **Foto:** cuántas solicitudes dentro del alcance y filtros (sin filtro de fecha) están **hoy** en cada `ApplicationStatus`, con `status_label`. Va en `/dashboard/summary`.
   - Todo con agregaciones en base de datos (`Count`, `Exists`/subconsultas), **sin consultas por fila**. Prueba con `django_assert_max_num_queries`.

## Parte 1 — App, permisos, filtros y dashboard
1. App `apps.reporting` (en `INSTALLED_APPS`), sin modelos todavía.
2. Migración de permisos (decisión 2).
3. `filters.py`: un `ReportFilters` (dataclass) + serializer de entrada que valida fechas (decisión 3), ids y alcance (decisión 4). Una función `scoped_applications(user, filters) -> QuerySet` que aplica alcance + filtros (`bank_id` por `bank_product.bank`, `partner_id`/`project_id` por el proyecto de la oportunidad o del inmueble — revisa dónde vive el proyecto y documenta la ruta que usaste, `purpose_code` por `purpose_item.code`).
4. Endpoints (`dashboard.read`):
   - `GET /dashboard/summary`: `period`, `clients_created`, `applications_created`, `snapshot` (lista `{status, status_label, count}` con todos los estados, incluso en 0), `tasks: {overdue, due_today}` (RF-71: tareas `PENDING`/abiertas del alcance — admin todas, asesor las suyas asignadas, broker 0 y no se calcula; reutiliza lo que ya calcula Mi día si existe una función), y para ADMIN/ADVISOR `amounts: {requested_total, approved_total, disbursed_total}` en COP como string decimal (de dónde salen los montos: revisa financiación y la respuesta de desembolso con monto del módulo 11; si un monto no existe en el modelo, déjalo fuera y anótalo). El broker **no** recibe `amounts` (campo ausente, no `null`).
   - `GET /dashboard/funnel`: `period`, `stages: [{code, label, count, conversion, step_conversion}]` (decisión 5).
   - `GET /dashboard/workload` (solo ADMIN/ADVISOR; broker → 403 `PERMISSION_DENIED`): por asesor `{advisor_id, advisor_name, open_applications, overdue_tasks, due_today_tasks, waiting_buyer, ready_to_file}`. El asesor solo ve su propia fila.
   - `GET /dashboard/bank-results` (solo ADMIN/ADVISOR): por banco, en el periodo (por `Filing.filed_at`): `{bank_id, bank_name, filings, returned, approved, rejected, disbursed, avg_days_to_response}` (de `FilingStatus`/respuestas; `avg_days_to_response` = promedio de días entre `filed_at` y la primera respuesta, 1 decimal, `null` si no hay).
5. OpenAPI completo (parámetros, 400/403, ejemplos) y etiquetas en español (`ChoiceLabelField`).
6. Pruebas: alcance por rol (admin/asesor/broker/constructora), cada 403 de filtro, rango por defecto, rango > 366, cohorte con saltos de etapa, conversión con 0, broker sin `amounts`, número de consultas acotado.

## Parte 2 — Reportes y CSV directo
1. `GET /reports/funnel` (`reports.read`): igual que `/dashboard/funnel` + filtro `status` + desglose opcional `group_by=advisor|bank|purpose` (cada grupo con sus `stages`). Comparte el servicio, no copies código.
2. `GET /reports/applications` (`reports.read`): paginado con el paginador del proyecto, orden `-created_at`. Columnas: `code`, `created_at`, `status` + `status_label`, `purpose` (label), `advisor_name`, `client_name`, `client_document_masked`, `bank_name`, `project_name`, `requested_amount`, `last_status_change_at`, `filings_count`. Filtra por fecha de **creación**.
3. **Enmascaramiento** (RNF-08, API §22): el documento sale como `******1234` (solo los últimos 4). Nunca correo, teléfono, dirección, datos financieros del comprador ni archivos. `requested_amount` sí (es dato operativo).
4. `GET /reports/applications.csv` (`reports.export`): mismas columnas y filtros, CSV UTF-8 **con BOM** (para que Excel abra bien las tildes), separador `,`, encabezados en español, `Content-Disposition: attachment; filename="solicitudes_<date_from>_<date_to>.csv"`, streaming (`StreamingHttpResponse`). Límite `REPORTS_CSV_MAX_ROWS = 5000`: si el resultado supera el límite → 422 `EXPORT_TOO_LARGE` con mensaje que invita a usar la exportación asíncrona.
   - **Inyección CSV:** cualquier celda que empiece con `=`, `+`, `-`, `@`, tab o CR se prefija con `'`. Prueba explícita.
5. Señal `report_exported` (en `apps/reporting/signals.py`) con `user`, `report_type`, `filters` (los ya validados), `row_count`, `format`. Se emite en el CSV directo y al completar un job. **No** llames a `apps.audit` (está en otro PR); el enganche con auditoría se hace después del merge del #24.
6. Límite de uso: un throttle `reports` de **20/min por usuario** para estos endpoints y los del dashboard (REQ §9.3: "límite inferior para endpoints costosos"). Que se pueda aflojar con un setting (no lo toques en `.env`).
7. Pruebas: columnas y máscara, CSV con BOM y fórmula neutralizada, 422 sobre el límite (bájalo con `override_settings`), broker 403, señal emitida una vez.

## Parte 3 — Exportación asíncrona (solo CSV)
1. Modelo `ReportExportJob` = tabla `report_export_jobs` de MODELO §10.7 (mismos campos e índices; `report_type` solo `applications`; `status`: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `EXPIRED`, con `status_label`). `filters` guarda los filtros **ya validados** (con el rango efectivo), nunca la query cruda.
2. `POST /reports/applications/export-jobs` (`reports.export`, con `@idempotent` del #23): crea el job y lo encola (Celery, eager en local); responde 202 con el job. Máximo **3 jobs `PENDING`/`RUNNING` por usuario** → 429 `TOO_MANY_EXPORTS`.
3. Tarea Celery: recalcula con el alcance **del solicitante al momento de ejecutar** (si perdió el permiso, `FAILED` con `error_code=PERMISSION_REVOKED`), escribe el CSV (mismo formato y saneamiento de la Parte 2, sin el límite de 5000; tope duro `REPORTS_EXPORT_MAX_ROWS = 100000` → `FAILED`/`EXPORT_TOO_LARGE`), lo sube con `get_storage().put` como `FileObject` limpio (revisa cómo el módulo de documentos crea un `FileObject` del paquete ZIP y haz lo mismo), guarda `row_count`, `completed_at` y `expires_at = completed_at + REPORTS_EXPORT_TTL_HOURS (24)`. Emite `report_exported`. Reintentos como el paquete de documentos.
4. `GET /reports/applications/export-jobs`: lista paginada de los jobs **propios** (admin con `reports.manage` puede pasar `?all=true`).
5. `GET /report-export-jobs/{job_id}`: propietario o `reports.manage`; si no, **404** (no confirmar que existe).
6. `GET /report-export-jobs/{job_id}/download`: igual que la descarga de documentos (`file_object_link`, URL firmada de 5 min, nunca en logs). Solo `COMPLETED` y no vencido; si no → 409 `EXPORT_NOT_READY` o 410 `EXPORT_EXPIRED`.
7. Comando `purge_report_exports`: marca `EXPIRED` los vencidos y borra el objeto del almacenamiento (el registro queda). Documenta que se agenda con Celery beat en producción (no lo agendes).
8. Pruebas: ciclo completo en eager, alcance recalculado, 3 jobs → 429, 404 a otro usuario, 409/410, purge, idempotencia (misma key → mismo job).

## Cierre
- Contrato regenerado y validado. `seed_demo_data` no cambia (el dashboard se alimenta de los datos que ya existen).
- Reporte final con: endpoints, decisiones que tuviste que interpretar (ruta del proyecto, montos), dudas y la lista de archivos tocados.
- Carlos trae `master` si avanzó (tú resuelves conflictos si los hay).
