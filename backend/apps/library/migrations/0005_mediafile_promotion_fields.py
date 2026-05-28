from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0004_librarydigesterror"),
    ]

    operations = [
        migrations.AddField(
            model_name="mediafile",
            name="digest_relative_path",
            field=models.CharField(blank=True, default="", max_length=2048),
        ),
        migrations.AddField(
            model_name="mediafile",
            name="storage_stage",
            field=models.CharField(choices=[("triv_in", "triv_in"), ("triv_up", "triv_up")], default="triv_in", max_length=16),
        ),
        migrations.AddField(
            model_name="mediafile",
            name="workflow_state",
            field=models.CharField(choices=[("unprocessed", "unprocessed"), ("unrevisioned", "unrevisioned"), ("revised", "revised"), ("exact_duplicate", "exact_duplicate"), ("variant", "variant")], default="unprocessed", max_length=24),
        ),
    ]
