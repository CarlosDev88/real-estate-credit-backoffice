# 12 · Auditorías: qué se encontró y cómo se solucionó

> **En simple:** además de las pruebas y el CI, el proyecto pasa por **tres auditorías independientes**: de seguridad, de rendimiento del frontend y de carga y estrés del backend. Cada una revisa con un método propio, deja su informe completo y una lista de hallazgos. Este documento junta las tres en lenguaje simple y, para cada hallazgo, cuenta **qué pasaba, por qué, qué se cambió, cómo se comprobó y en qué PR se cerró**.

> **Estado al 19 de noviembre de 2026.** La auditoría de **seguridad** terminó su fase A (encontrar y documentar) y está en `master` desde el #32; su fase B (corregir) está en curso, así que las columnas de causa, solución y verificación se llenan cuando se fusione. Las auditorías de **rendimiento del frontend** y de **carga del backend** siguen en preparación.

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
| Seguridad | La API completa (235 operaciones), el código, las dependencias, el historial de git y los contenedores | [`docs/SEGURIDAD.md`](../SEGURIDAD.md) y [`docs/seguridad/`](../seguridad/hallazgos.md) | **20**: 0 críticos, 0 altos, 5 medios, 10 bajos, 5 informativos | ✅ Fase A en `master` (#32) · 🔄 Fase B (correcciones) en curso |
| Rendimiento del frontend | Peso de las páginas, tiempos de carga y de interacción | `docs/PERFORMANCE.md` *(en curso)* | Pendiente | 🔄 En preparación |
| Carga y estrés del backend | Latencia bajo carga (el p95 < 800 ms de RNF-17), errores y límites | `docs/PERFORMANCE.md` *(en curso)* | Pendiente | 🔄 En preparación |

---

## 2. Seguridad

### 2.1 Qué se revisó y con qué método

En cuatro partes, todo en local, sobre datos de demo y con una base de datos de usar y tirar ([`docs/SEGURIDAD.md`](../SEGURIDAD.md) §2):

| Parte | Qué | Con qué | Detalle |
| --- | --- | --- | --- |
| 1 · Automático | Configuración de Django, código, dependencias, secretos en todo el historial y contenedores | `manage.py check --deploy`, bandit, semgrep, pip-audit, pnpm audit, gitleaks, hadolint | [`01-automatico.md`](../seguridad/01-automatico.md) |
| 2 · Dinámico | Ataques simulados contra una copia local de la API: fuzzing con 4 sesiones, escaneo pasivo y activo, cabeceras, CORS, cookies, límites y errores | schemathesis (~42.000 casos), OWASP ZAP (~72.000 peticiones), curl | [`02-dinamico.md`](../seguridad/02-dinamico.md) |
| 3 · Matriz de acceso | Cada una de las 235 operaciones pedida como cada uno de 9 actores: sin sesión, admin, la asesora dueña, otro asesor, el broker que originó, otro broker, la constructora, el comprador dueño y otro comprador | pytest (`backend/tests/security/`) | [`03-matriz-acceso.md`](../seguridad/03-matriz-acceso.md) |
| 4 · Manual | Revisión del código de 10 áreas sensibles, incluidas carreras (diez peticiones a la vez) | lectura de código, pytest, `backend/security/race_checks.py` | [`04-manual.md`](../seguridad/04-manual.md) |

**Lo más importante es lo que no apareció** (SEGURIDAD §1): la matriz dio **2.115 casos, todos con el resultado esperado, sin ninguna brecha de acceso**; nadie puede ver ni tocar expedientes, documentos, clientes o comisiones que no le corresponden; sin sesión no se llega a ningún dato; no hay inyecciones; los archivos se validan por su contenido real; y los enlaces del comprador, las radicaciones y los pagos no se duplican aunque lleguen diez peticiones a la vez.

**Lo que quedó en el CI** para que no vuelva a pasar: la matriz corre en cada PR y exige una fila para cada operación nueva del contrato; `pip-audit`, `gitleaks` y `bandit` corren en cada PR ([09 · Calidad §3](09-calidad.md#3-el-ci-dos-revisiones-obligatorias)).

**Criterio de la fase B** (SEGURIDAD §6): los críticos y altos se corrigen todos; los medios, si el esfuerzo es pequeño (si no, se aceptan con su motivo); los bajos e informativos se documentan y se corrigen si son de una línea.

### 2.2 Hallazgos por severidad

Escala de la auditoría: **Crítica** (acceso sin sesión a datos personales, tomar la cuenta de otro, ejecución de código), **Alta** (ver o cambiar datos de otro alcance, saltar la autenticación del comprador, un secreto real filtrado), **Media** (campos de más dentro del propio alcance, límites que se saltan, enumeración de usuarios, una cabecera que importa), **Baja** (endurecimiento) e **Informativa** (buena práctica o aplica solo al desplegar).

| Severidad | Cuántos | Corregidos | Aceptados |
| --- | ---: | ---: | ---: |
| Crítica | 0 | — | — |
| Alta | 0 | — | — |
| Media | 5 | *(fase B)* | *(fase B)* |
| Baja | 10 | *(fase B)* | *(fase B)* |
| Informativa | 5 | *(fase B)* | *(fase B)* |
| **Total** | **20** | *(fase B)* | *(fase B)* |

Los tres más importantes, según el informe: **SEC-09** (se puede probar una contraseña contra todas las cuentas desde un solo equipo, o una cuenta desde muchos), **SEC-04** (dos vulnerabilidades públicas de la librería de la API que permiten dejar sin respuesta al servidor sin cuenta) y **SEC-08** (datos personales que el navegador puede guardar en disco).

### 2.3 Hallazgos y cómo se solucionó cada uno

Problema y severidad, de [`docs/seguridad/hallazgos.md`](../seguridad/hallazgos.md), donde está la ficha de cada uno: dónde, cómo reproducirlo, impacto y la corrección sugerida.

| Id | Problema | Severidad | Causa | Solución aplicada | Cómo se verificó | PR |
| --- | --- | --- | --- | --- | --- | --- |
| [SEC-01](../seguridad/hallazgos.md) | No hay una configuración de producción: los puntos de entrada cargan la local, que fuerza `DEBUG=True` | Baja (sube a Alta si se desplegara así) | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-02](../seguridad/hallazgos.md) | La configuración base no endurece HTTPS (HSTS, redirección, cookies seguras de sesión) | Baja | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-03](../seguridad/hallazgos.md) | Las claves no se validan al arrancar; la clave JWT del `.env` local tiene 31 bytes | Baja | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-04](../seguridad/hallazgos.md) | La versión de Django REST Framework tiene dos vulnerabilidades públicas de denegación de servicio sin sesión | **Media** | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-05](../seguridad/hallazgos.md) | El compose publica PostgreSQL y el backend en todas las interfaces de la máquina | Baja | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-06](../seguridad/hallazgos.md) | La imagen del backend no fija su base por digest ni la versión de `pip`, y arranca con `runserver` | Informativa | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-07](../seguridad/hallazgos.md) | `OPTIONS` responde `500` en 27 rutas, una de ellas pública | Baja | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-08](../seguridad/hallazgos.md) | Las respuestas con datos personales no le piden al navegador que no las guarde (`Cache-Control: no-store`, `Vary: Cookie`) | **Media** | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-09](../seguridad/hallazgos.md) | El límite de intentos del login y de la recuperación se salta probando otros correos o desde otras IP | **Media** | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-10](../seguridad/hallazgos.md) | Faltan los límites generales por usuario que piden REQ §9.3 y API §26 | **Media** | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-11](../seguridad/hallazgos.md) | Un JSON de más de 2,5 MB responde `500` (o la página de depuración con `DEBUG`) en lugar de `413` | Baja | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-12](../seguridad/hallazgos.md) | Las rutas inexistentes y los ids que no son UUID responden HTML de Django, no el formato de error de la API | Baja | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-13](../seguridad/hallazgos.md) | El contrato no coincide con la API en 2 respuestas y no documenta varios estados | Informativa | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-14](../seguridad/hallazgos.md) | La recuperación de contraseña revela si el correo existe cuando falla el envío | **Media** | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-15](../seguridad/hallazgos.md) | El log de peticiones guarda la búsqueda completa (un documento o un nombre) | Baja | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-16](../seguridad/hallazgos.md) | El `409` al crear un cliente confirma que esa cédula ya está registrada | Baja (Media mientras falte SEC-10) | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-17](../seguridad/hallazgos.md) | Textos de la configuración de bancos sin longitud máxima | Informativa | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-18](../seguridad/hallazgos.md) | El `/admin/` de Django está publicado con la API y su login no tiene límite de intentos | Baja | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-19](../seguridad/hallazgos.md) | El esquema OpenAPI y la documentación interactiva son públicos | Informativa | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |
| [SEC-20](../seguridad/hallazgos.md) | La documentación de la API promete 9 rutas que no existen y omite 5 que sí | Informativa | *(Fase B en curso)* | *(Fase B en curso)* | *(Fase B en curso)* | — |

