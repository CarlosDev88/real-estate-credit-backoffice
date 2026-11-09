# Tarea: configuración documental (`documents`, paso 7)

## Objetivo
Administrar desde el backend qué documentos se piden y en qué condiciones: tipos documentales (restricciones técnicas del archivo) y requisitos versionados (quién, cuándo y cuántos). Es la base de la que el paso 10 materializará los `application_document_slots` de cada solicitud.

## Cuándo se construye
Paso 7 del orden de construcción (DER §15), después de `banking` (6). Rama: `feat/documents-config`, creada desde `master`.

**Fuera de alcance:** el expediente (`file_objects`, `application_document_slots`, `document_files`, `document_reviews`, `document_package_jobs`), que es el paso 10.

## Decisiones

1. **Versionado por alcance.** Un requisito lógico se identifica por su alcance: (`bank_product`, `document_type`, `purpose_item`, `employment_profile_item`, `participant_role`, `property_condition_item`). Cada fila es una versión. No se añaden columnas al DER.
   - `POST` crea la v1 en `DRAFT`. Si el alcance ya existe, responde `409 REQUIREMENT_SCOPE_EXISTS` con el id de la última versión en `details[0].resource_id`.
   - `PATCH` sobre un `DRAFT` lo edita en el sitio (`200`). Sobre una versión `ACTIVE` o `INACTIVE` no la modifica: crea un `DRAFT` con `version + 1` sobre la mayor existente (`201`).
   - Solo puede haber un `DRAFT` por alcance. Si ya existe, `409 REQUIREMENT_DRAFT_EXISTS` con su id.
   - **El alcance no se edita.** Si cambia, es un requisito nuevo y el anterior se desactiva (dos operaciones del administrador).
   - `activate` publica la versión, y la `ACTIVE` anterior del alcance pasa a `INACTIVE` en la misma transacción. Exige tipo activo (`422 DOCUMENT_TYPE_INACTIVE`) y una vigencia no vencida (`422 REQUIREMENT_EXPIRED`).
   - `deactivate` pasa la versión `ACTIVE` a `INACTIVE`. Sobre un `DRAFT` responde `409 INVALID_STATE_TRANSITION`.
   - En PostgreSQL: como máximo un `DRAFT` y un `ACTIVE` por alcance, y una versión única por alcance, todo con `UNIQUE NULLS NOT DISTINCT`. Un campo vacío del alcance cuenta como un valor más.
2. **Lectura solo para `ADMIN` y `ADVISOR`**, igual que `/banks`. `/document-types` y `/document-requirements` usan `document_requirements.read`; broker y partner reciben `403`. Escribir y publicar es solo de `ADMIN`.
3. **`INCOME_TAX_PROOF` es un grupo alternativo, no un tipo.** Se crean dos tipos, `INCOME_RETENTION_CERTIFICATE` e `INCOME_TAX_RETURN`, cuyos requisitos comparten `alternative_group_code = 'INCOME_TAX_PROOF'` (basta uno). Ambos son exonerables (`is_waivable = true`) para cubrir el "cuando aplique". El catálogo de REQUERIMIENTOS §7.1 queda en 17 tipos.
4. **Semilla.** Los 17 tipos se crean activos, aceptan PDF, JPEG y PNG, y tienen 10 MB como máximo. Solo son repetibles `PAYROLL_SLIP`, `BANK_STATEMENT` y `PENSION_PAYMENT_SLIP`. El checklist de Bancolombia (9 requisitos sobre `BANCOLOMBIA / MORTGAGE`) queda como v1 `ACTIVE`, vigente desde el 2026-01-01 (hora de Bogotá). FNA y Banco de Bogotá quedan sin requisitos por ahora.

## Reglas de validación adicionales (decididas en la implementación)

