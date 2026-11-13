from rest_framework import status

from config.exceptions import ApiError


class BankProductMismatch(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "BANK_PRODUCT_MISMATCH"
    default_detail = "El producto no es el de la financiación de la solicitud."


class PackageOutdated(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "PACKAGE_OUTDATED"
    default_detail = (
        "Los documentos cambiaron después de armar el paquete. Pide un paquete nuevo y "
        "entrégalo al banco."
    )


class PackageAlreadyFiled(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "PACKAGE_ALREADY_FILED"
    default_detail = "El paquete ya se usó en otra radicación."


class FilingReferenceExists(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "FILING_REFERENCE_EXISTS"
    default_detail = "Ya hay una radicación con esa referencia del banco para el producto."


class DocumentObserved(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "DOCUMENT_OBSERVED"
    default_detail = (
        "El banco observó esta versión del documento: aprueba la versión nueva que cargue "
        "el comprador."
    )


class FilingNotLatest(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "FILING_NOT_LATEST"
    default_detail = "Las respuestas del banco se registran solo en la última radicación."


class ResponseCorrectionNotAllowed(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "RESPONSE_CORRECTION_NOT_ALLOWED"
    default_detail = (
        "Solo se corrige la última respuesta de la radicación, con el mismo tipo, y si es "
        "RECEIVED, IN_ANALYSIS u OTHER."
    )


class EvidenceAlreadyAttached(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "EVIDENCE_ALREADY_ATTACHED"
    default_detail = "La respuesta ya tiene su evidencia; no se reemplaza."
