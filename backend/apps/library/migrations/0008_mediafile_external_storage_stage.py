from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0007_savedplaylist_savedplaylistentry"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mediafile",
            name="storage_stage",
            field=models.CharField(
                choices=[
                    ("triv_in", "triv_in"),
                    ("triv_up", "triv_up"),
                    ("external", "external"),
                ],
                default="triv_in",
                max_length=16,
            ),
        ),
    ]
