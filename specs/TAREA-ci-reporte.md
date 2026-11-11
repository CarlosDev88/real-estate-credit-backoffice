# Tarea: reporte del CI en cada PR

## Objetivo
Que cada PR muestre, en un comentario, el estado de cada verificación del CI: qué pasó, qué falló, qué dejó advertencias y con qué detalle. El comentario es informativo y sale siempre (en verde, con advertencias o en rojo). El que decide si el PR se puede fusionar sigue siendo el check obligatorio.

## Cuándo
- Después del merge de `TAREA-monorepo.md`: el workflow ya corre en `backend/` y existe `contracts/openapi.json`.
- Rama: `ci/pr-report`, desde `master` al día.

## Reglas de trabajo
- El agente **no** hace `commit`, `push`, `merge` ni `rebase`; git solo en lectura. Trabaja por partes y al cerrar cada una propone un mensaje de commit corto, sin `Co-Authored-By`. Carlos hace los commits.
- Antes de programar, el agente presenta las ambigüedades una por una, con su recomendación. Las precisiones acordadas se agregan al final de esta spec.
- No se agregan dependencias nuevas al backend para el reporte: el script usa solo la librería estándar de Python.

## Lo que existe hoy (verificar al empezar)
`.github/workflows/backend.yml` tiene un job, `Lint, types and tests`, que es el check obligatorio del ruleset `protect-master`. Sus pasos son:
1. ruff check
2. ruff format --check
3. mypy
4. makemigrations --check
5. pytest con cobertura (mínimo 95 %)
6. el contrato OpenAPI al día

Hoy el job se detiene en el primer paso que falla, y en el PR solo se ve una ✖ sin detalle.

## Qué construir

### 1. Que todas las verificaciones corran siempre
- Cada paso de verificación lleva un `id` y `continue-on-error: true`, y guarda su salida en `backend/.ci-report/` (carpeta ignorada por git).
- Un último paso, **"CI gate"**, con `if: always()`, falla el job si alguna verificación terminó en `failure`. Así el check obligatorio sigue bloqueando igual que hoy, pero el reporte muestra todos los problemas de una vez y no solo el primero.
- Las advertencias **nunca** hacen fallar el job.
- **No cambia el nombre del job.**

### 2. Salida de cada verificación, en un formato que se pueda leer

| Verificación | Cómo se captura | Qué se reporta |
| --- | --- | --- |
| Ruff (lint) | `--output-format=json` a archivo, y otra corrida con `--output-format=github` para anotar las líneas | Errores por regla, con archivo y línea. |
| Ruff (formato) | `--check` con la lista de archivos | Archivos sin formatear. |
| Mypy | Salida a archivo, más un *problem matcher* (`.github/matchers/mypy.json`) para anotar las líneas | Errores con archivo, línea y código. |
| Migraciones | `makemigrations --check --dry-run` a archivo | Apps con migraciones faltantes. |
| Tests | `--junit-xml=.ci-report/pytest.xml` | Total, pasan, fallan, saltados, duración y la lista de los que fallan (nombre y primera línea del error). |
| Cobertura | `--cov-report=xml:.ci-report/coverage.xml` | Total contra el mínimo (95 %), y los 5 módulos con menos cobertura. |
| Advertencias de pytest | Resumen de warnings de la corrida | Conteo por categoría (`DeprecationWarning`, `RuntimeWarning`…) y el ejemplo más frecuente de cada una. |
| Contrato OpenAPI | Avisos de `spectacular` y `git diff --stat` del contrato | "Al día", "desactualizado" (con las rutas que cambiaron) o advertencias del esquema. |

### 3. Script que arma el reporte
`backend/scripts/ci_report.py` (solo librería estándar):
- **Lee:** los archivos de `.ci-report/` y el resultado de cada paso, que le llega por variables de entorno (`${{ steps.<id>.outcome }}`).
- **Estados por verificación:**
  - ✅ pasó;
  - ⚠️ pasó con advertencias;
  - ❌ falló;
  - ⏭️ no corrió (por ejemplo, porque falló la instalación).
- **Genera un Markdown con:**
  - un encabezado con el resultado general, el commit corto, el enlace al run y la duración;
  - una tabla con una fila por verificación (estado, resumen corto y número);
  - un bloque `<details>` por cada verificación con problemas: máximo 50 líneas, y si hay más, "… y N más" con el enlace al log completo;
  - la lista de tests que fallan (máximo 20);
  - las advertencias agrupadas por categoría.
- **Escribe** ese Markdown en `$GITHUB_STEP_SUMMARY` (resumen del run en Actions) y en `.ci-report/report.md`.
- **Es tolerante a fallos:** si falta un archivo (porque el paso no corrió), marca ⏭️ y sigue. El script nunca hace fallar el job.

