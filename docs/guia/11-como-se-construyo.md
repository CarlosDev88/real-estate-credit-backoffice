# 11 · Cómo se construyó

> **En simple:** el proyecto lo construyeron **agentes de IA trabajando en paralelo**, cada uno en su propia copia del repositorio, a partir de **specs cerradas**: documentos que fijaban de antemano qué hacer, qué no tocar y qué decisiones ya estaban tomadas. Una persona, Carlos, tomó las decisiones de negocio, revisó cada parte, hizo todos los commits y fusionó cada PR. El CI fue el filtro final: nada entró sin las dos revisiones en verde.

Este documento cuenta el método tal como fue, incluidos los errores que se atraparon en el camino. Todo sale de [`specs/`](../../specs/), del historial de git y de los workflows.

---

## Índice

1. [Los papeles](#1-los-papeles)
2. [Specs cerradas](#2-specs-cerradas)
3. [Agentes en paralelo con carpetas propias](#3-agentes-en-paralelo-con-carpetas-propias)
4. [Git en solo lectura y el buzón](#4-git-en-solo-lectura-y-el-buzón)
5. [Revisión por partes](#5-revisión-por-partes)
6. [El CI como filtro](#6-el-ci-como-filtro)
7. [Errores reales que se atraparon](#7-errores-reales-que-se-atraparon)
8. [La línea de tiempo](#8-la-línea-de-tiempo)
9. [Lo que funcionó y lo que costó](#9-lo-que-funcionó-y-lo-que-costó)

---

## 1. Los papeles

| Quién | Qué hizo | Qué **no** hizo |
| --- | --- | --- |
| **Carlos** (el autor) | Fijó el alcance y las decisiones de negocio (el Anexo A de [`specs/TAREA-documentacion.md`](../../specs/TAREA-documentacion.md) las resume), aprobó cada parte, hizo los commits, abrió y fusionó los PR, configuró la protección de `master` y es el único que toca los `.env` | — |
| **El orquestador** (un agente de IA) | Escribió las specs a partir de los requerimientos, repartió el trabajo entre agentes, revisó los reportes, escribió las instrucciones de la siguiente parte en el buzón y resolvió algunos conflictos de fusión | No hizo commits |
| **Los agentes** (backend, frontend, design system, documentación, auditorías) | Escribieron el código, las pruebas, las migraciones y la documentación de su spec, en su carpeta | Ni commits, ni `push`, ni `merge`; no leen ni editan `.env*`; no tocan las carpetas de los otros |

El método no es "la IA escribió todo y ya": cada decisión que cambia el negocio pasó por Carlos, y cada línea entró por un PR con CI.

## 2. Specs cerradas

Cada tarea es un archivo `specs/TAREA-<nombre>.md` (25 en el repo, contando esta documentación). Todas tienen la misma forma:

1. **Objetivo** en pocas líneas, con las secciones de los requerimientos que cubre.
2. **Cuándo y dónde:** qué agente, qué carpeta y qué rama, desde qué commit, y qué está haciendo en paralelo otro agente (para no chocar).
3. **Reglas de trabajo:** git en solo lectura, no leer `.env`, pruebas acotadas, regenerar el contrato y los tipos del front al cerrar cada parte.
4. **Decisiones ya tomadas**, con su porqué (por ejemplo, las 4 de negocio al principio de [`specs/TAREA-radicacion.md`](../../specs/TAREA-radicacion.md)).
5. **Partes**, cada una con sus pruebas y su **mensaje de commit** propuesto.
6. **Cierre:** qué documentos actualizar, traer `master`, título y descripción del PR.
7. **Precisiones acordadas:** lo que el agente decidió por su cuenta durante el trabajo, con su motivo. Es la sección más valiosa para entender el código: casi todas las citas de esta guía salen de ahí.

**"No se presentan dudas."** Las primeras specs pedían al agente presentar cada ambigüedad con una recomendación y esperar ([`specs/TAREA-ci-reporte.md`](../../specs/TAREA-ci-reporte.md), línea 12). Con el proyecto andando se cambió a lo contrario: lo que la spec no cubre, el agente lo decide con la opción más simple, **lo anota en "Precisiones acordadas"** y sigue. Solo se detiene si la decisión rompe un contrato publicado, cambia el alcance, borra datos o exige tocar un `.env` (por ejemplo, [`specs/TAREA-radicacion.md`](../../specs/TAREA-radicacion.md), "Reglas de trabajo"). Así el trabajo no se frena en preguntas y cada decisión queda escrita para revisarla.

**Orden de construcción.** Los 16 módulos del backend se hicieron en el orden de dependencias del modelo de datos (DER §15): cada paso empezaba con los anteriores ya fusionados. Cuando un paso necesitaba algo de uno posterior, dejaba un punto de enganche que **fallaba cerrado** (por ejemplo, "¿hay una observación abierta?" devolvía siempre `False` hasta que llegó la radicación, decisión 5 de [`specs/TAREA-document-file.md`](../../specs/TAREA-document-file.md)).

## 3. Agentes en paralelo con carpetas propias

Para trabajar en paralelo sin pisarse, cada agente tuvo su **worktree**: una carpeta aparte con su propia rama, que comparte el mismo repositorio de git. Algunas, según sus specs:

| Carpeta | Rama | Tarea |
| --- | --- | --- |
| `wt-back-filings` | `feat/filings` | Radicación (módulo 11) |
| `wt-back-notifications` | `feat/notifications` | Notificaciones e idempotencia (13) |
| `wt-back-reports` | `feat/reports` | Reportes (15) |
| `wt-back-gaps` | `feat/backend-gaps` | Brechas del backend para los fronts |
| `wt-front-backoffice`, `wt-front-portal` | `feat/front-backoffice`, `feat/front-portal` | F1 y F2 del frontend, en paralelo |
| `wt-front-filings`, `wt-front-clients`, `wt-front-ops` | `feat/front-filings`, `feat/front-clients`, `feat/front-operations` | F3, F4 y F5 |
| `wt-front-ds` | `feat/design-system` | Design system en Storybook |
| `wt-docs` | `docs/project-guide` | Esta documentación |

Las reglas para convivir, escritas en las specs:

- **Cada agente toca solo lo suyo.** En el front, su grupo de rutas, sus carpetas de `features/` y su carpeta de `e2e/`; lo compartido (`components/ui`, `lib/`, `providers/`) va en un commit aparte y pequeño ([`specs/TAREA-frontend-base.md`](../../specs/TAREA-frontend-base.md), "Reglas para no chocar").
- **Base de pruebas propia.** Dos agentes corriendo pytest contra la misma base de pruebas se rompen entre sí; cada uno usó su `DATABASE_NAME` (por ejemplo `mvp_credit_filings`, que crea `test_mvp_credit_filings`) (Precisión de entorno de `TAREA-radicacion.md`; C.2 de [`specs/TAREA-brechas.md`](../../specs/TAREA-brechas.md)).
- **Contenedores de un solo uso.** Un agente de backend no levanta el `docker compose` (reiniciaría el backend que usan los demás en `:8000`): corre sus comandos en un `docker run --rm` que monta **su** carpeta (`TAREA-radicacion.md`, "Cómo corres el backend").
- **Puertos distintos** para los fronts en paralelo (3000 y 3001).
- **Poca memoria:** con cuatro agentes a la vez, cada uno corre solo las pruebas de lo que toca; la suite completa es del CI ([`specs/TAREA-auditoria.md`](../../specs/TAREA-auditoria.md), "Reglas de trabajo").

## 4. Git en solo lectura y el buzón

**Ningún agente escribe en git.** Ni `commit`, ni `add`, ni `mv`, ni `push`, ni `merge` (la regla aparece en 16 specs). Al cerrar cada parte, el agente propone el mensaje de commit exacto y Carlos hace el commit, **sin firmas ni `Co-Authored-By`**. Cuando hay que mover archivos, se escribe el nuevo y se borra el viejo, y git lo detecta al hacer el commit.

Por qué: el historial queda limpio y con un solo autor responsable; un agente no puede reescribir la historia ni empujar algo sin revisión.

**El buzón** es una carpeta `.buzon/` en cada worktree, **fuera de git** (excluida en `.git/info/exclude`), por donde se comunican el orquestador y el agente:

- `ESTADO.md`: lo actualiza el agente en cada paso (`trabajando`, `esperando listo`, `bloqueado`).
- `reportes/AAAA-MM-DD_parte-N.md`: el reporte completo de cada parte (qué se hizo, verificaciones con números, decisiones, archivos tocados, pendientes y el mensaje de commit).
- `PARA-AGENTE.md`: las instrucciones de la siguiente parte, que escribe el orquestador.

En la consola, el agente dice una sola línea: "Parte N lista, reporte en .buzon/reportes/…". Así el detalle no se pierde en el historial de una terminal.

## 5. Revisión por partes

Cada spec se parte en 2 a 7 partes. Al cerrar una, el agente entrega:

1. las verificaciones en verde, con sus comandos y números (`ruff`, `mypy .`, `makemigrations --check`, `spectacular --validate --fail-on-warn`, pruebas acotadas; en el front, `lint`, `typecheck`, pruebas, cobertura y `build`);
2. la lista corta de decisiones que tomó;
3. el mensaje de commit.

Y **espera el "listo"** antes de seguir. La revisión no es un trámite: varias correcciones de esta guía y del código salieron de ahí (por ejemplo, la inactividad del comprador por asesor, P0.12 de [`specs/TAREA-brechas.md`](../../specs/TAREA-brechas.md), o el botón "Registrar respuesta" que dejó de ser el principal después de ver las capturas, [`specs/TAREA-front-radicacion.md`](../../specs/TAREA-front-radicacion.md), Precisión 10).

## 6. El CI como filtro

Por encima de todo, el CI ([09 · Calidad §3](09-calidad.md#3-el-ci-dos-revisiones-obligatorias)): dos jobs obligatorios en `protect-master`, todas las verificaciones corren aunque una falle, y el reporte queda en el PR. Un agente puede equivocarse al declarar algo en verde; el CI no se lo cree: regenera el contrato y los tipos y compara, corre la suite completa con cobertura mínima, y compila Storybook con `axe`.

## 7. Errores reales que se atraparon

Los que pide la spec, con su fuente. Cuando la spec no lo cuenta como incidente y la evidencia es un commit o el código, se dice.

| Error | Causa | Cómo se resolvió | Fuente |
| --- | --- | --- | --- |
| **El grupo de concurrencia del CI compartido** | Los dos workflows corren en cada PR; con el mismo grupo `ci-<ref>` y `cancel-in-progress`, uno cancelaba al otro | El front tiene su propio grupo `ci-frontend-<ref>`, con un comentario que lo explica | `.github/workflows/frontend.yml`, línea 10; `specs/TAREA-frontend-base.md` (Parte 6 de F0), que lo fija como regla y pide verificar "que ninguno de los dos workflows cancele al otro" |
| **El reloj de Docker** | El reloj de la máquina virtual de Docker retrocedía hasta 10,5 s (10 veces en 60 s); eso invalidaba el `nbf`/`iat` de los JWT y daba `401 SESSION_EXPIRED` al azar en cualquier módulo | Del entorno: reiniciar Docker Desktop. Y dos arreglos en el código que eran correctos también en producción: la última evaluación bancaria se elige por **versión** y no por fecha (con una prueba que falla con el orden anterior), y la fecha por defecto de una radicación en el front va un minuto en el pasado | `specs/TAREA-radicacion.md` (Cierre, punto 5); PC.2 de `specs/TAREA-tareas-actividad.md`; `specs/TAREA-front-radicacion.md` |
| **El botón destructivo como principal** | `available_actions` no decía cuál acción era la principal; en la demo, la primera era "Cancelar solicitud" y quedaba como botón principal | El backend agregó `AvailableAction.kind` (`primary`, `secondary`, `destructive`), decidido por el estado destino; el front toma como principal la primera `primary` | `specs/TAREA-front-backoffice.md` (brechas); `specs/TAREA-frontend-base.md` (brechas de la F1); Agregado 2b de `specs/TAREA-tareas-actividad.md` (PR #20) |
| **Migraciones con el mismo número** | Reportes (#25) y comisiones (#27) agregaron cada uno una migración de acciones a `audit`; las dos nacieron como `0004` en ramas distintas | La de comisiones quedó como `0005_commission_actions.py`, dependiente de `0004_report_actions` (renumerada, sin migración de fusión). La spec no lo narra; la evidencia es el archivo y su dependencia | `backend/apps/audit/migrations/`; P1.9 de `specs/TAREA-comisiones.md` (que todavía dice `audit.0004`) |
| **La prueba de idempotencia con la lista a mano** | La prueba que verifica qué operaciones declaran `Idempotency-Key` compara contra una lista escrita a mano; al sumar `@idempotent` a los tres `POST` de comisiones, la lista quedó vieja y la prueba falló | Se agregaron las tres operaciones a la lista, en un commit propio del PR #27 ("test(idempotency): list the commission operations that accept Idempotency-Key"). Es una prueba que funcionó como debía: obliga a decidir a conciencia | `backend/tests/applications/idempotency/test_idempotency.py` |
| **Imports rotos después de mover componentes** | `FormField` y `useFormErrorHandler` pasaron de `features/applications` a `components/ui/form-field.tsx` (y el design system borró copias locales de otros componentes); la F4 seguía importando la ruta vieja. La spec no lo narra como incidente: la evidencia es el commit | Un commit dentro del PR #26: "fix(frontend): import FormField from components/ui and give the filing select helper more time" | `specs/TAREA-front-portal.md` (Precisiones); Parte 3 de `specs/TAREA-design-system.md` |

Otros que quedaron escritos en las Precisiones:

| Error | Cómo se atrapó y se resolvió | Fuente |
| --- | --- | --- |
| Dos usuarios internos con la misma clave de idempotencia chocaban | Lo detectó la prueba "clave de otro actor": `UNIQUE NULLS NOT DISTINCT` trataba igual los nulos del comprador. Se cambió por únicos parciales y se corrigió el SQL | `specs/TAREA-notificaciones.md`, Parte 3, P8 |
| La re-radicación fallaba con `PACKAGE_ALREADY_FILED` | Pedir un paquete después de una devolución sin cambios devolvía el ya radicado. Los paquetes radicados dejaron de reutilizarse | `specs/TAREA-radicacion.md`, Parte 2, P3 |
| Una liquidación anulada impedía volver a liquidar | `UNIQUE (filing_response_id)` total; pasó a único parcial entre las vigentes | `specs/TAREA-comisiones.md`, P2.4 |
| drf-spectacular renombró un enum ya publicado | Al agregar otro campo `code`, `CodeEnum` cambiaba de nombre y rompía los tipos del front. Se fijaron los nombres y se agregó `tests/test_contract_names.py` | `specs/TAREA-tareas-actividad.md`, P1.10 |
| Un `default=""` volvía obligatorio un campo en los tipos del front | `openapi-typescript` marcó `notes` como requerido y rompía la F4; se quitó el `default` | `specs/TAREA-brechas-2.md`, Parte 3 |
| Una tabla "cargando" fallaba la accesibilidad | El 60 % de opacidad bajaba el contraste de 4,5:1 y `axe` lo marcó como serio; se cambió por una barra de progreso | `specs/TAREA-design-system.md`, Parte 2 |
| Stories que fallaban al azar | Vite reoptimizaba dependencias en medio de la corrida; se fijaron en `optimizeDeps.include` | `specs/TAREA-design-system.md`, Parte 2 |
| Calcular la completitud por fila era caro | Se midió (6 a 10 consultas por fila) antes de decidir, y se guardó el valor en la solicitud | `specs/TAREA-applications-listado.md`, Precisión A |

## 8. La línea de tiempo

El historial de `master` (`git log --oneline`) tiene 30 PR numerados, del #1 al #31 (el #13 no aparece en `master`). Antes del primer PR entraron, como commits directos, la base de Django y los módulos 1 a 4 (identidad, catálogos, constructoras, invitaciones y usuarios). En grandes bloques:

| PR | Qué entró |
| --- | --- |
| — | Base del backend y módulos 1 a 4 (`cc0998e` a `91cdbdd`) |
| #1 | CI del backend |
| #2 a #8 | CRM, bancos, tipos documentales, solicitudes, acceso del comprador y expediente documental |
| #9, #10 | Tokens del design system y correcciones de su auditoría |
| #11, #12 | Monorepo con el contrato OpenAPI y el reporte del CI en el PR |
| #14, #15 | Modo local simple y la base del frontend (F0) con su CI |
| #16 a #18 | Campos del listado, backoffice (F1) y brechas para el front |
| #19 a #25 | Radicación (11), Mi día y actividad (12), portal (F2), pestaña de radicación (F3), notificaciones e idempotencia (13), auditoría (14) y reportes (15) |
| #26 a #31 | Clientes (F4), comisiones (16), design system en Storybook, README, operación (F5) y segundas brechas del backend |

Esta documentación va en un PR propio (#35) y, aparte, la demo con un solo comando.

## 9. Lo que funcionó y lo que costó

**Funcionó:**

- **Escribir las decisiones.** Las "Precisiones acordadas" hicieron posible esta guía: cada comportamiento raro del código tiene su porqué escrito al lado.
- **El contrato como frontera.** Back y front se construyeron en paralelo sin romperse, porque el CI compara el contrato y los tipos en cada PR.
- **Fallar cerrado** en los puntos de enganche: nada quedó "medio habilitado" mientras faltaba el módulo siguiente.
- **Pruebas que obligan a decidir** (la lista de idempotencia, los nombres de enums, el `ETag` declarado, los colores fijos): cuando algo cambia, una prueba pide confirmarlo.

**Costó:**

- **El entorno compartido:** bases de pruebas, puertos, memoria y el reloj de Docker dieron fallas que no eran del código.
- **Fusionar ramas paralelas** que tocan los mismos archivos de enganche (receptores de señales, `ENUM_NAME_OVERRIDES`, el README): se resolvió "quedándose con los dos lados" a mano y regenerando el contrato.
- **Las brechas entre back y front:** cada fase del front encontró datos que la API no daba (etiquetas, conteos, formas por rol) y se juntaron en tareas de "brechas" ([`specs/TAREA-brechas.md`](../../specs/TAREA-brechas.md), [`specs/TAREA-brechas-2.md`](../../specs/TAREA-brechas-2.md)) con una regla: solo se agrega al contrato.
- **Documentos que se quedan atrás:** el README raíz todavía decía "15 de 16 módulos" cuando comisiones ya estaba fusionado; por eso esta guía cuenta desde el código.
