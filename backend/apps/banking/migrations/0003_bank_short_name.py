from django.db import migrations, models


class Migration(migrations.Migration):
    """Nombre corto opcional del banco para listados (por ejemplo, FNA).

    ``db_default`` deja el valor por omisión en la base: el código anterior a este campo
    puede seguir insertando bancos mientras se despliega (la columna no rompe nada).
    """

    dependencies = [
        ("banking", "0002_seed_permissions_and_banks"),
    ]

    operations = [
        migrations.AddField(
            model_name="bank",
            name="short_name",
            field=models.CharField(blank=True, db_default="", default="", max_length=30),
        ),
    ]
