# 12 · Auditorías: qué se encontró y cómo se solucionó

> **En simple:** además de las pruebas y el CI, el proyecto pasa por **tres auditorías independientes**: de seguridad, de rendimiento del frontend y de carga y estrés del backend. Cada una revisa con un método propio, deja su informe completo y una lista de hallazgos. Este documento junta las tres en lenguaje simple y, para cada hallazgo, cuenta **qué pasaba, por qué, qué se cambió, cómo se comprobó y en qué PR se cerró**.

> **Estado al 18 de noviembre de 2026: las tres auditorías están en curso.** Ninguna está fusionada en `master` todavía. Este documento deja la estructura completa y se llena al cierre, cuando terminen las correcciones. Lo que ya se sabe está marcado como tal.

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
| Seguridad | Autenticación, autorización por rol y objeto, archivos, datos personales, configuración | `docs/SEGURIDAD.md` *(en curso)* y `docs/seguridad/` *(en curso)* | SEC-01 a SEC-13 (por severidad: pendiente del informe) | 🔄 En curso, rama `chore/security-audit` |
| Rendimiento del frontend | Peso de las páginas, tiempos de carga y de interacción | `docs/PERFORMANCE.md` *(en curso)* | Pendiente | 🔄 En preparación |
| Carga y estrés del backend | Latencia bajo carga (el p95 < 800 ms de RNF-17), errores y límites | `docs/PERFORMANCE.md` *(en curso)* | Pendiente | 🔄 En preparación |

Los informes se enlazarán aquí cuando se fusionen sus ramas.

---

## 2. Seguridad

### 2.1 Qué se revisó y con qué método

El método completo se describe en el informe al cierre. Su pieza central es una **matriz de acceso**: cada una de las **235 operaciones** del contrato probada con cada uno de los **9 actores** que define la auditoría (su lista estará en el informe). **Lo que ya se sabe: la matriz no encontró brechas** de acceso (dato del orquestador, rama `chore/security-audit`). El informe completo y la lista de hallazgos estarán en `docs/SEGURIDAD.md` *(en curso)* y `docs/seguridad/hallazgos.md` *(en curso)*.

Puntos que [04 · System design §10](04-system-design.md#10-lo-que-queda-pendiente-dicho-claro) ya marcaba como pendientes frente a REQ y que la auditoría debería confirmar o descartar: cabeceras de seguridad (HSTS, CSP), límite general de la API, análisis de dependencias en el CI y MFA.

### 2.2 Hallazgos por severidad

| Severidad | Cuántos | Corregidos | Aceptados |
| --- | ---: | ---: | ---: |
| Crítica | — | — | — |
| Alta | — | — | — |
| Media | — | — | — |
| Baja | — | — | — |
| Informativa | — | — | — |
| **Total** | **13** (SEC-01 a SEC-13) | — | — |

### 2.3 Hallazgos y cómo se solucionó cada uno

| Id | Problema | Causa | Solución aplicada | Cómo se verificó | PR |
| --- | --- | --- | --- | --- | --- |
| SEC-01 | 🔄 En curso | | | | |
| SEC-02 | 🔄 En curso | | | | |
| SEC-03 | 🔄 En curso | | | | |
| SEC-04 | 🔄 En curso | | | | |
| SEC-05 | 🔄 En curso | | | | |
| SEC-06 | 🔄 En curso | | | | |
| SEC-07 | 🔄 En curso | | | | |
| SEC-08 | 🔄 En curso | | | | |
| SEC-09 | 🔄 En curso | | | | |
| SEC-10 | 🔄 En curso | | | | |
| SEC-11 | 🔄 En curso | | | | |
| SEC-12 | 🔄 En curso | | | | |
| SEC-13 | 🔄 En curso | | | | |

### 2.4 Aceptados, con su motivo

*(Se completa al cierre: un hallazgo aceptado es uno que no se corrige en el MVP, con el riesgo explicado y quién lo aceptó.)*

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

---

## 6. Cómo leer las tablas

- **Id:** el identificador del hallazgo en su informe (por ejemplo, `SEC-04`).
- **Problema:** qué pasaba, en una frase y sin jerga.
- **Causa:** por qué pasaba (la raíz, no el síntoma).
- **Solución aplicada:** qué se cambió y dónde, con la ruta del archivo.
- **Cómo se verificó:** la prueba que lo cubre ahora, la medición antes y después o el re-test del auditor.
- **PR:** el que lo cerró.
- **Aceptado:** un hallazgo que se decidió no corregir en el MVP, siempre con su motivo.
