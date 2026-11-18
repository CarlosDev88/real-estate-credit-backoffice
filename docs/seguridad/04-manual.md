# Auditoría de seguridad — Parte 4: revisión manual

Lo que las herramientas no ven: lectura del código de cada control y una prueba por cada
punto, en `backend/tests/security/` cuando se pudo automatizar, o un comando reproducible
contra el servidor local de auditoría (`:8010`). 2026-11-18.

Esta parte abre **7 hallazgos** (SEC-14 a SEC-20): 1 Media, 3 Bajas y 3 Informativas,
ninguno Crítico ni Alto. Detalle en [`hallazgos.md`](hallazgos.md).

| Id | Título | Severidad |
| --- | --- | --- |
| SEC-14 | La recuperación de contraseña revela si el correo existe cuando falla el envío | Media |
| SEC-15 | El log de peticiones guarda la búsqueda completa (documento o nombre) | Baja |
| SEC-16 | Un `409` al crear un cliente confirma que esa cédula ya está registrada | Baja |
| SEC-17 | Textos de la configuración de bancos sin longitud máxima | Informativa |
| SEC-18 | `/admin/` de Django está publicado con la API y su login no tiene límite de intentos | Baja |
| SEC-19 | El esquema OpenAPI y la documentación interactiva son públicos | Informativa |
| SEC-20 | La documentación de la API promete 9 rutas que no existen y omite 5 que sí | Informativa |

**Pruebas nuevas de esta parte** (todas en `backend/tests/security/`): `test_auth.py`,
`test_business_rules.py`, `test_files.py`, `test_injection.py`, `test_mass_assignment.py`,
`test_exposure.py`, `test_resources.py` y `test_config_inventory.py`; 251 pruebas, 8 de ellas
`xfail(strict=True)` con su `SEC-NN`. Más el script `backend/security/race_checks.py` para
las carreras. Lo que ya cubrían las pruebas de los módulos no se repitió: se corrió y se
cita.

## Cómo se corre

```
pytest tests/security                     # toda la carpeta: 2401 pruebas, ~105 s con base nueva
python manage.py shell -c "exec(open('security/race_checks.py').read())"   # carreras, con DEBUG
```

El script de carreras escribe datos: va contra la base de auditoría (`mvp_credit_sec`), con
el servidor 8010 arriba y el volumen de documentos montado (ver `backend/security/README.md`).

---

## 1. Autenticación interna

**Revisado:** `apps/identity/tokens.py` (`issue_access_token`, `decode_access_token`),
`authentication.py` (`CookieJWTAuthentication`, `enforce_csrf`), `cookies.py`,
`services.py` (`login`, `refresh_session`, `_revoke_descendants`, `logout`,
`revoke_user_sessions`, `request_password_reset`, `confirm_password_reset`,
`change_password`), `emails.py`, `views.py`, `throttling.py`; `AUTH_PASSWORD_VALIDATORS` y
`PASSWORD_HASHERS` en `base.py`.

