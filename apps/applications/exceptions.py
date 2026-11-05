from rest_framework import status

from config.exceptions import ApiError


class ApplicationAlreadyOpen(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "APPLICATION_ALREADY_OPEN"
    default_detail = "La oportunidad ya tiene una solicitud en curso."


class ApplicationNotEditable(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "APPLICATION_NOT_EDITABLE"
    default_detail = "Los datos de la solicitud solo se editan antes de radicarla."


class ApplicationClosed(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "APPLICATION_CLOSED"
    default_detail = "La solicitud ya terminó y no admite cambios."


class StaleVersion(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "STALE_VERSION"
    default_detail = "La solicitud cambió desde que la consultaste. Vuelve a cargarla."


class PreconditionRequired(ApiError):
    status_code = status.HTTP_428_PRECONDITION_REQUIRED
    error_code = "PRECONDITION_REQUIRED"
    default_detail = "Envía la cabecera If-Match con la versión de la solicitud."


class ParticipantInactive(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "PARTICIPANT_INACTIVE"
    default_detail = "El participante fue retirado de la solicitud. Para usarlo, agrégalo de nuevo."
