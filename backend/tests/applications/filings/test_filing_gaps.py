"""Brechas de la radicación (TAREA-brechas-2, parte 2): etiquetas de los snapshots,
radicación vencida, campos por tipo de respuesta, evidencia y corrección del
desembolso."""

from datetime import timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.catalogs.workflow import ApplicationStatus
from apps.documents.models import DocumentPackageJob, FileObject, ScanStatus
from apps.filings.models import Filing, FilingResponse, FilingStatus
from apps.filings.responses import RULES, TYPED_FIELDS, response_type_metadata
from apps.filings.serializers import EvidenceSerializer
from apps.filings.signals import filing_response_recorded
from apps.notifications.models import Notification, NotificationType
from tests.applications.filings.test_filings_api import file, filing_url, package, ready
from tests.applications.filings.test_responses_api import (
    APPROVED_BODY,
    DISBURSED_BODY,
    filed,
    recorded,
    respond,
)
from tests.applications.test_status_api import transition
from tests.helpers import assert_error

__all__ = ["filed", "package", "ready"]

pytestmark = pytest.mark.django_db


# --- Snapshots --------------------------------------------------------------------------


def test_snapshots_carry_the_labels_without_queries_per_row(
    advisor_client: APIClient, ready: CreditApplication, package: DocumentPackageJob
) -> None:
    filing_id = file(advisor_client, ready, package).json()["id"]
    url = filing_url(filing_id, "/document-snapshots")

    with CaptureQueriesContext(connection) as all_rows:
        response = advisor_client.get(url)
    with CaptureQueriesContext(connection) as one_row:
        advisor_client.get(url, {"page_size": 1})

    items = response.json()["items"]
    assert len(items) > 1
    assert len(all_rows) == len(one_row)
    for item in items:
        assert item["document_type_label"]
        assert item["slot_label"].startswith(item["document_type_label"])


# --- Radicación vencida -----------------------------------------------------------------


def test_is_response_overdue(advisor_client: APIClient, filed: Filing) -> None:
    url = filing_url(filed)
    assert advisor_client.get(url).json()["is_response_overdue"] is False

    Filing.objects.filter(pk=filed.pk).update(
        filed_at=timezone.now() - timedelta(days=10),
        target_response_at=timezone.now() - timedelta(days=3),
    )
    assert advisor_client.get(url).json()["is_response_overdue"] is True

    recorded(advisor_client, filed, "RECEIVED")
    assert advisor_client.get(url).json()["is_response_overdue"] is False


# --- Evidencia --------------------------------------------------------------------------


def test_evidence_has_the_scan_status_label() -> None:
    evidence = FileObject(
        original_filename="carta.pdf",
        detected_mime_type="application/pdf",
        size_bytes=10,
        scan_status=ScanStatus.CLEAN,
        created_at=timezone.now(),
    )

    assert EvidenceSerializer(evidence).data["scan_status_label"] == "Limpio"


# --- Campos por tipo de respuesta -------------------------------------------------------


def test_response_type_metadata_comes_from_the_rules() -> None:
    for code, rule in RULES.items():
        metadata = response_type_metadata(code)
        own = [name for name in metadata["fields"] if name in TYPED_FIELDS]
        assert set(own) == set(rule.allowed)
        assert set(rule.required) <= set(metadata["fields"])
        assert metadata["required"] == list(rule.required)
        assert metadata["reason_catalog"] == rule.reason_catalog
    assert response_type_metadata("UNKNOWN") == {}
    assert response_type_metadata("RETURNED") == {
        "fields": ["reason_code", "observations", "public_message", "internal_comment"],
        "required": ["reason_code", "public_message", "observations"],
        "reason_catalog": "filing_return_reason",
    }


def test_the_catalog_publishes_the_fields_of_each_type(advisor_client: APIClient) -> None:
    catalog = advisor_client.get("/api/v1/metadata/catalogs/filing_response_type").json()
    bootstrap = advisor_client.get("/api/v1/metadata/bootstrap").json()

    for items in (catalog["items"], bootstrap["catalogs"]["filing_response_type"]):
        by_code = {item["code"]: item["metadata"] for item in items}
        assert set(by_code) == set(RULES)
        for code, metadata in by_code.items():
            assert {k: metadata[k] for k in ("fields", "required", "reason_catalog")} == (
                response_type_metadata(code)
            )


