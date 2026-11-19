# ADR 0002 · Contrato OpenAPI generado por el backend y tipos generados en el front

- **Estado:** aceptada.
- **Fecha:** paso del monorepo y F0 del frontend; registrada el 2026-11-18.
- **Fuentes:** [`specs/TAREA-monorepo.md`](../../specs/TAREA-monorepo.md); [`specs/TAREA-frontend-base.md`](../../specs/TAREA-frontend-base.md) ("Cliente API"); `.github/workflows/backend.yml` y `frontend.yml`; `backend/tests/test_contract_names.py`, `test_etag_contract.py`; [03 · Arquitectura §6](../guia/03-arquitectura.md#6-el-contrato-openapi-primero).

## Contexto

El backend y el frontend se construyen en paralelo, a veces por agentes distintos al mismo tiempo. El frontend no debe adivinar la forma de una respuesta ni copiar listas de negocio (REQ §8.5), y un cambio del backend que rompe al front debe verse antes de fusionar, no en el navegador.

## Opciones consideradas

1. **Contrato escrito a mano** (YAML) como fuente de verdad, con el código implementándolo. Se desincroniza fácil del código real.
2. **Sin contrato**: el front usa tipos escritos a mano. Cada cambio del backend es una sorpresa.
3. **GraphQL**: descartado en REQ §2 ("GraphQL no forma parte de este proyecto").
4. **Contrato generado desde el código** del backend, versionado en el repo, del que el front genera sus tipos, con el CI verificando los dos lados.

## Decisión

drf-spectacular genera `contracts/openapi.json` (OpenAPI 3.1) desde las vistas y los serializers con `--validate --fail-on-warn`; el front genera `frontend/src/lib/api/schema.d.ts` con `openapi-typescript 7.13.0` y llama a la API con `openapi-fetch` tipado. Los dos archivos se commitean, y **cada CI los regenera y falla si hay diferencias**. Regla de oro: solo se agrega al contrato; nada publicado cambia de forma ni de nombre.

## Consecuencias

- **A favor:** una ruta mal escrita o un campo inexistente no compila en el front; un cambio incompatible del backend aparece en el mismo PR.
- **Costo:** cada cambio del backend exige regenerar el contrato **y** los tipos del front (lo recuerdan todas las specs).
- **Nombres inestables de enums:** drf-spectacular puede renombrar un enum si otro campo coincide. Se fijan en `ENUM_NAME_OVERRIDES` y los protege `backend/tests/test_contract_names.py`.
- **Cabeceras:** el contrato declara `ETag` donde la API lo envía; `backend/tests/test_etag_contract.py` lo exige.
- Tamaño al 18-11-2026: 175 rutas, 235 operaciones, 374 esquemas.
