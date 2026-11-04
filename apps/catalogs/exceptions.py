from rest_framework import status

from config.exceptions import ApiError


class CatalogNotManageable(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "CATALOG_NOT_MANAGEABLE"
    default_detail = "Este catálogo lo administra el sistema y no se puede modificar por API."


class DuplicateCode(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "DUPLICATE_CODE"
    default_detail = "Ya existe un registro con ese código."


class TransitionNotEditable(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "TRANSITION_NOT_EDITABLE"
    default_detail = "Solo se puede editar una transición inactiva. Desactívala primero."
