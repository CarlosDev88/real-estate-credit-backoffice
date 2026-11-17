from rest_framework import status

from config.exceptions import ApiError


class IdempotencyConflict(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "IDEMPOTENCY_CONFLICT"
    default_detail = "La clave de idempotencia ya se usó con otro cuerpo."


class IdempotencyInProgress(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "IDEMPOTENCY_IN_PROGRESS"
    default_detail = "Otra petición con la misma clave de idempotencia sigue en curso."


class IdempotencyReplayUnavailable(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "IDEMPOTENCY_REPLAY_UNAVAILABLE"
    default_detail = (
        "La operación ya se hizo con esta clave y su respuesta no se guarda: repítela con "
        "una clave nueva."
    )
