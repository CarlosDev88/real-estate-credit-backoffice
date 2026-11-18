# ADR 0012 · Next.js App Router, TanStack Query y tipos generados

- **Estado:** aceptada.
- **Fecha:** F0 del frontend; registrada el 2026-11-18.
- **Fuentes:** [`specs/TAREA-frontend-base.md`](../../specs/TAREA-frontend-base.md) ("Stack" y "Decisiones de arquitectura"); `frontend/package.json`; `frontend/src/providers/query-provider.tsx`; `frontend/src/lib/api/client.ts`, `fetch.ts`, `errors.ts`; [08 · Frontend](../guia/08-frontend.md).

## Contexto

Hay que construir 22 vistas para dos públicos muy distintos (un backoffice denso de escritorio y un portal móvil) que no pueden tener listas ni reglas de negocio propias (REQ §8.5), con varios agentes trabajando en paralelo sobre el mismo frontend.

## Opciones consideradas

1. **Dos frontends** (backoffice y portal por separado). Duplica autenticación, componentes y CI.
2. **SPA sin framework de rutas del servidor.** Sin un proxy de mismo origen propio ni renderizado inicial del tema.
3. **Next.js con App Router**, una sola app con grupos de rutas por zona, **TanStack Query** para los datos del servidor y un cliente tipado desde el contrato.
4. Para los datos: `fetch` a mano con estado local, o una librería de caché de servidor.

## Decisión

Una sola app **Next.js 16 (App Router)** con grupos `(auth)`, `(backoffice)` y `(portal)`, cada uno con su guardia y su shell; Ant Design 6 + Tailwind 4 sobre los tokens del design system; **TanStack Query 5** con un `MutationCache` global que muestra los errores de escritura, lecturas que no se reintentan ante un `4xx`, y `staleTime` de 30 s; **`openapi-fetch`** con los tipos de `openapi-typescript` generados desde `contracts/openapi.json` ([ADR 0002](0002-contrato-openapi-generado.md)); **React Hook Form + Zod** solo para el formato, con los errores de negocio de la API llevados a su campo. Filtros, página y pestaña en la URL.

## Consecuencias

- **A favor:** una llamada mal escrita no compila; los errores se tratan en un solo lugar por su código (`SESSION_EXPIRED`, `CONSENT_REQUIRED`, `STALE_VERSION`, `429`); cada `features/<dominio>` se desarrolla en paralelo sin pisar a los demás; el rewrite de Next resuelve el mismo origen ([ADR 0003](0003-jwt-en-cookies-y-mismo-origen.md)).
- **En contra:** las reglas de negocio llegan solo como errores de la API, así que algunos formularios descubren un problema recién al guardar; cada cambio del contrato exige regenerar los tipos.
- **Disciplina:** lo compartido (`components/ui`, `lib/`, `providers/`) cambia en PR pequeños y aparte.
