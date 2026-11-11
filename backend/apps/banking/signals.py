"""Eventos de dominio del módulo banking.

La auditoría (paso 14) se suscribirá para registrar quién cambió la configuración
bancaria y por qué. Mientras tanto, el cambio se escribe en el log de la aplicación.

- ``bank_status_changed``: ``bank``, ``from_status``, ``to_status``, ``actor`` y
  ``reason``.
- ``bank_product_status_changed``: ``product``, ``from_status``, ``to_status``,
  ``actor`` y ``reason``.
- ``bank_policy_rule_status_changed``: ``rule``, ``from_status``, ``to_status`` y
  ``actor``. Al publicar una versión se emite también para la versión anterior que
  pasa a ``INACTIVE``.
"""

from django.dispatch import Signal

bank_status_changed = Signal()
bank_product_status_changed = Signal()
bank_policy_rule_status_changed = Signal()
