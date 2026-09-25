from django.db import migrations


TABLES = {
    'wiki_errcode': 'sqlstate', 'wiki_errcode_class': 'sqlstate_class',
    'wiki_errcode_release': 'sqlstate_version', 'wiki_catalog': 'catalog',
    'wiki_catalog_version': 'catalog_version', 'wiki_guc': 'guc',
    'wiki_guc_version': 'guc_version', 'wiki_waitevent': 'waitevent',
    'wiki_waitevent_version': 'waitevent_version', 'wiki_sqlcmd': 'sqlcmd',
    'wiki_func': 'func', 'wiki_func_version': 'func_version',
}


def rename_generated(schema_editor, reverse=False):
    # Inspect real names, including FK target names and generated hash suffixes.
    # Surviving entities have natural primary keys, so there are no sequences.
    import re
    q = schema_editor.quote_name
    mapping = {v: k for k, v in TABLES.items()} if reverse else TABLES
    pattern = re.compile('|'.join(re.escape(name) for name in sorted(mapping, key=len, reverse=True)))
    explicit = {'catalog_kind', 'sqlstate_class_order', 'sqlstate_tier', 'sqlstate_condition',
                'guc_group', 'func_group', 'sqlcmd_group', 'waitevent_type', 'waitevent_name'}

    def renamed(name):
        # Explicit RenameIndex operations reverse their own names afterwards.
        if reverse and name in explicit:
            return name
        return pattern.sub(lambda match: mapping[match.group()], name)

    with schema_editor.connection.cursor() as cursor:
        for table in TABLES.values():
            cursor.execute('SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass', [table])
            for (name,) in cursor.fetchall():
                target = renamed(name)
                if target != name:
                    cursor.execute('ALTER TABLE {} RENAME CONSTRAINT {} TO {}'.format(q(table), q(name), q(target)))
            cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname=current_schema() AND tablename=%s", [table])
            for (name,) in cursor.fetchall():
                target = renamed(name)
                if target != name:
                    cursor.execute('ALTER INDEX {} RENAME TO {}'.format(q(name), q(target)))


def forwards(apps, schema_editor):
    rename_generated(schema_editor)


def backwards(apps, schema_editor):
    rename_generated(schema_editor, reverse=True)


class Migration(migrations.Migration):
    dependencies = [('wiki', '0008_backfill_reference_documents')]
    operations = [
        migrations.RenameIndex(
            model_name='catalogrelation',
            new_name='catalog_kind',
            old_name='wiki_catalog_kind',
        ),
        migrations.RenameIndex(
            model_name='errorcode',
            new_name='sqlstate_class_order',
            old_name='wiki_errcode_class_order',
        ),
        migrations.RenameIndex(
            model_name='errorcode',
            new_name='sqlstate_tier',
            old_name='wiki_errcode_tier',
        ),
        migrations.RenameIndex(
            model_name='errorcode',
            new_name='sqlstate_condition',
            old_name='wiki_errcode_condition',
        ),
        migrations.RenameIndex(
            model_name='gucparameter',
            new_name='guc_group',
            old_name='wiki_guc_group',
        ),
        migrations.RenameIndex(
            model_name='pgfunction',
            new_name='func_group',
            old_name='wiki_func_group',
        ),
        migrations.RenameIndex(
            model_name='sqlcommand',
            new_name='sqlcmd_group',
            old_name='wiki_sqlcmd_group',
        ),
        migrations.RenameIndex(
            model_name='waitevent',
            new_name='waitevent_type',
            old_name='wiki_waitevent_type',
        ),
        migrations.RenameIndex(
            model_name='waitevent',
            new_name='waitevent_name',
            old_name='wiki_waitevent_name',
        ),
        migrations.AlterModelTable(
            name='catalogrelation',
            table='catalog',
        ),
        migrations.AlterModelTable(
            name='catalogversion',
            table='catalog_version',
        ),
        migrations.AlterModelTable(
            name='errorcode',
            table='sqlstate',
        ),
        migrations.AlterModelTable(
            name='errorcodeclass',
            table='sqlstate_class',
        ),
        migrations.AlterModelTable(
            name='errorcoderelease',
            table='sqlstate_version',
        ),
        migrations.AlterModelTable(
            name='funcversion',
            table='func_version',
        ),
        migrations.AlterModelTable(
            name='gucparameter',
            table='guc',
        ),
        migrations.AlterModelTable(
            name='gucversion',
            table='guc_version',
        ),
        migrations.AlterModelTable(
            name='pgfunction',
            table='func',
        ),
        migrations.AlterModelTable(
            name='sqlcommand',
            table='sqlcmd',
        ),
        migrations.AlterModelTable(
            name='waitevent',
            table='waitevent',
        ),
        migrations.AlterModelTable(
            name='waiteventversion',
            table='waitevent_version',
        ),
        migrations.RunPython(forwards, backwards),
    ]
