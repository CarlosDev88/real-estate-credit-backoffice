"""Etiquetas visibles de los códigos (``*_label``): una sola fuente en el backend."""

from rest_framework import serializers

from apps.banking.rule_engine import OUTCOME_LABELS, Outcome
from apps.catalogs.workflow import ApplicationStatus
from config.serializers import ChoiceLabelField


class _Example(serializers.Serializer):
    status = serializers.CharField()
    status_label = ChoiceLabelField(ApplicationStatus, source="status")
    previous_label = ChoiceLabelField(ApplicationStatus, source="previous", allow_null=True)
    outcome_label = ChoiceLabelField(OUTCOME_LABELS, source="outcome")


def test_every_rule_outcome_has_a_label() -> None:
    assert set(OUTCOME_LABELS) == {outcome.value for outcome in Outcome}


def test_labels_come_from_the_choices_or_the_map() -> None:
    data = _Example({"status": "DRAFT", "previous": None, "outcome": "MISSING_DATA"}).data

    assert data == {
        "status": "DRAFT",
        "status_label": "Borrador",
        "previous_label": None,
        "outcome_label": "Faltan datos",
    }


def test_the_label_field_is_read_only() -> None:
    assert _Example().fields["status_label"].read_only is True
