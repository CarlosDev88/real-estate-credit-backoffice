"""Eventos de dominio de los reportes.

- ``report_exported``: ``user`` (quién exportó), ``report_type`` (``applications``),
  ``filters`` (los filtros ya validados, con el rango efectivo, como diccionario JSON),
  ``row_count`` y ``format`` (``csv``). Se emite en la descarga directa del CSV y al
  completar una exportación asíncrona.

La auditoría se suscribirá cuando llegue su módulo; este módulo no la llama.
"""

from django.dispatch import Signal

report_exported = Signal()
