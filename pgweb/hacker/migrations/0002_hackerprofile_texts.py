from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('hacker', '0001_initial')]
    operations = [
        migrations.AddField(
            model_name='hackerprofile', name='texts',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
