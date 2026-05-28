from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tags", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tagvalue",
            name="display_order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterModelOptions(
            name="tagvalue",
            options={"ordering": ["definition_id", "display_order", "normalized_key", "id"]},
        ),
    ]
