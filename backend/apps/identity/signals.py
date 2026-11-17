"""Eventos de dominio del acceso del comprador.

- ``buyer_access_consumed``: ``link`` (el enlace consumido) y ``session`` (la sesión que
  abrió). Se envía después de confirmar la transacción del consumo. Lo usan las
  notificaciones (paso 13) para dar la bienvenida al portal.
"""

from django.dispatch import Signal

buyer_access_consumed = Signal()
