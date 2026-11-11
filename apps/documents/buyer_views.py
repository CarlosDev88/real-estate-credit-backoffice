"""Expediente documental en el portal del comprador (decisiones 2, 4, 5, 11 y 12).

- ``GET /buyer/applications/{id}/document-slots``
- ``GET /buyer/document-slots/{slot_id}`` y ``.../versions``
- ``POST /buyer/document-slots/{slot_id}/uploads`` (``multipart/form-data``)
- ``GET /buyer/document-files/{file_id}/download``

Solo la cookie del comprador autentica. Un slot de otra solicitud o retirado responde
``404``. La carga exige CSRF y los consentimientos, y responde ``409
APPLICATION_CLOSED`` con la solicitud terminada. No usa ``If-Match``: los documentos no
cambian la versión de la solicitud (acordada 6).
"""

from typing import Any, BinaryIO, cast

from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.models import CreditApplication
from apps.documents import dossier, downloads, uploads
from apps.documents.buyer_serializers import (
    BuyerDocumentSlotSerializer,
    BuyerDocumentUploadSerializer,
    BuyerDocumentVersionSerializer,
)
from apps.documents.dossier_serializers import DocumentDownloadSerializer
from apps.documents.dossier_views import DOWNLOAD_DESCRIPTION, no_store
from apps.documents.exceptions import PayloadTooLarge
from apps.documents.models import ApplicationDocumentSlot
from apps.identity.buyer_portal_views import (
    BUYER_PORTAL_TAG,
    NOT_FOUND,
    SESSION_ERRORS,
    BuyerPortalView,
)
from apps.identity.throttling import (
    BuyerDocumentUploadRateThrottle,
    DocumentDownloadRateThrottle,
)
from config.serializers import ErrorSerializer


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


READ_ERRORS = {**NOT_FOUND, **SESSION_ERRORS}


class BuyerDossierView(BuyerPortalView):
    def get_slot(self, slot_id: Any) -> ApplicationDocumentSlot:
        return get_object_or_404(dossier.buyer_slot_queryset(self.buyer_session), pk=slot_id)

    def slot_context(self) -> dict[str, Any]:
        application = CreditApplication.objects.only("status").get(
            pk=self.buyer_session.application_id
        )
        return {"application": application}

    def slot_response(self, slot_id: Any, **kwargs: Any) -> Response:
        slot = self.get_slot(slot_id)
        return Response(
            BuyerDocumentSlotSerializer(slot, context=self.slot_context()).data, **kwargs
        )


