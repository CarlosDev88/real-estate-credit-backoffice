"""Solicitudes radicadas de ``seed_demo_data`` (Cierre del paso 11).

La idempotencia la prueba ``tests/applications/test_demo_data.py``: su segundo
``seed`` cuenta también las radicaciones y las respuestas.
"""

import pytest
from django.utils import timezone

from apps.applications.demo_data import DEMO_CASES
from apps.catalogs.workflow import ApplicationStatus
from apps.documents import uploads
from apps.documents.models import SlotStatus
from apps.filings.demo_data import FILED_DEMO_CASES, FILED_DEMO_STATUSES
from apps.filings.models import (
    Filing,
    FilingDocumentSnapshot,
    FilingResponseObservation,
    FilingStatus,
)
from apps.filings.observations import open_observations
from tests.applications.test_demo_data import seed

pytestmark = pytest.mark.django_db


def test_seed_files_three_applications_with_bank_responses() -> None:
    seed()

    filings = list(
        Filing.objects.select_related("application", "package_job").order_by("created_at")
    )
    assert len(filings) == len(FILED_DEMO_CASES) == 3
    assert [filing.application.status for filing in filings] == list(FILED_DEMO_STATUSES)
    assert [filing.status for filing in filings] == [
        FilingStatus.IN_ANALYSIS,
        FilingStatus.RETURNED,
        FilingStatus.APPROVED,
    ]
    now = timezone.now()
    for filing, filed in zip(filings, FILED_DEMO_CASES, strict=True):
        assert filing.sequence_number == 1
        assert filing.channel_item.code == filed.channel
        assert filing.package_job.status == "COMPLETED"
        assert filing.package_job.manifest is not None
        packaged = [
            entry for entry in filing.package_job.manifest["documents"] if entry["file"] is not None
        ]
        assert FilingDocumentSnapshot.objects.filter(filing=filing).count() == len(packaged) > 0
        history = filing.responses.order_by("received_at")
        codes = list(history.values_list("response_type_item__code", flat=True))
        assert codes == list(filed.responses)
        received = history.values_list("received_at", flat=True)
        assert all(filing.filed_at < moment < now for moment in received)

    # La devuelta tiene un documento observado que el comprador puede reemplazar.
    returned = filings[1].application
    observation = FilingResponseObservation.objects.select_related("document_slot").get(
        document_slot__application=returned
    )
    assert list(open_observations(returned.pk)) == [observation]
    slot = observation.document_slot
    assert slot.status == SlotStatus.REJECTED
    assert uploads.upload_block(returned, slot) is None

    # La aprobada lleva las condiciones de su financiación.
    approved = filings[2].responses.get(response_type_item__code="APPROVED")
    assert approved.approved_amount_cop and approved.approved_term_months
    assert approved.public_message

    # Las demás solicitudes de la demo no se radican.
    assert Filing.objects.exclude(application__status__in=FILED_DEMO_STATUSES).count() == 0
    assert len(DEMO_CASES) == 30
    assert ApplicationStatus.READY_TO_FILE not in FILED_DEMO_STATUSES
