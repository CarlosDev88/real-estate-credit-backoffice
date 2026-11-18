from rest_framework import status

from config.exceptions import ApiError


class FilterOutOfScope(ApiError):
    """Un filtro que sale del alcance del usuario (API §22): nunca resultados vacíos."""

    status_code = status.HTTP_403_FORBIDDEN
    error_code = "FILTER_OUT_OF_SCOPE"
    default_detail = "Uno de los filtros está fuera de tu alcance."


class ExportTooLarge(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "EXPORT_TOO_LARGE"
    default_detail = (
        "El resultado supera el límite de la descarga directa. Usa la exportación "
        "asíncrona o acota los filtros."
    )


class TooManyExports(ApiError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "TOO_MANY_EXPORTS"
    default_detail = (
        "Ya tienes 3 exportaciones pendientes o en proceso. Espera a que terminen para pedir otra."
    )


class ExportNotReady(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "EXPORT_NOT_READY"
    default_detail = "La exportación todavía no está lista o falló."


class ExportExpired(ApiError):
    status_code = status.HTTP_410_GONE
    error_code = "EXPORT_EXPIRED"
    default_detail = "La exportación venció. Pide una nueva."
