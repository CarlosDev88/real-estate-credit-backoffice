"""Eventos de dominio de la radicación (paso 11).

Los módulos de tareas (paso 12), notificaciones (paso 13), comisiones y auditoría
(paso 14) se suscribirán. Se envían después de confirmar la transacción, a
continuación de ``application_status_changed`` cuando la solicitud cambió de estado.

- ``filing_created``: ``filing``, ``application`` y ``actor``.
- ``filing_response_recorded``: ``response``, ``filing``, ``application``,
  ``status_changed`` (si la solicitud cambió de estado) y ``actor``. Un `DISBURSED`
  trae en ``response`` la fecha (``received_at``) y el monto desembolsado.
"""

from django.dispatch import Signal

filing_created = Signal()
filing_response_recorded = Signal()
