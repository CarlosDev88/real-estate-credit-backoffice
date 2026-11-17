"""Modelos de la radicación (Parte 1): las restricciones del esquema (§8 del SQL)."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.contrib import admin
from django.db import IntegrityError, transaction
from django.test import RequestFactory
from django.utils import timezone

from apps.applications.models import CreditApplication
from apps.documents.models import DocumentFile
from apps.filings.models import (
    Filing,
    FilingDocumentSnapshot,
    FilingResponse,
    FilingResponseObservation,
    FilingStatus,
)
from apps.identity.models import User
from tests.applications.conftest import catalog_item
from tests.applications.filings.conftest import FilingFactory, ObservationFactory

pytestmark = pytest.mark.django_db


def violates(constraint: str, create: Callable[..., Any], **values: Any) -> None:
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        create(**values)


def test_filing_defaults_and_text(
    make_filing: FilingFactory, application: CreditApplication
) -> None:
    filing = make_filing(application)

    assert filing.status == FilingStatus.FILED
    assert (filing.sequence_number, filing.target_response_at, filing.comment) == (1, None, None)
    assert str(filing) == f"{application.id} #1 (FILED)"
    assert list(FilingStatus.values) == [
        "FILED",
        "RECEIVED",
        "IN_ANALYSIS",
        "RETURNED",
        "APPROVED",
        "REJECTED",
        "DISBURSED",
    ]


def test_filing_constraints(make_filing: FilingFactory, application: CreditApplication) -> None:
    first = make_filing(application, external_reference="RAD-1")
    now = timezone.now()

    violates("uq_filings_application_sequence", lambda: make_filing(application, sequence_number=1))
    violates("ck_filings_sequence", lambda: make_filing(application, sequence_number=0))
    violates("ck_filings_status", lambda: make_filing(application, status="LOST"))
    violates(
        "ck_filings_target",
        lambda: make_filing(application, filed_at=now, target_response_at=now - timedelta(days=1)),
    )
    # La referencia del banco es única por producto; sin referencia no hay choque.
    violates(
        "uq_filings_external_reference",
        lambda: make_filing(application, external_reference="RAD-1"),
    )
    make_filing(application, external_reference=None)
    make_filing(application, external_reference=None)
    with pytest.raises(IntegrityError), transaction.atomic():
        Filing.objects.create(
            application=application,
            package_job=first.package_job,
            sequence_number=9,
            bank_product=first.bank_product,
            channel_item=first.channel_item,
            filed_by=first.filed_by,
            filed_at=now,
        )


def test_snapshot_is_unique_per_filing_and_version(
    make_filing: FilingFactory,
    application: CreditApplication,
    make_document_file: Callable[..., DocumentFile],
) -> None:
    filing = make_filing(application)
    version = make_document_file()

    def snapshot() -> FilingDocumentSnapshot:
        return FilingDocumentSnapshot.objects.create(
            filing=filing,
            document_file=version,
            file_object=version.file_object,
            sha256=version.file_object.sha256,
            document_type_code="IDENTITY_DOCUMENT",
        )

    assert str(snapshot()) == f"{filing.id}: IDENTITY_DOCUMENT"
    violates("uq_filing_document_snapshots_file", snapshot)


def response(filing: Filing, user: User, **extra: Any) -> FilingResponse:
    extra.setdefault("response_type_item", catalog_item("filing_response_type", "APPROVED"))
    return FilingResponse.objects.create(
        filing=filing, received_at=timezone.now(), recorded_by=user, **extra
    )


def test_response_constraints(
    make_filing: FilingFactory, application: CreditApplication, advisor_user: User
) -> None:
    filing = make_filing(application)
    approved = response(
        filing,
        advisor_user,
        approved_amount_cop=0,
        approved_term_months=1,
        disbursed_amount_cop=0,
    )
    assert str(approved) == f"{filing.id}: {approved.response_type_item_id}"

    for constraint, values in [
        ("ck_filing_responses_approved_amount", {"approved_amount_cop": -1}),
        ("ck_filing_responses_approved_term", {"approved_term_months": 0}),
        ("ck_filing_responses_disbursed_amount", {"disbursed_amount_cop": -1}),
    ]:
        violates(constraint, response, filing=filing, user=advisor_user, **values)

    correction = response(filing, advisor_user, corrects_response=approved)
    assert approved.correction == correction
    # Una respuesta se corrige una sola vez y nunca a sí misma.
    violates(
        "corrects_response_id", lambda: response(filing, advisor_user, corrects_response=approved)
    )
    with pytest.raises(IntegrityError, match="ck_filing_responses_not_self_correction"):
        with transaction.atomic():
            FilingResponse.objects.filter(pk=correction.pk).update(corrects_response=correction)


def test_observation_constraints(
    make_observation: ObservationFactory,
    make_document_file: Callable[..., DocumentFile],
) -> None:
    version = make_document_file()
    observation = make_observation(version.slot)

    assert observation.is_open
    assert str(observation) == f"{observation.filing_response_id}: {version.slot_id}"
    violates(
        "uq_filing_response_observations_slot",
        lambda: FilingResponseObservation.objects.create(
            filing_response=observation.filing_response,
            document_slot=version.slot,
            reason_item=observation.reason_item,
            buyer_message="Otra vez.",
        ),
    )
    for values in ({"resolved_at": timezone.now()}, {"resolved_by_file": version}):
        violates(
            "ck_filing_response_observations_resolution",
            FilingResponseObservation.objects.filter(pk=observation.pk).update,
            **values,
        )

    FilingResponseObservation.objects.filter(pk=observation.pk).update(
        resolved_by_file=version, resolved_at=timezone.now()
    )
    observation.refresh_from_db()
    assert not observation.is_open


@pytest.mark.parametrize(
    "model",
    [Filing, FilingDocumentSnapshot, FilingResponse, FilingResponseObservation],
)
def test_admin_is_read_only(model: type[Any], admin_user: User) -> None:
    model_admin = admin.site._registry[model]
    request = RequestFactory().get("/admin/")
    request.user = admin_user

    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)
