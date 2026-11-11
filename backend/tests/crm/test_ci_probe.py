# Prueba del reporte del CI (rama test/ci-report-red). No se fusiona.
import warnings

from apps.crm.ci_probe import PROBE


def test_probe_fails() -> None:
    assert PROBE == {"a": 2}


def test_probe_warns() -> None:
    warnings.warn("ci_probe: este helper está obsoleto", DeprecationWarning, stacklevel=1)
