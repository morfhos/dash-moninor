from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_auditlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="slug",
            field=models.SlugField(blank=True, max_length=100, null=True, unique=True),
        ),
    ]
