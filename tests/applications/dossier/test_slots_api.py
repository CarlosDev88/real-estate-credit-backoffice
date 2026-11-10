"""Lectura interna del expediente y recálculo manual (API §19, decisión 10)."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import ApplicationParticipant, CreditApplication
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentReview,
    ParticipantRole,
    ReviewDecision,
    ScanStatus,
    SlotStatus,
)
from apps.identity.models import User
from tests.applications.conftest import application_url, catalog_item, seeded_product
from tests.applications.dossier.conftest import (
    DocumentFileFactory,
    FileObjectFactory,
    SlotFactory,
)
from tests.applications.dossier.test_slots import requirement, set_profile, sync
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

SLOTS_URL = "/api/v1/document-slots"


def slots_url(application: CreditApplication, suffix: str = "") -> str:
    return application_url(application, f"/document-slots{suffix}")


def slot_url(slot: ApplicationDocumentSlot, suffix: str = "") -> str:
    return f"{SLOTS_URL}/{slot.id}{suffix}"


@pytest.fixture
def dossier(application: CreditApplication, primary: ApplicationParticipant) -> CreditApplication:
    """Checklist de Bancolombia para un titular empleado, más un documento del inmueble."""
    application.bank_product = seeded_product()
    application.save(update_fields=["bank_product"])
    set_profile(primary, "EMPLOYEE")
    requirement("PROPERTY_OWNERSHIP_DOCUMENT", sort_order=1)
    sync(application)
    return application


def slot_of(application: CreditApplication, type_code: str, index: int = 1) -> Any:
    return ApplicationDocumentSlot.objects.get(
        application=application,
        document_type__code=type_code,
        slot_index=index,
        retired_at__isnull=True,
    )


@pytest.fixture
def anonymous() -> APIClient:
    return APIClient()


# --- Matriz de permisos ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("client_name", "expected"),
    [
        ("admin_client", 200),
        ("advisor_client", 200),
        ("other_advisor_client", 404),
        ("broker_client", 403),
        ("partner_client", 403),
        ("anonymous", 401),
    ],
)
def test_access_matrix(
    request: pytest.FixtureRequest, dossier: CreditApplication, client_name: str, expected: int
) -> None:
    client: APIClient = request.getfixturevalue(client_name)
    slot = slot_of(dossier, "IDENTITY_DOCUMENT")

    responses = [
        client.get(slots_url(dossier)),
        client.get(slot_url(slot)),
        client.get(slot_url(slot, "/versions")),
        client.post(slots_url(dossier, "/refresh")),
    ]

    assert [response.status_code for response in responses] == [expected] * 4


def test_unknown_ids_are_404(advisor_client: APIClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"

    assert_error(advisor_client.get(f"{SLOTS_URL}/{missing}"), 404, "RESOURCE_NOT_FOUND")
    response = advisor_client.get(f"/api/v1/applications/{missing}/document-slots")
    assert_error(response, 404, "RESOURCE_NOT_FOUND")


# --- Lista ------------------------------------------------------------------------------


def test_list_returns_the_dossier_in_display_order(
    advisor_client: APIClient, dossier: CreditApplication, primary: ApplicationParticipant
) -> None:
    response = advisor_client.get(slots_url(dossier))

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["total"] == 8
    rows = body["items"]
    # Primero el documento de la solicitud, después los del titular por `sort_order`.
    assert rows[0]["document_type"]["code"] == "PROPERTY_OWNERSHIP_DOCUMENT"
    assert rows[0]["participant"] is None
    assert rows[0]["document_type"]["holder_scope"] == "APPLICATION"
    assert [row["document_type"]["code"] for row in rows[1:]] == [
        "IDENTITY_DOCUMENT",
        "INCOME_RETENTION_CERTIFICATE",
        "INCOME_TAX_RETURN",
        "EMPLOYMENT_CERTIFICATE",
        "PAYROLL_SLIP",
        "PAYROLL_SLIP",
        "PAYROLL_SLIP",
    ]
    identity = rows[1]
    assert identity["participant"] == {
        "id": str(primary.id),
        "role": "PRIMARY",
        "client_id": str(primary.client_id),
        "full_name": "Laura Gómez Vélez",
        "is_active": True,
    }
    assert identity["label"] == "Copia del documento de identidad"
    assert identity["document_type"]["allowed_mime_types"] == [
        "application/pdf",
        "image/jpeg",
        "image/png",
    ]
    assert identity["document_type"]["max_size_bytes"] == 10 * 1024 * 1024
    assert identity["status"] == "PENDING"
    assert identity["current_file"] is None
    assert identity["waiver_reason"] is None
    assert identity["is_retired"] is False
    assert [row["label"] for row in rows[5:]] == [
        "Desprendible o comprobante de nómina 1 de 3",
        "Desprendible o comprobante de nómina 2 de 3",
        "Desprendible o comprobante de nómina 3 de 3",
    ]


def test_list_filters(
    advisor_client: APIClient,
    dossier: CreditApplication,
    primary: ApplicationParticipant,
    make_client: Callable[..., Client],
) -> None:
    retention = slot_of(dossier, "INCOME_RETENTION_CERTIFICATE")
    retention.status = SlotStatus.WAIVED
    retention.waiver_reason_item = catalog_item("document_waiver_reason", "NOT_APPLICABLE")
    retention.save(update_fields=["status", "waiver_reason_item"])
    other = ApplicationParticipant.objects.create(
        application=dossier,
        client=make_client(document_number="80123456"),
        role=ParticipantRole.CO_APPLICANT,
    )
    sync(dossier)
    ApplicationDocumentSlot.objects.filter(
        document_type__code="INCOME_TAX_RETURN", participant=other
    ).update(is_required=False)

    def count(**params: Any) -> int:
        response = advisor_client.get(slots_url(dossier), params)
        assert response.status_code == 200, response.content
        return int(response.json()["total"])

    assert count() == 11
    assert count(participant_id=str(other.id)) == 3
    assert count(participant_id=str(primary.id)) == 7
    assert count(status="WAIVED") == 1
    assert count(document_type_code="PAYROLL_SLIP") == 3
    assert count(required="false") == 1
    assert count(required="true") == 10

    waived = advisor_client.get(slots_url(dossier), {"status": "WAIVED"}).json()["items"][0]
    assert waived["waiver_reason"]["code"] == "NOT_APPLICABLE"


def test_list_hides_retired_slots_unless_asked(
    advisor_client: APIClient, dossier: CreditApplication, primary: ApplicationParticipant
) -> None:
    set_profile(primary, "PENSIONER")
    sync(dossier)

    assert advisor_client.get(slots_url(dossier)).json()["total"] == 8
    response = advisor_client.get(slots_url(dossier), {"include_retired": "true"})
    rows = response.json()["items"]
    assert len(rows) == 12
    retired = [row for row in rows if row["is_retired"]]
    assert {row["document_type"]["code"] for row in retired} == {
        "EMPLOYMENT_CERTIFICATE",
        "PAYROLL_SLIP",
    }
    assert all(row["retired_at"] for row in retired)
    # Un slot retirado conserva la etiqueta de su snapshot.
    assert "Desprendible o comprobante de nómina 3 de 3" in {row["label"] for row in retired}


def test_list_rejects_an_unknown_status(
    advisor_client: APIClient, dossier: CreditApplication
) -> None:
    response = advisor_client.get(slots_url(dossier), {"status": "MISSING"})

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "status"


# --- Detalle y versiones ----------------------------------------------------------------


def test_detail_shows_the_current_file(
    advisor_client: APIClient,
    dossier: CreditApplication,
    make_document_file: DocumentFileFactory,
) -> None:
    slot = slot_of(dossier, "PAYROLL_SLIP", 2)
    current = make_document_file(slot=slot, client_filename="nomina-febrero.pdf")
    slot.current_file = current
    slot.status = SlotStatus.UPLOADED
    slot.save(update_fields=["current_file", "status"])

    response = advisor_client.get(slot_url(slot))

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["id"] == str(slot.id)
    assert body["application_id"] == str(dossier.id)
    assert body["label"] == "Desprendible o comprobante de nómina 2 de 3"
    assert body["requirement_version"] == 1
    assert body["minimum_files"] == 3
    assert body["status"] == "UPLOADED"
    assert body["current_file"] == {
        "id": str(current.id),
        "version_number": 1,
        "status": "UPLOADED",
        "client_filename": "nomina-febrero.pdf",
        "document_date": None,
        "expires_at": None,
        "scan_status": "PENDING",
        "created_at": body["current_file"]["created_at"],
    }


def test_detail_includes_retired_slots(
    advisor_client: APIClient, dossier: CreditApplication, primary: ApplicationParticipant
) -> None:
    certificate = slot_of(dossier, "EMPLOYMENT_CERTIFICATE")
    set_profile(primary, "INDEPENDENT")
    sync(dossier)

    response = advisor_client.get(slot_url(certificate))

    assert response.status_code == 200, response.content
    assert response.json()["is_retired"] is True


def test_versions_list_every_upload_with_its_reviews(
    advisor_client: APIClient,
    advisor_user: User,
    dossier: CreditApplication,
    make_document_file: DocumentFileFactory,
    make_file_object: FileObjectFactory,
) -> None:
    slot = slot_of(dossier, "IDENTITY_DOCUMENT")
    first = make_document_file(
        slot=slot,
        file_object=make_file_object(scan_status=ScanStatus.CLEAN, scanned_at=timezone.now()),
        status="REJECTED",
    )
    DocumentReview.objects.create(
        document_file=first,
        reviewer=advisor_user,
        decision=ReviewDecision.APPROVED,
    )
    later = timezone.now() + timedelta(seconds=1)
    correction = DocumentReview.objects.create(
        document_file=first,
        reviewer=advisor_user,
        decision=ReviewDecision.REJECTED,
        reason_item=catalog_item("document_rejection_reason", "ILLEGIBLE"),
        buyer_comment="La foto está borrosa.",
        internal_comment="Revisar la otra cara.",
    )
    DocumentReview.objects.filter(pk=correction.pk).update(created_at=later)
    second = make_document_file(slot=slot, version_number=2, client_filename="cedula-2.pdf")
    slot.current_file = second
    slot.save(update_fields=["current_file"])

    response = advisor_client.get(slot_url(slot, "/versions"))

    assert response.status_code == 200, response.content
    rows = response.json()["items"]
    assert [row["version_number"] for row in rows] == [2, 1]
    assert [row["is_current"] for row in rows] == [True, False]
    newest, oldest = rows
    assert newest["reviews"] == []
    assert newest["file"]["scan_status"] == "PENDING"
    assert set(newest["file"]) == {
        "id",
        "detected_mime_type",
        "size_bytes",
        "sha256",
        "scan_status",
        "scanned_at",
    }
    assert "object_key" not in response.content.decode()
    assert oldest["status"] == "REJECTED"
    assert oldest["file"]["scan_status"] == "CLEAN"
    assert [review["decision"] for review in oldest["reviews"]] == ["REJECTED", "APPROVED"]
    rejection = oldest["reviews"][0]
    assert rejection["reason"]["code"] == "ILLEGIBLE"
    assert rejection["buyer_comment"] == "La foto está borrosa."
    assert rejection["internal_comment"] == "Revisar la otra cara."
    assert rejection["reviewer"]["id"] == str(advisor_user.id)
    assert oldest["uploaded_by_buyer_session_id"] == str(first.uploaded_by_buyer_session_id)


def test_versions_of_an_empty_slot(
    advisor_client: APIClient, application: CreditApplication, make_slot: SlotFactory
) -> None:
    slot = make_slot()

    response = advisor_client.get(slot_url(slot, "/versions"))

    assert response.status_code == 200
    assert response.json()["items"] == []


# --- Recálculo manual -------------------------------------------------------------------


def test_refresh_picks_up_a_requirement_published_later(
    advisor_client: APIClient, dossier: CreditApplication, primary: ApplicationParticipant
) -> None:
    requirement("BANK_STATEMENT", minimum_files=2, sort_order=200)

    response = advisor_client.post(slots_url(dossier, "/refresh"))

    assert response.status_code == 200, response.content
    body = response.json()
    created = set(
        ApplicationDocumentSlot.objects.filter(
            application=dossier, document_type__code="BANK_STATEMENT"
        ).values_list("pk", flat=True)
    )
    assert {uuid for uuid in body["created"]} == {str(pk) for pk in created}
    assert body["retired"] == body["revived"] == body["updated"] == []
    assert len(body["slots"]) == 10
    assert body["slots"][-1]["label"] == "Extracto bancario 2 de 2"
    dossier.refresh_from_db(fields=["version"])
    assert dossier.version == 1


def test_refresh_reports_retired_and_revived_slots(
    admin_client: APIClient, dossier: CreditApplication, primary: ApplicationParticipant
) -> None:
    certificate = slot_of(dossier, "EMPLOYMENT_CERTIFICATE")
    set_profile(primary, "INDEPENDENT")
    first = admin_client.post(slots_url(dossier, "/refresh")).json()
    assert str(certificate.id) in first["retired"]
    assert len(first["created"]) == 4

    set_profile(primary, "EMPLOYEE")
    second = admin_client.post(slots_url(dossier, "/refresh")).json()

    assert str(certificate.id) in second["revived"]
    assert len(second["retired"]) == 4


def test_refresh_is_not_allowed_after_filing(
    advisor_client: APIClient, dossier: CreditApplication
) -> None:
    CreditApplication.objects.filter(pk=dossier.pk).update(status=ApplicationStatus.FILED)

    response = advisor_client.post(slots_url(dossier, "/refresh"))

    assert_error(response, 409, "APPLICATION_NOT_EDITABLE")