### 4. Comentario en el PR
- Lo publica `actions/github-script`, con la versión fijada.
- Hay **un solo comentario por PR**, identificado con el marcador `<!-- ci-report:backend -->`. Si ya existe, se edita; si no, se crea. Así no se llena el PR de comentarios.
- Solo corre en eventos `pull_request` del mismo repo.
- Permisos del job: `contents: read` y `pull-requests: write`, nada más.

### 5. Artefactos
`backend/.ci-report/` se sube con `actions/upload-artifact`, guardado por 7 días, para descargar el JUnit y la cobertura completos.

## Ejemplo del comentario

```
## Backend CI · ❌ 2 de 6 fallaron · ⚠️ 1 con advertencias
Commit abc1234 · Ver run · 2 min 14 s

| Verificación | Estado | Detalle |
| --- | --- | --- |
| Ruff (lint) | ✅ | Sin errores |
| Ruff (formato) | ❌ | 2 archivos sin formatear |
| Mypy | ✅ | Sin errores |
| Migraciones | ✅ | Al día |
| Tests | ❌ | 1529 pasan · 2 fallan · 0 saltados |
| Cobertura | ✅ | 98,31 % (mínimo 95 %) |
| Advertencias | ⚠️ | 3 (DeprecationWarning: 3) |
| Contrato OpenAPI | ✅ | Al día |

<details><summary>Tests que fallan (2)</summary>…</details>
<details><summary>Ruff (formato): 2 archivos</summary>…</details>
<details><summary>Advertencias (3)</summary>…</details>
```

## Seguridad
- El reporte no incluye variables de entorno, secretos ni el `.env`. Solo salidas de las herramientas, truncadas.
- El texto de las herramientas se escapa antes de meterlo en el Markdown, para que no rompa el comentario.
- No hay acciones de terceros fuera de las oficiales de GitHub (`actions/*`), y todas van con versión fijada.

## Pruebas
- `backend/tests/ci/test_ci_report.py`, con archivos de ejemplo (JUnit, `coverage.xml` y salidas de ruff, mypy y spectacular). Casos:
  - todo en verde;
  - fallos y advertencias juntos;
  - un paso que no corrió;
  - salidas muy largas (truncado);
  - caracteres especiales (escape).
- El script pasa ruff y mypy como el resto del backend. Para que el script cuente en la cobertura, se agrega `scripts` a `--cov` o se mide aparte; el agente propone cuál de las dos.

## Verificación real (la hace Carlos)
1. Abrir el PR de esta tarea: el comentario debe salir en verde.
2. En una rama de prueba aparte, meter a propósito un error de ruff, un test que falle y un warning. Comprobar que el comentario muestra los tres, que las líneas quedan anotadas en "Files changed" y que el check obligatorio sale en rojo.
3. Corregir y hacer push: el mismo comentario se actualiza a verde.
4. Borrar la rama de prueba sin fusionarla.

## Después
Cuando exista el CI del frontend (`TAREA-frontend-base.md`, F0, parte 6), se usa el mismo formato con el marcador `<!-- ci-report:frontend -->`: lint, typecheck, tests, cobertura, `api:gen` sin diferencias y build.

## Definición de terminado
- En cada PR aparece un único comentario con el estado de todas las verificaciones, en verde, con advertencias o en rojo.
- El check obligatorio se comporta igual que antes: rojo si algo falla, y las advertencias no bloquean.
- Los errores de ruff y mypy quedan anotados en la línea en "Files changed".
- El resumen del run en Actions muestra la misma tabla.
- Tests del script en verde; ruff y mypy sin errores.

## Precisiones acordadas

### 1. Contrato OpenAPI
- El paso mantiene `--fail-on-warn`: una advertencia del esquema es ❌ (bloquea como hoy), con los avisos de `spectacular` en su `<details>`.
- Estados de la fila: ✅ al día; ❌ desactualizado, con las rutas y métodos agregados, quitados o cambiados (y los esquemas de `components` que cambiaron), calculados comparando el JSON generado con el del repo, porque `git diff --stat` solo da conteos de líneas; ❌ con advertencias del esquema.
- "Las advertencias nunca hacen fallar el job" aplica solo a los warnings de pytest.
- El resumen separa los cambios por tipo: `Desactualizado: 1 ruta nueva · 4 esquemas cambiados` (rutas nuevas, quitadas y cambiadas; luego esquemas nuevos, quitados y cambiados).
- No se captura `git diff --stat`: la lista de rutas y esquemas ya dice qué cambió, y el log del paso muestra el diff completo. El contrato se regenera de forma estable (dos corridas en el mismo entorno dan el mismo archivo, byte a byte), así que el diff solo trae lo que cambió.

