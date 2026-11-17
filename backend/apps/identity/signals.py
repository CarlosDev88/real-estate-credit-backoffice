"""Eventos de dominio del acceso del comprador.

- ``buyer_access_consumed``: ``link`` (el enlace consumido) y ``session`` (la sesión que
  abrió). Se envía después de confirmar la transacción del consumo. Lo usan las
  notificaciones (paso 13) para dar la bienvenida al portal.
- ``buyer_access_link_issued``: ``link`` (el enlace nuevo) y ``actor`` (quien lo
  emitió). Se envía después de confirmar la transacción. Lo usa la actividad (paso 12).
- ``consent_recorded``: ``record`` (la fila de ``consent_records``) y ``session``. Solo
  cuando se crea una fila: repetir la última acción no la envía. Después de confirmar.
"""

from django.dispatch import Signal

buyer_access_consumed = Signal()
buyer_access_link_issued = Signal()
consent_recorded = Signal()