- `allowed_mime_types` es un subconjunto no vacío y sin repetidos de la lista cerrada `apps/documents/constants.py` (`application/pdf`, `image/jpeg`, `image/png`). `max_size_bytes` va de 1 a 10 MB (REQUERIMIENTOS §9.3).
- `minimum_files > 1` exige un tipo repetible. Un tipo no puede dejar de ser repetible mientras tenga requisitos `DRAFT`/`ACTIVE` que pidan más de un archivo.
- Si un requisito tiene producto y finalidad, el producto debe admitir esa finalidad (`bank_product_purposes` activa).
- Cada código de catálogo se valida contra su catálogo: `loan_purpose`, `employment_profile` y `property_condition`.
- Desactivar un tipo no toca sus requisitos, pero estos dejan de aplicarse a casos nuevos y no se pueden publicar.
- El índice parcial del esquema se llama `ix_doc_requirements_active`, porque Django limita los nombres de índice a 30 caracteres.

## Lista documental aplicable (`POST /document-requirements/preview`)

`services.applicable_requirements` y `services.preview_checklist` son el punto de partida del paso 10.

- Entrada: `bank_product_id`, `purpose_code` y `property_condition_code` (todos opcionales), `participants: [{role, employment_profile_code}]` (de 1 a 10) y `at` (por defecto, ahora).
- Aplican las versiones `ACTIVE`, vigentes en `at`, cuyo tipo esté activo.
- Un campo vacío del requisito aplica a cualquier valor del caso. Si el caso no trae un dato, solo aplican los requisitos que lo dejan vacío. Los requisitos sin producto son generales y aplican a cualquier banco.
- Rol y perfil laboral se evalúan por participante. Todo se resuelve en una sola consulta.
- `validity_days` en la respuesta es la del requisito o, si no tiene, la sugerida por el tipo.

## Pendientes para el paso 10 (expediente)

1. **Formatos y tamaños para el comprador.** El comprador no consulta `/document-types`. Conocerá los MIME y el tamaño máximo a través de los slots de su propia solicitud, que deben exponer esas restricciones del tipo.
2. **Lista vacía no permite `READY_TO_FILE`.** Una solicitud sin requisitos documentales (hoy, cualquier producto de FNA o Banco de Bogotá) no puede pasar a `READY_TO_FILE`: la regla "todos los obligatorios aprobados" no puede cumplirse con una lista vacía. El guard de esa transición debe rechazarla explícitamente.
3. **Documentos de la solicitud y documentos del participante.** El DER no tiene el "titular posible" que menciona la API §23.4. El preview asume que todo requisito es por participante, lo que es correcto para la semilla actual. Los soportes del inmueble (`PROPERTY_*`, `REMODELING_BUDGET`, `EXTERNAL_APPROVAL_LETTER`) son de la solicitud: falta decidir cómo se distinguen al crear slots con `participant_id` nulo.
4. **Varios archivos en un slot.** `minimum_files = 3` (nómina, extractos, pagos de pensión) choca con el único `current_file_id` del slot. Falta decidir si se crean varios slots o si un slot admite varios archivos vigentes.
5. **Huella y firma física** de `IDENTITY_DOCUMENT` (REQUERIMIENTOS §7.1): no hay columna en la configuración. Corresponde al slot o al archivo.
6. **Grupo alternativo satisfecho.** El backend, no el portal, decide cuándo un grupo (`INCOME_TAX_PROOF`) está completo, y la exoneración aplica al grupo entero.
7. **Tipos sin requisito.** `CO_APPLICANT_INCOME_SUPPORT` y `EXTERNAL_APPROVAL_LETTER` existen como tipos pero no tienen requisito. El primero lo cubren hoy las reglas por perfil de cada participante. El segundo depende de la modalidad `EXTERNAL_CREDIT_APPROVED`, que no es un campo del alcance.

## Documentación pendiente de actualizar

- API §23.4: falta la subsección de versionado y publicación (como en §23.3) y la forma del `preview`.
- API §5.5: faltan los errores nuevos `REQUIREMENT_SCOPE_EXISTS`, `REQUIREMENT_DRAFT_EXISTS`, `REQUIREMENT_EXPIRED` y `DOCUMENT_TYPE_INACTIVE`.
