from rest_framework import status

from config.exceptions import ApiError


class RequirementScopeExists(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "REQUIREMENT_SCOPE_EXISTS"
    default_detail = "Ya existe un requisito con ese alcance: edítalo para crear una versión nueva."


class RequirementDraftExists(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "REQUIREMENT_DRAFT_EXISTS"
    default_detail = "El requisito ya tiene un borrador: edita ese borrador en lugar de crear otro."


class RequirementExpired(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "REQUIREMENT_EXPIRED"
    default_detail = "La vigencia del requisito ya terminó: crea una versión con otra vigencia."


class DocumentTypeInactive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "DOCUMENT_TYPE_INACTIVE"
    default_detail = "El tipo documental está inactivo: actívalo antes de publicar el requisito."


# --- Archivos del expediente (paso 10) ----------------------------------------------------


class UnsupportedFileType(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "UNSUPPORTED_FILE_TYPE"
    default_detail = "El formato del archivo no está permitido para este documento."


class FileTooLarge(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "FILE_TOO_LARGE"
    default_detail = "El archivo supera el tamaño máximo permitido para este documento."


class StorageUnavailable(Exception):
    """El almacenamiento de objetos no respondió o rechazó la operación.

    No es un error de la API: quien lo captura decide si responde ``503`` o reintenta.
    El mensaje nunca incluye la clave del objeto ni credenciales.
    """


class ScannerUnavailable(Exception):
    """El antivirus no respondió o devolvió un error. El archivo sigue ``PENDING``."""
