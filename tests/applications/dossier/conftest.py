"""Fixtures del expediente documental (paso 10).

Viven bajo ``tests/applications`` para heredar la solicitud, el titular y los usuarios;
los enlaces y sesiones del comprador se importan de ``buyer_access``.
"""

import hashlib
import io
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.applications.models import ApplicationParticipant, CreditApplication
from apps.catalogs.models import CatalogItem
from apps.crm.models import Client
from apps.documents.constants import JPEG, PDF, PNG
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentFileStatus,
    DocumentType,
    FileObject,
    ScanStatus,
    SlotStatus,
)
from apps.documents.storage import get_storage
from apps.identity.models import BuyerAccessLink, BuyerSession
from apps.identity.tokens import generate_opaque_token, hash_token
from tests.applications.buyer_access.conftest import (
    accept_consents,
    buyer_client,
    buyer_csrf_client,
    make_link,
    make_session,
    portal,
)

__all__ = [
    "accept_consents",
    "buyer_client",
    "buyer_csrf_client",
    "make_link",
    "make_session",
    "portal",
]

SlotFactory = Callable[..., ApplicationDocumentSlot]
FileObjectFactory = Callable[..., FileObject]
DocumentFileFactory = Callable[..., DocumentFile]
ApproveStored = Callable[..., DocumentFile]
WaiveSlot = Callable[..., ApplicationDocumentSlot]


@pytest.fixture
def make_file_object(db: Any) -> FileObjectFactory:
    """Objeto físico creado directamente en la base, sin pasar por el almacenamiento."""

    def _make_file_object(**extra: Any) -> FileObject:
        content = uuid.uuid4().bytes
        extra.setdefault("storage_provider", "s3")
        extra.setdefault("bucket_name", "mvp-credit-private")
        extra.setdefault("object_key", f"documents/{uuid.uuid4()}")
        extra.setdefault("original_filename", "documento.pdf")
        extra.setdefault("detected_mime_type", PDF)
        extra.setdefault("size_bytes", len(content))
        extra.setdefault("sha256", hashlib.sha256(content).hexdigest())
        return FileObject.objects.create(**extra)

    return _make_file_object


@pytest.fixture
def make_slot(application: CreditApplication, primary: ApplicationParticipant) -> SlotFactory:
    """Slot del titular de ``application`` para el tipo indicado (por omisión, cédula)."""

    def _make_slot(**extra: Any) -> ApplicationDocumentSlot:
        extra.setdefault("application", application)
        extra.setdefault("participant", primary)
        extra.setdefault("document_type", DocumentType.objects.get(code="IDENTITY_DOCUMENT"))
        extra.setdefault("is_required", True)
        extra.setdefault("is_waivable", False)
        return ApplicationDocumentSlot.objects.create(**extra)

    return _make_slot


@pytest.fixture
def buyer_session(make_session: Callable[..., BuyerSession]) -> BuyerSession:
    return make_session()


@pytest.fixture
def make_document_file(
    make_slot: SlotFactory, make_file_object: FileObjectFactory, buyer_session: BuyerSession
) -> DocumentFileFactory:
    """Versión cargada por el comprador, con su objeto físico."""

    def _make_document_file(**extra: Any) -> DocumentFile:
        if "slot" not in extra:
            extra["slot"] = make_slot()
        if "file_object" not in extra:
            extra["file_object"] = make_file_object()
        extra.setdefault("version_number", 1)
        extra.setdefault("uploaded_by_buyer_session", buyer_session)
        extra.setdefault("client_filename", "cedula.pdf")
        return DocumentFile.objects.create(**extra)

    return _make_document_file


def approve_required_slots(application: CreditApplication) -> list[ApplicationDocumentSlot]:
    """Aprueba los slots vigentes obligatorios con una versión limpia cada uno, cargada
    por una sesión del comprador creada en la base. Devuelve los slots aprobados."""
    client = application.opportunity.client
    link = BuyerAccessLink.objects.create(
        application=application,
        client=client,
        token_hash=hash_token(generate_opaque_token()),
        expires_at=timezone.now() + timedelta(hours=72),
        consumed_at=timezone.now(),
    )
    session = BuyerSession.objects.create(
        access_link=link,
        client=client,
        application=application,
        session_token_hash=hash_token(generate_opaque_token()),
        expires_at=timezone.now() + timedelta(hours=24),
    )
    slots = list(
        ApplicationDocumentSlot.objects.filter(
            application=application, retired_at__isnull=True, is_required=True
        )
    )
    for slot in slots:
        content = uuid.uuid4().bytes
        file_object = FileObject.objects.create(
            storage_provider="memory",
            bucket_name="memory-bucket",
            object_key=f"documents/{application.pk}/{uuid.uuid4()}",
            original_filename="documento.pdf",
            detected_mime_type=PDF,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            scan_status=ScanStatus.CLEAN,
            scanned_at=timezone.now(),
        )
        version = DocumentFile.objects.create(
            slot=slot,
            file_object=file_object,
            version_number=slot.files.count() + 1,
            uploaded_by_buyer_session=session,
            client_filename="documento.pdf",
            status=DocumentFileStatus.APPROVED,
        )
        slot.current_file = version
        slot.status = SlotStatus.APPROVED
        slot.save(update_fields=["current_file", "status", "updated_at"])
    return slots


