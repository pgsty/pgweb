from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('ext', '0001_catalog')]
    operations = [migrations.RunSQL(
        # Archive and verify the local copy before applying this migration.
        # This affects the PGWeb replica only, never the PGEXT source database.
        sql='DROP TABLE pgext.doc;',
        # Reversal restores the schema; archived data must be restored separately.
        reverse_sql="""
CREATE TABLE pgext.doc (
    id integer NOT NULL,
    ext text NOT NULL,
    pkg text NOT NULL,
    repo_url text,
    license_url text,
    control_url text,
    author_url text,
    home_url text,
    cargo_url text,
    en_doc text,
    zh_doc text,
    PRIMARY KEY (id),
    UNIQUE (ext)
);
""",
    )]
