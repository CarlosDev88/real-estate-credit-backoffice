import django.db.models.functions.text
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    """Alinea ``users`` con el esquema: timestamps, borrado lógico y correo único sin
    distinguir mayúsculas.

    ``date_joined`` se renombra a ``created_at`` para conservar la fecha de alta de
    los usuarios existentes.
    """

    dependencies = [
        ("identity", "0002_permission_role_rolepermission_userrole"),
    ]

    operations = [
        migrations.RunSQL(
            sql="UPDATE users SET email = LOWER(TRIM(email));",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RenameField(
            model_name="user",
            old_name="date_joined",
            new_name="created_at",
        ),
        migrations.AlterField(
            model_name="user",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AddField(
            model_name="user",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="user",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("email"),
                name="uq_users_email_lower",
            ),
        ),
    ]
