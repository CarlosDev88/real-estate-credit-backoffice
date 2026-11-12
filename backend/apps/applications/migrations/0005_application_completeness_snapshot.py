from django.db import migrations, models


class Migration(migrations.Migration):
    """Completitud guardada para el listado (TAREA-applications-listado, ambigüedad A).

    Los tres campos quedan nulos: los llena ``refresh_application_completeness`` y,
    desde entonces, cada cambio de datos o del expediente (``refresh_completeness``).
    """

    dependencies = [
        ("applications", "0004_status_history_buyer_actor"),
    ]

    operations = [
        migrations.AddField(
            model_name="creditapplication",
            name="completeness_pct",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="ready_to_file_ok",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="completeness_refreshed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="creditapplication",
            constraint=models.CheckConstraint(
                condition=models.Q(completeness_pct__isnull=True)
                | models.Q(completeness_pct__lte=100),
                name="ck_credit_applications_completeness_pct",
            ),
        ),
    ]
