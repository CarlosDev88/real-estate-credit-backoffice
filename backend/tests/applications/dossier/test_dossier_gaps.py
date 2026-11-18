"""Brechas del expediente (TAREA-brechas-2, parte 2): datos del archivo vigente en la
lista de slots, quién cargó cada versión y la lista de paquetes de la solicitud."""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.catalogs.models import CatalogItem
from apps.documents.models import (
    DocumentFile,
    DocumentPackageJob,
    DocumentReview,
    DocumentType,
    ReviewDecision,
)
from apps.documents.packages import build_package, request_package
from apps.identity.models import User
from tests.applications.dossier.conftest import (
    DocumentFileFactory,
    PackageDossier,
    SlotFactory,
)
from tests.applications.dossier.test_packages_api import create_url
from tests.applications.dossier.test_slots_api import slots_url
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db


def review(version: DocumentFile, reviewer: User, decision: str, comment: str | None) -> None:
    reason = None
    if decision == ReviewDecision.REJECTED:
        reason = CatalogItem.objects.get(catalog__code="document_rejection_reason", code="OUTDATED")
    DocumentReview.objects.create(
        slot=version.slot,
        document_file=version,
        reviewer=reviewer,
        decision=decision,
        reason_item=reason,
        buyer_comment=comment,
    )


def current(advisor_client: APIClient, application: CreditApplication) -> list[dict | None]:
    response = advisor_client.get(slots_url(application))
    assert response.status_code == 200, response.content
    return [slot["current_file"] for slot in response.json()["items"]]


# --- CurrentFile -------------------------------------------------------------------------


def test_current_file_carries_size_mime_and_the_last_buyer_comment(
    advisor_client: APIClient,
    advisor_user: User,
    application: CreditApplication,
    make_slot: SlotFactory,
    make_document_file: DocumentFileFactory,
) -> None:
    slot = make_slot()
    version = make_document_file(slot=slot)
    slot.current_file = version
    slot.save(update_fields=["current_file"])
    review(version, advisor_user, ReviewDecision.REJECTED, "La foto no se lee.")
    later = DocumentReview.objects.filter(document_file=version)
    later.update(created_at=timezone.now() - timedelta(minutes=5))
    review(version, advisor_user, ReviewDecision.REJECTED, "Falta el reverso.")

    [item] = current(advisor_client, application)

    assert item is not None
    assert item["size_bytes"] == version.file_object.size_bytes
    assert item["detected_mime_type"] == "application/pdf"
    assert item["last_buyer_comment"] == "Falta el reverso."


def test_last_buyer_comment_is_null_without_comment_or_review(
    advisor_client: APIClient,
    advisor_user: User,
    application: CreditApplication,
    make_slot: SlotFactory,
    make_document_file: DocumentFileFactory,
) -> None:
    reviewed = make_slot()
    plain = make_slot(document_type=DocumentType.objects.get(code="PAYROLL_SLIP"))
    empty = make_slot(document_type=DocumentType.objects.get(code="BANK_STATEMENT"))
    for slot in (reviewed, plain):
        version = make_document_file(slot=slot)
        slot.current_file = version
        slot.save(update_fields=["current_file"])
    review(reviewed.current_file, advisor_user, ReviewDecision.APPROVED, "")  # type: ignore[arg-type]

    items = current(advisor_client, application)

    assert sorted(item is None for item in items) == [False, False, True]
    assert [item["last_buyer_comment"] for item in items if item] == [None, None]
    assert empty.current_file_id is None


def test_slot_list_queries_do_not_grow_with_the_rows(
    advisor_client: APIClient,
    advisor_user: User,
    application: CreditApplication,
    make_slot: SlotFactory,
    make_document_file: DocumentFileFactory,
) -> None:
    def add(code: str) -> None:
        slot = make_slot(document_type=DocumentType.objects.get(code=code))
        version = make_document_file(slot=slot)
        slot.current_file = version
        slot.save(update_fields=["current_file"])
        review(version, advisor_user, ReviewDecision.REJECTED, "Otra vez, por favor.")

    add("IDENTITY_DOCUMENT")
    with CaptureQueriesContext(connection) as one:
        current(advisor_client, application)
    for code in ("PAYROLL_SLIP", "BANK_STATEMENT", "EMPLOYMENT_CERTIFICATE"):
        add(code)
    with CaptureQueriesContext(connection) as four:
        items = current(advisor_client, application)

    assert len(four) == len(one)
    assert {item["last_buyer_comment"] for item in items if item} == {"Otra vez, por favor."}


# --- DocumentFile.uploaded_by ------------------------------------------------------------


def test_document_file_says_the_buyer_uploaded_it(
    advisor_client: APIClient, make_document_file: DocumentFileFactory
) -> None:
    version = make_document_file()

    body = advisor_client.get(f"/api/v1/document-files/{version.pk}").json()

    assert body["uploaded_by"] == {"type": "buyer", "name": "Comprador"}


# --- Paquetes de la solicitud ------------------------------------------------------------


@pytest.fixture
def two_jobs(package_dossier: PackageDossier, advisor_user: User) -> list[DocumentPackageJob]:
    first = request_package(advisor_user, package_dossier.application).job
    build_package(first.pk)
    DocumentPackageJob.objects.filter(pk=first.pk).update(
        created_at=timezone.now() - timedelta(hours=2)
    )
    # Un paquete fallido no se reutiliza: el siguiente pedido crea otro.
    DocumentPackageJob.objects.filter(pk=first.pk).update(status="FAILED")
    second = request_package(advisor_user, package_dossier.application).job
    return [second, first]


def test_application_packages_are_listed_newest_first(
    advisor_client: APIClient, package_dossier: PackageDossier, two_jobs: list[DocumentPackageJob]
) -> None:
    response = advisor_client.get(create_url(package_dossier.application))

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [str(job.pk) for job in two_jobs]
    assert [(i["status"], i["status_label"]) for i in body["items"]] == [
        ("PENDING", "Pendiente"),
        ("FAILED", "Fallido"),
    ]


def test_package_list_uses_the_package_permission(
    broker_client: APIClient,
    other_advisor_client: APIClient,
    package_dossier: PackageDossier,
    two_jobs: list[DocumentPackageJob],
) -> None:
    url = create_url(package_dossier.application)

    assert_error(broker_client.get(url), 403, "PERMISSION_DENIED")
    assert_error(other_advisor_client.get(url), 404, "RESOURCE_NOT_FOUND")


def test_package_detail_has_the_status_label(
    advisor_client: APIClient, two_jobs: list[DocumentPackageJob]
) -> None:
    first = two_jobs[1]
    past = timezone.now() - timedelta(minutes=10)
    DocumentPackageJob.objects.filter(pk=first.pk).update(
        status="COMPLETED",
        started_at=past,
        completed_at=past,
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    body = advisor_client.get(f"/api/v1/document-package-jobs/{first.pk}").json()

    assert (body["status"], body["status_label"]) == ("EXPIRED", "Vencido")
