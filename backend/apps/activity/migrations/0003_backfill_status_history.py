"""Backfill: la actividad de las solicitudes que ya existían, desde
``application_status_history``.

- La fila sin ``from_status`` (la creación) da un ``APPLICATION_CREATED`` interno.
- Cada cambio de estado da dos ``STATUS_CHANGED``: uno interno con las etiquetas del
  backend y el comentario, y otro para el comprador con las etiquetas públicas (catálogo
  ``application_status``) y sin comentario.
- Conservan la fecha y el actor del historial.
- Es idempotente: cada fila guarda ``metadata.status_history_id`` y una fila del
  historial que ya tiene actividad no se repite.
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

from apps.activity.texts import application_created_title, clip, status_changed_title
from apps.catalogs.workflow import ApplicationStatus

BATCH_SIZE = 500


def backfill(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    ActivityLog = apps.get_model("activity", "ActivityLog")
    ApplicationStatusHistory = apps.get_model("applications", "ApplicationStatusHistory")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")

    public = dict(
        CatalogItem.objects.filter(catalog__code="application_status").values_list(
            "code", "label"
        )
    )

    def internal_label(code: str) -> str:
        return str(ApplicationStatus(code).label)

    def public_label(code: str) -> str:
        return public[code] if code in public else internal_label(code)

    done = {
        str(value)
        for value in ActivityLog.objects.filter(
            metadata__has_key="status_history_id"
        ).values_list("metadata__status_history_id", flat=True)
        if value
    }
    rows = []
    history = ApplicationStatusHistory.objects.select_related("application__opportunity").order_by(
        "created_at"
    )
    for item in history.iterator():
        if str(item.pk) in done:
            continue
        application = item.application
        common = {
            "created_at": item.created_at,
            "application_id": application.pk,
            "opportunity_id": application.opportunity_id,
            "client_id": application.opportunity.client_id,
            "actor_user_id": item.actor_user_id,
            "actor_buyer_session_id": item.actor_buyer_session_id,
        }
        if item.from_status is None:
            rows.append(
                ActivityLog(
                    event_type="APPLICATION_CREATED",
                    visibility="INTERNAL",
                    title=application_created_title(application.code),
                    metadata={"status_history_id": str(item.pk)},
                    **common,
                )
            )
            continue
        metadata = {
            "from_status": item.from_status,
            "to_status": item.to_status,
            "status_history_id": str(item.pk),
        }
        rows.append(
            ActivityLog(
                event_type="STATUS_CHANGED",
                visibility="INTERNAL",
                title=clip(
                    status_changed_title(
                        internal_label(item.from_status), internal_label(item.to_status)
                    )
                ),
                message=item.comment or "",
                metadata=metadata,
                **common,
            )
        )
        rows.append(
            ActivityLog(
                event_type="STATUS_CHANGED",
                visibility="BUYER",
                title=clip(
                    status_changed_title(
                        public_label(item.from_status), public_label(item.to_status)
                    )
                ),
                metadata=metadata,
                **common,
            )
        )
    ActivityLog.objects.bulk_create(rows, batch_size=BATCH_SIZE)


class Migration(migrations.Migration):
    dependencies = [
        ("activity", "0002_seed_note_permission"),
        ("applications", "0005_application_completeness_snapshot"),
        ("catalogs", "0003_workflowtransition_system_only"),
    ]

    operations = [
        # Deshacerla no borra nada: la actividad es inmutable.
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
