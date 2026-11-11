"""Eventos de dominio de la configuración documental.

La auditoría (paso 14) se suscribirá para registrar quién cambió qué documentos se
piden. Mientras tanto, el cambio se escribe en el log de la aplicación.

- ``document_type_status_changed``: ``document_type``, ``is_active``, ``actor`` y
  ``reason``.
- ``document_requirement_status_changed``: ``requirement``, ``from_status``,
  ``to_status`` y ``actor``. Al publicar una versión se emite también para la versión
  anterior del mismo alcance que pasa a ``INACTIVE``.
"""

from django.dispatch import Signal

document_type_status_changed = Signal()
document_requirement_status_changed = Signal()
