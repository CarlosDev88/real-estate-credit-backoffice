"""Fixtures de la radicación (paso 11).

Viven bajo ``tests/applications`` para heredar la solicitud, el titular y los usuarios;
las del expediente documental se importan de ``dossier``.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.applications.models import CreditApplication
from apps.documents.models import ApplicationDocumentSlot, DocumentPackageJob, PackageJobStatus
from apps.filings.models import Filing, FilingResponse, FilingResponseObservation
from apps.identity.models import User
from tests.applications.conftest import catalog_item, seeded_product
from tests.applications.dossier.conftest import (
    accept_consents,
    approve_stored,
    buyer_client,
    buyer_csrf_client,
    buyer_session,
    make_document_file,
    make_file_object,
    make_link,
    make_session,
    make_slot,
    package_dossier,
    portal,
    waive_slot,
)

__all__ = [
    "accept_consents",
    "approve_stored",
    "buyer_client",
    "buyer_csrf_client",
    "buyer_session",
    "make_document_file",
    "make_file_object",
    "make_link",
    "make_session",
    "make_slot",
    "package_dossier",
    "portal",
    "waive_slot",
]

FilingFactory = Callable[..., Filing]
ObservationFactory = Callable[..., FilingResponseObservation]


@pytest.fixture
def make_filing(advisor_user: User) -> FilingFactory:
    """Radicación creada directamente en la base, con un paquete terminado propio."""

    def _make_filing(application: CreditApplication, **extra: Any) -> Filing:
        now = timezone.now()
        job = DocumentPackageJob.objects.create(
            application=application,
            requested_by=advisor_user,
            application_version=application.version,
            status=PackageJobStatus.COMPLETED,
            manifest={"files": []},
            started_at=now - timedelta(minutes=1),
            completed_at=now,
            expires_at=now + timedelta(days=1),
        )
        extra.setdefault("sequence_number", application.filings.count() + 1)
        extra.setdefault("bank_product", seeded_product())
        extra.setdefault("channel_item", catalog_item("filing_channel", "BANK_PORTAL"))
        extra.setdefault("filed_by", advisor_user)
        extra.setdefault("filed_at", now)
        return Filing.objects.create(application=application, package_job=job, **extra)

    return _make_filing


@pytest.fixture
def make_observation(advisor_user: User, make_filing: FilingFactory) -> ObservationFactory:
    """Devolución del banco con una observación abierta sobre ``slot``."""

    def _make_observation(slot: ApplicationDocumentSlot, **extra: Any) -> FilingResponseObservation:
        filing = extra.pop("filing", None) or make_filing(slot.application)
        response = FilingResponse.objects.create(
            filing=filing,
            response_type_item=catalog_item("filing_response_type", "RETURNED"),
            reason_item=catalog_item("filing_return_reason", "DOCUMENT_CORRECTION"),
            received_at=timezone.now(),
            public_message="El banco pide corregir un documento.",
            recorded_by=advisor_user,
        )
        extra.setdefault("reason_item", catalog_item("document_rejection_reason", "ILLEGIBLE"))
        extra.setdefault("buyer_message", "Vuelve a cargarlo, no se lee.")
        return FilingResponseObservation.objects.create(
            filing_response=response, document_slot=slot, **extra
        )

    return _make_observation
