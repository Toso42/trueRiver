from django.db import migrations, models


def enable_manual_lookup(apps, schema_editor):
    RemoteMetadataSettings = apps.get_model("catalog", "RemoteMetadataSettings")
    RemoteMetadataSettings.objects.all().update(enabled=True, lookup_mode="manual")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_remote_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="remotemetadatasettings",
            name="lookup_mode",
            field=models.CharField(
                choices=[
                    ("manual", "manual"),
                    ("auto", "auto"),
                ],
                default="manual",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="remotemetadatasettings",
            name="enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(enable_manual_lookup, migrations.RunPython.noop),
    ]
