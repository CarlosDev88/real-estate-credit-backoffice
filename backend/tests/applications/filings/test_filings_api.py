"""Radicaciones (Parte 2, API §20.1): precondiciones, efectos, snapshots, alcance por
rol, re-radicación y corrección."""

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import (
    ApplicationStatusHistory,
    BankRuleEvaluation,
    CreditApplication,
)
from apps.applications.signals import application_status_changed
from apps.banking.models import Bank, BankPolicyRule
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Opportunity
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentFileStatus,
    DocumentPackageJob,
    FileObject,
    PackageJobStatus,
    ScanStatus,
    SlotStatus,
)
from apps.documents.packages import request_package
from apps.filings.models import Filing, FilingDocumentSnapshot
from apps.filings.signals import filing_created
from apps.identity.models import Role, User, UserRole
from tests.applications.conftest import application_url, seeded_product
from tests.applications.dossier.conftest import approve_required_slots
from tests.applications.filings.conftest import FilingFactory
from tests.applications.test_property_financing_api import PROPERTY, bank_credit, put
from tests.applications.test_status_api import blocking_rule, set_status, transition
from tests.helpers import assert_error
from tests.partners.conftest import client_for

__all__ = ["blocking_rule"]

pytestmark = pytest.mark.django_db

FILING_FIELDS = {
    "id",
    "application_id",
    "sequence_number",
    "status",
    "status_label",
    "bank_product",
    "channel",
    "external_reference",
    "package_job_id",
    "filed_by",
    "filed_at",
    "target_response_at",
    "comment",
    "responses_count",
    "application_status",
    "application_status_label",
    "created_at",
    "updated_at",
}


def filings_url(application: CreditApplication) -> str:
    return application_url(application, "/filings")


def filing_url(filing: Filing | str, suffix: str = "") -> str:
    filing_id = filing if isinstance(filing, str) else filing.id
    return f"/api/v1/filings/{filing_id}{suffix}"


def complete(job: DocumentPackageJob) -> DocumentPackageJob:
    """El worker no corre en las pruebas: el paquete se marca terminado."""
    now = timezone.now()
    DocumentPackageJob.objects.filter(pk=job.pk).update(
        status=PackageJobStatus.COMPLETED,
        started_at=now - timedelta(minutes=1),
        completed_at=now,
        expires_at=now + timedelta(days=7),
    )
    job.refresh_from_db()
    return job


def new_package(application: CreditApplication, user: User) -> DocumentPackageJob:
    result = request_package(user, application)
    assert result.created
    return complete(result.job)


def payload(
    application: CreditApplication, job: DocumentPackageJob, **extra: Any
) -> dict[str, Any]:
    application.refresh_from_db()
    return {
        "bank_product_id": str(seeded_product().id),
        "package_job_id": str(job.id),
        "channel_code": "BANK_PORTAL",
        "external_reference": "RAD-2026-008154",
        "filed_at": (timezone.now() - timedelta(hours=1)).isoformat(),
        "comment": "Radicada en el portal del banco.",
        "expected_version": application.version,
        **extra,
    }


def file(
    client: APIClient, application: CreditApplication, job: DocumentPackageJob, **extra: Any
) -> Any:
    return client.post(filings_url(application), payload(application, job, **extra), format="json")


@pytest.fixture
def ready(advisor_client: APIClient, application: CreditApplication) -> CreditApplication:
    """Inmueble, crédito bancario y documentos aprobados, en `READY_TO_FILE` (versión 4)."""
    assert put(advisor_client, application, "property", PROPERTY).status_code == 201
    assert put(advisor_client, application, "financing", bank_credit(), '"2"').status_code == 201
    assert approve_required_slots(application)
    set_status(application, ApplicationStatus.DOCUMENTS_REVIEW)
    response = transition(advisor_client, application, "READY_TO_FILE", version=3)
    assert response.status_code == 200, response.content
    application.refresh_from_db()
    return application


@pytest.fixture
def package(ready: CreditApplication, advisor_user: User) -> DocumentPackageJob:
    return new_package(ready, advisor_user)


@pytest.fixture
def events() -> Iterator[list[tuple[str, dict[str, Any]]]]:
    received: list[tuple[str, dict[str, Any]]] = []

    def on_status(**kwargs: Any) -> None:
        received.append(("status", kwargs))

    def on_filing(**kwargs: Any) -> None:
        received.append(("filing", kwargs))

    application_status_changed.connect(on_status)
    filing_created.connect(on_filing)
    yield received
    application_status_changed.disconnect(on_status)
    filing_created.disconnect(on_filing)


