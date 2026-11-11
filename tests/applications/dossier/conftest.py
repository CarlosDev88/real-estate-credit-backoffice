"""Fixtures del expediente documental (paso 10).

Viven bajo ``tests/applications`` para heredar la solicitud, el titular y los usuarios;
los enlaces y sesiones del comprador se importan de ``buyer_access``.
"""

import hashlib
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.applications.models import ApplicationParticipant, CreditApplication
from apps.documents.constants import PDF
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentFileStatus,
    DocumentType,
    FileObject,
    ScanStatus,
    SlotStatus,
)
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
