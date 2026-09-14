# 配置参数栏目：两张表，逐版本快照与变化记录放 JSON 列。

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wiki', '0002_catalog'),
    ]

    operations = [
        migrations.CreateModel(
            name='GucVersion',
            fields=[
                ('major', models.CharField(max_length=8, primary_key=True, serialize=False)),
                ('label', models.TextField(blank=True, default='')),
                ('status', models.TextField(blank=True, default='')),
                ('support_status', models.TextField(blank=True, default='')),
                ('source_key', models.TextField(blank=True, default='')),
                ('server_version', models.TextField(blank=True, default='')),
                ('doc_slug', models.TextField(blank=True, default='')),
                ('parameter_count', models.IntegerField(default=0)),
                ('added_count', models.IntegerField(default=0)),
                ('removed_count', models.IntegerField(default=0)),
                ('default_changed_count', models.IntegerField(default=0)),
                ('changed_count', models.IntegerField(default=0)),
                ('reworded_count', models.IntegerField(default=0)),
                ('schema_source', models.TextField(blank=True, default='')),
                ('transition', models.JSONField(blank=True, default=dict)),
                ('position', models.IntegerField(default=0)),
            ],
            options={
                'db_table': 'wiki_guc_version',
                'ordering': ('position',),
            },
        ),
        migrations.CreateModel(
            name='GucParameter',
            fields=[
                ('name', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('key', models.CharField(max_length=64, unique=True)),
                ('group', models.CharField(blank=True, default='', max_length=64)),
                ('group_slug', models.CharField(blank=True, default='', max_length=32)),
                ('category', models.TextField(blank=True, default='')),
                ('category_zh', models.TextField(blank=True, default='')),
                ('vartype', models.CharField(blank=True, default='', max_length=16)),
                ('context', models.CharField(blank=True, default='', max_length=24)),
                ('unit', models.TextField(blank=True, default='')),
                ('boot_val', models.TextField(blank=True, null=True)),
                ('boot_human', models.TextField(blank=True, default='')),
                ('short_desc', models.TextField(blank=True, default='')),
                ('short_desc_zh', models.TextField(blank=True, default='')),
                ('enumvals', django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), blank=True, default=list, size=None)),
                ('min_val', models.TextField(blank=True, default='')),
                ('max_val', models.TextField(blank=True, default='')),
                ('first_version', models.CharField(blank=True, default='', max_length=8)),
                ('last_version', models.CharField(blank=True, default='', max_length=8)),
                ('present_in', django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), blank=True, default=list, size=None)),
                ('changed_in', django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), blank=True, default=list, size=None)),
                ('default_changed_in', django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), blank=True, default=list, size=None)),
                ('baseline', models.BooleanField(default=False)),
                ('versions', models.JSONField(blank=True, default=dict)),
                ('changes', models.JSONField(blank=True, default=list)),
                ('default_history', models.JSONField(blank=True, default=list)),
                ('docs', models.JSONField(blank=True, default=dict)),
                ('editorial', models.JSONField(blank=True, default=dict)),
                ('intro_commit', models.JSONField(blank=True, default=dict)),
                ('position', models.IntegerField(default=0)),
                ('source_rev', models.TextField(blank=True, default='')),
                ('imported_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'wiki_guc',
                'ordering': ('position',),
                'indexes': [models.Index(fields=['group_slug', 'name'], name='wiki_guc_group')],
            },
        ),
    ]
