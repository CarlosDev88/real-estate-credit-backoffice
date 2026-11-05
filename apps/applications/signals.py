"""Eventos de dominio del módulo applications.

Los módulos de actividad (paso 12), notificaciones (paso 13) y auditoría (paso 14) se
suscribirán para dejar la bitácora que exige RF-31 ("los cambios quedan auditados").
Se envían después de confirmar la transacción.

- ``application_created``: ``application`` y ``actor``.
- ``application_updated``: ``application``, ``fields`` (nombres de los campos que
  cambiaron) y ``actor``.
- ``application_assigned``: ``application``, ``previous_advisor_id``, ``advisor_id``,
  ``actor`` y ``reason``.
- ``participant_added``: ``application``, ``participant``, ``reactivated`` (si volvió un
  participante retirado) y ``actor``.
- ``participant_removed``: ``application``, ``participant`` y ``actor``.

Los cambios de un participante, de su perfil financiero o de sus fuentes de ingreso
salen por ``application_updated``, con ``fields`` como ``participants``,
``financial_profile`` o ``income_sources``.
"""

from django.dispatch import Signal

application_created = Signal()
application_updated = Signal()
application_assigned = Signal()
participant_added = Signal()
participant_removed = Signal()
