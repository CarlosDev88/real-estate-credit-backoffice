"""Completitud guardada para el listado (TAREA-applications-listado, Parte 3).

Después de cada punto de enganche, el valor guardado es igual a ``completeness()``.
"""

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications import services
from apps.applications.models import CreditApplication
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, Opportunity
from apps.documents import scans
from apps.documents.constants import PDF
from apps.documents.models import ApplicationDocumentSlot, DocumentFile
from apps.identity.models import User
from tests.applications import test_status_api
from tests.applications.conftest import APPLICATIONS_URL, application_url
from tests.applications.dossier import test_slots_api
from tests.applications.dossier.conftest import SlotFactory
from tests.applications.test_applications_api import SUMMARY_KEYS, create
from tests.applications.test_property_financing_api import PROPERTY, put

pytestmark = pytest.mark.django_db

# Fixtures de otras pruebas: `in_review` (inmueble y crédito bancario, versión 3, en
# revisión documental), `documents_ok` (todos los obligatorios aprobados) y `dossier`
# (checklist de Bancolombia para un titular empleado).
in_review = test_status_api.in_review
documents_ok = test_status_api.documents_ok
dossier = test_slots_api.dossier

Capture = Callable[..., Any]
PDF_BYTES = b"%PDF-1.7\n" + b"contenido de prueba " * 20


def clear(application: CreditApplication) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(
        completeness_pct=None, ready_to_file_ok=None, completeness_refreshed_at=None
    )


def assert_snapshot(application_id: Any) -> CreditApplication:
    """El valor guardado es el mismo que calcula ``/completeness`` ahora."""
    stored = CreditApplication.objects.get(pk=application_id)
    expected = services.completeness(services.applications_queryset().get(pk=application_id))
    assert stored.completeness_refreshed_at is not None
    assert (stored.completeness_pct, stored.ready_to_file_ok) == (
        expected.percentage,
        expected.ready_to_file,
    )
    return stored


def edit_property(client: APIClient, application: CreditApplication, unit: str) -> Any:
    return put(client, application, "property", {**PROPERTY, "unit_reference": unit}, '"3"')


def upload(client: APIClient, slot: ApplicationDocumentSlot) -> Any:
    file = SimpleUploadedFile("cedula.pdf", PDF_BYTES, content_type=PDF)
    data = {"file": file, "document_date": timezone.localdate() - timedelta(days=1)}
    return client.post(f"/api/v1/buyer/document-slots/{slot.id}/uploads", data, format="multipart")


def review(client: APIClient, slot: ApplicationDocumentSlot, **data: Any) -> Any:
    return client.patch(f"/api/v1/document-slots/{slot.id}/review", data, format="json")


