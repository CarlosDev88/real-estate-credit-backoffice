"""Pruebas de las verificaciones de seguridad del reporte del CI (``scripts/ci_report.py``):
pip-audit, gitleaks, bandit y la matriz de acceso."""

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import ci_report
from scripts.ci_report import Context, Status


def make_ctx(report_dir: Path, **outcomes: str) -> Context:
    return Context(
        report_dir=report_dir, outcomes=outcomes, coverage_min=95.0, base_dir=report_dir.parent
    )


@pytest.fixture
def report_dir(tmp_path: Path) -> Path:
    path = tmp_path / ".ci-report"
    path.mkdir()
    return path


def write(report_dir: Path, name: str, data: Any) -> None:
    text = data if isinstance(data, str) else json.dumps(data)
    (report_dir / name).write_text(text, encoding="utf-8")


def vuln(identifier: str, fixes: list[str]) -> dict[str, Any]:
    return {"id": identifier, "fix_versions": fixes}


# --- pip-audit -----------------------------------------------------------------------------


def test_pip_audit_blocks_only_vulnerabilities_with_a_fix(report_dir: Path) -> None:
    write(
        report_dir,
        "pip-audit.json",
        {
            "dependencies": [
                {"name": "django", "version": "5.2.1", "vulns": [vuln("CVE-1", ["5.2.2"])]},
                {"name": "pyjwt", "version": "2.1", "vulns": [vuln("CVE-2", [])]},
                {"name": "django", "version": "5.2.1", "vulns": [vuln("CVE-3", ["5.2.3", "6.0"])]},
                "no es un objeto",
                {"name": "celery", "vulns": ["tampoco"]},
            ]
        },
    )
    ctx = make_ctx(report_dir, pip_audit="failure")

    verdict = ci_report.check_pip_audit(ctx)
    assert verdict.status is Status.FAILED
    assert verdict.summary == "2 con arreglo: django"
    assert list(verdict.details[0].entries) == [
        "django 5.2.1  CVE-1  → 5.2.2",
        "django 5.2.1  CVE-3  → 5.2.3, 6.0",
    ]

    unfixed = ci_report.check_pip_audit_unfixed(ctx)
    assert unfixed.status is Status.WARNING
    assert unfixed.summary == "1 sin arreglo: pyjwt"
    assert list(unfixed.details[0].entries) == ["pyjwt 2.1  CVE-2  → sin arreglo"]


def test_pip_audit_clean_without_ignored_vulnerabilities(report_dir: Path) -> None:
    write(report_dir, "pip-audit.json", {"dependencies": []})
    write(report_dir, "pip-audit.txt", "No known vulnerabilities found\n")
    verdict = ci_report.check_pip_audit(make_ctx(report_dir, pip_audit="success"))
    assert (verdict.status, verdict.summary) == (Status.PASSED, "Sin vulnerabilidades con arreglo")


def test_pip_audit_without_report(report_dir: Path) -> None:
    ok = ci_report.check_pip_audit(make_ctx(report_dir, pip_audit="success"))
    assert (ok.status, ok.summary) == (Status.PASSED, "Sin vulnerabilidades con arreglo")

    write(report_dir, "pip-audit.txt", "ERROR: no se pudo resolver requirements.txt\n")
    failed = ci_report.check_pip_audit(make_ctx(report_dir, pip_audit="failure"))
    assert (failed.status, failed.summary) == (Status.FAILED, "Falló (ver el log)")
    assert list(failed.details[0].entries) == ["ERROR: no se pudo resolver requirements.txt"]

    write(report_dir, "pip-audit.json", ["no es un objeto"])
    assert ci_report.load_pip_audit(make_ctx(report_dir)) is None
    assert ci_report.check_pip_audit_unfixed(make_ctx(report_dir)).summary == "Ninguna"


# --- gitleaks ------------------------------------------------------------------------------


def test_gitleaks_never_shows_the_secret(report_dir: Path) -> None:
    write(
        report_dir,
        "gitleaks.json",
        [
            {
                "RuleID": "generic-api-key",
                "File": "backend/a.py",
                "StartLine": 3,
                "Commit": "0123456789abcdef",
                "Secret": "valor-que-no-debe-salir",
                "Match": "key = valor-que-no-debe-salir",
            },
            {"RuleID": "aws-access-token", "File": "backend/a.py", "StartLine": "x"},
            "no es un objeto",
        ],
    )
    verdict = ci_report.check_gitleaks(make_ctx(report_dir, gitleaks="failure"))
    assert verdict.status is Status.FAILED
    assert verdict.summary == "2 posibles secretos en 1 archivo"
    entries = list(verdict.details[0].entries)
    assert entries == [
        "generic-api-key  backend/a.py:3  0123456",
        "aws-access-token  backend/a.py:0  ",
    ]
    assert all("valor-que-no-debe-salir" not in entry for entry in entries)


