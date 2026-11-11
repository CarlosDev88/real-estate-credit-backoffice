from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import serializers

from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.models import CatalogItem
from config.serializers import StrictSerializer

pytestmark = pytest.mark.django_db


class PurposeSerializer(StrictSerializer):
    purpose = CatalogItemCodeField(catalog_code="loan_purpose")


class HistoricalPurposeSerializer(StrictSerializer):
    purpose = CatalogItemCodeField(catalog_code="loan_purpose", allow_unavailable=True)


def test_resolves_code_to_catalog_item() -> None:
    serializer = PurposeSerializer(data={"purpose": "PURCHASE_NEW"})
    assert serializer.is_valid(), serializer.errors
    item = serializer.validated_data["purpose"]
    assert isinstance(item, CatalogItem)
    assert item.catalog.code == "loan_purpose"
    assert PurposeSerializer({"purpose": item}).data == {"purpose": "PURCHASE_NEW"}


def test_rejects_codes_from_another_catalog() -> None:
    # `NEW` existe, pero en `property_condition`, no en `loan_purpose`.
    serializer = PurposeSerializer(data={"purpose": "NEW"})
    assert not serializer.is_valid()
    assert "no existe en el catálogo loan_purpose" in str(serializer.errors["purpose"][0])


@pytest.mark.parametrize("value", [123, "", None, ["PURCHASE_NEW"]])
def test_rejects_non_string_values(value: object) -> None:
    assert not PurposeSerializer(data={"purpose": value}).is_valid()


def test_rejects_inactive_or_expired_items() -> None:
    items = CatalogItem.objects.filter(catalog__code="loan_purpose")
    items.filter(code="PURCHASE_NEW").update(is_active=False)
    items.filter(code="PURCHASE_USED").update(valid_to=timezone.localdate() - timedelta(days=1))

    for code in ("PURCHASE_NEW", "PURCHASE_USED"):
        serializer = PurposeSerializer(data={"purpose": code})
        assert not serializer.is_valid()
        assert "no está activo o vigente" in str(serializer.errors["purpose"][0])


def test_allow_unavailable_accepts_inactive_items() -> None:
    CatalogItem.objects.filter(catalog__code="loan_purpose", code="PURCHASE_NEW").update(
        is_active=False
    )
    assert HistoricalPurposeSerializer(data={"purpose": "PURCHASE_NEW"}).is_valid()


def test_field_is_a_drf_field() -> None:
    assert isinstance(PurposeSerializer().fields["purpose"], serializers.Field)
