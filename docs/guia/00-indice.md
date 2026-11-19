# Guía del proyecto

Esta guía explica **qué es** este proyecto, **cómo está hecho** y **por qué se decidió así**, sin tener que leer el código. Está escrita en español y en lenguaje simple: primero la idea y después el detalle técnico, siempre con la ruta del archivo de donde sale cada afirmación.

El proyecto es un MVP para gestionar **solicitudes de crédito de vivienda en Colombia**: un backoffice para el equipo interno (asesores, administradores, brokers y constructoras) y un portal donde el comprador completa sus datos y sube sus documentos desde el celular, sin crear cuenta. Corre en local y en CI; no tiene despliegue.

## En cifras

Contado en `master` el **18 de noviembre de 2026**:

| Qué | Cuánto | Dónde se explica |
| --- | ---: | --- |
| Módulos del backend (apps de Django) | 16 | [06 · Módulos](06-modulos.md) |
| Tablas propias en PostgreSQL | 57 | [05 · Modelo de datos](05-modelo-de-datos.md) |
| Operaciones de la API (contrato OpenAPI 3.1) | 235 | [03 · Arquitectura §6](03-arquitectura.md#6-el-contrato-openapi-primero) |
| Vistas del producto (14 de operación y 8 del portal) | 22 | [01 · El producto §5](01-el-producto.md#5-las-22-vistas) |
| Funciones de prueba del backend · cobertura mínima | 1.794 · 95 % | [09 · Calidad](09-calidad.md#2-los-números) |
| Archivos de prueba del frontend · cobertura mínima | 45 · 70 % | [09 · Calidad](09-calidad.md#2-los-números) |
| Revisiones obligatorias del CI por PR | 2 | [09 · Calidad §3](09-calidad.md#3-el-ci-dos-revisiones-obligatorias) |
| Decisiones de arquitectura registradas | 15 | [ADR](../adr/README.md) |

## Por dónde empezar

| Si eres… | Lee en este orden | Para entender |
| --- | --- | --- |
| **Reclutador o perfil no técnico** | [01 · El producto](01-el-producto.md) → [11 · Cómo se construyó](11-como-se-construyo.md) → [12 · Auditorías](12-auditorias.md) | Qué problema resuelve, cómo se trabajó y qué se encontró y corrigió al revisarlo. |
| **Ingeniero o líder técnico** | [03 · Arquitectura](03-arquitectura.md) → [04 · System design](04-system-design.md) → [06 · Módulos](06-modulos.md) → [ADR](../adr/README.md) | Las piezas, los requisitos no funcionales, cada módulo y las decisiones con sus alternativas. |
| **Quien quiere correrlo** | 10 · Operación local *(en preparación)*; mientras tanto, [`backend/README.md`](../../backend/README.md) ("Quick Start") | Requisitos, la demo con un solo comando y los problemas comunes. |
| **Quien quiere entender el negocio** | [01 · El producto](01-el-producto.md) → [02 · Negocio](02-negocio.md) → [07 · Flujos](07-flujos.md) | Los roles, los estados, las reglas y el recorrido de punta a punta. |
| **Quien va a tocar el frontend** | [08 · Frontend](08-frontend.md) → [09 · Calidad](09-calidad.md) → [ADR 0012](../adr/0012-nextjs-tanstack-tipos-generados.md) y [0013](../adr/0013-design-system-en-storybook.md) | La estructura, los datos tipados, los errores y lo que revisa el CI. |

## Mapa de la documentación

| Documento | De qué trata | Estado |
| --- | --- | --- |
| [01 · El producto](01-el-producto.md) | El problema, los cinco roles, el recorrido del comprador contado como historia, las 22 vistas y el glosario. | ✅ |
| [02 · Negocio](02-negocio.md) | El crédito de vivienda como dominio: estados de la oportunidad y de la solicitud, documentos, radicación y respuestas del banco, comprador, consentimientos, notificaciones, reportes, comisiones y todas las decisiones de negocio con su porqué. | ✅ |
| [03 · Arquitectura](03-arquitectura.md) | Contexto y contenedores (estilo C4), monolito modular, capas, señales entre módulos, contrato OpenAPI primero, mismo origen por el proxy de Next, los dos modos locales y el paso a producción. | ✅ |
| [04 · System design](04-system-design.md) | Cada requisito no funcional (seguridad, concurrencia, asincronía, rendimiento, observabilidad, límites, privacidad, escalabilidad): qué pide, cómo se resolvió, dónde está y qué lo prueba, más lo que queda pendiente dicho claro. | ✅ |
| [05 · Modelo de datos](05-modelo-de-datos.md) | Las 57 tablas por grupo con un diagrama entidad-relación de cada uno, las convenciones y los desvíos del SQL. | ✅ |
| [06 · Módulos](06-modulos.md) | Los 16 módulos en orden de construcción: qué resuelve cada uno, sus tablas, endpoints, permisos, reglas, eventos, decisiones, pruebas y lo que quedó fuera. | ✅ |
| [07 · Flujos](07-flujos.md) | La ruta crítica de punta a punta en seis flujos con diagramas de secuencia, y lo que valida el backend en cada paso. | ✅ |
| [08 · Frontend](08-frontend.md) | App Router, `features/` por dominio, design system, datos tipados, formularios, errores, permisos, portal móvil, accesibilidad y las 22 vistas con sus endpoints. | ✅ |
| [09 · Calidad](09-calidad.md) | Estrategia de pruebas, números reales, CI con reporte en el PR, contrato verificado, la regla de colores y lo que el CI no cubre. | ✅ |
| 10 · Operación local | Cómo correrlo, la demo en un comando, los dos modos, comandos útiles y problemas comunes. | *(en preparación)* |
| [11 · Cómo se construyó](11-como-se-construyo.md) | El método: specs cerradas, agentes en paralelo, revisión, el CI como filtro y los errores reales que se atraparon. | ✅ |
| [12 · Auditorías](12-auditorias.md) | Las auditorías de seguridad, performance del front y carga del backend: qué se encontró y cómo se solucionó. | 🔄 Estructura lista; se llena al cierre de las auditorías |
| [ADR](../adr/README.md) | 15 registros de decisiones de arquitectura, cada uno con contexto, opciones, decisión y consecuencias. | ✅ |

## Documentación de referencia

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
| [`backend/README.md`](../../backend/README.md) | Módulos del backend, modos locales, comandos y convenciones (en inglés). |
| `docs/SEGURIDAD.md`, `docs/PERFORMANCE.md`, `docs/DESIGN-SYSTEM.md` | *(en curso, por otros equipos de trabajo; se enlazarán aquí cuando estén en `master`)* |

## Convenciones de esta guía

- **Cada afirmación técnica lleva su fuente**: una ruta del repositorio (`backend/apps/filings/responses.py`) o una sección de un documento (REQ §4.5 es la sección 4.5 de los requerimientos).
- **Las cifras llevan fecha.** Se contaron en `master` el 18 de noviembre de 2026, sin correr las suites.
- **Cada diagrama tiene una línea "Qué mirar"** que dice qué buscar en él. Los diagramas son Mermaid y GitHub los muestra directamente.
- **Lo que no está hecho se dice.** Las secciones "Lo que queda pendiente" ([04 §10](04-system-design.md#10-lo-que-queda-pendiente-dicho-claro)) y "Qué no cubre el CI" ([09 §7](09-calidad.md#7-qué-no-cubre-el-ci)) existen para eso.
- **Los términos del dominio** (radicar, legalización, deudor solidario…) están en el [glosario](01-el-producto.md#6-glosario).
- Lo que está en otra rama y todavía no en `master` se marca *(en curso)*; lo que falta escribir, *(en preparación)*.
