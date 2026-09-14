# 等待事件栏目：两张表，逐版本快照、变化记录与图谱档案放 JSON 列。

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wiki', '0003_guc'),
    ]

    operations = [
        migrations.CreateModel(
            name='WaitEventVersion',
            fields=[
                ('major', models.CharField(max_length=8, primary_key=True, serialize=False)),
                ('label', models.TextField(blank=True, default='')),
                ('status', models.TextField(blank=True, default='')),
                ('support_status', models.TextField(blank=True, default='')),
                ('doc_slug', models.TextField(blank=True, default='')),
                ('has_wait_events', models.BooleanField(default=True)),
                ('method', models.TextField(blank=True, default='')),
                ('event_count', models.IntegerField(default=0)),
                ('type_counts', models.JSONField(blank=True, default=dict)),
                ('transition', models.JSONField(blank=True, default=dict)),
                ('position', models.IntegerField(default=0)),
                ('notes', models.JSONField(blank=True, default=dict)),
            ],
            options={
                'db_table': 'wiki_waitevent_version',
                'ordering': ('position',),
            },
        ),
        migrations.CreateModel(
            name='WaitEvent',
            fields=[
                ('key', models.CharField(max_length=96, primary_key=True, serialize=False)),
                ('type', models.CharField(max_length=16)),
                ('type_slug', models.CharField(max_length=16)),
                ('name', models.TextField()),
                ('slug', models.TextField(blank=True, default='')),
                ('aliases', django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), blank=True, default=list, size=None)),
                ('type_variants', django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), blank=True, default=list, size=None)),
                ('summary', models.TextField(blank=True, default='')),
                ('summary_zh', models.TextField(blank=True, default='')),
                ('first_version', models.CharField(blank=True, default='', max_length=8)),
                ('last_version', models.CharField(blank=True, default='', max_length=8)),
                ('present_in', django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), blank=True, default=list, size=None)),
                ('changed_in', django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), blank=True, default=list, size=None)),
                ('versions', models.JSONField(blank=True, default=dict)),
                ('changes', models.JSONField(blank=True, default=list)),
                ('dossier', models.JSONField(blank=True, default=dict)),
                ('has_dossier', models.BooleanField(default=False)),
                ('position', models.IntegerField(default=0)),
                ('source_rev', models.TextField(blank=True, default='')),
                ('imported_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'wiki_waitevent',
                'ordering': ('position',),
                'indexes': [
                    models.Index(fields=['type_slug', 'name'], name='wiki_waitevent_type'),
                    models.Index(fields=['name'], name='wiki_waitevent_name'),
                ],
            },
        ),
    ]
