from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('wiki', '0004_waitevent')]

    operations = [
        migrations.CreateModel(
            name='SqlCommand',
            fields=[
                ('slug', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('name', models.TextField()),
                ('aliases', ArrayField(models.TextField(), blank=True, default=list, size=None)),
                ('verb', models.CharField(max_length=16)),
                ('object', models.TextField(blank=True, default='')),
                ('group', models.CharField(max_length=24)),
                ('purpose', models.TextField(blank=True, default='')),
                ('purpose_zh', models.TextField(blank=True, default='')),
                ('first_version', models.CharField(max_length=8)),
                ('last_version', models.CharField(max_length=8)),
                ('present_in', ArrayField(models.TextField(), blank=True, default=list, size=None)),
                ('changed_in', ArrayField(models.TextField(), blank=True, default=list, size=None)),
                ('synopsis', models.TextField(blank=True, default='')),
                ('related', ArrayField(models.TextField(), blank=True, default=list, size=None)),
                ('versions', models.JSONField(blank=True, default=dict)),
                ('changes', models.JSONField(blank=True, default=list)),
                ('editorial', models.JSONField(blank=True, default=dict)),
                ('position', models.IntegerField(default=0)),
                ('source_rev', models.TextField(blank=True, default='')),
                ('imported_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'wiki_sqlcmd', 'ordering': ('position',),
                     'indexes': [models.Index(fields=('group', 'slug'), name='wiki_sqlcmd_group')]},
        ),
    ]
