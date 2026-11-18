"""Eventos de dominio de los reportes.

- ``report_exported``: ``user`` (quién exportó), ``report_type`` (``applications``),
  ``filters`` (los filtros ya validados, con el rango efectivo, como diccionario JSON),
  ``row_count``, ``format`` (``csv``) y ``job`` (la ``ReportExportJob``, o ``None`` en la
  descarga directa). Se emite en la descarga directa del CSV y al completar una
  exportación asíncrona.

La auditoría la escucha (``apps.audit.receivers.on_report_exported``).
"""

from django.dispatch import Signal

report_exported = Signal()