def broken(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("error inesperado")


@pytest.fixture
def slot(make_slot: SlotFactory) -> ApplicationDocumentSlot:
    return make_slot(validity_days=30)


# --- Servicio ----------------------------------------------------------------------------


def test_refresh_does_not_touch_version_nor_updated_at(application: CreditApplication) -> None:
    before = CreditApplication.objects.values_list("version", "updated_at").get(pk=application.pk)

    services.refresh_completeness(application.pk)

    stored = assert_snapshot(application.pk)
    assert (stored.version, stored.updated_at) == before


def test_refresh_of_a_missing_application_does_nothing() -> None:
    services.refresh_completeness(uuid.uuid4())

    assert services.refresh_completeness_safely(uuid.uuid4()) is True


# --- Puntos de enganche ------------------------------------------------------------------


def test_data_edit(
    advisor_client: APIClient,
    in_review: CreditApplication,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    clear(in_review)

    with django_capture_on_commit_callbacks(execute=True):
        response = edit_property(advisor_client, in_review, "B")

    assert response.status_code == 200, response.content
    assert_snapshot(in_review.pk)


@pytest.mark.usefixtures("documents_ok")
def test_status_transition(
    advisor_client: APIClient,
    in_review: CreditApplication,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    clear(in_review)

    with django_capture_on_commit_callbacks(execute=True):
        response = test_status_api.transition(advisor_client, in_review, "READY_TO_FILE", version=3)

    assert response.status_code == 200, response.content
    stored = assert_snapshot(in_review.pk)
    assert (stored.status, stored.ready_to_file_ok) == (ApplicationStatus.READY_TO_FILE, True)


def test_bank_evaluation(
    advisor_client: APIClient,
    in_review: CreditApplication,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    clear(in_review)

    with django_capture_on_commit_callbacks(execute=True):
        response = advisor_client.post(application_url(in_review, "/bank-rule-evaluations"))

    assert response.status_code == 201, response.content
    assert_snapshot(in_review.pk)


def test_creation(
    advisor_client: APIClient,
    opportunity: Opportunity,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    """Crear la solicitud arma sus slots: pasa por el recálculo de slots."""
    with django_capture_on_commit_callbacks(execute=True):
        response = create(advisor_client, opportunity)

    assert response.status_code == 201, response.content
    assert_snapshot(response.json()["id"])


def test_upload(
    portal: APIClient,
    slot: ApplicationDocumentSlot,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    clear(slot.application)

    with django_capture_on_commit_callbacks(execute=True):
        response = upload(portal, slot)

    assert response.status_code == 201, response.content
    assert_snapshot(slot.application_id)


def test_scan_result(
    portal: APIClient,
    slot: ApplicationDocumentSlot,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    # Sin ejecutar los on_commit de la carga: el análisis todavía no corrió.
    assert upload(portal, slot).status_code == 201
    file_object_id = DocumentFile.objects.get(slot=slot).file_object_id
    clear(slot.application)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        scans.scan_document_file(file_object_id)

    assert len(callbacks) == 1  # Solo el refresco que deja el análisis.
    assert_snapshot(slot.application_id)


def test_review(
    portal: APIClient,
    advisor_client: APIClient,
    slot: ApplicationDocumentSlot,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        assert upload(portal, slot).status_code == 201
    version = DocumentFile.objects.get(slot=slot)
    clear(slot.application)

    with django_capture_on_commit_callbacks(execute=True):
        response = review(
            advisor_client, slot, decision="APPROVED", document_file_id=str(version.id)
        )

    assert response.status_code == 200, response.content
    assert_snapshot(slot.application_id)


def test_waiver_and_reopening(
    advisor_client: APIClient,
    make_slot: SlotFactory,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    waivable = make_slot(is_waivable=True)
    clear(waivable.application)

    with django_capture_on_commit_callbacks(execute=True):
        waived = review(advisor_client, waivable, decision="WAIVED", reason_code="NOT_APPLICABLE")
    assert waived.status_code == 200, waived.content
    after_waiver = assert_snapshot(waivable.application_id)

    clear(waivable.application)
    with django_capture_on_commit_callbacks(execute=True):
        reopened = review(advisor_client, waivable, decision="REOPENED", internal_comment="Error.")
    assert reopened.status_code == 200, reopened.content
    after_reopening = assert_snapshot(waivable.application_id)
    # Exonerar el único obligatorio sube los documentos; reabrirlo los vuelve a bajar.
    assert after_waiver.completeness_pct is not None
    assert after_reopening.completeness_pct is not None
    assert after_reopening.completeness_pct < after_waiver.completeness_pct


def test_slot_refresh(
    advisor_client: APIClient,
    dossier: CreditApplication,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    """Un requisito publicado después: el recálculo crea slots y la completitud cambia."""
    test_slots_api.requirement("BANK_STATEMENT", minimum_files=2, sort_order=200)
    clear(dossier)

    with django_capture_on_commit_callbacks(execute=True):
        response = advisor_client.post(application_url(dossier, "/document-slots/refresh"))

    assert response.status_code == 200, response.content
    assert response.json()["created"]
    assert_snapshot(dossier.pk)


def test_slot_refresh_without_changes_does_not_recalculate(
    advisor_client: APIClient,
    dossier: CreditApplication,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    clear(dossier)

    with django_capture_on_commit_callbacks(execute=True):
        response = advisor_client.post(application_url(dossier, "/document-slots/refresh"))

    assert response.status_code == 200, response.content
    assert CreditApplication.objects.get(pk=dossier.pk).completeness_refreshed_at is None


def test_a_failed_refresh_does_not_break_the_request(
    advisor_client: APIClient,
    in_review: CreditApplication,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    monkeypatch.setattr(services, "completeness", broken)
    CreditApplication.objects.filter(pk=in_review.pk).update(completeness_pct=40)

    with django_capture_on_commit_callbacks(execute=True):
        response = edit_property(advisor_client, in_review, "C")

    assert response.status_code == 200, response.content
    # Conserva el valor anterior y el error queda en el log con el id.
    assert CreditApplication.objects.get(pk=in_review.pk).completeness_pct == 40
    records = [r for r in caplog.records if r.name == "apps.applications.services"]
    messages = [r.getMessage() for r in records if r.exc_info]
    assert f"No se pudo recalcular la completitud de la solicitud {in_review.pk}" in messages


# --- Comando refresh_application_completeness --------------------------------------------


@pytest.fixture
def another(
    make_application: Callable[..., CreditApplication],
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
) -> Callable[..., CreditApplication]:
    numbers = iter(range(1, 100))

    def _another(status: str, *, refreshed: bool) -> CreditApplication:
        client = make_client(document_number=f"52{next(numbers):08}")
        other = make_application(make_opportunity(client))
        CreditApplication.objects.filter(pk=other.pk).update(
            status=status,
            completeness_pct=7 if refreshed else None,
            completeness_refreshed_at=timezone.now() if refreshed else None,
        )
        return other

    return _another


def test_command_recalculates_open_and_never_calculated(
    application: CreditApplication,
    another: Callable[..., CreditApplication],
    capsys: pytest.CaptureFixture[str],
) -> None:
    open_and_refreshed = another(ApplicationStatus.WAITING_DOCUMENTS, refreshed=True)
    closed_and_refreshed = another(ApplicationStatus.REJECTED, refreshed=True)
    closed_never = another(ApplicationStatus.WITHDRAWN, refreshed=False)
    clear(application)

    call_command("refresh_application_completeness")

    assert capsys.readouterr().out.strip() == "Completitud: 3 recalculadas, 0 con error"
    for recalculated in (application, open_and_refreshed, closed_never):
        assert_snapshot(recalculated.pk)
    # Una cerrada que ya tiene valor no se recalcula salvo con --all.
    assert CreditApplication.objects.get(pk=closed_and_refreshed.pk).completeness_pct == 7

    call_command("refresh_application_completeness", "--all")

    assert capsys.readouterr().out.strip() == "Completitud: 4 recalculadas, 0 con error"
    assert_snapshot(closed_and_refreshed.pk)


def test_command_reports_errors_and_goes_on(
    application: CreditApplication,
    another: Callable[..., CreditApplication],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failing = another(ApplicationStatus.DRAFT, refreshed=False)
    real_completeness = services.completeness

    def fails_for_one(target: CreditApplication) -> Any:
        if target.pk == failing.pk:
            raise RuntimeError("error inesperado")
        return real_completeness(target)

    monkeypatch.setattr(services, "completeness", fails_for_one)
    clear(application)

    call_command("refresh_application_completeness")  # Sin excepción: código de salida 0.

    assert capsys.readouterr().out.strip() == "Completitud: 1 recalculadas, 1 con error"
    assert_snapshot(application.pk)
    assert CreditApplication.objects.get(pk=failing.pk).completeness_refreshed_at is None


# --- Listado -----------------------------------------------------------------------------


def row(client: APIClient) -> dict[str, Any]:
    response = client.get(APPLICATIONS_URL)
    assert response.status_code == 200, response.content
    [item] = response.json()["items"]
    return dict(item)


@pytest.mark.parametrize(
    ("status", "pct", "ok", "blocked"),
    [
        (ApplicationStatus.READY_TO_FILE, 100, True, False),
        (ApplicationStatus.READY_TO_FILE, 90, False, True),  # Ya no cumple.
        (ApplicationStatus.READY_TO_FILE, None, None, None),  # Sin calcular.
        (ApplicationStatus.DOCUMENTS_REVIEW, 60, False, None),  # Otro estado.
    ],
)
def test_list_fields(
    advisor_client: APIClient,
    application: CreditApplication,
    status: str,
    pct: int | None,
    ok: bool | None,
    blocked: bool | None,
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(
        status=status, completeness_pct=pct, ready_to_file_ok=ok
    )

    item = row(advisor_client)

    assert item["completeness_pct"] == pct
    assert item["ready_to_file_blocked"] is blocked


def test_broker_does_not_see_the_completeness(
    broker_client: APIClient, broker_user: User, application: CreditApplication
) -> None:
    Opportunity.objects.filter(pk=application.opportunity_id).update(origin_user=broker_user)
    CreditApplication.objects.filter(pk=application.pk).update(
        completeness_pct=80, ready_to_file_ok=False
    )

    item = row(broker_client)

    assert set(item) == SUMMARY_KEYS
