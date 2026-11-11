"""Lista blanca de campos que pueden usar las condiciones de las reglas bancarias.

Es el único lugar donde se declaran. Una condición que nombre un campo que no está
aquí se rechaza al guardar y al publicar. ``apps.applications.rule_context`` construye,
a partir de la solicitud, un contexto con esta misma forma::

    {"financing": {"requested_amount_cop": 294000000}, "property": {...}}

Los nombres siguen las columnas de ``credit_applications``, ``financial_profiles``,
``properties`` y ``financing_preferences`` del modelo de datos. Los valores de
catálogo se exponen por su código (``*_code``). Un dato que la solicitud todavía no
tiene llega como ``null`` y la regla da ``MISSING_DATA``. Si se retira un campo, las
reglas publicadas que lo usen dejarán de poder publicarse de nuevo hasta corregirse.
"""

from dataclasses import dataclass
from enum import StrEnum


class FieldType(StrEnum):
    NUMBER = "number"
    STRING = "string"
    BOOLEAN = "boolean"


@dataclass(frozen=True)
class RuleField:
    type: FieldType
    description: str


RULE_FIELDS: dict[str, RuleField] = {
    # Solicitud
    "application.purpose_code": RuleField(FieldType.STRING, "Finalidad (`loan_purpose`)."),
    "application.is_joint": RuleField(
        FieldType.BOOLEAN, "Solicitud conjunta: hay un co-solicitante activo."
    ),
    "application.participant_count": RuleField(
        FieldType.NUMBER, "Participantes activos, incluido el titular."
    ),
    # Solicitante principal
    "applicant.employment_profile_code": RuleField(
        FieldType.STRING, "Perfil laboral del solicitante principal (`employment_profile`)."
    ),
    "applicant.contract_type_code": RuleField(
        FieldType.STRING, "Tipo de contrato del solicitante principal (`contract_type`)."
    ),
    "applicant.employment_months": RuleField(
        FieldType.NUMBER, "Meses completos desde el inicio del empleo hasta hoy."
    ),
    "applicant.monthly_income_cop": RuleField(FieldType.NUMBER, "Ingreso mensual consolidado."),
    "applicant.monthly_expenses_cop": RuleField(FieldType.NUMBER, "Gastos mensuales."),
    "applicant.assets_cop": RuleField(FieldType.NUMBER, "Activos."),
    "applicant.liabilities_cop": RuleField(FieldType.NUMBER, "Pasivos."),
    # Hogar: participantes activos que aportan ingresos
    "household.monthly_income_cop": RuleField(
        FieldType.NUMBER,
        "Suma del aporte de los participantes que aportan ingresos: `income_share_cop` si "
        "está informado y, si no, el ingreso de su perfil.",
    ),
    "household.monthly_expenses_cop": RuleField(
        FieldType.NUMBER, "Suma de los gastos mensuales de los participantes que aportan ingresos."
    ),
    "household.liabilities_cop": RuleField(
        FieldType.NUMBER, "Suma de los pasivos de los participantes que aportan ingresos."
    ),
    # Inmueble
    "property.property_type_code": RuleField(
        FieldType.STRING, "Tipo de inmueble (`property_type`)."
    ),
    "property.condition_code": RuleField(
        FieldType.STRING, "Estado del inmueble (`property_condition`)."
    ),
    "property.city_code": RuleField(FieldType.STRING, "Municipio DANE (`municipality`)."),
    "property.estimated_value_cop": RuleField(FieldType.NUMBER, "Valor estimado del inmueble."),
    "property.is_owned_by_applicant": RuleField(
        FieldType.BOOLEAN, "El inmueble es del solicitante (remodelación)."
    ),
    "property.has_project": RuleField(
        FieldType.BOOLEAN, "El inmueble pertenece a un proyecto de una constructora."
    ),
    # Financiación
    "financing.financing_mode_code": RuleField(
        FieldType.STRING, "Modalidad de financiación (`financing_mode`)."
    ),
    "financing.requested_amount_cop": RuleField(FieldType.NUMBER, "Monto solicitado."),
    "financing.term_months": RuleField(FieldType.NUMBER, "Plazo en meses."),
    "financing.own_resources_cop": RuleField(FieldType.NUMBER, "Recursos propios."),
    "financing.uses_severance_funds": RuleField(FieldType.BOOLEAN, "Usa cesantías."),
    "financing.severance_funds_cop": RuleField(FieldType.NUMBER, "Valor estimado de cesantías."),
    "financing.currency_mode_code": RuleField(
        FieldType.STRING, "Modalidad monetaria (`currency_mode`)."
    ),
    "financing.amortization_mode_code": RuleField(
        FieldType.STRING, "Modalidad de amortización (`amortization_mode`)."
    ),
    "financing.external_approved_amount_cop": RuleField(
        FieldType.NUMBER, "Monto aprobado por otra entidad (crédito externo)."
    ),
}
