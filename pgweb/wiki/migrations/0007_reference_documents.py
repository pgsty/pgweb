from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('wiki', '0006_func')]
    operations = [
        # Only the historical reverse accessor changes. Preserve the existing FK.
        migrations.SeparateDatabaseAndState(state_operations=[migrations.AlterField(
            model_name='errorcodetext', name='errcode',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                    related_name='legacy_texts', to='wiki.errorcode'))]),
        *[migrations.AddField(model_name=name, name='content_hash',
                              field=models.CharField(max_length=64, blank=True, default=''))
          for name in ('errorcode', 'catalogrelation', 'gucparameter', 'waitevent',
                       'sqlcommand', 'pgfunction')],
        *[migrations.AddField(model_name='errorcode', name=name,
                              field=models.TextField(blank=True, default=''))
          for name in ('name_zh', 'summary_zh')],
        *[migrations.AddField(model_name='errorcode', name=name,
                              field=models.JSONField(blank=True, default=dict))
          for name in ('texts', 'evidence')],
    ]
