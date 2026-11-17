"""Nombres de componentes del contrato que el frontend ya usa (``schema.d.ts``).

drf-spectacular renombra un enum cuando otro campo con el mismo nombre tiene otras
opciones; ``ENUM_NAME_OVERRIDES`` los fija. Si esta prueba falla, falta un override.
"""

from typing import Any

import pytest
from drf_spectacular.generators import SchemaGenerator

STABLE_ENUMS = {
    "CodeEnum": ["property", "financing", "bank_product", "bank_evaluation", "financial_profile"],
    "AttentionSegmentEnum": [
        "REVIEW_DOCUMENTS",
        "READY_TO_FILE",
        "FILED",
        "IN_ANALYSIS",
        "OBSERVED",
        "BUYER_INACTIVE",
        "TASKS_DUE",
    ],
    "NextActionEnum": [
        "COMPLETE_DRAFT",
        "FOLLOW_UP_BUYER_DATA",
        "FOLLOW_UP_DOCUMENTS",
        "REVIEW_DOCUMENTS",
        "FILE_WITH_BANK",
        "WAIT_BANK_RESPONSE",
        "RESOLVE_OBSERVATIONS",
        "START_LEGALIZATION",
        "FOLLOW_UP_LEGALIZATION",
    ],
    "PublicSlotStatusEnum": ["TO_UPLOAD", "TO_FIX", "IN_REVIEW", "DONE", "NOT_APPLICABLE"],
    "ProgressStageStateEnum": ["done", "current", "pending"],
}


@pytest.fixture(scope="module")
def components() -> dict[str, Any]:
    schema = SchemaGenerator().get_schema(request=None, public=True)
    return dict(schema["components"]["schemas"])


@pytest.mark.parametrize(("name", "values"), STABLE_ENUMS.items())
def test_published_enum_names_do_not_change(
    components: dict[str, Any], name: str, values: list[str]
) -> None:
    assert components[name]["enum"] == values