def manifest_files(job: DocumentPackageJob) -> set[tuple[str, str, str, str]]:
    assert job.manifest is not None
    return {
        (
            entry["file"]["document_file_id"],
            entry["file"]["file_object_id"],
            entry["file"]["sha256"],
            entry["document_type"]["code"],
        )
        for entry in job.manifest["documents"]
        if entry["file"] is not None
    }


# --- Registrar --------------------------------------------------------------------------


def test_filing_registers_the_delivery(
    advisor_client: APIClient,
    advisor_user: User,
    ready: CreditApplication,
    package: DocumentPackageJob,
    events: list[tuple[str, dict[str, Any]]],
) -> None:
    filed_at = timezone.now() - timedelta(hours=2)

    response = file(advisor_client, ready, package, filed_at=filed_at.isoformat())

    assert response.status_code == 201, response.content
    assert response["ETag"] == '"5"'
    body = response.json()
    assert set(body) == FILING_FIELDS
    filing = Filing.objects.get(pk=body["id"])
    product = seeded_product()
    assert body == {
        **body,
        "application_id": str(ready.id),
        "sequence_number": 1,
        "status": "FILED",
        "status_label": "Radicada",
        "channel": {"code": "BANK_PORTAL", "label": "Portal del banco"},
        "external_reference": "RAD-2026-008154",
        "package_job_id": str(package.id),
        "filed_by": {"id": str(advisor_user.id), "name": advisor_user.get_full_name()},
        "target_response_at": None,
        "comment": "Radicada en el portal del banco.",
        "responses_count": 0,
        "application_status": "FILED",
        "application_status_label": "Radicada",
    }
    assert body["bank_product"]["id"] == str(product.id)
    assert body["bank_product"]["bank"]["code"] == "BANCOLOMBIA"
    assert filing.filed_at == filed_at

    ready.refresh_from_db()
    assert (ready.status, ready.version) == ("FILED", 5)
    history = ApplicationStatusHistory.objects.select_related("transition").latest("created_at")
    assert history.transition is not None
    assert (history.from_status, history.to_status, history.transition.code) == (
        "READY_TO_FILE",
        "FILED",
        "FILE",
    )
    assert history.actor_user == advisor_user

    snapshots = FilingDocumentSnapshot.objects.filter(filing=filing)
    assert {
        (str(s.document_file_id), str(s.file_object_id), s.sha256, s.document_type_code)
        for s in snapshots
    } == manifest_files(package)
    assert manifest_files(package)
    assert package.manifest is not None
    slot_ids = [entry["slot_id"] for entry in package.manifest["documents"]]
    assert not ApplicationDocumentSlot.objects.filter(pk__in=slot_ids, locked_at__isnull=True)

    assert [name for name, _ in events] == ["status", "filing"]
    assert events[0][1]["transition_code"] == "FILE"
    assert (events[1][1]["filing"], events[1][1]["actor"]) == (filing, advisor_user)


def test_target_response_uses_the_bank_days(
    advisor_client: APIClient, ready: CreditApplication, package: DocumentPackageJob
) -> None:
    Bank.objects.filter(code="BANCOLOMBIA").update(filing_response_days=7)
    filed_at = timezone.now() - timedelta(days=1)

    response = file(advisor_client, ready, package, filed_at=filed_at.isoformat())

    assert response.status_code == 201, response.content
    filing = Filing.objects.get(pk=response.json()["id"])
    assert filing.target_response_at == filed_at + timedelta(days=7)


def test_blank_reference_and_comment_are_stored_as_null(
    advisor_client: APIClient, ready: CreditApplication, package: DocumentPackageJob
) -> None:
    response = file(advisor_client, ready, package, external_reference="  ", comment="")

    assert response.status_code == 201, response.content
    body = response.json()
    assert (body["external_reference"], body["comment"]) == (None, None)


# --- Precondiciones ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (ApplicationStatus.DOCUMENTS_REVIEW, "INVALID_STATE_TRANSITION"),
        (ApplicationStatus.FILED, "INVALID_STATE_TRANSITION"),
        (ApplicationStatus.CANCELLED, "APPLICATION_CLOSED"),
    ],
)
def test_only_a_ready_application_is_filed(
    advisor_client: APIClient,
    ready: CreditApplication,
    package: DocumentPackageJob,
    status: str,
    code: str,
) -> None:
    set_status(ready, status)

    assert_error(file(advisor_client, ready, package), 409, code)
    assert not Filing.objects.exists()


