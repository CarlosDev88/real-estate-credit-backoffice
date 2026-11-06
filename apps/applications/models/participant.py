import uuid

from django.db import models
from django.db.models import Q

# Los requisitos documentales (paso 7) ya filtran por estos mismos roles; se comparte
# la enumeración para que ambos módulos no puedan divergir.
from apps.documents.models import ParticipantRole


class ApplicationParticipant(models.Model):
    """Persona que participa en una solicitud: titular, co-solicitante o deudor solidario.

    Tabla N:M entre solicitudes y clientes con el papel de cada persona. Retirar un
    participante lo marca inactivo, para conservar su historia.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    application = models.ForeignKey(
        "applications.CreditApplication", on_delete=models.RESTRICT, related_name="participants"
    )
    client = models.ForeignKey(
        "crm.Client", on_delete=models.RESTRICT, related_name="application_participations"
    )
    role = models.CharField(max_length=30, choices=ParticipantRole.choices)
    contributes_income = models.BooleanField(default=True)
    # Aporte declarado al hogar; vacío usa el ingreso de su perfil financiero.
    income_share_cop = models.BigIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "application_participants"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["application", "client"], name="uq_application_participants_client"
            ),
            # Exactamente un titular vigente por solicitud (el "al menos uno" lo
            # garantiza el servicio, que lo crea junto con la solicitud).
            models.UniqueConstraint(
                fields=["application"],
                condition=Q(role=ParticipantRole.PRIMARY, is_active=True),
                name="uq_application_participants_primary",
            ),
            models.CheckConstraint(
                condition=Q(role__in=ParticipantRole.values),
                name="ck_application_participants_role",
            ),
            models.CheckConstraint(
                condition=Q(income_share_cop__isnull=True) | Q(income_share_cop__gte=0),
                name="ck_application_participants_income_share",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.role} {self.client_id} en {self.application_id}"


class FinancialProfile(models.Model):
    """Resumen financiero de un participante dentro de una solicitud.

    No vive en ``clients`` porque puede cambiar entre solicitudes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    participant = models.OneToOneField(
        ApplicationParticipant, on_delete=models.CASCADE, related_name="financial_profile"
    )
    # Ítem del catálogo `employment_profile`; decide los documentos de ingresos.
    employment_profile_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    # Ítem del catálogo `contract_type`.
    contract_type_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    employer_name = models.CharField(max_length=180, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    employment_start_date = models.DateField(null=True, blank=True)
    monthly_income_cop = models.BigIntegerField(default=0)
    monthly_expenses_cop = models.BigIntegerField(default=0)
    assets_cop = models.BigIntegerField(default=0)
    liabilities_cop = models.BigIntegerField(default=0)
    # Ítem del catálogo `funds_origin`.
    funds_origin_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    data_confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "financial_profiles"
        constraints = [
            models.CheckConstraint(
                condition=Q(monthly_income_cop__gte=0),
                name="ck_financial_profiles_income",
            ),
            models.CheckConstraint(
                condition=Q(monthly_expenses_cop__gte=0),
                name="ck_financial_profiles_expenses",
            ),
            models.CheckConstraint(
                condition=Q(assets_cop__gte=0), name="ck_financial_profiles_assets"
            ),
            models.CheckConstraint(
                condition=Q(liabilities_cop__gte=0),
                name="ck_financial_profiles_liabilities",
            ),
        ]

    def __str__(self) -> str:
        return f"Perfil de {self.participant_id}"


class IncomeSource(models.Model):
    """Empleo, pensión, arriendo u otro ingreso de un perfil financiero."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    financial_profile = models.ForeignKey(
        FinancialProfile, on_delete=models.CASCADE, related_name="income_sources"
    )
    # Ítem del catálogo `income_source_type`.
    source_type_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    payer_name = models.CharField(max_length=180, blank=True)
    monthly_amount_cop = models.BigIntegerField()
    start_date = models.DateField(null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "income_sources"
        ordering = ["-is_primary", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(monthly_amount_cop__gte=0), name="ck_income_sources_amount"
            ),
        ]

    def __str__(self) -> str:
        return f"Ingreso {self.monthly_amount_cop} de {self.financial_profile_id}"
