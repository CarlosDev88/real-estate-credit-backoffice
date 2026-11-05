"""Eventos de dominio del módulo applications.

Los módulos de actividad (paso 12), notificaciones (paso 13) y auditoría (paso 14) se
suscribirán para dejar la bitácora que exige RF-31 ("los cambios quedan auditados").
Se envían después de confirmar la transacción.

- ``application_created``: ``application`` y ``actor``.
- ``application_updated``: ``application``, ``fields`` (nombres de los campos que
  cambiaron) y ``actor``.
- ``application_assigned``: ``application``, ``previous_advisor_id``, ``advisor_id``,
  ``actor`` y ``reason``.
"""

from django.dispatch import Signal

application_created = Signal()
application_updated = Signal()
application_assigned = Signal()