| Control | Cómo se probó | Resultado |
| --- | --- | --- |
| Algoritmo fijo | `jwt.decode(..., algorithms=["HS256"])`. `test_auth.py`: un token HS512 con la misma clave → 401. `tests/identity`: `alg=none`, firma alterada y otra clave → 401 | ✓ |
| `iss`, `aud`, `exp`, `nbf`, `sub`, `sid`, `jti`, `typ` obligatorios | `options={"require": ...}`. `test_auth.py`: otro emisor, otro `typ`, sin `sid`/`jti`/`exp`, `sid` o `sub` ajenos → 401; `tests/identity`: otra audiencia | ✓ |
| `leeway` de 5 s | `test_jwt_leeway_is_five_seconds`: vencido +4 s → 200; +6 s → 401 | ✓ |
| Clave propia | `AUTH_JWT_SIGNING_KEY` distinta de `SECRET_KEY`; un token firmado con `SECRET_KEY` → 401 | ✓ (la longitud de la clave local es SEC-03) |
| Sesión viva en cada petición | El JWT lleva `sid`; la autenticación lee la `AuthSession` y `can_authenticate` en cada petición | ✓ (también en la Parte 3: usuario desactivado → 401) |
| Refresh: rotación, reuso, logout | `tests/identity/test_sessions.py` (rotación, el acceso de la sesión rotada deja de servir, reusar un refresh ya rotado revoca toda la cadena sin tocar otros dispositivos, logout revoca y es idempotente) | ✓ |
| Cambio y restablecimiento revocan las otras sesiones | `tests/identity/test_passwords.py` (`change_password` conserva la actual y revoca las demás; `confirm_password_reset` revoca todas) | ✓ |
| CSRF en toda escritura autenticada | `enforce_csrf` dentro de la autenticación por cookie. `tests/identity`: sin cabecera → 403. `test_auth.py`: con **otro** token → `403 CSRF_FAILED`; con el correcto llega a la validación | ✓ |
| Enumeración en el login | Mismo código y mensaje (`401 INVALID_CREDENTIALS`) para correo existente o no, y el inexistente calcula un hash igual. 20 intentos de cada uno en el 8010 (Argon2 real): mediana **187,2 ms** frente a **185,6 ms** (+1,5 ms) | ✓ |
| Enumeración en la recuperación | Mismo `202` y mensaje. Tiempo: 42,4 ms frente a 28,2 ms (+14,2 ms, bajo los 100 ms de la spec; el correo va a la consola). Pero el correo se envía dentro de la petición y solo si el usuario existe: con el envío fallando, **500** para el que existe y **202** para el que no | **SEC-14** |
| Política de contraseñas | Los 4 validadores de Django (similitud con el usuario, mínimo 8, comunes, solo números). `test_weak_passwords_are_rejected`: corta, solo números, común y parecida al correo → 400 | ✓ (mínimo 8, el de Django y NIST; se puede subir a 12 si se quiere) |
| Argon2id | `test_production_hasher_meets_the_owasp_minimum`: `argon2$argon2id$`, memoria ≥ 19 MiB, ≥ 2 iteraciones (REQ §9.1). Las pruebas usan MD5 por velocidad (`test.py`); `tests/identity` verifica el hasher de `base.py` | ✓ |
| Token de restablecimiento | 256 bits (`secrets.token_urlsafe(32)`), solo el hash en la base, un solo uso, 30 min, el nuevo invalida al anterior (`tests/identity/test_passwords.py`). No va a ningún `logger` (revisadas las 93 llamadas). En local sí aparece en `docker logs`, porque `local.py` manda el correo a la consola: es SEC-01 | ✓ |

## 2. Enlace mágico y sesión del comprador

**Revisado:** `apps/identity/buyer_access.py` (`issue_access_link`), `buyer_sessions.py`
(`consume_access_link`, `_ensure_link_usable`, `find_active_session`,
`logout_buyer_session`), `buyer_authentication.py`, `buyer_portal_views.py`.

| Control | Resultado |
| --- | --- |
| Entropía y generación | `secrets.token_urlsafe(32)`: 256 bits. ✓ |
| Guardado hasheado | Solo `token_hash` (SHA-256) en `BuyerAccessLink`; la sesión, `session_token_hash`. ✓ |
| Un solo uso, vencimiento, revocación | `_ensure_link_usable` (consumido, revocado, vencido, solicitud terminada o titular inactivo → 401); emitir uno nuevo revoca los pendientes (`tests/applications/buyer_access`). ✓ |
| **Carrera: 10 consumos simultáneos** del mismo token | `race_checks.py`, transacciones reales: **1 OK, 9 `MAGIC_LINK_CONSUMED`, 1 sesión creada** (`select_for_update` sobre el enlace). ✓ |
| Token fuera de logs, auditoría y `Referer` | El consumo es `POST` con el token en el cuerpo y responde 200 con la cookie: no hay redirecciones. El log escribe el id del enlace y de la sesión, no el token. La auditoría (`BUYER_LINK_CONSUMED`) pasó el escáner de `tests/applications/audit` sin problemas (punto 6). ✓ |
| Duración de la sesión | `BUYER_SESSION_LIFETIME` = 24 h absoluta (cookie `Max-Age=86400`), no se renueva con la actividad. ✓ |
| Una sola sesión viva | Consumir otro enlace del mismo cliente y solicitud revoca la anterior (se vio en la auditoría: la carrera del punto 2 cerró la sesión del comprador A). ✓ |
| La sesión no sirve para otra solicitud | Parte 3: el comprador B recibe 404 en los 26 recursos del comprador A, y el A en `/buyer/applications/{id_B}`, la descarga y la notificación de B. ✓ |

