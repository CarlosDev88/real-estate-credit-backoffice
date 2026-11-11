from rest_framework import status

from config.exceptions import ApiError


class DuplicateClientDocument(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "DUPLICATE_CLIENT_DOCUMENT"
    default_detail = "Ya existe un cliente con ese tipo y número de documento."


class DuplicateOpportunity(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "DUPLICATE_OPPORTUNITY"
    default_detail = "El cliente ya tiene una oportunidad abierta para ese proyecto."


class OpportunityNotEditable(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "OPPORTUNITY_NOT_EDITABLE"
    default_detail = "La oportunidad está cerrada y no se puede modificar."


class AdvisorNotEligible(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "ADVISOR_NOT_ELIGIBLE"
    default_detail = "El responsable debe ser un usuario activo con rol ADVISOR."
