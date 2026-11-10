# Tarea: pasar el repo a monorepo

## Objetivo
Que el repo `CarlosDev88/real-estate-credit-backoffice` aloje backend y frontend juntos, sin perder historial ni romper el CI ni la protección de `master`.

Estructura final:

```
/
├── backend/            ← todo lo que hoy está en la raíz y es de Django
├── frontend/           ← se crea en TAREA-frontend-base.md (no en esta tarea)
├── contracts/
│   └── openapi.json    ← contrato generado por el backend; el frontend genera sus tipos desde aquí
├── design/             ← design system Umbral y mockups (ya existe)
├── docs/               ← documentación funcional (ya existe)
├── specs/              ← tareas (ya existe)
├── .github/workflows/  ← backend.yml (y luego frontend.yml)
├── .gitignore
└── README.md           ← README general del monorepo
```

## Cuándo
- Después del merge de la fase 10 (`feat/document-file`) y con **ninguna otra rama abierta** que toque el backend. Mover archivos con ramas vivas genera conflictos en todos los archivos.
- Rama: `chore/monorepo`, creada desde `master` al día.

## Reglas de trabajo
- El agente **no** hace `commit`, `push`, `merge` ni `rebase`. Git solo en lectura (`status`, `diff`, `log`). Carlos hace los commits de cada parte.
- Ningún mensaje propuesto lleva `Co-Authored-By` ni firmas.
- El agente no lee `.env` (lo bloquea su configuración).

## Parte 1: mover sin cambiar contenido
Solo movimientos con `git mv`, para que `git log --follow` conserve el historial. **En esta parte no se edita ningún archivo.**

A `backend/`:
- `apps/`, `config/`, `tests/`
- `manage.py`, `pyproject.toml`, `pytest.ini`, `requirements.txt`
- `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`

Se quedan en la raíz: `.github/`, `.gitignore`, `README.md`, `docs/`, `specs/` y `design/`.

Archivos no versionados que Carlos mueve a mano, porque el agente no los toca:
- `.env` → `backend/.env`
- Los cachés (`.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.coverage`) se pueden borrar; se regeneran solos.

Antes de proponer el commit, el agente lista lo que movió con `git status` y confirma que el diff no tiene cambios de contenido (solo `renamed:`).

## Parte 2: que todo vuelva a funcionar
1. **`.github/workflows/backend.yml`**
   - Agregar `defaults: run: working-directory: backend`.
   - En `actions/setup-python`, agregar `cache-dependency-path: backend/requirements.txt`.
   - **No cambiar el nombre del job** (`Lint, types and tests`): es el check obligatorio del ruleset `protect-master`.
   - **No agregar `paths:` al `on:`.** Si el workflow no corre en un PR que solo toca el frontend, el check obligatorio queda pendiente y el PR no se puede fusionar. El backend corre siempre; tarda poco.
2. **`backend/docker-compose.yml` y `backend/Dockerfile`**: el `context: .` sigue siendo válido porque los dos se movieron juntos. Verificar volúmenes, `env_file` y el init del almacenamiento. Los comandos de Docker se corren desde `backend/`.
3. **`backend/pyproject.toml` y `backend/pytest.ini`**: revisar rutas relativas (ruff, mypy, coverage). Con todo dentro de `backend/` deberían seguir sirviendo igual; confirmarlo corriendo las herramientas.
4. **`.gitignore` de la raíz**: que siga ignorando `.env`, cachés y `__pycache__` dentro de `backend/`, y que deje listo `frontend/node_modules`, `frontend/.next` y `frontend/playwright-report`.

Verificación local, desde `backend/`:

```
ruff check .
ruff format --check .
mypy .
python manage.py makemigrations --check --dry-run
pytest --cov=apps --cov-fail-under=95
docker compose up -d
```

## Parte 3: contrato OpenAPI y README
1. **`contracts/openapi.json`**: generarlo desde `backend/` con:
   ```
   python manage.py spectacular --file ../contracts/openapi.json --validate --fail-on-warn
   ```
   Formato JSON con indentación estable, para que el diff sea legible.
2. **Paso nuevo en `backend.yml`**, después de los tests: regenerar el contrato y fallar si cambió sin commitear.
   ```
   python manage.py spectacular --file ../contracts/openapi.json --validate --fail-on-warn
   git diff --exit-code ../contracts/openapi.json
   ```
   Así, todo PR que cambie la API trae su contrato actualizado, y el frontend nunca trabaja contra un contrato viejo.
3. **`README.md` de la raíz**: qué es el proyecto, la estructura de carpetas, cómo levantar el backend y enlaces a `backend/README.md`, `design/README.md`, `docs/` y `specs/`.
   El contenido técnico actual del backend pasa a **`backend/README.md`**, con los comandos desde `backend/`.
4. Las specs viejas (`specs/TAREA-*.md`) **no se reescriben**: son historia y sus rutas eran válidas cuando se hicieron.

## Después del merge (lo hace Carlos)
- La carpeta local `mvp-backoffice/backend` es la raíz del repo y ahora tendrá un `backend/` adentro. Conviene renombrarla, por ejemplo a `mvp-backoffice/real-estate-credit-backoffice`, con VS Code y los agentes cerrados.
- Si hay worktrees creados, después de renombrar se corre `git worktree repair` desde la carpeta principal, o se borran antes con `git worktree remove`.

## Definición de terminado
- CI verde en el PR, con el mismo check obligatorio.
- `git log --follow backend/apps/applications/services.py` muestra el historial completo.
- `docker compose up` desde `backend/` levanta todo y `/health` responde.
- `contracts/openapi.json` existe y el CI falla si queda desactualizado.
- Un commit por parte, en el orden 1 → 2 → 3, y luego squash merge.