# --- Corrección del desembolso ----------------------------------------------------------


@pytest.fixture
def disbursed(advisor_client: APIClient, filed: Filing) -> FilingResponse:
    application = filed.application
    recorded(advisor_client, filed, "APPROVED", **APPROVED_BODY)
    application.refresh_from_db()
    response = transition(advisor_client, application, "LEGALIZATION", version=application.version)
    assert response.status_code == 200, response.content
    return recorded(
        advisor_client, filed, "DISBURSED", **DISBURSED_BODY, external_reference="DES-1"
    )


def correct(api: APIClient, filed: Filing, corrected: FilingResponse, **extra: Any) -> Any:
    return respond(
        api,
        filed,
        "DISBURSED",
        disbursed_amount_cop=300_000_000,
        corrects_response_id=str(corrected.pk),
        **extra,
    )


def test_admin_corrects_the_disbursement_without_changing_states(
    admin_client: APIClient, filed: Filing, disbursed: FilingResponse
) -> None:
    application = CreditApplication.objects.get(pk=filed.application_id)
    version = application.version
    received = timezone.now() - timedelta(minutes=10)
    events: list[dict[str, Any]] = []

    def on_response(**kwargs: Any) -> None:
        events.append(kwargs)

    filing_response_recorded.connect(on_response)
    try:
        response = correct(
            admin_client,
            filed,
            disbursed,
            received_at=received.isoformat(),
            external_reference="DES-1-CORREGIDO",
            internal_comment="El banco corrigió el monto.",
        )
    finally:
        filing_response_recorded.disconnect(on_response)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["corrects_response_id"] == str(disbursed.pk)
    assert body["disbursed_amount_cop"] == 300_000_000
    assert body["external_reference"] == "DES-1-CORREGIDO"
    application.refresh_from_db()
    filed.refresh_from_db()
    assert (application.status, application.version) == (ApplicationStatus.DISBURSED, version)
    assert filed.status == FilingStatus.DISBURSED
    [event] = events
    assert (event["response"].corrects_response_id, event["status_changed"]) == (
        disbursed.pk,
        False,
    )

    # Se corrige la última: la corrección también se puede corregir; la original ya no.
    fixed = FilingResponse.objects.get(pk=body["id"])
    assert_error(correct(admin_client, filed, disbursed), 409, "RESPONSE_CORRECTION_NOT_ALLOWED")
    assert correct(admin_client, filed, fixed).status_code == 201


def test_only_the_admin_corrects_a_disbursement(
    advisor_client: APIClient, filed: Filing, disbursed: FilingResponse
) -> None:
    assert_error(correct(advisor_client, filed, disbursed), 403, "PERMISSION_DENIED")
    assert FilingResponse.objects.filter(corrects_response=disbursed).count() == 0


def test_a_disbursement_correction_keeps_the_type_rules(
    admin_client: APIClient, filed: Filing, disbursed: FilingResponse
) -> None:
    missing = respond(admin_client, filed, "DISBURSED", corrects_response_id=str(disbursed.pk))
    foreign = correct(admin_client, filed, disbursed, approved_term_months=240)

    assert assert_error(missing, 400, "VALIDATION_ERROR")["details"][0]["field"] == (
        "disbursed_amount_cop"
    )
    assert assert_error(foreign, 400, "VALIDATION_ERROR")["details"][0]["field"] == (
        "approved_term_months"
    )


def test_a_new_disbursement_on_a_disbursed_application_is_still_closed(
    admin_client: APIClient, filed: Filing, disbursed: FilingResponse
) -> None:
    assert_error(
        respond(admin_client, filed, "DISBURSED", **DISBURSED_BODY), 409, "APPLICATION_CLOSED"
    )


def test_the_buyer_is_not_notified_again(
    admin_client: APIClient, filed: Filing, disbursed: FilingResponse
) -> None:
    notified = Notification.objects.filter(notification_type=NotificationType.DISBURSED)
    before = notified.count()
    assert before == 1

    assert correct(admin_client, filed, disbursed).status_code == 201

    assert notified.count() == before