@pytest.fixture
def approve_stored(
    make_document_file: DocumentFileFactory, make_file_object: FileObjectFactory
) -> ApproveStored:
    """Aprueba el slot con una versión limpia nueva cuyo contenido sí está en el
    almacenamiento (lo necesita el paquete). Devuelve la versión."""

    def _approve_stored(
        slot: ApplicationDocumentSlot,
        *,
        content: bytes | None = None,
        mime_type: str = PDF,
        client_filename: str = "cedula.pdf",
        document_date: date | None = None,
        expires_at: date | None = None,
    ) -> DocumentFile:
        content = content if content is not None else b"%PDF-1.7 " + uuid.uuid4().bytes
        key = f"documents/{slot.application_id}/{uuid.uuid4()}"
        get_storage().put(key, io.BytesIO(content), content_type=mime_type)
        version = make_document_file(
            slot=slot,
            file_object=make_file_object(
                object_key=key,
                detected_mime_type=mime_type,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                scan_status=ScanStatus.CLEAN,
                scanned_at=timezone.now(),
            ),
            version_number=slot.files.count() + 1,
            client_filename=client_filename,
            status=DocumentFileStatus.APPROVED,
            document_date=document_date,
            expires_at=expires_at,
        )
        ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(
            current_file=version, status=SlotStatus.APPROVED
        )
        slot.refresh_from_db()
        return version

    return _approve_stored


@pytest.fixture
def waive_slot(db: Any) -> WaiveSlot:
    """Exonera el slot con el motivo ``OTHER`` del catálogo."""

    def _waive_slot(slot: ApplicationDocumentSlot) -> ApplicationDocumentSlot:
        reason = CatalogItem.objects.get(catalog__code="document_waiver_reason", code="OTHER")
        ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(
            status=SlotStatus.WAIVED, is_waivable=True, waiver_reason_item=reason
        )
        slot.refresh_from_db()
        return slot

    return _waive_slot


@dataclass(frozen=True)
class PackageDossier:
    """Expediente listo para empaquetar: un documento de la solicitud, el titular (cédula,
    dos desprendibles y una certificación exonerada) y un co-solicitante (cédula)."""

    application: CreditApplication
    co_applicant: ApplicationParticipant
    ownership: ApplicationDocumentSlot
    identity: ApplicationDocumentSlot
    payroll_1: ApplicationDocumentSlot
    payroll_2: ApplicationDocumentSlot
    employment: ApplicationDocumentSlot
    co_identity: ApplicationDocumentSlot
    contents: dict[str, bytes]


@pytest.fixture
def package_dossier(
    application: CreditApplication,
    make_client: Callable[..., Client],
    make_slot: SlotFactory,
    approve_stored: ApproveStored,
    waive_slot: WaiveSlot,
) -> PackageDossier:
    co_applicant = ApplicationParticipant.objects.create(
        application=application,
        client=make_client(
            document_number="80123456", first_names="Andrés Felipe", last_names="Moreno Peña"
        ),
        role="CO_APPLICANT",
    )

    def doc_type(code: str) -> DocumentType:
        return DocumentType.objects.get(code=code)

    ownership = make_slot(participant=None, document_type=doc_type("PROPERTY_OWNERSHIP_DOCUMENT"))
    identity = make_slot()
    payroll_1 = make_slot(document_type=doc_type("PAYROLL_SLIP"), minimum_files=2)
    payroll_2 = make_slot(document_type=doc_type("PAYROLL_SLIP"), minimum_files=2, slot_index=2)
    employment = waive_slot(make_slot(document_type=doc_type("EMPLOYMENT_CERTIFICATE")))
    co_identity = make_slot(participant=co_applicant)
    # Ni el opcional pendiente ni el retirado van en el paquete.
    make_slot(document_type=doc_type("BANK_STATEMENT"), is_required=False)
    approve_stored(
        make_slot(document_type=doc_type("INCOME_TAX_RETURN"), retired_at=timezone.now())
    )

    contents = {
        "ownership": b"%PDF-1.7 escritura",
        "identity": b"%PDF-1.7 cedula titular",
        "payroll_1": b"%PDF-1.7 nomina enero",
        "payroll_2": b"\x89PNG\r\n\x1a\n nomina febrero",
        "co_identity": b"\xff\xd8\xff cedula co-solicitante",
    }
    approve_stored(ownership, content=contents["ownership"], client_filename="escritura.pdf")
    approve_stored(identity, content=contents["identity"], client_filename="cédula Laura.pdf")
    approve_stored(
        payroll_1,
        content=contents["payroll_1"],
        client_filename="enero.pdf",
        document_date=date(2026, 10, 30),
    )
    approve_stored(
        payroll_2, content=contents["payroll_2"], mime_type=PNG, client_filename="febrero.png"
    )
    approve_stored(
        co_identity, content=contents["co_identity"], mime_type=JPEG, client_filename="cc.jpg"
    )
    return PackageDossier(
        application=application,
        co_applicant=co_applicant,
        ownership=ownership,
        identity=identity,
        payroll_1=payroll_1,
        payroll_2=payroll_2,
        employment=employment,
        co_identity=co_identity,
        contents=contents,
    )
