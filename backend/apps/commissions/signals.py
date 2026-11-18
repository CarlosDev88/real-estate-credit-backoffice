"""Eventos de dominio de comisiones (paso 16). Se envían con ``transaction.on_commit``.
Los usan la actividad (``apps.activity.receivers``) y la auditoría
(``apps.audit.receivers``). Nunca llevan montos a esos registros.

- ``commission_settled``: ``settlement`` y ``actor`` (``None`` si la disparó el sistema).
- ``commission_settlement_voided``: ``settlement``, ``reason`` y ``actor``.
- ``commission_share_paid``: ``share`` y ``actor``.
- ``commission_plan_missing``: ``application``, ``response`` (la del desembolso) y
  ``actor``. La liquidación automática no encontró un plan vigente.
"""

from django.dispatch import Signal

commission_settled = Signal()
commission_settlement_voided = Signal()
commission_share_paid = Signal()
commission_plan_missing = Signal()