## 3. Archivos

**Revisado:** `apps/documents/uploads.py`, `file_validation.py` (`inspect_upload`,
`sanitize_filename`), `scanning.py`, `storage.py` (`new_document_key`,
`attachment_disposition`, `sign_object_url`, `read_object_token`,
`FilesystemStorage._path`), `downloads.py`, `storage_views.py`; `apps/filings/evidence.py`.

| Caso de la spec | Cómo se probó | Resultado |
| --- | --- | --- |
| Tipo real por contenido | Firma de bytes (`%PDF-`, JPEG, PNG), no la extensión ni el `Content-Type`. `test_files.py` + `tests/documents` | ✓ |
| "PDF" que es HTML, SVG, ZIP, `.pdf.exe`, PNG con nombre `.pdf` | `test_malicious_uploads_are_rejected` (8 casos): `UNKNOWN_CONTENT`, `BLOCKED_EXTENSION`, `EXTENSION_MISMATCH` | ✓ |
| PDF con JavaScript; PNG con HTML al final | Pasan (la firma es válida) pero quedan con su tipo real (`test_polyglots_keep_their_real_type`); se sirven siempre adjuntos y con `nosniff` | aceptado: el JavaScript de un PDF lo cubren el antivirus (ClamAV en el modo completo) y el visor; sin hallazgo |
| Nombres con `../`, `\`, byte nulo, unicode de control (RTL), 300 caracteres | `test_client_names_lose_paths_and_control_characters` y `test_a_300_character_name_is_cut_to_255_and_keeps_the_extension` | ✓ |
| ¿El nombre llega a la clave de almacenamiento? | No: `documents/<solicitud>/<uuid>` (`test_storage_key_is_built_from_ids_only`). Solo va al `Content-Disposition`, con nombre ASCII escapado y `filename*` UTF-8 (RFC 6266; `tests/documents`) | ✓ |
| 10 MB y 10 MB + 1 byte | `test_ten_megabytes_pass_and_one_more_byte_does_not`: exacto pasa, uno más → `FILE_TOO_LARGE`; el tamaño se cuenta leyendo, no por la cabecera | ✓ |
| `Content-Length` que miente (8010, socket crudo) | declara 1000 y manda 11 MB → `400 VALIDATION_ERROR` (se lee solo lo declarado); declara 20 MB → `413 PAYLOAD_TOO_LARGE` antes de leer; 10,5 MB + 1 → `413` | ✓ |
| `PENDING` o `INFECTED` nunca se firman | `test_unclean_files_are_never_signed`: `PENDING`, `INFECTED` e `INVALID` → `409 FILE_NOT_CLEAN` sin `url`, para el asesor y para el comprador | ✓ |
| URL firmadas: 5 min, ligadas a su clave, fuera de los logs | `test_signed_url_lasts_five_minutes_and_is_bound_to_its_key` (300 s; alterada o a los 301 s → inválida); el log de `runserver` las escribe como `/storage/objects/***` (visto en `docker logs` y en `tests/documents`) | ✓ |
| ¿Se lee un archivo del disco por ruta directa? | 8010: `/data/documents/`, `/documents/`, `/media/` → 404; `/api/v1/storage/objects/documents` (sin firma) → 403; `..%2F..%2Fetc%2Fpasswd` → 404. `/static/../data/documents/` → 500 del servidor de estáticos de `runserver`, que bloquea la ruta (`SuspiciousFileOperation`): nota en SEC-06 | ✓ |

## 4. Inyección

| Punto | Cómo se revisó | Resultado |
| --- | --- | --- |
| SQL | `grep` de `raw(`, `RawSQL`, `.extra(`, `cursor().execute`, `Func`/`Value` con texto del usuario en `apps` y `config`: solo `SELECT nextval(%s)` con un parámetro constante (`applications/models/application.py:47`) y el `cursor()` de `/ready` | ✓ |
| Filtros con `**request.query_params` | Ninguno | ✓ |
| `?ordering=` | Todas las vistas usan `StrictOrderingFilter` (lista cerrada). `test_ordering_only_accepts_declared_fields`: en los **18** listados que lo aceptan, `password`, `-password`, `assigned_advisor__password`, `created_by__password`, `user__password`, `client__document_number`, `token_hash` e `id,password` → 400 | ✓ |
| CSV | `apps/reporting/exports.py` (`neutralize_formula`). `test_report_csv_neutralizes_formulas`: un cliente con `=HYPERLINK(...)` y `+SUM(...)` sale neutralizado; ninguna celda empieza por `=`, `+`, `-`, `@`, tabulador o retorno. No hay otras exportaciones a CSV (el paquete documental es un ZIP de archivos) | ✓ |
| Plantillas de correo | `notifications/email.html` y `.txt` con plantillas de Django (autoescape). `test_notification_email_escapes_client_data`: `<script>` e `<img onerror>` salen escapados. Los correos de identidad son de texto plano | ✓ |
| `X-Request-ID` | `config/middleware.py` solo acepta `^[A-Za-z0-9._-]{8,64}$`; si no, genera un UUID. `test_request_id_from_the_client_is_validated` (CRLF, LF, 65 caracteres, corto, ruta, HTML) | ✓ |

## 5. Asignación masiva

**Revisado:** `config/serializers.py` (`StrictSerializer`: rechaza cualquier campo no
declarado con `400 UNKNOWN_FIELD`).

`test_mass_assignment.py`: a **las 95 escrituras** del contrato con cuerpo se les mandaron
`status`, `version`, `assigned_advisor(_id)`, `is_active`, `is_superuser`, `is_staff`,
`roles`, `role_codes`, `permissions`, `client_id`, `application_id`, `approved_amount_cop`,
`disbursed_amount_cop`, `requested_amount_cop`, `public_status`, `review_status`,
`scan_status`, `paid_at`, `created_by`, `deleted_at` y `password` (solo los que su esquema
**no** declara), como el actor que puede usar la operación. **Las 95 responden
`400 UNKNOWN_FIELD` nombrando todos los campos extra**; ninguna los ignora ni los aplica.
✓ Los campos que sí declara cada escritura los cubren la matriz (quién) y las pruebas de
cada módulo (qué valores).

## 6. Exposición de datos

| Punto | Cómo se revisó | Resultado |
| --- | --- | --- |
| Respuestas al broker y al comprador | Parte 3: `FORBIDDEN_FIELDS_BY_ACTOR` en todas sus respuestas permitidas, documento enmascarado, resumen del broker | ✓ |
| `logger.` con datos personales o secretos | Las 93 llamadas de `apps` y `config`: solo ids, códigos y tipos de excepción | ✓ |
| Logs reales de los flujos sensibles | En el 8010: login fallido, recuperación, consumo con token inválido, búsquedas, creación de un cliente, descarga firmada. `docker logs`: sin contraseñas, JWT, tokens del enlace ni URL firmadas; el correo de recuperación sale entero por la consola (local, SEC-01); **la URL de las búsquedas trae el documento y el nombre** | **SEC-15** |
| Mensajes de error con datos de otros | El duplicado de cliente solo trae `resource_id` si el usuario ve ese cliente (`test_duplicate_document_never_reveals_the_other_client`), pero el `409` mismo confirma que la cédula existe | **SEC-16** |
| Auditoría | El escáner de `tests/applications/audit` (`problems`) sobre los **390 eventos** de la base de auditoría (14 acciones, incluidas las de la Parte 2 y las carreras): **0 con datos prohibidos** | ✓ |

## 7. Lógica de negocio

| Caso | Cómo se probó | Resultado |
| --- | --- | --- |
| Saltar estados (`DRAFT` → `APPROVED`, `FILED`, `DISBURSED`, `READY_TO_FILE`) | `test_status_cannot_jump_from_draft` | `409 INVALID_STATE_TRANSITION`, el estado no cambia ✓ |
| Editar el expediente después de radicar, con `If-Match` vigente y viejo | `test_filed_application_cannot_be_edited` (propósito, financiación e inmueble, con cuerpos completos tomados del `GET`) | 409, nada cambia ✓ |
| El comprador cambia banco, producto o financiación después de radicar | `test_buyer_cannot_change_bank_or_financing_after_filing` | 409 ✓ |
| Doble radicación **sin** `Idempotency-Key`, 10 en paralelo | `race_checks.py` (HTTP contra el 8010) | **1 × 201, 9 × 409; 1 radicación creada** ✓ |
| Liquidar dos veces | `test_settlement_is_not_duplicated` | 200 con la misma liquidación (API §23.6: idempotente); una sola `ACTIVE` ✓ |
| Pagar dos veces la misma parte | `test_share_cannot_be_paid_twice...` (secuencial) y `race_checks.py` (10 en paralelo) | 200 y 409; en paralelo **1 × 200, 9 × 409** ✓ |
| Anular con partes pagadas | mismo test | `409 COMMISSION_SETTLEMENT_HAS_PAYMENTS` ✓ |
| Dos `PATCH` simultáneos con la misma versión | `race_checks.py` y `test_stale_if_match_is_rejected_on_a_draft` | en paralelo **1 × 200, 1 × 409**, la versión sube una vez ✓ |

## 8. Consumo de recursos

| Punto | Cómo se probó | Resultado |
| --- | --- | --- |
| `page_size` | `test_page_size_is_capped`: `page_size=100000` en los **53** listados paginados → nunca más de 100 | ✓ |
| Búsqueda con comodines largos | 8010: `search` de 30 000 caracteres → 0,08 s; `%_` × 5000 → 0,10 s (el ORM escapa los comodines) | ✓ (no tiene tope de largo, pero con el tope de la URL no pesa) |
| Rango de reportes | `test_report_range_is_capped`: 2000-01-01 a hoy en los 7 reportes y paneles → `400` ("no puede superar 366 días") | ✓ |
| Exportaciones simultáneas | `tests/reporting/test_export_jobs.py::test_a_fourth_active_export_is_rejected` (`TOO_MANY_EXPORTS` con 3 activas) | ✓ |
| Textos libres de 1 MB | `test_free_text_fields_have_a_maximum_length`: nota, tarea, cambio de estado, respuesta del banco (interna y pública), revisión, cliente (asesor y broker) y desistimiento del comprador → `400 MAX_LENGTH`. La configuración de bancos acepta 1 MB | ✓ / **SEC-17** |
| Sin límite general por usuario | Parte 2 | SEC-10 |

## 9. Secretos y configuración

| Punto | Resultado |
| --- | --- |
| `SECRET_KEY` y `AUTH_JWT_SIGNING_KEY` sin valor por defecto | Sin cada una, `django.setup()` falla: `ImproperlyConfigured: Set the DJANGO_SECRET_KEY environment variable` (y lo mismo con la JWT). ✓ |
| `DEBUG` por defecto | Falso en `base.py`, pero los puntos de entrada cargan `local` → SEC-01 |
| `ALLOWED_HOSTS` | Sin comodín por defecto; ZAP probó `Host` de metadatos de nube y todos dieron `DisallowedHost` (Parte 2). ✓ |
| `/admin/` | Publicado en el mismo host, 42 modelos, **sin límite de intentos**; hoy 0 usuarios `is_staff` → **SEC-18** |
| `/openapi.json` y `/docs` | Públicos también sin `DEBUG` → **SEC-19** (Informativa, como pide la spec) |
| `health` / `ready` | `{"status": "ok"}` y `{"status": "ready"}`; sin versión, host ni datos de la base (`test_health_and_ready_expose_nothing_internal`). ✓ |

## 10. Inventario

| Comparación | Resultado |
| --- | --- |
| Código (`config/urls.py`) frente al contrato | Iguales (`test_every_api_route_is_in_the_contract_and_back`). Fuera del contrato a propósito: `/api/v1/storage/objects/{token}` (descarga local firmada), `/health`, `/ready`, `/openapi.json`, `/docs`, y las 263 rutas de `/admin/` (SEC-18). ✓ |
| Versiones viejas o rutas de depuración | Solo `/api/v1`; ninguna ruta de depuración aparte del admin y la documentación. ✓ |
| Documentación (`docs/API_REST_MVP_CREDITO.md`) frente al contrato | 9 rutas documentadas que no existen y 5 rutas de direcciones del cliente sin documentar → **SEC-20** |

---

## Versiones y entorno

Imagen del backend (Python 3.11.18, Django 5.2.19, DRF 3.17.2, PyJWT 2.15.1) para todo;
servidor de auditoría `mvp-sec-api` (8010, `DEBUG=True`) reconstruido en esta parte con un
volumen propio de documentos (`mvp_sec_documents`), porque el de la Parte 2 había perdido
los archivos de la demo al recrearse.
