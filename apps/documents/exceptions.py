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