def test_expected_version_must_match(
    advisor_client: APIClient, ready: CreditApplication, package: DocumentPackageJob
) -> None:
    stale = file(advisor_client, ready, package, expected_version=3)
    body = assert_error(stale, 409, "STALE_VERSION")
    assert body["details"][0]["current_version"] == 4

    missing = payload(ready, package)
    del missing["expected_version"]
    response = advisor_client.post(filings_url(ready), missing, format="json")
    assert_error(response, 400, "VALIDATION_ERROR")


def test_product_must_be_the_financing_product(
    advisor_client: APIClient, ready: CreditApplication, package: DocumentPackageJob
) -> None:
    other = seeded_product("FNA")

    body = assert_error(
        file(advisor_client, ready, package, bank_product_id=str(other.id)),
        422,
        "BANK_PRODUCT_MISMATCH",
    )
    assert body["details"][0]["field"] == "bank_product_id"


def test_required_documents_must_be_approved_or_waived(
    advisor_client: APIClient, ready: CreditApplication, package: DocumentPackageJob
) -> None:
    slot = ApplicationDocumentSlot.objects.filter(application=ready, is_required=True).first()
    assert slot is not None
    ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(status=SlotStatus.REJECTED)

    body = assert_error(file(advisor_client, ready, package), 422, "APPLICATION_NOT_READY")
    assert [(d["code"], d["resource_id"]) for d in body["details"]] == [
        ("DOCUMENT_PENDING", str(slot.pk))
    ]


def test_blocking_bank_rules_prevent_filing(
    advisor_client: APIClient,
    ready: CreditApplication,
    package: DocumentPackageJob,
    blocking_rule: BankPolicyRule,
) -> None:
    evaluations = BankRuleEvaluation.objects.filter(application=ready).count()

    body = assert_error(file(advisor_client, ready, package), 422, "APPLICATION_NOT_READY")

    assert [detail["code"] for detail in body["details"]] == ["BANK_RULE_BLOCKED"]
    # La guarda evaluó con la regla nueva y la evaluación queda guardada.
    assert BankRuleEvaluation.objects.filter(application=ready).count() == evaluations + 1
    ready.refresh_from_db()
    assert ready.status == ApplicationStatus.READY_TO_FILE


def test_package_must_belong_to_the_application(
    advisor_client: APIClient,
    ready: CreditApplication,
    package: DocumentPackageJob,
    make_application: Callable[..., CreditApplication],
    make_opportunity: Callable[..., Opportunity],
    make_client: Callable[..., Any],
    advisor_user: User,
) -> None:
    other = make_application(make_opportunity(make_client(document_number="80123456")))
    foreign = complete(
        DocumentPackageJob.objects.create(
            application=other, requested_by=advisor_user, application_version=1
        )
    )

    for job_id in (str(foreign.id), "00000000-0000-0000-0000-000000000000"):
        body = assert_error(
            file(advisor_client, ready, package, package_job_id=job_id), 400, "VALIDATION_ERROR"
        )
        assert body["details"][0]["field"] == "package_job_id"


@pytest.mark.parametrize(
    "job_status", [PackageJobStatus.PENDING, PackageJobStatus.RUNNING, PackageJobStatus.FAILED]
)
def test_package_must_be_completed(
    advisor_client: APIClient,
    ready: CreditApplication,
    package: DocumentPackageJob,
    job_status: str,
) -> None:
    DocumentPackageJob.objects.filter(pk=package.pk).update(status=job_status)

    assert_error(file(advisor_client, ready, package), 409, "PACKAGE_NOT_READY")


def test_expired_package_is_rejected(
    advisor_client: APIClient, ready: CreditApplication, package: DocumentPackageJob
) -> None:
    DocumentPackageJob.objects.filter(pk=package.pk).update(
        completed_at=timezone.now() - timedelta(days=8),
        started_at=timezone.now() - timedelta(days=8, minutes=1),
        expires_at=timezone.now() - timedelta(days=1),
    )

    assert_error(file(advisor_client, ready, package), 409, "PACKAGE_EXPIRED")


