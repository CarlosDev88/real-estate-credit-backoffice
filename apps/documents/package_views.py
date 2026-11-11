"""Paquetes para radicar (API §19, decisiones 14, 15 y 36 a 42).

Acceso (decisión 37): ``filings.prepare`` con la solicitud en el alcance, para pedir,
consultar y descargar. Un asesor reasignado ve los paquetes anteriores de la solicitud;
uno al que se le quitó, ``404``. Broker y partner no tienen el permiso: ``403``.
"""

from typing import Any

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.documents import packages
from apps.documents.dossier_serializers import DocumentDownloadSerializer
from apps.documents.dossier_views import (
    COMMON_ERRORS,
    DOSSIER_TAG,
    NOT_FOUND,
    DossierView,
    error_response,
    no_store,
)
from apps.documents.models import DocumentPackageJob
from apps.documents.package_serializers import DocumentPackageJobSerializer
from apps.identity.throttling import DocumentDownloadRateThrottle

PREPARE = "filings.prepare"


class PackageView(DossierView):
    def get_job(self, job_id: Any) -> DocumentPackageJob:
        return get_object_or_404(packages.jobs_visible_to(self.actor), pk=job_id)


class ApplicationDocumentPackageJobView(PackageView):
    required_permissions = {"POST": PREPARE}

    @extend_schema(
        tags=[DOSSIER_TAG],
        operation_id="applications_document_package_jobs_create",
        summary="Pedir el paquete para radicar",
        description=(
            "Arma en segundo plano un ZIP con la versión vigente aprobada de cada "
            "documento, en carpetas por titular (`00_SOLICITUD`, `01_TITULAR_...`), y un "
            "`manifest.json` para el banco. Exige solo los documentos: los obligatorios "
            "aprobados y no vencidos, o exonerados. No exige `If-Match` ni evalúa las "
            "reglas del banco. El contenido queda fijo al pedirlo: una carga posterior no "
            "entra en el ZIP.\n\n"
            "Si ya hay un paquete pendiente, en proceso o listo y sin vencer con la misma "
            "huella documental, responde ese con `200` en lugar de crear otro (`201`). Se "
            "consulta en `GET /document-package-jobs/{job_id}`."
        ),
        request=None,
        responses={
            200: DocumentPackageJobSerializer,
            201: DocumentPackageJobSerializer,
            409: error_response("APPLICATION_CLOSED"),
            422: error_response(
                "APPLICATION_NOT_READY, con `DOCUMENT_PENDING`, `DOCUMENT_EXPIRED` o "
                "`DOCUMENTS_NOT_CONFIGURED` en `details`"
            ),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        result = packages.request_package(self.actor, application)
        code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return Response(DocumentPackageJobSerializer(result.job).data, status=code)


class DocumentPackageJobDetailView(PackageView):
    required_permissions = {"GET": PREPARE}

    @extend_schema(
        tags=[DOSSIER_TAG],
        operation_id="document_package_jobs_retrieve",
        summary="Estado de un paquete para radicar",
        description=(
            "`PENDING` → `RUNNING` → `COMPLETED` o `FAILED` (`error_code`: "
            "`CHECKSUM_MISMATCH` o `STORAGE_UNAVAILABLE`). Un `FAILED` no se reintenta: se "
            "pide otro. Un `COMPLETED` pasa a `EXPIRED` a los "
            "`DOCUMENT_PACKAGE_TTL_DAYS` días (7 por omisión). `documents` es el contenido "
            "fijado al pedirlo, con los datos internos que no van al banco."
        ),
        responses={200: DocumentPackageJobSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, job_id: Any) -> Response:
        return Response(DocumentPackageJobSerializer(self.get_job(job_id)).data)


class DocumentPackageJobDownloadView(PackageView):
    required_permissions = {"GET": PREPARE}
    throttle_classes = [DocumentDownloadRateThrottle]

    @extend_schema(
        tags=[DOSSIER_TAG],
        operation_id="document_package_jobs_download",
        summary="Descargar un paquete para radicar",
        description=(
            "URL prefirmada de corta duración (`DOCUMENT_DOWNLOAD_URL_SECONDS`, 5 minutos "
            "por omisión) del ZIP, con `Content-Disposition: attachment`. Comparte el "
            "límite de 60 descargas por hora con las versiones. La URL no se guarda ni va "
            "a los logs."
        ),
        responses={
            200: DocumentDownloadSerializer,
            409: error_response(
                "PACKAGE_NOT_READY (pendiente, en proceso o fallido) o PACKAGE_EXPIRED"
            ),
            429: error_response("RATE_LIMITED"),
            503: error_response("SERVICE_UNAVAILABLE (almacenamiento no disponible)"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def get(self, request: Request, job_id: Any) -> Response:
        job = self.get_job(job_id)
        link = packages.package_download(job, requested_by=f"user:{self.actor.pk}")
        return no_store(Response(DocumentDownloadSerializer(link).data))
