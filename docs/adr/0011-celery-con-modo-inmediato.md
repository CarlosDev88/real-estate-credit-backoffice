# ADR 0011 · Celery con modo inmediato en local

- **Estado:** aceptada.
- **Fecha:** módulo 10 (antivirus y paquetes) y tarea del modo local simple; registrada el 2026-11-18.
- **Fuentes:** REQ §8.3 (principio 7), RNF-17, RNF-19; Tanda 1 decisión 2 de [`specs/TAREA-document-file.md`](../../specs/TAREA-document-file.md); Parte 2 y Precisión 5 de [`specs/TAREA-local-simple.md`](../../specs/TAREA-local-simple.md); Parte 2 de [`specs/TAREA-notificaciones.md`](../../specs/TAREA-notificaciones.md); `backend/config/celery.py`, `backend/config/settings/base.py`; [04 · System design §4](../guia/04-system-design.md#4-trabajo-asíncrono).

## Contexto

El antivirus, el ZIP del expediente, el correo y los CSV grandes no deben bloquear la petición HTTP y deben poder reintentarse. Pero levantar Redis, un worker y ClamAV para probar el proyecto en una máquina con poca memoria es caro.

## Opciones consideradas

1. **Todo dentro de la petición.** Bloquea al usuario y un fallo externo rompe la operación.
2. **Siempre con worker y broker**, también en local. Más contenedores y memoria para cualquiera que quiera ver la demo.
3. **Celery con dos modos**: worker real con Redis en el modo completo, y **modo inmediato** (`CELERY_TASK_ALWAYS_EAGER`) en el modo simple, donde la tarea corre en el mismo proceso después del commit.

## Decisión

Opción 3. Cinco tareas (`scan_file_object`, `build_document_package`, `scan_filing_evidence`, `deliver_notification_email`, `build_report_export`), todas idempotentes, que solo reciben ids, con `acks_late` y reintentos con espera creciente. Se encolan con `on_commit`. En modo inmediato: el broker es `memory://` (nada se conecta a Redis) y `CELERY_TASK_EAGER_PROPAGATES = False`, así un fallo de la tarea queda en el log y en el estado del archivo o paquete, nunca en la respuesta al usuario.

## Consecuencias

- **A favor:** la demo corre con 3 contenedores; el código de las tareas es el mismo en los dos modos.
- **En contra:** en modo inmediato Celery ignora el `countdown`, así que los reintentos corren seguidos dentro de la petición; con `clamd` caído, una carga podría esperar minutos. Por eso el modo inmediato va con el escáner de prueba.
- **Diseño por eso:** la tarea del correo no usa `self.retry`; en modo inmediato no reintenta en el acto y la retoma `retry_notification_deliveries` cuando vence su espera.
- **Pendiente para producción:** agendar los comandos periódicos (no hay `beat_schedule`).
