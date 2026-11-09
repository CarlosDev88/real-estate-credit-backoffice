# Tarea: CI del backend con GitHub Actions

## Objetivo
Que cada push a `master` y cada pull request corran automáticamente, en una máquina limpia de GitHub, las mismas verificaciones que hoy corro en local: ruff, mypy, migraciones y pytest. Si algo falla, el PR queda en rojo.

## Contexto del repo (verificado)
- Repo: `CarlosDev88/real-estate-credit-backoffice` (hoy el repo es solo `backend/`; más adelante será monorepo).
- Python 3.11 (Dockerfile y `pyproject.toml`).
- Dependencias: `requirements.txt` (incluye pytest, pytest-django, pytest-cov, ruff, mypy, django-stubs).
- Pytest usa `--ds=config.settings.test` (ver `pytest.ini`).
- `config/settings/test.py` usa caché en memoria y email locmem: **las pruebas solo necesitan PostgreSQL**, no Redis.
- `config/settings/base.py` lee de entorno: `DJANGO_SECRET_KEY`, `AUTH_JWT_SIGNING_KEY`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_HOST`, `DATABASE_PORT`.
- mypy usa `django_settings_module = "config.settings.local"` (en `pyproject.toml`), que importa `base.py`: necesita las mismas variables de entorno.

## Qué crear
Archivo `.github/workflows/backend.yml` con este contenido como punto de partida:

```yaml
name: Backend CI

on:
  push:
    branches: [master]
  pull_request:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  quality:
    name: Lint, types and tests
    runs-on: ubuntu-latest
    timeout-minutes: 15

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: mvp_credit
          POSTGRES_USER: mvp_credit_user
          POSTGRES_PASSWORD: ci_password
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U mvp_credit_user -d mvp_credit"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10

    env:
      DJANGO_SETTINGS_MODULE: config.settings.test
      DJANGO_SECRET_KEY: ci-secret-key-not-for-production
      AUTH_JWT_SIGNING_KEY: ci-jwt-signing-key-not-for-production
      DATABASE_HOST: localhost
      DATABASE_PORT: "5432"
      DATABASE_NAME: mvp_credit
      DATABASE_USER: mvp_credit_user
      DATABASE_PASSWORD: ci_password

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Ruff (lint)
        run: ruff check .

      - name: Ruff (format)
        run: ruff format --check .

      - name: Mypy
        run: mypy .

      - name: Migrations are up to date
        run: python manage.py makemigrations --check --dry-run

      - name: Tests
        run: pytest --cov=apps --cov-report=term-missing
```

## Reparto: el agente edita, Carlos hace git
El agente **no ejecuta** `git commit`, `git push`, `git switch`, `git stash`, `git rebase` ni `git merge`, y no abre PRs. Solo puede usar git en modo lectura (`git status`, `git diff`, `git log`). Carlos hace todos los commits, pushes y PRs.

## Pasos
1. (Carlos) Ya estás en la rama `ci/backend-workflow`, creada desde `master` limpio.
2. (Agente) Corre en local, dentro del contenedor, los mismos comandos del CI y reporta el resultado de cada uno:
   - `docker compose run --rm backend ruff check .`
   - `docker compose run --rm backend ruff format --check .`
   - `docker compose run --rm backend mypy .`
   - `docker compose run --rm backend python manage.py makemigrations --check --dry-run`
   - `docker compose run --rm backend pytest`
3. (Agente) Si `ruff format --check` falla, corre `ruff format .`. Si ruff o mypy reportan errores reales, corrígelos sin cambiar lógica de negocio. Si un error no se puede corregir sin cambiar lógica, **para y pregúntame**.
4. (Agente) Crea `.github/workflows/backend.yml` con el contenido de arriba.
5. (Agente) Agrega el badge al inicio del `README.md`, debajo del título:
   `[![Backend CI](https://github.com/CarlosDev88/real-estate-credit-backoffice/actions/workflows/backend.yml/badge.svg)](https://github.com/CarlosDev88/real-estate-credit-backoffice/actions/workflows/backend.yml)`
6. (Agente) Al terminar, entrégame la **propuesta de commits**: qué archivos van en cada uno y el mensaje. Por ejemplo:
   - `style: apply ruff format` (solo cambios de formato)
   - `fix(types): ...` o `fix(lint): ...` (si hubo correcciones)
   - `ci: add backend workflow (ruff, mypy, migrations, pytest)` (workflow y badge)
7. (Carlos) Hace los commits, el push y abre el PR hacia `master`.
8. (Agente) Si el CI falla en GitHub, Carlos le pasa el log. El agente propone el plan de corrección y espera aprobación antes de editar. Después vuelve al paso 6.
9. (Carlos) Cuando el CI esté en verde, hace el merge.

## Criterios de "terminado"
- [ ] El workflow corre en push a `master` y en cada PR.
- [ ] Los 5 pasos (ruff check, ruff format, mypy, migraciones, pytest) pasan en GitHub.
- [ ] Los 256 tests (o más) pasan en CI, el mismo número que en local.
- [ ] El badge aparece en el README y está en verde.
- [ ] No se agregó ningún secreto real: solo valores de prueba en el YAML.

## Restricciones
- No bajar la exigencia de mypy ni de ruff (no tocar `pyproject.toml` para silenciar errores) sin preguntarme.
- No agregar `# type: ignore` ni `# noqa` sin justificarlo en el mensaje del commit.
- No modificar lógica de negocio para que pase el CI.
- No ejecutar comandos de git que modifiquen el repositorio: commits, push, ramas y PRs los hace Carlos.

## Para después (monorepo)
Cuando el repo pase a tener `backend/` y `frontend/`, agregar en el workflow:
```yaml
on:
  push:
    branches: [master]
    paths: ["backend/**", ".github/workflows/backend.yml"]
  pull_request:
    paths: ["backend/**", ".github/workflows/backend.yml"]

defaults:
  run:
    working-directory: backend
```
y el `cache-dependency-path: backend/requirements.txt` en `setup-python`.