def test_package_must_have_the_current_fingerprint(
    advisor_client: APIClient,
    ready: CreditApplication,
    package: DocumentPackageJob,
    make_file_object: Callable[..., FileObject],
) -> None:
    """Una versión nueva aprobada después del paquete: los documentos siguen completos,
    pero el paquete ya no es lo que se entregaría."""
    slot = ApplicationDocumentSlot.objects.filter(application=ready, is_required=True).first()
    assert slot is not None and slot.current_file is not None
    newer = DocumentFile.objects.create(
        slot=slot,
        file_object=make_file_object(scan_status=ScanStatus.CLEAN, scanned_at=timezone.now()),
        version_number=slot.current_file.version_number + 1,
        uploaded_by_buyer_session=slot.current_file.uploaded_by_buyer_session,
        client_filename="nueva.pdf",
        status=DocumentFileStatus.APPROVED,
    )
    ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(current_file=newer)

    assert_error(file(advisor_client, ready, package), 409, "PACKAGE_OUTDATED")


def test_package_is_filed_only_once(
    advisor_client: APIClient, ready: CreditApplication, package: DocumentPackageJob
) -> None:
    assert file(advisor_client, ready, package).status_code == 201
    set_status(ready, ApplicationStatus.READY_TO_FILE)

    response = file(advisor_client, ready, package, external_reference="RAD-OTRA")

    assert_error(response, 409, "PACKAGE_ALREADY_FILED")
    assert Filing.objects.count() == 1


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"filed_at": "2999-01-01T00:00:00Z"}, "filed_at"),
        ({"channel_code": "FAX"}, "channel_code"),
        ({"status": "APPROVED"}, "status"),
        ({"external_reference": "x" * 101}, "external_reference"),
    ],
)
def test_body_is_validated(
    advisor_client: APIClient,
    ready: CreditApplication,
    package: DocumentPackageJob,
    changes: dict[str, Any],
    field: str,
) -> None:
    body = assert_error(file(advisor_client, ready, package, **changes), 400, "VALIDATION_ERROR")
    assert [detail["field"] for detail in body["details"]] == [field]


# --- Re-radicación ----------------------------------------------------------------------


def test_second_filing_after_a_return(
    advisor_client: APIClient,
    advisor_user: User,
    ready: CreditApplication,
    package: DocumentPackageJob,
) -> None:
    first = file(advisor_client, ready, package, external_reference="RAD-1")
    assert first.status_code == 201, first.content
    # Las respuestas del banco llegan en la Parte 3: la devolución se simula.
    set_status(ready, ApplicationStatus.BANK_OBSERVATION)
    refile = transition(advisor_client, ready, "READY_TO_FILE", version=ready.version)
    assert refile.status_code == 200, refile.content
    ready.refresh_from_db()

    # El paquete radicado no se reutiliza aunque la huella sea la misma.
    second_package = new_package(ready, advisor_user)
    assert second_package.pk != package.pk
    duplicated = file(advisor_client, ready, second_package, external_reference="RAD-1")
    assert_error(duplicated, 409, "FILING_REFERENCE_EXISTS")
    second = file(advisor_client, ready, second_package, external_reference="RAD-2")

    assert second.status_code == 201, second.content
    assert second.json()["sequence_number"] == 2
    listed = advisor_client.get(filings_url(ready)).json()
    assert [item["sequence_number"] for item in listed["items"]] == [2, 1]
    assert listed["total"] == 2
    assert [item["application_status"] for item in listed["items"]] == ["FILED", "FILED"]


# --- Alcance ----------------------------------------------------------------------------


@pytest.fixture
def originated(ready: CreditApplication, broker_user: User) -> CreditApplication:
    Opportunity.objects.filter(pk=ready.opportunity_id).update(origin_user=broker_user)
    return ready


def test_broker_reads_the_filings_he_originated_without_the_comment(
    advisor_client: APIClient,
    broker_client: APIClient,
    originated: CreditApplication,
    package: DocumentPackageJob,
) -> None:
    filing_id = file(advisor_client, originated, package).json()["id"]

    listed = broker_client.get(filings_url(originated))
    detail = broker_client.get(filing_url(filing_id))

    assert listed.status_code == 200
    assert detail.status_code == 200
    assert set(listed.json()["items"][0]) == FILING_FIELDS - {"comment"}
    assert set(detail.json()) == FILING_FIELDS - {"comment"}
    assert broker_client.get(filing_url(filing_id, "/document-snapshots")).status_code == 403
    assert broker_client.patch(filing_url(filing_id), {"comment": "x"}).status_code == 403
    assert_error(file(broker_client, originated, package), 403, "PERMISSION_DENIED")


