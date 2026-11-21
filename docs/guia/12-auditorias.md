# 12 · Auditorías: qué se encontró y cómo se solucionó

> **En simple:** además de las pruebas y el CI, el proyecto pasa por **tres auditorías independientes**: de seguridad, de rendimiento del frontend y de carga y estrés del backend. Cada una revisa con un método propio, deja su informe completo y una lista de hallazgos. Este documento junta las tres en lenguaje simple y, para cada hallazgo, cuenta **qué pasaba, por qué, qué se cambió, cómo se comprobó y en qué PR se cerró**.

> **Estado al 19 de noviembre de 2026.** La auditoría de **seguridad** está cerrada: la fase A (encontrar y documentar) entró con el #32 y la fase B (corregir y volver a probar) con el #37. Quedaron 21 hallazgos, 20 corregidos y 1 aceptado. Las auditorías de **rendimiento del frontend** y de **carga del backend** siguen en preparación.

---

## Índice

1. [Resumen](#1-resumen)
2. [Seguridad](#2-seguridad)
3. [Rendimiento del frontend](#3-rendimiento-del-frontend)
4. [Carga y estrés del backend](#4-carga-y-estrés-del-backend)
5. [Lo que aprendimos](#5-lo-que-aprendimos)
6. [Cómo leer las tablas](#6-cómo-leer-las-tablas)

---

## 1. Resumen

| Auditoría | Qué revisa | Informe | Hallazgos | Estado |
| --- | --- | --- | --- | --- |
| Seguridad | La API completa (autenticación, autorización por rol y por objeto, archivos, datos personales, configuración), el código, las dependencias, el historial de git y los contenedores | [`docs/SEGURIDAD.md`](../SEGURIDAD.md) y [`docs/seguridad/`](../seguridad/hallazgos.md) | **21**: 0 críticos, 0 altos, 5 medios, 10 bajos, 6 informativos | ✅ Fase A (#32) y fase B (#37): 20 corregidos y 1 aceptado |
| Rendimiento del frontend | Peso de las páginas, tiempos de carga y de interacción | [`docs/PERFORMANCE.md`](../PERFORMANCE.md) y [`docs/performance/`](../performance/) | 13: 4 altos, 5 medios, 1 bajo, 3 informativos | ✅ #39: 7 corregidos, 4 aceptados y 2 que dependen del backend |
| Carga y estrés del backend | Latencia bajo carga (el p95 < 800 ms de RNF-17), errores y límites | `docs/PERFORMANCE.md` *(en curso)* | Pendiente | 🔄 En preparación |

Los informes de rendimiento y carga se enlazarán aquí cuando se fusionen sus ramas.

---

## 2. Seguridad

Informe completo: [`docs/SEGURIDAD.md`](../SEGURIDAD.md) (resumen, método, modelo de amenazas, matriz de acceso, cada hallazgo con su ficha y el re-test). Fichas largas: [`docs/seguridad/hallazgos.md`](../seguridad/hallazgos.md). Cómo repetir la auditoría en local: [`backend/security/README.md`](../../backend/security/README.md).

### 2.1 Qué se revisó y con qué método

**Fase A (#32), encontrar y documentar.** En cuatro partes, todo en local, sobre datos de demo y con una base de datos de usar y tirar ([`docs/SEGURIDAD.md`](../SEGURIDAD.md) §2):

| Parte | Qué | Con qué | Detalle |
| --- | --- | --- | --- |
| 1 · Automático | Configuración de Django, código, dependencias, secretos en todo el historial y contenedores | `manage.py check --deploy`, bandit, semgrep, pip-audit, pnpm audit, gitleaks, hadolint | [`01-automatico.md`](../seguridad/01-automatico.md) |
| 2 · Dinámico | Ataques simulados contra una copia local de la API: fuzzing con 4 sesiones, escaneo pasivo y activo, cabeceras, CORS, cookies, límites y errores | schemathesis (~42.000 casos), OWASP ZAP (~72.000 peticiones), curl | [`02-dinamico.md`](../seguridad/02-dinamico.md) |
| 3 · Matriz de acceso | Cada una de las 235 operaciones de entonces pedida como cada uno de 9 actores: sin sesión, admin, la asesora dueña, otro asesor, el broker que originó, otro broker, la constructora, el comprador dueño y otro comprador | pytest (`backend/tests/security/`) | [`03-matriz-acceso.md`](../seguridad/03-matriz-acceso.md) |
| 4 · Manual | Revisión del código de 10 áreas sensibles, incluidas carreras (diez peticiones a la vez) | lectura de código, pytest, `backend/security/race_checks.py` | [`04-manual.md`](../seguridad/04-manual.md) |

**Lo más importante es lo que no apareció** (SEGURIDAD §1): la matriz dio **2.115 casos, todos con el resultado esperado, sin ninguna brecha de acceso**; nadie puede ver ni tocar expedientes, documentos, clientes o comisiones que no le corresponden; sin sesión no se llega a ningún dato; no hay inyecciones; los archivos se validan por su contenido real; y los enlaces del comprador, las radicaciones y los pagos no se duplican aunque lleguen diez peticiones a la vez.

**Criterio con que se decidió cada hallazgo** (SEGURIDAD §6): los críticos y altos se corrigen todos; los medios, si el esfuerzo es pequeño (si no, se aceptan con su motivo); los bajos e informativos se documentan y se corrigen si son de una línea. No hubo críticos ni altos, y los cinco medios se corrigieron.

**Fase B (#37), corregir y volver a probar.** Cada corrección trae su prueba en `backend/tests/security/` (tres archivos nuevos, `test_deployment.py`, `test_http_responses.py` y `test_rate_limits.py`, y casos agregados a los existentes). Después, el re-test repitió cada reproducción de la fase A con su "antes" y su "después" y volvió a pasar las mismas herramientas con las mismas versiones (SEGURIDAD §9):

| Herramienta | Fase A | Fase B (re-test) |
| --- | --- | --- |
| schemathesis, como admin | 3.866 casos; 6 respuestas 5xx (`OPTIONS`), 66 errores sin documentar | 9.101 casos; **0 respuestas 5xx**, 0 errores sin documentar |
| OWASP ZAP activo | ~72.000 peticiones, ningún 5xx, ninguna alerta alta | 61.717 peticiones, **ningún 5xx**; la única alerta alta (inyección SQL) se comprobó a mano y es un falso positivo |
| gitleaks (todo el historial) | 7 resultados, todos descartados | **0** |
| `pytest tests/security` | ~2.400 pruebas, 8 `xfail` (las brechas abiertas) | **2.493 pruebas, 0 `xfail`**; matriz de **2.124 casos** sin brechas (9 más por la operación que sumó el #36) |
| `check --deploy` con la configuración de producción | 4 avisos | Solo `W021` (el *preload* de HSTS, que se decide al tener dominio) |

**Lo que quedó en el CI** para que no vuelva a pasar: la matriz corre en cada PR y exige una fila para cada operación nueva del contrato (ya pasó una vez: el #36 sumó `GET /bank-policy-rules/fields` con su fila, y hoy son 236 operaciones y 2.124 casos, en [`docs/seguridad/03-matriz-acceso.md`](../seguridad/03-matriz-acceso.md)); cada vista nueva hereda los límites generales de SEC-10 (una prueba lo exige); el contrato documenta solo sus errores (el *hook* de SEC-13); y `pip-audit`, `gitleaks` y `bandit` corren en cada PR ([09 · Calidad §3](09-calidad.md#3-el-ci-dos-revisiones-obligatorias)).

### 2.2 Hallazgos por severidad

Escala de la auditoría: **Crítica** (acceso sin sesión a datos personales, tomar la cuenta de otro, ejecución de código), **Alta** (ver o cambiar datos de otro alcance, saltar la autenticación del comprador, un secreto real filtrado), **Media** (campos de más dentro del propio alcance, límites que se saltan, enumeración de usuarios, una cabecera que importa), **Baja** (endurecimiento) e **Informativa** (buena práctica o aplica solo al desplegar).

| Severidad | Cuántos | Corregidos | Aceptados |
| --- | ---: | ---: | ---: |
| Crítica | 0 | — | — |
| Alta | 0 | — | — |
| Media | 5 | 5 | 0 |
| Baja | 10 | 9 | 1 |
| Informativa | 6 | 6 | 0 |
| **Total** | **21** (SEC-01 a SEC-21) | **20** | **1** |

La fase A encontró 20; **SEC-21** (informativo) apareció en el re-test de la fase B y se corrigió en el mismo PR. Los tres más importantes de la fase A, los tres corregidos: **SEC-09** (se podía probar una contraseña contra todas las cuentas desde un solo equipo, o una cuenta desde muchos), **SEC-04** (dos vulnerabilidades públicas de la librería de la API que permitían dejar sin respuesta al servidor sin cuenta) y **SEC-08** (datos personales que el navegador podía guardar en disco).

### 2.3 Hallazgos y cómo se solucionó cada uno

Cada id lleva a su ficha en [`docs/seguridad/hallazgos.md`](../seguridad/hallazgos.md): dónde, cómo reproducirlo, impacto y la corrección. El "antes" y el "después" medidos de cada uno están en SEGURIDAD §9.1. Las pruebas citadas están en `backend/tests/security/`.

| Id | Problema | Severidad | Causa | Solución aplicada | Cómo se verificó | PR |
| --- | --- | --- | --- | --- | --- | --- |
| [SEC-01](../seguridad/hallazgos.md#sec-01--no-hay-configuración-de-producción-y-los-puntos-de-entrada-cargan-local-que-fuerza-debugtrue) | No había configuración de producción | Baja (Alta si se desplegara así) | Los puntos de entrada cargaban `local`, que fuerza `DEBUG=True` | `backend/config/settings/production.py` (`DEBUG` fijo en `False`); `wsgi`, `asgi` y Celery la usan por defecto | `test_deployment.py`; `check --deploy` solo con `W021` | #37 |
| [SEC-02](../seguridad/hallazgos.md#sec-02--la-configuración-base-no-endurece-https) | HTTPS sin endurecer | Baja | Nada fijaba HSTS, la redirección ni las cookies `Secure` | Lo fija `production.py` (HSTS de una hora para empezar, redirección y cookies solo por HTTPS) | `test_deployment.py`; la imagen `production` redirige con `301` y manda HSTS | #37 |
| [SEC-03](../seguridad/hallazgos.md#sec-03--las-claves-no-se-validan-al-arrancar-la-clave-jwt-local-tiene-31-bytes) | Claves sin validar | Baja | Se exigía que existieran, no que fueran fuertes | *System check* `identity.E001`/`E002` en `backend/apps/identity/checks.py` (con `DEBUG`, solo aviso) | `test_deployment.py`; sin `DEBUG`, el backend no arranca con claves débiles | #37 |
| [SEC-04](../seguridad/hallazgos.md#sec-04--djangorestframework-3172-tiene-dos-cve-de-denegación-de-servicio-sin-sesión) | DRF con dos CVE de denegación de servicio | **Media** | El rango de `requirements.txt` dejaba fuera la versión corregida | DRF `>=3.18.2,<3.19` | `test_resources.py`; un cuerpo comprimido de 96 bytes ya no se expande a 5 MB | #37 |
| [SEC-05](../seguridad/hallazgos.md#sec-05--el-compose-publica-postgresql-y-el-backend-en-todas-las-interfaces-del-equipo) | Puertos en todas las interfaces | Baja | El compose no ponía IP | `127.0.0.1:` en cada puerto de `backend/docker-compose.yml` | `test_deployment.py`; compose levantado | #37 |
| [SEC-06](../seguridad/hallazgos.md#sec-06--imagen-del-backend-base-sin-digest-pip-sin-versión-y-runserver-como-comando) | Imagen no reproducible y con `runserver` | Informativa | Una sola etapa, con la base y `pip` sin fijar | `backend/Dockerfile` en dos etapas (`dev` y `production`), base por digest, `pip` fijo y gunicorn en `production` | `test_deployment.py`; hadolint sin `DL3013`; la imagen responde `Server: gunicorn` | #37 |
| [SEC-07](../seguridad/hallazgos.md#sec-07--options-responde-500-en-27-rutas-una-de-ellas-pública) | `OPTIONS` respondía `500` | Baja | La metadata de DRF fallaba en las vistas sin `serializer_class` | `DEFAULT_METADATA_CLASS = None` | `test_http_responses.py`; 0 de 176 rutas con 5xx | #37 |
| [SEC-08](../seguridad/hallazgos.md#sec-08--las-respuestas-con-datos-personales-no-llevan-cache-control-no-store-ni-vary-cookie) | Datos personales que el navegador podía guardar | **Media** | DRF no pone `Cache-Control` | Un *middleware* (`backend/config/middleware.py`) con `Cache-Control: no-store` y `Vary: Cookie` en toda la API | `test_http_responses.py`; ZAP ya no la marca como cacheable | #37 |
| [SEC-09](../seguridad/hallazgos.md#sec-09--el-límite-de-login-y-de-recuperación-se-salta-con-otros-correos-o-con-otras-ip) | El límite del login se saltaba | **Media** | Una sola clave, "IP + correo" | Límites por IP (sobre todas las cuentas) y por cuenta (desde todas las IP) en `backend/apps/identity/throttling.py` | `test_rate_limits.py`; corta en el 21.º correo desde una IP y en el 11.º fallo de una cuenta desde 3 IP | #37 |
| [SEC-10](../seguridad/hallazgos.md#sec-10--no-existen-los-límites-generales-por-usuario-que-piden-req-93-y-api-26) | Sin límites generales por usuario | **Media** | No había `DEFAULT_THROTTLE_CLASSES` | 600 lecturas, 120 escrituras y 20 cambios de estado por minuto (`AUTH_RATE_LIMITS` en `base.py`) | `test_rate_limits.py`; `429` con `Retry-After` en la petición 601, 121 y 21 | #37 |
| [SEC-11](../seguridad/hallazgos.md#sec-11--un-json-de-más-de-25-mb-responde-500-sin-debug-o-la-página-de-depuración-con-debug-no-413) | Un JSON grande respondía `500` | Baja | `RequestDataTooBig` es de Django y DRF no lo traduce | `413 PAYLOAD_TOO_LARGE` en `backend/config/exceptions.py` | `test_http_responses.py` | #37 |
| [SEC-12](../seguridad/hallazgos.md#sec-12--las-rutas-inexistentes-y-los-ids-que-no-son-uuid-responden-html-de-django-no-el-formato-de-error-de-la-api) | `404` en HTML | Baja | Sin `handler404` ni `handler500` | Errores en JSON bajo `/api/` (`backend/config/urls.py`, sin `DEBUG`) | `test_http_responses.py` | #37 |
| [SEC-13](../seguridad/hallazgos.md#sec-13--el-contrato-no-coincide-con-la-api-en-2-respuestas-y-no-documenta-varios-estados) | Contrato desalineado | Informativa | Dos esquemas mal y errores sin documentar | Esquemas corregidos y un *hook* (`backend/config/openapi.py`) que documenta `400`, `404` y `428` | `test_deployment.py`; schemathesis sin `ST103` ni `ST108` | #37 |
| [SEC-14](../seguridad/hallazgos.md#sec-14--la-recuperación-de-contraseña-revela-si-el-correo-existe-cuando-falla-el-envío) | La recuperación revelaba si el correo existe | **Media** | El correo salía en la misma petición, solo si el usuario existía | El correo va por la cola de Celery (`backend/apps/identity/tasks.py`) y el token se genera en el worker | `test_auth.py`; `202` siempre y el mismo tiempo de respuesta | #37 |
| [SEC-15](../seguridad/hallazgos.md#sec-15--el-log-de-peticiones-guarda-la-búsqueda-completa-documento-o-nombre) | Búsquedas completas en el log | Baja | El filtro solo ocultaba tokens | `***` en `search`, `email`, `document_number` y `q` (`backend/config/log_redaction.py`); gunicorn sin *access log* | `test_exposure.py` | #37 |
| [SEC-16](../seguridad/hallazgos.md#sec-16--un-409-al-crear-un-cliente-confirma-que-esa-cédula-ya-está-registrada) | El `409` confirma que una cédula ya es cliente | Baja | La unicidad del documento es una regla de negocio | **Aceptado** (ver 2.4) | `test_exposure.py` fija el comportamiento | #37 |
| [SEC-17](../seguridad/hallazgos.md#sec-17--textos-de-la-configuración-de-bancos-sin-longitud-máxima) | Textos de bancos sin tope | Informativa | Sin `max_length` | `max_length=4000` en `backend/apps/banking/serializers.py` | `test_resources.py`; 100.000 caracteres → `400` | #37 |
| [SEC-18](../seguridad/hallazgos.md#sec-18--admin-de-django-está-publicado-con-la-api-y-su-login-no-tiene-límite-de-intentos) | `/admin/` publicado y sin límite | Baja | Se montaba siempre | Solo con `DEBUG` o `ADMIN_ENABLED`, en `ADMIN_URL_PATH` y con límite por IP | `test_config_inventory.py`; `429` en el 11.º intento | #37 |
| [SEC-19](../seguridad/hallazgos.md#sec-19--el-esquema-openapi-y-la-documentación-interactiva-son-públicos) | Esquema y Swagger públicos | Informativa | Se montaban siempre | Solo con `DEBUG` o `API_DOCS_PUBLIC`; la referencia pública es la de GitHub Pages, hecha con `contracts/openapi.json` | `test_config_inventory.py` | #37 |
| [SEC-20](../seguridad/hallazgos.md#sec-20--la-documentación-de-la-api-promete-9-rutas-que-no-existen-y-omite-5-que-sí) | La documentación de la API no coincidía con las rutas | Informativa | No se actualizó al construir el MVP | `docs/API_REST_MVP_CREDITO.md`: 9 rutas a "Fuera del MVP" y las que faltaban, documentadas | `test_config_inventory.py`, en los dos sentidos | #37 |
| [SEC-21](../seguridad/hallazgos.md#sec-21--las-respuestas-que-cambian-según-el-rol-no-validan-cuando-la-página-está-vacía) | Respuestas por rol que no validaban con la página vacía | Informativa | Con `oneOf`, una página vacía valía para las dos formas | `anyOf` en el contrato | `test_deployment.py`; schemathesis sin `ST108` | #37 |

### 2.4 Aceptados, con su motivo

- **SEC-16 (baja), aceptado por Carlos.** El documento identifica a la persona y no tiene sentido crear el mismo cliente una vez por broker: la unicidad es regla de negocio. Mitigación: el `409` no trae ningún dato del otro cliente y el límite general de escrituras (SEC-10) deja probar como mucho 120 cédulas por minuto. Riesgo residual: confirmar que una cédula ya es cliente, sin saber de quién.

### 2.5 Riesgo residual

Lo que queda después de la fase B, según SEGURIDAD §7:

- **Fuerza bruta muy distribuida y bloqueo de cuentas.** El límite por cuenta frena el ataque a una cuenta desde muchas IP, pero quien conozca un correo puede dejar esa cuenta 15 minutos sin entrar. Un ataque desde miles de IP lo frena la protección perimetral (WAF o límites en el proxy) al desplegar.
- **Producción todavía no existe.** La configuración y la imagen `production` quedaron listas y probadas en local; al desplegar faltan el proxy con TLS, los secretos reales (el check de SEC-03 exige que sean fuertes, pero generarlos y rotarlos es del despliegue), los logs centralizados y los backups. La imagen `production` todavía trae las herramientas de prueba, porque `requirements.txt` es uno solo.
- **El modo local simple.** Allí la recuperación de contraseña envía el correo en el mismo proceso (no hay worker), así que el tiempo del envío se nota cuando el correo existe; producción usa el worker. Y los contenedores que ya estaban creados siguen publicados en todas las interfaces hasta que se recrean con el compose nuevo.
- **Archivos y enlaces.** Un PDF con contenido activo es un PDF válido (lo acotan el antivirus del modo completo, la descarga siempre adjunta y con `nosniff`); quien tenga un enlace mágico antes que el comprador entra a su portal (lo acotan el solo uso, el vencimiento, la revocación y la sesión de 24 h).
- **No se probó** el frontend como aplicación (XSS, CSP del sitio), el modo completo con S3 real y Celery distribuido, ni la carga sostenida (esa es la auditoría de la §4).

---

## 3. Rendimiento del frontend

Informe completo: [`docs/PERFORMANCE.md`](../PERFORMANCE.md) (resumen, método, antes y después, cada hallazgo y los presupuestos del CI). Fichas largas: [`docs/performance/frontend-hallazgos.md`](../performance/frontend-hallazgos.md). Cómo repetir la medición en local: [`frontend/scripts/perf/README.md`](../../frontend/scripts/perf/README.md).

> **En simple:** el expediente cargaba de entrada todo lo que podía llegar a usar y pedía sus datos en cadena. El dashboard saltaba mientras cargaba, y abrir un modal congelaba la pantalla medio segundo. Hoy el expediente baja 30 % menos de JavaScript y muestra su contenido 1,3 s antes en un móvil, el dashboard no se mueve y el modal abre al instante. Y el CI no deja pasar un PR que engorde una página.

### 3.1 Qué se revisó y con qué método

- **13 páginas, con el usuario que corresponde a cada una:**
  - las 3 públicas (login, aceptar invitación y acceso del comprador);
  - del administrador: dashboard, reportes y usuarios;
  - de la asesora: Mi día, el listado, un expediente radicado, clientes y sus comisiones;
  - la del broker (prospectos);
  - el portal del comprador.
- **Herramientas:**
  - Lighthouse 13.6, en móvil (un teléfono de gama media con 4G lento simulado) y en escritorio;
  - Web Vitals de laboratorio (LCP, CLS, INP) con Playwright;
  - tres interacciones reales;
  - el tamaño del JavaScript de cada ruta.
- **Siempre sobre el build de producción**, con 5 corridas por página y la mediana.
- **Antes y después, el mismo día.** La línea base del primer día se midió con el equipo cargado, y el mismo código daba otros números. Por eso el antes y el después se miden el mismo día, uno detrás de otro.

### 3.2 Hallazgos por severidad

| Severidad | Cuántos | Corregidos | Aceptados | Dependen del backend |
| --- | ---: | ---: | ---: | ---: |
| Alta | 4 | 3 | 0 | 1 (el portal) |
| Media | 5 | 3 | 2 | 0 |
| Baja | 1 | 1 | 0 | 0 |
| Informativa | 3 | 0 | 2 | 1 |

PERF-01 está corregido; el resto de su LCP también depende del backend.

### 3.3 Hallazgos y cómo se solucionó cada uno

| Id | Problema | Causa | Solución aplicada | Antes → después | PR |
| --- | --- | --- | --- | --- | --- |
| PERF-01 | El expediente tardaba en mostrar su título | Pedía sus secciones después del detalle, cargaba de entrada todas sus pestañas y modales, y se repintaba entero con cada respuesta | Secciones en paralelo; pestañas, paneles y modales cargados al usarlos; cada tarjeta escucha solo su dato (`workspace-screen.tsx`, `route-prefetch.ts`) | LCP móvil 5,1 → 3,9 s; JS −30 % | #39 |
| PERF-02 | El dashboard saltaba mientras cargaba | Los bloques de carga eran mucho más bajos que el contenido | Las tarjetas muestran sus etiquetas desde el principio y los bloques reservan su alto (`summary-blocks.tsx`) | CLS 0,21–0,56 → 0 | #39 |
| PERF-03 | El portal del comprador tardaba en mostrar su texto principal | Formularios en la primera carga y la cadena sesión → solicitud | Retiro y carga de documentos, al abrirlos (`home-screen.tsx`) | LCP 5,3 → 4,7 s; JS −25 %. El resto depende del backend | #39 |
| PERF-04 | Abrir "Registrar respuesta" congelaba la pantalla | Se armaba todo el modal en el mismo clic | El modal se abre en una transición, con el botón en estado de carga (`response-timeline.tsx`) | INP 360 → 104 ms | #39 |
| PERF-05 | Las páginas con sesión pintan después de validar la sesión | La guarda espera la sesión | Se probó adelantar datos y se revirtió: no ayudaba | Aceptado: pide la sesión en el servidor | #39 |
| PERF-06 | Mi día y Prospectos saltaban al cargar | El mismo patrón que el dashboard | Esqueletos con la forma final (`tray.tsx`, `broker-screen.tsx`) | CLS 0,148 → 0,010 y 0,214 → 0 | #39 |
| PERF-07 | El listado tenía mucho trabajo en el hilo principal | La hidratación de Ant Design y de la tabla | Se probó un cambio en las pestañas y se revirtió: la medición mostró que no ayudaba | Aceptado; propuesta: el modo `zeroRuntime` de Ant Design | #39 |
| PERF-08 | "Aceptar invitación" sin token pintaba tarde | El aviso esperaba al JavaScript, y se cargaba el formulario entero | El servidor pinta el aviso; el formulario se carga solo con token (`accept-invitation-*.tsx`) | LCP móvil 3,7 → 0,8 s; JS −30 % | #39 |
| PERF-09 | Una petición de sesión quedaba abierta | No se leía el cuerpo de la respuesta | Se lee (`session.ts`) | Cargas que no terminaban: 5 de 5 → 0 | #39 |
| PERF-10 | El login cargaba Zod para dos campos | Validación en la primera carga | El esquema se carga al validar (`login-schema.ts`) | JS −9 % | #39 |
| PERF-11 | El catálogo de metadatos (36 kB) se descarga en cada carga | El backend lo marca como no cacheable | — | Depende del backend | — |
| PERF-12 | Fuentes sin precarga | `@fontsource` en el CSS | No se cambia: no hay nada que mover | Aceptado | — |
| PERF-13 | Cada fila del listado precarga su expediente | Comportamiento por defecto de Next | Se deja: hace instantánea la navegación | Aceptado | — |

**Lo que quedó en el CI para que no vuelva:**
- un presupuesto de JavaScript por ruta (lo medido + 10 %), que bloquea si una página engorda;
- Lighthouse CI en las tres páginas públicas, que bloquea si bajan la performance, la accesibilidad o las buenas prácticas, o si suben el LCP, el CLS o el bloqueo del hilo principal.

---

## 4. Carga y estrés del backend

### 4.1 Qué se revisó y con qué método

*(Se completa con el informe: herramienta de carga, escenarios — por ejemplo, listado de solicitudes, "Mi día", carga de documentos y reportes —, usuarios concurrentes, duración, y el objetivo de RNF-17: p95 menor a 800 ms en las lecturas normales.)*

Lo que el diseño ya prepara para esta auditoría está en [04 · System design §5](04-system-design.md#5-rendimiento): listas sin consultas por fila (48 aserciones de número de consultas en las pruebas), agregados en la base, índices para las pantallas y la completitud del listado guardada en lugar de calculada por fila.

### 4.2 Hallazgos por severidad

| Severidad | Cuántos | Corregidos | Aceptados |
| --- | ---: | ---: | ---: |
| *(pendiente)* | | | |

### 4.3 Hallazgos y cómo se solucionó cada uno

| Id | Problema | Causa | Solución aplicada | Antes → después (p95, errores) | PR |
| --- | --- | --- | --- | --- | --- |
| *(pendiente)* | | | | | |

---

## 5. Lo que aprendimos

*(Se completa al cierre con los patrones que se repitieron en las tres auditorías y la regla que quedó en el CI para que no vuelvan.)*

Mientras tanto, los patrones que ya se vieron durante la construcción y la regla automática que dejaron ([11 · Cómo se construyó §7](11-como-se-construyo.md#7-errores-reales-que-se-atraparon)):

| Patrón | Regla que quedó | Dónde |
| --- | --- | --- |
| Un cambio del backend rompe al front sin que nadie lo note | El CI regenera el contrato y los tipos del front y falla si hay diferencias | `.github/workflows/backend.yml`, `frontend.yml` |
| Un nombre de enum publicado cambia solo | Nombres fijos y una prueba que los protege | `backend/tests/test_contract_names.py` |
| Una operación con `If-Match` sin `ETag` declarado | Una prueba que recorre el esquema | `backend/tests/test_etag_contract.py` |
| Un `POST` nuevo con `@idempotent` sin declararlo a conciencia | Una lista esperada en la prueba del contrato | `backend/tests/applications/idempotency/test_idempotency.py` |
| Consultas que crecen con las filas | Aserciones de número de consultas en los listados | 20 archivos de `backend/tests/` |
| Colores escritos a mano y contraste insuficiente | Prueba sin colores fijos y `axe` en cada story en el CI | `frontend/src/test/no-hardcoded-colors.test.ts`, paso "Storybook (a11y)" |
| Secretos o documentos en la auditoría | Un fixture que revisa cada evento escrito en las pruebas | `backend/tests/applications/audit/` (P1.10 de [`specs/TAREA-auditoria.md`](../../specs/TAREA-auditoria.md)) |
| Una operación nueva de la API sin decidir quién puede usarla | La matriz de acceso exige una fila (9 actores) por cada operación del contrato, y su documento generado debe estar al día | `backend/tests/security/access_matrix.py`, paso "Access matrix document is up to date" |
| Una dependencia con una vulnerabilidad que ya tiene arreglo, o un secreto en cualquier commit | `pip-audit` y `gitleaks` (todo el historial) en cada PR | `.github/workflows/backend.yml`, `backend/security/pip-audit-ignore.txt`, `.gitleaks.toml` |
| Código con un patrón inseguro conocido | `bandit` en cada PR (bloquea la severidad alta) | `.github/workflows/backend.yml` |

---

## 6. Cómo leer las tablas

- **Id:** el identificador del hallazgo en su informe (por ejemplo, `SEC-04`).
- **Problema:** qué pasaba, en una frase y sin jerga.
- **Causa:** por qué pasaba (la raíz, no el síntoma).
- **Solución aplicada:** qué se cambió y dónde, con la ruta del archivo.
- **Cómo se verificó:** la prueba que lo cubre ahora, la medición antes y después o el re-test del auditor.
- **PR:** el que lo cerró.
- **Aceptado:** un hallazgo que se decidió no corregir en el MVP, siempre con su motivo.
