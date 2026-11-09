"""DTO del portal para el inmueble, la financiación, los productos y el desistimiento.

Las salidas del inmueble y la financiación son las del detalle del portal
(``buyer_portal_serializers``). Las entradas reutilizan los validadores internos; el
inmueble del comprador no acepta ``project_id`` ni ``ownership_notes``.
"""

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.applications.serializers import NamedRefSerializer, PropertyInputSerializer
from apps.banking.models import BankProduct


class BuyerPropertyInputSerializer(PropertyInputSerializer):
    """Reemplazo de los datos del inmueble que controla el comprador.

    El proyecto lo asigna el asesor o la constructora, y ``ownership_notes`` es texto del
    asesor: los dos conservan su valor.
    """

    # DRF quita del serializer un campo heredado que se declara como `None`.
    ownership_notes = None  # type: ignore[assignment]


class BuyerEligibleBankProductSerializer(serializers.ModelSerializer):
    """Producto disponible para la finalidad y si los datos actuales lo permiten.

    No expone el detalle ni el conteo de las reglas: eso es del asesor.
    """

    bank = NamedRefSerializer(read_only=True)
    eligible = serializers.SerializerMethodField()

    class Meta:
        model = BankProduct
        fields = [
            "id",
            "name",
            "bank",
            "min_amount_cop",
            "max_amount_cop",
            "min_term_months",
            "max_term_months",
            "eligible",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.BooleanField())
    def get_eligible(self, product: BankProduct) -> bool:
        evaluations: dict[Any, Any] = self.context["evaluations"]
        return bool(evaluations[product.pk].eligible)
