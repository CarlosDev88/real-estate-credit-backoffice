# ADR 0006 · Auditoría inmutable con trigger de PostgreSQL

- **Estado:** aceptada.
- **Fecha:** módulo 14; registrada el 2026-11-18.
- **Fuentes:** RNF-04, REQ §9.5, API §24.1; [`specs/TAREA-auditoria.md`](../../specs/TAREA-auditoria.md); `backend/apps/audit/` (`models.py`, `sanitize.py`, `hooks.py`, `receivers.py`, `retention.py`, `migrations/0002_block_updates_trigger.py`).

## Contexto

Para investigar un incidente hace falta saber quién hizo qué, sobre qué, con qué resultado, desde dónde y con qué `request_id`, y esa bitácora no puede poder alterarse, ni siquiera por un error del propio código. Tampoco puede guardar secretos.

## Opciones consideradas

1. **Reutilizar la actividad** del expediente. Es funcional, la leen asesores y compradores, y no cubre login, `403` ni configuración.
2. **Logs de texto.** Sin estructura para consultar y sin garantía de inmutabilidad.
3. **Tabla propia inmutable**, protegida en la aplicación **y** en la base, con saneamiento único.

## Decisión

Tabla `audit_events`, inmutable en tres capas: el modelo rechaza `save()` sobre una fila existente y `delete()`; el `QuerySet` rechaza `update()` y `delete()` salvo en la retención (`allow_purge()`); y un trigger de PostgreSQL bloquea todo `UPDATE`, también por SQL directo. Los eventos llegan por señales del dominio y por `audit_actions` en las vistas; todo `403` y todo `429` se registran. Un saneamiento único descarta claves con `password`, `token`, `cookie`, `url`…, enmascara documentos y reemplaza URL con consulta. De una vista se guardan los **nombres** de los campos enviados, nunca los valores. Solo el admin la lee. Lo fallido dentro de una transacción se escribe por una conexión aparte, para que el rollback no lo borre.

## Consecuencias

- **A favor:** ni un bug ni un `UPDATE` manual reescriben la historia; una prueba automática revisa cada evento escrito en las pruebas y falla si encuentra datos prohibidos.
- **En contra:** borrar solo es posible por retención (`purge_audit_events`, 365 días); la conexión aparte agrega una conexión a la base; un evento cuyo actor se creó en la misma transacción fallida se pierde (queda en el log; límite conocido, P1.2).
- **Alcance:** las lecturas permitidas del expediente no se auditan en el MVP; su traza funcional es la actividad.