### 2.4 Aceptados, con su motivo

*(Se completa con la fase B: un hallazgo aceptado es uno que no se corrige en el MVP, con el riesgo explicado y quién lo aceptó.)*

### 2.5 Riesgo residual

Lo que queda aunque se corrija todo, según SEGURIDAD §7: la fuerza bruta distribuida (desde miles de IP) necesita protección perimetral al desplegar; un PDF con contenido activo es un PDF válido (lo acotan el antivirus, la descarga siempre adjunta y con `nosniff`); quien tenga un enlace mágico antes que el comprador entra a su portal (lo acotan el solo uso, el vencimiento y la sesión de 24 h); y la configuración de producción (HTTPS, HSTS, secretos, logs, respaldos) se revisa al desplegar. **No se probó** el frontend como aplicación (XSS, CSP del sitio), el modo completo con S3 real ni la carga sostenida.

---

## 3. Rendimiento del frontend

### 3.1 Qué se revisó y con qué método

*(Se completa con el informe: herramienta de medición, páginas medidas, en qué dispositivo y red, y las métricas — por ejemplo, tamaño de JavaScript por ruta, tiempo hasta el contenido principal y respuesta a la interacción.)*

### 3.2 Hallazgos por severidad

| Severidad | Cuántos | Corregidos | Aceptados |
| --- | ---: | ---: | ---: |
| *(pendiente)* | | | |

### 3.3 Hallazgos y cómo se solucionó cada uno

| Id | Problema | Causa | Solución aplicada | Antes → después | PR |
| --- | --- | --- | --- | --- | --- |
| *(pendiente)* | | | | | |

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
