"""Catálogos nuevos del bootstrap (TAREA-brechas-3-demo, parte 1): papel del participante
y estados de liquidación y de parte de comisión. Sus etiquetas son las del código."""

import pytest
from django.db import models
from rest_framework.test import APIClient

from apps.catalogs.models import Catalog, CatalogItem
from apps.commissions.models import SettlementStatus, ShareStatus
from apps.documents.models import ParticipantRole

pytestmark = pytest.mark.django_db

CATALOGS: dict[str, type[models.TextChoices]] = {
    "participant_role": ParticipantRole,
    "commission_settlement_status": SettlementStatus,
    "commission_share_status": ShareStatus,
}


def labels(catalog_code: str) -> list[tuple[str, str]]:
    items = CatalogItem.objects.filter(catalog__code=catalog_code).order_by("sort_order")
    return list(items.values_list("code", "label"))


@pytest.mark.parametrize("catalog_code", list(CATALOGS))
def test_the_catalog_has_the_labels_of_the_code(catalog_code: str) -> None:
    choices = CATALOGS[catalog_code]

    assert labels(catalog_code) == [(str(value), str(label)) for value, label in choices.choices]
    assert Catalog.objects.get(code=catalog_code).is_manageable is False


def test_the_bootstrap_brings_them(advisor_client: APIClient) -> None:
    catalogs = advisor_client.get("/api/v1/metadata/bootstrap").json()["catalogs"]

    assert [(i["code"], i["label"]) for i in catalogs["participant_role"]] == [
        ("PRIMARY", "Titular"),
        ("CO_APPLICANT", "Co-solicitante"),
        ("SOLIDARY_DEBTOR", "Deudor solidario"),
    ]
    assert [i["label"] for i in catalogs["commission_settlement_status"]] == [
        "Vigente",
        "Anulada",
    ]
    assert [i["label"] for i in catalogs["commission_share_status"]] == [
        "Pendiente de pago",
        "Pagada",
        "Anulada",
    ]
