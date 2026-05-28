from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("library", "0002_sourcefolder_accessoryfile_mediafile_source_folder"),
    ]

    operations = [
        migrations.CreateModel(
            name="LibraryDigestJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("pending", "pending"), ("running", "running"), ("done", "done"), ("error", "error"), ("canceled", "canceled")], default="pending", max_length=16)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("target_count", models.BigIntegerField(default=0)),
                ("processed_count", models.BigIntegerField(default=0)),
                ("created_track_count", models.BigIntegerField(default=0)),
                ("reused_track_count", models.BigIntegerField(default=0)),
                ("error_count", models.BigIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
                ("library", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="digest_jobs", to="library.library")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
