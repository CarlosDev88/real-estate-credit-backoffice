from rest_framework import status

from config.exceptions import ApiError


class OutOfScope(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "OUT_OF_SCOPE"
    default_detail = "No tienes una membresía activa en una constructora."


class DuplicateTaxId(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "DUPLICATE_TAX_ID"
    default_detail = "Ya existe una constructora con ese NIT."


class PartnerNotActive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "PARTNER_NOT_ACTIVE"
    default_detail = "La constructora no está activa."


class UserNotEligible(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "USER_NOT_ELIGIBLE"
    default_detail = "El usuario debe estar activo y tener el rol CONSTRUCTION_PARTNER."


class UserAlreadyInPartner(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "USER_ALREADY_IN_PARTNER"
    default_detail = "El usuario ya tiene una membresía activa en una constructora."


class MembershipEnded(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "MEMBERSHIP_ENDED"
    default_detail = "La membresía ya finalizó; crea una nueva si el usuario regresa."


class DuplicateProjectName(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "DUPLICATE_PROJECT_NAME"
    default_detail = "La constructora ya tiene un proyecto abierto con ese nombre o código."


class ProjectNotEditable(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "PROJECT_NOT_EDITABLE"
    default_detail = "El proyecto no se puede editar en su estado actual."


class InvalidStateTransition(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "INVALID_STATE_TRANSITION"
    default_detail = "La acción no está permitida en el estado actual del proyecto."


class ProjectNotActive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "PROJECT_NOT_ACTIVE"
    default_detail = "Solo un proyecto activo puede asociarse a oportunidades nuevas."
