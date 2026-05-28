from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0008_mediafile_external_storage_stage"),
    ]

    operations = [
        migrations.CreateModel(
            name="AutoImportSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("enabled", models.BooleanField(default=False)),
                ("trive_scan_enabled", models.BooleanField(default=False)),
                ("trive_up_enabled", models.BooleanField(default=False)),
                ("classic_scan_enabled", models.BooleanField(default=False)),
                ("classic_up_enabled", models.BooleanField(default=False)),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("last_triggered_at", models.DateTimeField(blank=True, null=True)),
                ("last_trive_signature", models.JSONField(blank=True, default=dict)),
                ("last_classic_signatures", models.JSONField(blank=True, default=dict)),
                ("last_result", models.JSONField(blank=True, default=dict)),
                ("last_error", models.TextField(blank=True, default="")),
                ("library", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="auto_import_settings", to="library.library")),
            ],
            options={
                "ordering": ["library__name"],
            },
        ),
    ]
