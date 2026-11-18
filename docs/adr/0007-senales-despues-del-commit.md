# ADR 0007 · Señales después del commit en lugar de un *outbox*

- **Estado:** aceptada (reemplaza la propuesta de REQ §8.3 y del DER).
- **Fecha:** se consolidó entre los módulos 11 y 16; registrada el 2026-11-18.
- **Fuentes:** REQ §8.3 (principio 7); precisión 1 del orquestador en [`specs/TAREA-comisiones.md`](../../specs/TAREA-comisiones.md); `backend/apps/*/signals.py` y `receivers.py`; [03 · Arquitectura §5](../guia/03-arquitectura.md#5-cómo-se-hablan-los-módulos-señales-después-del-commit).

## Contexto

Cuando pasa algo en el dominio (una respuesta del banco, un rechazo de documento), otros módulos deben reaccionar: avisar al comprador, escribir la actividad, auditar, liquidar la comisión. El diseño original proponía una tabla `outbox_events` escrita en la misma transacción y publicada por un proceso aparte.

## Opciones consideradas

1. **Llamadas directas** del servicio de dominio a cada módulo interesado. Acopla todo con todo y un error en un aviso rompería la operación.
2. **Outbox:** evento en una tabla dentro de la transacción y un publicador. Garantiza que ningún evento se pierda, a costa de una tabla, un proceso, una cola y su monitoreo.
3. **Señales de Django enviadas cuando la transacción ya confirmó**, con receptores idempotentes que nunca rompen la operación original.

## Decisión

Opción 3. Las señales se envían al salir del bloque atómico o con `transaction.on_commit`. Cada receptor trabaja en su propia transacción (`never_raises`: un error se registra y no se propaga) y es idempotente (clave de deduplicación de avisos, liquidación única, `status_history_id` en la actividad). La tabla `outbox_events` del SQL no se implementó.

## Consecuencias

- **A favor:** un módulo nuevo se engancha sin tocar los existentes (comisiones solo agregó un receptor de `filing_response_recorded`); el código de un receptor es una función simple de probar.
- **En contra (aceptado):** si el proceso muere entre el commit y el receptor, ese efecto no ocurre. Se mitiga donde importa: el trabajo que sale del sistema queda como estado en la base y tiene comandos de reintento (`retry_notification_deliveries`, `requeue_pending_scans`, `requeue_document_packages`), y la liquidación tiene un endpoint manual idempotente.
- **Escala:** los receptores corren en el proceso de la petición. Si se volvieran lentos, el siguiente paso sería moverlos a tareas o adoptar el outbox.
- **Desvío documentado:** 57 tablas en el código frente a 58 en el SQL.
