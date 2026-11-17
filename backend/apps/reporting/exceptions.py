from rest_framework import status

from config.exceptions import ApiError


class FilterOutOfScope(ApiError):
    """Un filtro que sale del alcance del usuario (API §22): nunca resultados vacíos."""

    status_code = status.HTTP_403_FORBIDDEN
    error_code = "FILTER_OUT_OF_SCOPE"
    default_detail = "Uno de los filtros está fuera de tu alcance."
