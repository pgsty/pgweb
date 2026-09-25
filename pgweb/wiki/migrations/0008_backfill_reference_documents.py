from django.db import migrations
from ._reference_documents import backfill


class Migration(migrations.Migration):
    dependencies = [('wiki', '0007_reference_documents')]
    # 0010 restores children before this expansion is reversed. Added JSON keys
    # in facts are retained on downgrade: their original values are never removed.
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
