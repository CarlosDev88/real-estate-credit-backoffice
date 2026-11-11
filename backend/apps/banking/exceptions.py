from rest_framework import status

from config.exceptions import ApiError


class RuleDraftExists(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "RULE_DRAFT_EXISTS"
    default_detail = "La regla ya tiene un borrador: edita ese borrador en lugar de crear otro."


class RuleConditionInvalid(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "RULE_CONDITION_INVALID"
    default_detail = "La condición de la regla ya no es válida con los campos permitidos."


class RuleExpired(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "RULE_EXPIRED"
    default_detail = "La vigencia de la regla ya terminó: crea una versión con otra vigencia."
