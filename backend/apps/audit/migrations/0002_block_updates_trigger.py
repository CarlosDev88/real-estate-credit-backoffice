"""Trigger de PostgreSQL que bloquea ``UPDATE`` sobre ``audit_events``.

El modelo ya rechaza ``save()`` sobre una fila existente y ``QuerySet.update()``; el
trigger cubre también el SQL directo. No bloquea ``DELETE``: la retención
(``purge_audit_events``) es la única forma de borrar.
"""

from django.db import migrations

CREATE = """
CREATE FUNCTION audit_events_block_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events es inmutable: no se permite UPDATE';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_events_block_update
    BEFORE UPDATE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_block_update();
"""

DROP = """
DROP TRIGGER IF EXISTS trg_audit_events_block_update ON audit_events;
DROP FUNCTION IF EXISTS audit_events_block_update();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(CREATE, DROP),
    ]
