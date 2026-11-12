from typing import Any

from django.db import migrations

# El banco se busca por su código estable, nunca por el nombre (que se puede editar).
FNA_CODE = "FNA"
FNA_SHORT_NAME = "FNA"


def set_fna_short_name(apps: Any, schema_editor: Any) -> None:
    Bank = apps.get_model("banking", "Bank")
    Bank.objects.filter(code=FNA_CODE).update(short_name=FNA_SHORT_NAME)


def clear_fna_short_name(apps: Any, schema_editor: Any) -> None:
    Bank = apps.get_model("banking", "Bank")
    Bank.objects.filter(code=FNA_CODE).update(short_name="")


class Migration(migrations.Migration):
    """El Fondo Nacional del Ahorro se muestra como "FNA" en los listados. Bancolombia y
    Banco de Bogotá quedan sin nombre corto (el frontend muestra `name`)."""

    dependencies = [
        ("banking", "0003_bank_short_name"),
    ]

    operations = [
        migrations.RunPython(set_fna_short_name, clear_fna_short_name),
    ]