def test_out_of_scope_users_get_404(
    advisor_client: APIClient,
    other_advisor_client: APIClient,
    broker_client: APIClient,
    ready: CreditApplication,
    package: DocumentPackageJob,
) -> None:
    filing_id = file(advisor_client, ready, package).json()["id"]

    for client in (other_advisor_client, broker_client):
        assert client.get(filings_url(ready)).status_code == 404
        assert client.get(filing_url(filing_id)).status_code == 404
    assert other_advisor_client.patch(filing_url(filing_id), {"comment": "x"}).status_code == 404
    assert file(other_advisor_client, ready, package).status_code == 404
    assert other_advisor_client.get(filing_url(filing_id, "/document-snapshots")).status_code == (
        404
    )


def test_partner_has_no_access(partner_client: APIClient, ready: CreditApplication) -> None:
    assert partner_client.get(filings_url(ready)).status_code == 403


def test_admin_files_any_application(
    admin_client: APIClient, ready: CreditApplication, package: DocumentPackageJob
) -> None:
    response = file(admin_client, ready, package)

    assert response.status_code == 201, response.content
    assert admin_client.get(
        filing_url(response.json()["id"], "/document-snapshots")
    ).status_code == (200)


def test_only_the_assigned_advisor_writes(
    make_user: Callable[..., User],
    originated: CreditApplication,
    package: DocumentPackageJob,
    broker_user: User,
) -> None:
    """Un asesor que también es broker ve lo que originó, pero solo escribe en lo que
    tiene asignado."""
    UserRole.objects.create(user=broker_user, role=Role.objects.get(code="ADVISOR"))
    client = client_for(broker_user)

    assert client.get(filings_url(originated)).status_code == 200
    assert_error(file(client, originated, package), 403, "PERMISSION_DENIED")


# --- Detalle, corrección y snapshots ----------------------------------------------------


def test_detail_and_unknown_filing(
    advisor_client: APIClient, ready: CreditApplication, package: DocumentPackageJob
) -> None:
    created = file(advisor_client, ready, package).json()

    assert advisor_client.get(filing_url(created["id"])).json() == created
    assert advisor_client.get(filing_url("00000000-0000-0000-0000-000000000000")).status_code == (
        404
    )


def test_patch_only_changes_reference_and_comment(
    advisor_client: APIClient,
    ready: CreditApplication,
    package: DocumentPackageJob,
    make_filing: FilingFactory,
) -> None:
    created = file(advisor_client, ready, package).json()
    ready.refresh_from_db()
    version = ready.version

    response = advisor_client.patch(
        filing_url(created["id"]),
        {"external_reference": " RAD-NUEVA ", "comment": ""},
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert (body["external_reference"], body["comment"]) == ("RAD-NUEVA", None)
    assert body["status"] == "FILED"
    unchanged = advisor_client.patch(filing_url(created["id"]), {}, format="json")
    assert unchanged.json() == body
    ready.refresh_from_db()
    assert ready.version == version

    for changes in ({"status": "APPROVED"}, {"filed_at": "2026-01-01T00:00:00Z"}):
        assert_error(
            advisor_client.patch(filing_url(created["id"]), changes, format="json"),
            400,
            "VALIDATION_ERROR",
        )
    make_filing(ready, external_reference="RAD-OCUPADA")
    assert_error(
        advisor_client.patch(
            filing_url(created["id"]), {"external_reference": "RAD-OCUPADA"}, format="json"
        ),
        409,
        "FILING_REFERENCE_EXISTS",
    )


def test_snapshots_list_the_delivered_versions(
    advisor_client: APIClient, ready: CreditApplication, package: DocumentPackageJob
) -> None:
    filing_id = file(advisor_client, ready, package).json()["id"]

    response = advisor_client.get(filing_url(filing_id, "/document-snapshots"))

    assert response.status_code == 200
    items = response.json()["items"]
    assert {
        (item["document_file_id"], item["sha256"], item["document_type_code"]) for item in items
    } == {(file_id, sha, code) for file_id, _, sha, code in manifest_files(package)}
    first = items[0]
    version = DocumentFile.objects.select_related("file_object").get(pk=first["document_file_id"])
    assert first == {
        **first,
        "slot_id": str(version.slot_id),
        "version_number": version.version_number,
        "client_filename": version.client_filename,
        "mime_type": version.file_object.detected_mime_type,
        "size_bytes": version.file_object.size_bytes,
    }


def test_list_runs_a_fixed_number_of_queries(
    advisor_client: APIClient, ready: CreditApplication, make_filing: FilingFactory
) -> None:
    def count_queries() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert advisor_client.get(filings_url(ready)).status_code == 200
        return len(queries)

    make_filing(ready)
    one = count_queries()
    make_filing(ready)
    make_filing(ready, bank_product=seeded_product("FNA"))

    assert count_queries() == one
