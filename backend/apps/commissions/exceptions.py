from rest_framework import status

from config.exceptions import ApiError


class CommissionPlanNotFound(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "COMMISSION_PLAN_NOT_FOUND"
    default_detail = (
        "No hay un plan de comisión vigente para el producto en la fecha de desembolso."
    )


class CommissionPlanOverlap(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "COMMISSION_PLAN_OVERLAP"
    default_detail = "La vigencia se solapa con otro plan del mismo producto."


class CommissionPlanInUse(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "COMMISSION_PLAN_IN_USE"
    default_detail = "El plan ya se usó en una liquidación: no se edita. Ciérralo y crea uno nuevo."


class ApplicationNotDisbursed(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "APPLICATION_NOT_DISBURSED"
    default_detail = "La solicitud no está desembolsada."


class SettlementHasPayments(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "COMMISSION_SETTLEMENT_HAS_PAYMENTS"
    default_detail = "La liquidación tiene partes pagadas: no se puede anular."


class ShareNotPayable(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "COMMISSION_SHARE_NOT_PAYABLE"
    default_detail = "La parte no está pendiente de pago."
