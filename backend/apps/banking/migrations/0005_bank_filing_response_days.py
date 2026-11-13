from typing import Any

from django.db import migrations, models

# El banco se busca por su código estable, nunca por el nombre (que se puede editar).
FNA_CODE = "FNA"
# REQUERIMIENTOS, etapas del FNA: la respuesta a la radicación llega en unos 7 días.
FNA_FILING_RESPONSE_DAYS = 7


def set_fna_response_days(apps: Any, schema_editor: Any) -> None:
    Bank = apps.get_model("banking", "Bank")
    Bank.objects.filter(code=FNA_CODE).update(filing_response_days=FNA_FILING_RESPONSE_DAYS)


def clear_fna_response_days(apps: Any, schema_editor: Any) -> None:
    Bank = apps.get_model("banking", "Bank")
    Bank.objects.filter(code=FNA_CODE).update(filing_response_days=None)


class Migration(migrations.Migration):
    """Días de respuesta del banco a una radicación (paso 11). La radicación calcula su
    fecha objetivo de respuesta con ellos; los demás bancos quedan sin dato."""

    dependencies = [
        ("banking", "0004_seed_fna_short_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="bank",
            name="filing_response_days",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(set_fna_response_days, clear_fna_response_days),
    ]
