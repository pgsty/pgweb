from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Entries without a manual page: the extension catalogue.

    The nullability of document_id/version is changed with plain ALTER
    COLUMN statements rather than AlterField, which would drop and recreate
    the foreign key and lose the ON DELETE CASCADE set up in 0002.
    """

    dependencies = [('search', '0003_invalidate_changed_source')]
    operations = [
        migrations.AddField(
            model_name='searchentry',
            name='source',
            field=models.CharField(default='pg', max_length=8),
        ),
        migrations.AddField(
            model_name='searchentry',
            name='url',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='searchentry',
            name='weight',
            field=models.FloatField(default=0),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='searchentry',
                    name='document',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='entries', to='search.indexedpage'),
                ),
                migrations.AlterField(
                    model_name='searchentry',
                    name='version',
                    field=models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
ALTER TABLE search_searchentry ALTER COLUMN document_id DROP NOT NULL;
ALTER TABLE search_searchentry ALTER COLUMN version DROP NOT NULL;
""",
                    reverse_sql="""
DELETE FROM search_searchentry WHERE document_id IS NULL OR version IS NULL;
ALTER TABLE search_searchentry ALTER COLUMN document_id SET NOT NULL;
ALTER TABLE search_searchentry ALTER COLUMN version SET NOT NULL;
""",
                ),
            ],
        ),
        migrations.AddIndex(
            model_name='searchentry',
            index=models.Index(fields=['source', 'kind'], name='docsearch_source_kind'),
        ),
    ]
