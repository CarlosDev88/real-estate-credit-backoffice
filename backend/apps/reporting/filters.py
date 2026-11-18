"""Filtros comunes del dashboard y los reportes (API §22, decisiones 3 y 4 de la tarea).

Rango de fechas (``date_from``/``date_to``, ``YYYY-MM-DD``, ambas incluidas, en la zona
del proyecto ``TIME_ZONE`` = ``America/Bogota``):

- Sin ninguna: el mes en curso (día 1 a hoy).
- Solo ``date_to``: ``date_from`` es el día 1 del mes de ``date_to``.
- Solo ``date_from``: ``date_to`` es hoy.
- ``date_to`` en el futuro se recorta a hoy (no es error).
- ``date_from > date_to`` o un rango de más de ``REPORTS_MAX_RANGE_DAYS`` (366) días
  responde ``400 VALIDATION_ERROR``.

Alcance de los filtros: uno que sale del alcance responde ``403 FILTER_OUT_OF_SCOPE``,
nunca resultados vacíos. El asesor solo puede mandar su propio ``advisor_id``; el broker
no puede mandar ``advisor_id``, ``partner_id`` ni ``project_id``. El alcance se revisa
antes que la existencia, para no confirmar qué ids existen. Un id que no existe, o un
``status``/``purpose_code`` desconocido, responde ``400``.

Ruta del proyecto (``partner_id``/``project_id``): el proyecto de una solicitud es el del
inmueble financiado (``properties.project_id``) y, si el inmueble no tiene proyecto o aún
no se registró, el de la oportunidad (``opportunities.project_id``). La constructora es
la de ese proyecto.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from django.conf import settings
from django.db.models import QuerySet
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import serializers

from apps.applications.models import CreditApplication
from apps.applications.services import application_scope_filter, get_application_scope
from apps.banking.models import Bank
from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.services import CrmScope
from apps.identity.models import User
from apps.partners.models import Partner, Project
from apps.reporting.exceptions import FilterOutOfScope

PURPOSE_CATALOG = "loan_purpose"

# Filtros que el broker nunca puede usar: delatan la operación de otros.
BROKER_FORBIDDEN_FILTERS = ("advisor_id", "partner_id", "project_id")


@dataclass(frozen=True)
class ReportFilters:
    """Filtros ya validados, con el rango efectivo."""

    date_from: date
    date_to: date
    advisor_id: uuid.UUID | None = None
    partner_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    bank_id: uuid.UUID | None = None
    purpose_code: str | None = None
    statuses: tuple[str, ...] = field(default=())

    @property
    def period(self) -> dict[str, date]:
        return {"date_from": self.date_from, "date_to": self.date_to}

    def datetime_range(self) -> tuple[datetime, datetime]:
        """``[inicio de date_from, inicio del día siguiente a date_to)`` en Bogotá."""
        start = timezone.make_aware(datetime.combine(self.date_from, time.min))
        end = timezone.make_aware(datetime.combine(self.date_to + timedelta(days=1), time.min))
        return start, end

    def as_dict(self) -> dict[str, Any]:
        """Forma serializable (JSON) de los filtros validados, para señales y trabajos."""
        return {
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
            "advisor_id": str(self.advisor_id) if self.advisor_id else None,
            "partner_id": str(self.partner_id) if self.partner_id else None,
            "project_id": str(self.project_id) if self.project_id else None,
            "bank_id": str(self.bank_id) if self.bank_id else None,
            "purpose_code": self.purpose_code,
            "status": list(self.statuses),
        }


def effective_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """Completa y valida el rango (ver el docstring del módulo)."""
    today = timezone.localdate()
    if date_to is not None and date_to > today:
        date_to = today
    if date_to is None:
        date_to = today
        if date_from is None:
            date_from = today.replace(day=1)
    elif date_from is None:
        date_from = date_to.replace(day=1)
    if date_from > date_to:
        raise serializers.ValidationError({"date_from": ["Debe ser anterior o igual a `date_to`."]})
    max_days = settings.REPORTS_MAX_RANGE_DAYS
    if (date_to - date_from).days + 1 > max_days:
        raise serializers.ValidationError(
            {"date_to": [f"El rango no puede superar {max_days} días."]}
        )
    return date_from, date_to


class DashboardFilterSerializer(serializers.Serializer):
    """Parámetros comunes del dashboard. ``context`` lleva ``user`` y ``scope``."""

    date_from = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
    date_to = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
    advisor_id = serializers.UUIDField(required=False)
    partner_id = serializers.UUIDField(required=False)
    project_id = serializers.UUIDField(required=False)
    bank_id = serializers.UUIDField(required=False)
    purpose_code = serializers.CharField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        self._ensure_in_scope(attrs)
        self._ensure_exist(attrs)
        attrs["date_from"], attrs["date_to"] = effective_range(
            attrs.get("date_from"), attrs.get("date_to")
        )
        return attrs

    def _ensure_in_scope(self, attrs: dict[str, Any]) -> None:
        user: User = self.context["user"]
        scope: CrmScope = self.context["scope"]
        if scope.sees_everything:
            return
        if scope.is_restricted:
            for name in BROKER_FORBIDDEN_FILTERS:
                if attrs.get(name) is not None:
                    raise out_of_scope(name)
            return
        advisor_id = attrs.get("advisor_id")
        if advisor_id is not None and advisor_id != user.pk:
            raise out_of_scope("advisor_id")

    def _ensure_exist(self, attrs: dict[str, Any]) -> None:
        checks: list[tuple[str, QuerySet[Any]]] = [
            ("advisor_id", User.objects.all()),
            ("partner_id", Partner.objects.all()),
            ("project_id", Project.objects.all()),
            ("bank_id", Bank.objects.all()),
        ]
        errors: dict[str, list[str]] = {}
        for name, queryset in checks:
            value = attrs.get(name)
            if value is not None and not queryset.filter(pk=value).exists():
                errors[name] = ["No existe."]
        purpose = attrs.get("purpose_code")
        if (
            purpose
            and not CatalogItem.objects.filter(catalog__code=PURPOSE_CATALOG, code=purpose).exists()
        ):
            errors["purpose_code"] = ["Valor no permitido: no existe en `loan_purpose`."]
        if errors:
            raise serializers.ValidationError(errors)

    def to_filters(self) -> ReportFilters:
        data = self.validated_data
        return ReportFilters(
            date_from=data["date_from"],
            date_to=data["date_to"],
            advisor_id=data.get("advisor_id"),
            partner_id=data.get("partner_id"),
            project_id=data.get("project_id"),
            bank_id=data.get("bank_id"),
            purpose_code=data.get("purpose_code") or None,
            statuses=tuple(data.get("status") or ()),
        )


class ReportFilterSerializer(DashboardFilterSerializer):
    """Parámetros de los reportes: los del dashboard y ``status`` (multivalor:
    ``status=FILED&status=APPROVED``)."""

    status = serializers.ListField(
        child=serializers.ChoiceField(choices=ApplicationStatus.choices), required=False
    )


def out_of_scope(name: str) -> FilterOutOfScope:
    message = "Este filtro está fuera de tu alcance."
    return FilterOutOfScope(
        details=[{"field": name, "code": FilterOutOfScope.error_code, "message": message}]
    )


def parse_filters(
    query_params: Any,
    user: User,
    scope: CrmScope | None = None,
    *,
    serializer_class: type[DashboardFilterSerializer] = DashboardFilterSerializer,
) -> ReportFilters:
    """Valida los parámetros de la petición y devuelve los filtros efectivos."""
    serializer = serializer_class(
        data=query_params,
        context={"user": user, "scope": scope or get_application_scope(user)},
    )
    serializer.is_valid(raise_exception=True)
    return serializer.to_filters()


def scoped_applications(
    user: User,
    filters: ReportFilters,
    *,
    scope: CrmScope | None = None,
    by_creation_date: bool = True,
    by_bank: bool = True,
) -> QuerySet[CreditApplication]:
    """Solicitudes del alcance del usuario con los filtros aplicados.

    ``by_creation_date=False`` omite el rango (la foto por estado y la carga por asesor
    son de hoy); ``by_bank=False`` omite ``bank_id`` (los resultados por banco filtran por
    el banco de la radicación, no por el de la solicitud).
    """
    applications = CreditApplication.objects.all()
    condition = application_scope_filter(user, scope)
    if condition is not None:
        applications = applications.filter(condition)
    if by_creation_date:
        start, end = filters.datetime_range()
        applications = applications.filter(created_at__gte=start, created_at__lt=end)
    if filters.advisor_id is not None:
        applications = applications.filter(assigned_advisor_id=filters.advisor_id)
    if filters.project_id is not None:
        applications = applications.alias(
            report_project_id=Coalesce("financed_property__project_id", "opportunity__project_id")
        ).filter(report_project_id=filters.project_id)
    if filters.partner_id is not None:
        applications = applications.alias(
            report_partner_id=Coalesce(
                "financed_property__project__partner_id", "opportunity__project__partner_id"
            )
        ).filter(report_partner_id=filters.partner_id)
    if by_bank and filters.bank_id is not None:
        applications = applications.filter(bank_product__bank_id=filters.bank_id)
    if filters.purpose_code:
        applications = applications.filter(purpose_item__code=filters.purpose_code)
    if filters.statuses:
        applications = applications.filter(status__in=filters.statuses)
    return applications
