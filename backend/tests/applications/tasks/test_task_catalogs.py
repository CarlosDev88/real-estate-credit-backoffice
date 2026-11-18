"""Catálogos `task_status` y `task_due` (TAREA-brechas-2, parte 3): las etiquetas del
estado de una tarea y de las opciones del filtro `due` salen del backend."""

import pytest
from rest_framework.test import APIClient

from apps.catalogs.models import Catalog, CatalogItem
from apps.tasks.models import TaskStatus
from apps.tasks.services import DueWindow

pytestmark = pytest.mark.django_db


def labels(catalog_code: str) -> list[tuple[str, str]]:
    items = CatalogItem.objects.filter(catalog__code=catalog_code).order_by("sort_order")
    return list(items.values_list("code", "label"))


def test_the_catalogs_have_the_labels_of_the_code() -> None:
    assert labels("task_status") == [(str(v), str(label)) for v, label in TaskStatus.choices]
    assert labels("task_due") == [(str(v), str(label)) for v, label in DueWindow.choices]
    managed = Catalog.objects.filter(code__in=["task_status", "task_due"])
    assert set(managed.values_list("is_manageable", flat=True)) == {False}


def test_the_bootstrap_brings_them(advisor_client: APIClient) -> None:
    catalogs = advisor_client.get("/api/v1/metadata/bootstrap").json()["catalogs"]

    assert [item["code"] for item in catalogs["task_due"]] == ["overdue", "today", "upcoming"]
    assert [item["label"] for item in catalogs["task_status"]] == [
        "Pendiente",
        "Completada",
        "Cancelada",
    ]
