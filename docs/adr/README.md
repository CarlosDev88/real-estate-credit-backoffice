# Registros de decisiones de arquitectura (ADR)

Un **ADR** (*Architecture Decision Record*) es una nota corta que registra **una** decisión de arquitectura: el problema que había, las opciones que se consideraron, lo que se eligió y lo que eso trae, bueno y malo. Sirve para que alguien que llega después entienda **por qué** el sistema es así y no de otra forma, sin tener que reconstruirlo desde el código.

Cada ADR de esta carpeta tiene la misma forma:

- **Estado:** aceptada, reemplazada o descartada.
- **Contexto:** qué problema había que resolver.
- **Opciones consideradas:** las alternativas reales, con su costo.
- **Decisión:** lo que se eligió, con las rutas del código donde vive.
- **Consecuencias:** lo que se gana, lo que se paga y lo que queda pendiente.

Las decisiones salen de los requerimientos ([`docs/REQUERIMIENTOS_MVP_CREDITO.md`](../REQUERIMIENTOS_MVP_CREDITO.md)) y de las "Precisiones acordadas" de cada [`specs/TAREA-*.md`](../../specs/). Se registraron el 18 de noviembre de 2026, sobre el código de `master`. Para el contexto general, ver la [guía del proyecto](../guia/00-indice.md).

## Lista

| # | Decisión | En una línea |
| ---: | --- | --- |
| [0001](0001-monolito-modular.md) | Monolito modular en Django + DRF | Una sola app y una sola base, partida en 16 apps con dueño de sus tablas. |
| [0002](0002-contrato-openapi-generado.md) | Contrato OpenAPI generado y tipos generados | El backend genera el contrato, el front sus tipos, y cada CI verifica que estén al día. |
| [0003](0003-jwt-en-cookies-y-mismo-origen.md) | JWT en cookies `HttpOnly` con CSRF y mismo origen | El token nunca toca JavaScript; Next.js reenvía `/api/v1` y no hace falta CORS. |
| [0004](0004-enlace-magico-sin-cuenta.md) | Enlace mágico sin cuenta para el comprador | Un solo uso, 72 h, sesión de 24 h ligada a una solicitud. |
| [0005](0005-alcance-por-rol-con-404.md) | Alcance por rol con `404` | Permiso por código en cada vista y consultas que nacen filtradas; lo ajeno no existe. |
| [0006](0006-auditoria-inmutable.md) | Auditoría inmutable con trigger | Tres capas, incluida PostgreSQL, y saneamiento único sin secretos. |
| [0007](0007-senales-despues-del-commit.md) | Señales después del commit en lugar de outbox | Efectos entre módulos desacoplados y receptores que nunca rompen la operación. |
| [0008](0008-idempotencia-opcional.md) | `Idempotency-Key` opcional | Una repetición devuelve la respuesta original sin romper a quien no manda la cabecera. |
| [0009](0009-concurrencia-optimista-etag.md) | Concurrencia optimista con `ETag` / `If-Match` | Nadie pisa la edición de otro; los documentos no tocan la versión. |
| [0010](0010-almacenamiento-privado-y-antivirus.md) | Almacenamiento privado, URL firmadas y antivirus | Tipo real por bytes y un antivirus que, si falla, no aprueba nada. |
| [0011](0011-celery-con-modo-inmediato.md) | Celery con modo inmediato en local | Las mismas tareas en un worker real o en el mismo proceso. |
| [0012](0012-nextjs-tanstack-tipos-generados.md) | Next.js App Router, TanStack Query y tipos generados | Una sola app con dos zonas, datos tipados y errores tratados por código. |
| [0013](0013-design-system-en-storybook.md) | Design system propio en Storybook con a11y en el CI | Tokens como fuente única, `axe` en cada story y sin colores a mano. |
| [0014](0014-comisiones-con-decimal.md) | Comisiones con `Decimal` y redondeo al peso | La suma de las partes siempre cuadra y la liquidación no cambia. |
| [0015](0015-modo-local-simple-y-completo.md) | Modo local simple y completo | Tres contenedores para la demo; la arquitectura asíncrona a un perfil de distancia. |