def test_gitleaks_states(report_dir: Path) -> None:
    ok = ci_report.check_gitleaks(make_ctx(report_dir, gitleaks="success"))
    assert (ok.status, ok.summary) == (Status.PASSED, "Sin secretos nuevos")

    write(report_dir, "gitleaks.txt", "docker: Error response from daemon\n")
    crashed = ci_report.check_gitleaks(make_ctx(report_dir, gitleaks="failure"))
    assert (crashed.status, crashed.summary) == (Status.FAILED, "Falló (ver el log)")
    assert list(crashed.details[0].entries) == ["docker: Error response from daemon"]


# --- bandit --------------------------------------------------------------------------------


def bandit_item(severity: str, line: int, text: str, base: Path) -> dict[str, Any]:
    return {
        "test_id": "B000",
        "filename": str(base / "apps" / "crm" / "views.py"),
        "line_number": line,
        "issue_severity": severity,
        "issue_text": text,
    }


def test_bandit_blocks_only_high_severity(report_dir: Path) -> None:
    base = report_dir.parent
    write(
        report_dir,
        "bandit.json",
        {
            "results": [
                bandit_item("HIGH", 10, "shell=True\nsegunda línea", base),
                bandit_item("MEDIUM", 20, "posible SQL armado a mano", base),
                bandit_item("LOW", 30, "assert", base),
                "no es un objeto",
            ]
        },
    )
    ctx = make_ctx(report_dir, bandit="failure")

    high = ci_report.check_bandit(ctx)
    assert (high.status, high.summary) == (Status.FAILED, "1 hallazgo de severidad alta")
    assert list(high.details[0].entries) == ["B000  apps/crm/views.py:10  shell=True"]

    medium = ci_report.check_bandit_medium(ctx)
    assert (medium.status, medium.summary) == (Status.WARNING, "1 hallazgo")
    assert list(medium.details[0].entries) == [
        "B000  apps/crm/views.py:20  posible SQL armado a mano"
    ]


def test_bandit_states(report_dir: Path) -> None:
    ok = ci_report.check_bandit(make_ctx(report_dir, bandit="success"))
    assert (ok.status, ok.summary) == (Status.PASSED, "Sin hallazgos de severidad alta")
    assert ci_report.check_bandit_medium(make_ctx(report_dir)).summary == "Ninguno"

    write(report_dir, "bandit.txt", "ERROR: archivo no encontrado\n")
    crashed = ci_report.check_bandit(make_ctx(report_dir, bandit="failure"))
    assert (crashed.status, crashed.summary) == (Status.FAILED, "Falló (ver el log)")

    write(report_dir, "bandit.json", "[]")
    assert ci_report.load_bandit(make_ctx(report_dir), "HIGH") is None


# --- Matriz de acceso ----------------------------------------------------------------------


def test_security_matrix(report_dir: Path) -> None:
    ok = ci_report.check_security_matrix(make_ctx(report_dir, security_matrix="success"))
    assert (ok.status, ok.summary) == (Status.PASSED, "Al día")

    write(report_dir, "security-matrix.txt", "docs/seguridad/03-matriz-acceso.md no está al día\n")
    stale = ci_report.check_security_matrix(make_ctx(report_dir, security_matrix="failure"))
    assert stale.status is Status.FAILED
    assert stale.summary == "Desactualizada: correr python security/render_matrix.py"
    assert list(stale.details[0].entries) == ["docs/seguridad/03-matriz-acceso.md no está al día"]


def test_new_checks_are_registered_with_their_outcomes() -> None:
    specs = {spec.name: (spec.outcome_key, spec.blocking) for spec in ci_report.CHECKS}
    assert specs[ci_report.PIP_AUDIT] == ("pip_audit", True)
    assert specs[ci_report.PIP_AUDIT_UNFIXED] == ("pip_audit", False)
    assert specs[ci_report.GITLEAKS] == ("gitleaks", True)
    assert specs[ci_report.BANDIT] == ("bandit", True)
    assert specs[ci_report.BANDIT_MEDIUM] == ("bandit", False)
    assert specs[ci_report.SECURITY_MATRIX] == ("security_matrix", True)
    assert {"pip_audit", "gitleaks", "bandit", "security_matrix"} <= set(ci_report.OUTCOME_KEYS)
