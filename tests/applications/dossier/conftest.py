"""Fixtures del expediente documental (paso 10).

Viven bajo ``tests/applications`` para heredar la solicitud, el titular y los usuarios;
los enlaces y sesiones del comprador se importan de ``buyer_access``.
"""

import hashlib
import uuid
from collections.abc import Callable
from typing import Any

import pytest

from apps.applications.models import ApplicationParticipant, CreditApplication
from apps.documents.constants import PDF
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentType,
    FileObject,
)
from apps.identity.models import BuyerSession
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
