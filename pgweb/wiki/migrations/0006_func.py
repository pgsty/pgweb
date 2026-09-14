from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('wiki', '0005_sqlcmd')]

    operations = [
        migrations.CreateModel(
            name='FuncVersion',
            fields=[
                ('major', models.CharField(max_length=8, primary_key=True, serialize=False)),
                ('label', models.TextField(blank=True, default='')),
                ('status', models.TextField(blank=True, default='')),
                ('support_status', models.TextField(blank=True, default='')),
                ('doc_slug', models.TextField(blank=True, default='')),
                ('source', models.TextField(blank=True, default='')),
                ('layout', models.TextField(blank=True, default='')),
                ('function_count', models.IntegerField(default=0)),
                ('signature_count', models.IntegerField(default=0)),
                ('zh_coverage', models.IntegerField(default=0)),
                ('added_count', models.IntegerField(default=0)),
                ('removed_count', models.IntegerField(default=0)),
                ('changed_count', models.IntegerField(default=0)),
                ('transition', models.JSONField(blank=True, default=dict)),
                ('position', models.IntegerField(default=0)),
            ],
            options={'db_table': 'wiki_func_version', 'ordering': ('position',)},
        ),
        migrations.CreateModel(
            name='PgFunction',
            fields=[
                ('slug', models.CharField(max_length=80, primary_key=True, serialize=False)),
                ('name', models.TextField()),
                ('name_key', models.CharField(db_index=True, max_length=80)),
                ('group', models.CharField(max_length=32)),
                ('group_label', models.TextField(blank=True, default='')),
                ('groups', ArrayField(models.TextField(), blank=True, default=list, size=None)),
                ('summary', models.TextField(blank=True, default='')),
                ('summary_zh', models.TextField(blank=True, default='')),
                ('signature', models.TextField(blank=True, default='')),
                ('first_version', models.CharField(blank=True, default='', max_length=8)),
                ('last_version', models.CharField(blank=True, default='', max_length=8)),
                ('present_in', ArrayField(models.TextField(), blank=True, default=list, size=None)),
                ('changed_in', ArrayField(models.TextField(), blank=True, default=list, size=None)),
                ('signature_count', models.IntegerField(default=0)),
                ('versions', models.JSONField(blank=True, default=dict)),
                ('changes', models.JSONField(blank=True, default=list)),
                ('position', models.IntegerField(default=0)),
                ('source_rev', models.TextField(blank=True, default='')),
                ('imported_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'wiki_func', 'ordering': ('position',),
                     'indexes': [models.Index(fields=('group', 'name_key'), name='wiki_func_group')]},
        ),
    ]
