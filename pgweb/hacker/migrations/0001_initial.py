from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='HackerProfile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_id', models.CharField(max_length=64, unique=True)),
                ('slug', models.SlugField(max_length=160, unique=True)),
                ('name', models.CharField(max_length=250)),
                ('organization', models.CharField(blank=True, db_index=True, default='', max_length=250)),
                ('country', models.CharField(blank=True, db_index=True, default='', max_length=100)),
                ('bio', models.TextField(blank=True, default='')),
                ('data', models.JSONField(blank=True, default=dict)),
                ('avatar', models.BinaryField(blank=True, null=True)),
                ('avatar_content_type', models.CharField(blank=True, default='', max_length=50)),
                ('avatar_sha256', models.CharField(blank=True, default='', max_length=64)),
                ('content_hash', models.CharField(max_length=64)),
                ('source_fetched_at', models.DateTimeField()),
                ('imported_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'hacker_profile', 'ordering': ('name', 'source_id')},
        ),
    ]
