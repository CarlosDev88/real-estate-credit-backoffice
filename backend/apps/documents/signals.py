"""Eventos de dominio de la configuración documental y de la revisión del expediente.

La auditoría (paso 14) se suscribirá para registrar quién cambió qué documentos se
piden. Mientras tanto, el cambio se escribe en el log de la aplicación.

- ``document_type_status_changed``: ``document_type``, ``is_active``, ``actor`` y
  ``reason``.
- ``document_requirement_status_changed``: ``requirement``, ``from_status``,
  ``to_status`` y ``actor``. Al publicar una versión se emite también para la versión
  anterior del mismo alcance que pasa a ``INACTIVE``.
- ``document_reviewed``: ``slot``, ``document_file`` (la versión revisada; ``None`` al
  exonerar o reabrir un slot sin versión), ``review`` (la fila de ``document_reviews``)
  y ``actor``. Una vez por cada fila de revisión: aprobar y rechazar dejan una;
  exonerar y reabrir, una por slot afectado. Se envía después de confirmar la
  transacción (``transaction.on_commit``), así que una revisión dentro de otra
  operación (las observaciones de una devolución del banco) se emite cuando esa
  operación confirma. Lo usan las notificaciones (paso 13) y las tareas (paso 12).
"""

from django.dispatch import Signal

document_type_status_changed = Signal()
document_requirement_status_changed = Signal()
document_reviewed = Signal()
