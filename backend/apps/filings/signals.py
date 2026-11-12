"""Eventos de dominio de la radicación (paso 11).

Los módulos de tareas (paso 12), notificaciones (paso 13) y auditoría (paso 14) se
suscribirán. Se envían después de confirmar la transacción, a continuación de
``application_status_changed``.

- ``filing_created``: ``filing``, ``application`` y ``actor``.
"""

from django.dispatch import Signal

filing_created = Signal()
