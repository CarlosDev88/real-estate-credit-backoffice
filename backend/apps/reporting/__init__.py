"""Dashboard y reportes (módulo 15, REQUERIMIENTOS §5.8 RF-70 a RF-72, API §22).

Alcance del MVP (decisión de Carlos, alcance "medio"):

- Entran los cuatro endpoints de ``/dashboard/*``, ``/reports/funnel``,
  ``/reports/applications``, ``/reports/applications.csv`` y la exportación asíncrona
  solo en CSV (``report_export_jobs``).
- **Quedan fuera por decisión del MVP**: la exportación XLSX, ``/reports/advisors``,
  ``/reports/banks`` y ``/reports/document-quality``. La carga por asesor y los
  resultados por banco ya los cubre el dashboard (``/dashboard/workload`` y
  ``/dashboard/bank-results``).

El alcance por rol reutiliza el de ``applications`` (``application_scope_filter``); los
filtros y el rango de fechas viven en ``filters.py``.
"""
