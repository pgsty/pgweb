from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('info', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='infoitem',
            name='thumb',
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
    ]
