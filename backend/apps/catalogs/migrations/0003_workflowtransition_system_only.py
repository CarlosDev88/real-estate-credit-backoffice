from django.db import migrations, models


class Migration(migrations.Migration):
    """Marca las transiciones que solo ejecuta el servicio de su módulo (paso 11: la
    radicación y las respuestas del banco). ``POST /status-transitions`` las rechaza y las
    acciones disponibles no las listan.

    ``db_default`` deja el valor en la base: el código anterior puede seguir insertando
    transiciones mientras se despliega.
    """

    dependencies = [
        ("catalogs", "0002_seed_permissions_and_catalogs"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowtransition",
            name="system_only",
            field=models.BooleanField(db_default=False, default=False),
        ),
    ]