### 2. Warnings de pytest
- Se capturan con el hook `pytest_warning_recorded` en `tests/conftest.py`. El hook acumula en memoria y escribe `$CI_REPORT_DIR/warnings.json` una sola vez, en `pytest_sessionfinish`. Si `CI_REPORT_DIR` no está definida, no hace nada. Lleva tipos y pasa mypy.
- Cuenta todo lo que pytest registra, incluidos los warnings de librerías de terceros (lo mismo que el `warnings summary` de la consola).
- El reporte muestra el conteo por categoría y el mensaje más frecuente de cada una, con su ubicación y cuántas veces aparece.
- Si el paso de tests corrió y no hay archivo, son 0 warnings; si no corrió, la fila es ⏭️.

### 3. Cobertura
- Paso aparte, **"Coverage"**: `python -m coverage report --fail-under=95`. El paso de tests queda sin `--cov-fail-under` y mide `--cov=apps --cov=scripts` en una sola corrida, con un solo `coverage.xml` y un solo mínimo.
- Si el paso de tests falla, Coverage corre igual cuando existe el archivo de datos, y la fila lo marca: `98,40 % · mínimo 95 % · con tests fallidos` (sin paréntesis encadenados; sin tests fallidos queda `98,41 % (mínimo 95 %)`). Si no hay datos, ⏭️.
- La lista de los 5 módulos con menos cobertura excluye las migraciones y los archivos sin sentencias. La configuración de coverage no cambia: el total sigue siendo el mismo.
- En "X de N", N es el número de verificaciones que pueden bloquear: 7 (todas menos "Advertencias"). Las ⏭️ cuentan en N y el encabezado las indica (`❌ 1 de 7 fallaron · ⏭️ 6 no corrieron`; en verde, `✅ 7 de 7 pasaron`).

### 4. Versiones de las acciones
- Las cuatro se fijan por SHA completo del commit, con la versión en un comentario (`uses: actions/checkout@<sha> # v4.4.0`).
- Nuevas en su última versión: `actions/github-script` v9.0.0 y `actions/upload-artifact` v7.0.2.
- Las existentes no cambian de versión mayor: `actions/checkout` v4.4.0 y `actions/setup-python` v5.6.0.

### 5. Documentación
- `backend/README.md`: sección "CI Report" (qué muestra el comentario, cómo leer los estados, el artefacto y cómo generar el reporte en local con Docker).
- `README.md` raíz: una línea en la estructura del repo. Ambos en inglés, como el resto de los README.

### 6. Detalles de implementación
- El reporte va en español, con coma decimal (`98,31 %`).
- La duración va desde un paso inicial que guarda la hora hasta el paso del reporte.
- Escape: la salida de las herramientas va en bloques de código con una cerca de comillas invertidas más larga que cualquiera del contenido; en tablas y títulos se escapan `<`, `>`, `&` y `|` (nadie puede inyectar el marcador). El comentario tiene un tope de 60 000 caracteres (GitHub admite 65 536).
- Mypy corre con `--show-absolute-path`, para que el *problem matcher* anote la línea correcta aunque el job corra en `backend/`.
- `actions/upload-artifact` lleva `include-hidden-files: true` (sin eso, v4+ omite `.ci-report/`).
- `.ci-report/` se agrega a `.gitignore` y a `backend/.dockerignore`.
- El script se importa como `scripts.ci_report` (con `scripts/__init__.py`); los archivos de ejemplo de los tests van en `backend/tests/ci/fixtures/`.

### 7. Orden de los pasos, condiciones y permisos
- Orden: las 7 verificaciones → reporte → subida del artefacto → comentario → CI gate.
- El reporte, la subida del artefacto, el comentario y el CI gate llevan `if: always()`; el comentario, además, solo corre si `github.event_name == 'pull_request'` y la rama de origen es del mismo repo.
- El reporte y el comentario llevan `continue-on-error: true`: un problema de permisos (por ejemplo, en un PR de Dependabot) no pone el check en rojo.
- El CI gate falla si alguna verificación terminó en `failure` o si falló la instalación.
- Permisos a nivel de job: solo `contents: read` y `pull-requests: write`.

### 8. Revisión antes del commit de la parte 2
- Al reproducir los pasos en Docker, el agente entrega el Markdown generado en los dos casos (verde y con fallos) para revisarlo antes del commit.

## Pendientes (fuera de esta tarea)
- Subir `actions/checkout` y `actions/setup-python` de versión mayor.
- Agregar Dependabot para `github-actions`, que mantiene los SHA al día con PRs.
