from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('docs', '0004_docpageredirect')]

    operations = [
        migrations.CreateModel(
            name='CompareDataset',
            fields=[
                ('key', models.CharField(max_length=32, primary_key=True, serialize=False)),
                ('kind', models.CharField(max_length=16)),
                ('language', models.CharField(blank=True, max_length=8)),
                ('metadata', models.JSONField(default=dict)),
                ('members', models.JSONField(default=list)),
                ('revisions', models.JSONField(default=list)),
                ('release_count', models.PositiveIntegerField(default=0)),
                ('entry_count', models.PositiveIntegerField(default=0)),
                ('content_hash', models.CharField(max_length=64)),
                ('revision', models.PositiveBigIntegerField(default=1)),
                ('imported_at', models.DateTimeField()),
            ], options={'db_table': 'release_dataset'},
        ),
        migrations.CreateModel(
            name='CompareRelease',
            fields=[
                ('version', models.CharField(max_length=24, primary_key=True, serialize=False)),
                ('major', models.CharField(db_index=True, max_length=12)),
                ('minor', models.PositiveIntegerField()),
                ('sort_num', models.PositiveIntegerField(db_index=True)),
                ('status', models.CharField(max_length=16)),
                ('released_at', models.DateField(blank=True, db_index=True, null=True)),
                ('active_languages', ArrayField(base_field=models.CharField(max_length=8), default=list, size=None)),
                ('payloads', models.JSONField(default=dict)),
                ('revisions', models.JSONField(default=list)),
                ('content_hash', models.CharField(max_length=64)),
                ('imported_at', models.DateTimeField()),
            ], options={'db_table': 'release', 'ordering': ('sort_num',)},
        ),
        migrations.CreateModel(
            name='ComparePatch',
            fields=[
                ('id', models.CharField(max_length=32, primary_key=True, serialize=False)),
                ('commits', ArrayField(base_field=models.CharField(max_length=40), default=list, size=None)),
                ('evidence', models.JSONField(default=dict)),
                ('revisions', models.JSONField(default=list)),
                ('content_hash', models.CharField(max_length=64)),
                ('imported_at', models.DateTimeField()),
                ('merged_into', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='merged_groups', to='docs.comparepatch')),
            ], options={'db_table': 'release_patch', 'indexes': [GinIndex(fields=['commits'], name='release_patch_commits_gin')]},
        ),
        migrations.CreateModel(
            name='CompareEntry',
            fields=[
                ('id', models.CharField(max_length=32, primary_key=True, serialize=False)),
                ('part', models.CharField(max_length=24)),
                ('position', models.PositiveIntegerField()),
                ('category', models.CharField(db_index=True, max_length=24)),
                ('statement_hash', models.CharField(db_index=True, max_length=64)),
                ('patch_ids', ArrayField(base_field=models.CharField(max_length=32), default=list, size=None)),
                ('cves', ArrayField(base_field=models.CharField(max_length=32), default=list, size=None)),
                ('active_languages', ArrayField(base_field=models.CharField(max_length=8), default=list, size=None)),
                ('payloads', models.JSONField(default=dict)),
                ('revisions', models.JSONField(default=list)),
                ('relations', models.JSONField(default=list)),
                ('content_hash', models.CharField(max_length=64)),
                ('imported_at', models.DateTimeField()),
                ('release', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='changes', to='docs.comparerelease')),
            ], options={
                'db_table': 'release_entry', 'ordering': ('release__sort_num', 'position', 'id'),
                'indexes': [models.Index(fields=['release', 'position'], name='release_entry_order_idx'),
                            GinIndex(fields=['patch_ids'], name='release_entry_patches_gin'),
                            GinIndex(fields=['cves'], name='release_entry_cves_gin'),
                            GinIndex(fields=['relations'], name='release_entry_relations_gin')],
            },
        ),
    ]
