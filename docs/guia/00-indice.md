# Guía del proyecto

> **Borrador.** Este índice se completa en la última parte de la documentación. Los documentos marcados *(en preparación)* todavía no existen; sus enlaces funcionarán cuando se agreguen.

Esta guía explica **qué es** este proyecto, **cómo está hecho** y **por qué se decidió así**, sin tener que leer el código. Está escrita en español y en lenguaje simple: primero la idea y después el detalle técnico, siempre con la ruta del archivo de donde sale cada afirmación.

El proyecto es un MVP para gestionar **solicitudes de crédito de vivienda en Colombia**: un backoffice para el equipo interno (asesores, administradores, brokers y constructoras) y un portal donde el comprador completa sus datos y sube sus documentos desde el celular, sin crear cuenta.

## Por dónde empezar

| Si eres… | Lee en este orden | Para entender |
| --- | --- | --- |
| **Reclutador o perfil no técnico** | [01 · El producto](01-el-producto.md) → [11 · Cómo se construyó](11-como-se-construyo.md) → [12 · Auditorías](12-auditorias.md) | Qué problema resuelve, cómo se trabajó y qué se encontró y corrigió al revisarlo. |
| **Ingeniero o líder técnico** | [03 · Arquitectura](03-arquitectura.md) → [04 · System design](04-system-design.md) → [06 · Módulos](06-modulos.md) → [ADR](../adr/README.md) | Las piezas, los requisitos no funcionales, cada módulo y las decisiones con sus alternativas. |
| **Quien quiere correrlo** | [10 · Operación local](10-operacion-local.md) | Requisitos, la demo con un solo comando y los problemas comunes. |
| **Quien quiere entender el negocio** | [01 · El producto](01-el-producto.md) → [02 · Negocio](02-negocio.md) → [07 · Flujos](07-flujos.md) | Los roles, los estados, las reglas y el recorrido de punta a punta. |

## Mapa de la documentación

| Documento | De qué trata | Estado |
| --- | --- | --- |
| [01 · El producto](01-el-producto.md) | El problema, los cinco roles, el recorrido del comprador contado como historia, las 22 vistas y el glosario. | ✅ Listo |
| [02 · Negocio](02-negocio.md) | El crédito de vivienda como dominio: estados de la oportunidad y de la solicitud, documentos, radicación y respuestas del banco, comprador, consentimientos, notificaciones, reportes, comisiones y todas las decisiones de negocio con su porqué. | ✅ Listo |
| [03 · Arquitectura](03-arquitectura.md) | Contexto y contenedores (estilo C4), monolito modular, capas, señales entre módulos, contrato OpenAPI primero, mismo origen por el proxy de Next, los dos modos locales y el paso a producción. | ✅ Listo |
| [04 · System design](04-system-design.md) | Cada requisito no funcional (seguridad, concurrencia, asincronía, rendimiento, observabilidad, límites, privacidad, escalabilidad): qué pide, cómo se resolvió, dónde está y qué lo prueba, más lo que queda pendiente dicho claro. | ✅ Listo |
| [05 · Modelo de datos](05-modelo-de-datos.md) | Las 57 tablas por grupo con un diagrama entidad-relación de cada uno, las convenciones y los desvíos del SQL. | ✅ Listo |
| [06 · Módulos](06-modulos.md) | Los 16 módulos en orden de construcción: qué resuelve cada uno, sus tablas, endpoints, permisos, reglas, eventos, decisiones, pruebas y lo que quedó fuera. | ✅ Listo |
| [07 · Flujos](07-flujos.md) | La ruta crítica de punta a punta con diagramas de secuencia y de estados. | *(en preparación)* |
| [08 · Frontend](08-frontend.md) | App Router, `features/` por dominio, design system, datos tipados, formularios, errores, permisos y las 22 vistas. | *(en preparación)* |
| [09 · Calidad](09-calidad.md) | Estrategia de pruebas, números reales, CI con reporte en el PR, accesibilidad y contrato verificado. | *(en preparación)* |
| [10 · Operación local](10-operacion-local.md) | Cómo correrlo, la demo en un comando, los dos modos, comandos útiles y problemas comunes. | *(en preparación)* |
| [11 · Cómo se construyó](11-como-se-construyo.md) | El método: specs cerradas, agentes en paralelo, revisión, el CI como filtro y los errores reales que se atraparon. | *(en preparación)* |
| [12 · Auditorías](12-auditorias.md) | Las auditorías de seguridad, performance del front y carga del backend: qué se encontró y cómo se solucionó. | *(en preparación)* |
| [ADR](../adr/README.md) | Registros de decisiones de arquitectura: contexto, opciones, decisión y consecuencias. | *(en preparación)* |

## Documentación de referencia (ya existente)

Estos documentos son la especificación original. La guía los resume y los enlaza; cuando el código se desvió de ellos, la guía lo anota como "la spec decía X; quedó Y".

| Documento | Contenido |
| --- | --- |
| [Requerimientos](../REQUERIMIENTOS_MVP_CREDITO.md) | Alcance, actores, estados, requerimientos funcionales y no funcionales. |
| [API REST](../API_REST_MVP_CREDITO.md) | Convenciones, errores y cada grupo de endpoints. |
| [DER completo](../DER_COMPLETO_MVP_CREDITO.md) | Diagramas entidad-relación por módulo y orden de construcción. |
| [Modelo de datos](../MODELO_DATOS_DER_MVP_CREDITO.md) | Diccionario de tablas y columnas. |
| [Esquema PostgreSQL](../ESQUEMA_POSTGRESQL_MVP_CREDITO.sql) | El SQL de referencia. |
| [Contrato OpenAPI](../../contracts/openapi.json) | Generado por el backend; es la frontera con el frontend. |
| [Specs de construcción](../../specs/) | Cada tarea con sus decisiones ("Precisiones acordadas"). |
| `docs/SEGURIDAD.md`, `docs/PERFORMANCE.md`, `docs/DESIGN-SYSTEM.md` | *(en preparación por otros equipos de trabajo; se enlazarán aquí cuando existan)* |

## Convenciones de esta guía

- **Cada afirmación técnica lleva su fuente**: una ruta del repositorio (`backend/apps/filings/responses.py`) o una sección de un documento (REQ §4.5).
- **Las cifras llevan fecha.** Se contaron en `master`; la fecha está al principio de cada documento.
- **Cada diagrama tiene una línea "Qué mirar"** que dice qué buscar en él. Los diagramas son Mermaid y GitHub los muestra directamente.
- **Los términos del dominio** (radicar, legalización, deudor solidario…) están en el [glosario](01-el-producto.md#6-glosario).
