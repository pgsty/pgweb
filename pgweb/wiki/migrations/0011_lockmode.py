import django.db.models.lookups
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('wiki', '0010_retire_errcode_children')]

    operations = [
        migrations.CreateModel(
            name='LockMode',
            fields=[
                ('slug', models.CharField(max_length=40, primary_key=True, serialize=False)),
                ('name', models.TextField()),
                ('name_zh', models.TextField()),
                ('abbrev', models.CharField(max_length=8)),
                ('scope', models.CharField(choices=[('table', '表级锁'), ('row', '行级锁')], max_length=8)),
                ('summary', models.TextField(blank=True, default='')),
                ('position', models.PositiveSmallIntegerField()),
                ('versions', models.JSONField(default=dict)),
                ('content_hash', models.CharField(blank=True, default='', max_length=64)),
                ('source_rev', models.TextField(blank=True, default='')),
                ('imported_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'lock_mode',
                'ordering': ('position',),
                'constraints': [
                    models.CheckConstraint(condition=models.Q(scope__in=('table', 'row')),
                                           name='lock_mode_scope'),
                    models.CheckConstraint(condition=django.db.models.lookups.Exact(
                        models.Func(models.F('versions'), function='jsonb_typeof',
                                    output_field=models.CharField()), models.Value('object')),
                        name='lock_mode_versions_object'),
                ],
            },
        ),
    ]