class BuyerDocumentSlotListView(BuyerDossierView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_document_slots_list",
        summary="Documentos que pide la solicitud",
        description=(
            "Un elemento por archivo esperado: primero los documentos de la solicitud "
            "(`participant` nulo) y después los de cada participante. Trae los formatos y "
            "el tamaño máximo que admite cada uno, si hoy admite una carga y, si está "
            "rechazado, el motivo y el comentario del asesor."
        ),
        responses={200: BuyerDocumentSlotSerializer(many=True), **READ_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        self.ensure_session_application(application_id)
        page = self.paginate_queryset(dossier.buyer_slot_queryset(self.buyer_session))
        data = BuyerDocumentSlotSerializer(page, many=True, context=self.slot_context()).data
        return self.get_paginated_response(data)


class BuyerDocumentSlotDetailView(BuyerDossierView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_document_slots_retrieve",
        summary="Detalle de un documento esperado",
        responses={200: BuyerDocumentSlotSerializer, **READ_ERRORS},
    )
    def get(self, request: Request, slot_id: Any) -> Response:
        return self.slot_response(slot_id)


class BuyerDocumentSlotVersionListView(BuyerDossierView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_document_slots_versions_list",
        summary="Archivos cargados en un documento",
        description="De la más reciente a la primera. `is_current` marca la vigente.",
        responses={200: BuyerDocumentVersionSerializer(many=True), **READ_ERRORS},
    )
    def get(self, request: Request, slot_id: Any) -> Response:
        slot = self.get_slot(slot_id)
        page = self.paginate_queryset(dossier.buyer_versions(slot))
        context = {"current_file_id": slot.current_file_id}
        return self.get_paginated_response(
            BuyerDocumentVersionSerializer(page, many=True, context=context).data
        )


def _ensure_request_size(request: Request) -> None:
    """Corta un cuerpo demasiado grande antes de leerlo: la autenticación del comprador
    lee el formulario al validar el CSRF."""
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    limit = settings.DOCUMENT_UPLOAD_MAX_REQUEST_BYTES
    if length > limit:
        raise PayloadTooLarge(f"La carga supera el máximo de {limit} bytes.")


class BuyerDocumentUploadView(BuyerDossierView):
    parser_classes = [MultiPartParser]
    throttle_classes = [BuyerDocumentUploadRateThrottle]

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        _ensure_request_size(request)
        super().initial(request, *args, **kwargs)

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_document_slots_upload",
        summary="Cargar un archivo en un documento",
        description=(
            "Cada carga es una versión nueva: la anterior se conserva y el documento queda "
            "`UPLOADED` mientras corre el análisis de seguridad. Se valida el tipo real por "
            "su contenido, la extensión y el tamaño máximo del documento. Antes de la "
            "radicación se puede cargar en documentos pendientes, cargados o rechazados; "
            "después, solo en los rechazados con una observación abierta del banco. "
            "Límite: 60 cargas por hora por sesión. Responde el documento actualizado."
        ),
        request={"multipart/form-data": BuyerDocumentUploadSerializer},
        responses={
            201: BuyerDocumentSlotSerializer,
            400: _error("VALIDATION_ERROR (sin archivo, vacío o fecha futura)"),
            401: SESSION_ERRORS[401],
            403: _error("CSRF_FAILED o CONSENT_REQUIRED"),
            409: _error(
                "DOCUMENT_LOCKED, DOCUMENT_NOT_REJECTED, DOCUMENT_QUOTA_EXCEEDED o "
                "APPLICATION_CLOSED"
            ),
            413: _error("PAYLOAD_TOO_LARGE"),
            422: _error("UNSUPPORTED_FILE_TYPE o FILE_TOO_LARGE"),
            429: _error("RATE_LIMITED"),
            503: _error("SERVICE_UNAVAILABLE (almacenamiento no disponible)"),
            **NOT_FOUND,
        },
    )
    def post(self, request: Request, slot_id: Any) -> Response:
        slot = self.get_slot(slot_id)
        serializer = BuyerDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data["file"]
        uploads.upload_document(
            self.buyer_session,
            slot,
            uploads.Upload(
                stream=cast(BinaryIO, uploaded),
                filename=uploaded.name or "",
                declared_mime_type=uploaded.content_type,
                document_date=serializer.validated_data["document_date"],
            ),
        )
        return self.slot_response(slot_id, status=status.HTTP_201_CREATED)


class BuyerDocumentFileDownloadView(BuyerDossierView):
    throttle_classes = [DocumentDownloadRateThrottle]

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_document_files_download",
        summary="Descargar un archivo cargado",
        description=(
            "Cualquier versión de un documento vigente de la solicitud de la sesión. "
            + DOWNLOAD_DESCRIPTION
        ),
        responses={
            200: DocumentDownloadSerializer,
            409: _error("FILE_NOT_CLEAN"),
            429: _error("RATE_LIMITED"),
            503: _error("SERVICE_UNAVAILABLE (almacenamiento no disponible)"),
            **READ_ERRORS,
        },
    )
    def get(self, request: Request, file_id: Any) -> Response:
        version = get_object_or_404(dossier.buyer_files(self.buyer_session), pk=file_id)
        link = downloads.download_link(
            version, requested_by=f"buyer_session:{self.buyer_session.pk}"
        )
        return no_store(Response(DocumentDownloadSerializer(link).data))
