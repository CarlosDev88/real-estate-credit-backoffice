"""Exoneraciones y reaperturas en `document_reviews` (desvío del DER, Parte 5 del paso 10).

- `slot_id NOT NULL`: se llena desde la versión revisada (`document_files.slot_id`)
  antes de volverlo obligatorio.
- `document_file_id` pasa a ser nulable: obligatorio al aprobar o rechazar.
- `decision` admite `WAIVED` y `REOPENED`, y `decision_batch_id` agrupa las filas de
  una misma exoneración o reapertura.
"""

import django.db.models.deletion
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps
from django.db.models import F, Q

DECISION_CHOICES = [
    ("APPROVED", "Aprobado"),
    ("REJECTED", "Rechazado"),
    ("WAIVED", "Exonerado"),
    ("REOPENED", "Exoneración reabierta"),
]


def fill_review_slots(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Cada revisión existente es de una versión: su slot es el de esa versión."""
    DocumentReview = apps.get_model("documents", "DocumentReview")
    DocumentFile = apps.get_model("documents", "DocumentFile")
    slot_of_file = DocumentFile.objects.filter(pk=models.OuterRef("document_file_id")).values(
        "slot_id"
    )
    DocumentReview.objects.filter(slot__isnull=True).update(slot_id=models.Subquery(slot_of_file))


def drop_slot_decisions(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Al revertir, las exoneraciones y reaperturas no caben en el esquema anterior."""
    DocumentReview = apps.get_model("documents", "DocumentReview")
    DocumentReview.objects.filter(decision__in=["WAIVED", "REOPENED"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0004_seed_dossier"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="documentreview", name="ck_document_reviews_decision"
        ),
        migrations.AddField(
            model_name="documentreview",
            name="slot",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="reviews",
                to="documents.applicationdocumentslot",
            ),
        ),
        migrations.AddField(
            model_name="documentreview",
            name="decision_batch_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.RunPython(fill_review_slots, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="documentreview",
            name="slot",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="reviews",
                to="documents.applicationdocumentslot",
            ),
        ),
        migrations.RunPython(migrations.RunPython.noop, drop_slot_decisions),
        migrations.AlterField(
            model_name="documentreview",
            name="document_file",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="reviews",
                to="documents.documentfile",
            ),
        ),
        migrations.AlterField(
            model_name="documentreview",
            name="decision",
            field=models.CharField(choices=DECISION_CHOICES, max_length=20),
        ),
        migrations.AddConstraint(
            model_name="documentreview",
            constraint=models.CheckConstraint(
                condition=Q(decision__in=["APPROVED", "REJECTED", "WAIVED", "REOPENED"]),
                name="ck_document_reviews_decision",
            ),
        ),
        migrations.AddConstraint(
            model_name="documentreview",
            constraint=models.CheckConstraint(
                condition=~Q(decision__in=["APPROVED", "REJECTED"])
                | Q(document_file__isnull=False, decision_batch_id__isnull=True),
                name="ck_document_reviews_file",
            ),
        ),
        migrations.AddConstraint(
            model_name="documentreview",
            constraint=models.CheckConstraint(
                condition=~Q(decision__in=["WAIVED", "REOPENED"])
                | Q(decision_batch_id__isnull=False),
                name="ck_document_reviews_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="documentreview",
            constraint=models.CheckConstraint(
                condition=~Q(decision="WAIVED") | Q(reason_item__isnull=False),
                name="ck_document_reviews_waiver",
            ),
        ),
        migrations.AddConstraint(
            model_name="documentreview",
            constraint=models.CheckConstraint(
                condition=~Q(decision="REOPENED")
                | (Q(internal_comment__isnull=False) & ~Q(internal_comment="")),
                name="ck_document_reviews_reopen",
            ),
        ),
        migrations.AddIndex(
            model_name="documentreview",
            index=models.Index(F("slot"), F("created_at").desc(), name="ix_document_reviews_slot"),
        ),
        migrations.AddIndex(
            model_name="documentreview",
            index=models.Index(
                condition=Q(decision_batch_id__isnull=False),
                fields=["decision_batch_id"],
                name="ix_document_reviews_batch",
            ),
        ),
    ]
