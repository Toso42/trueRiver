import uuid

import apps.catalog.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("library", "0007_savedplaylist_savedplaylistentry"),
        ("catalog", "0005_track_dedup_jobs"),
    ]

    operations = [
        migrations.CreateModel(
            name="RemoteMetadataSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("enabled", models.BooleanField(default=False)),
                ("video_enabled", models.BooleanField(default=True)),
                ("audio_enabled", models.BooleanField(default=True)),
                ("allow_remote_artwork", models.BooleanField(default=True)),
                ("preferred_language", models.CharField(blank=True, default="en-US", max_length=16)),
                ("preferred_region", models.CharField(blank=True, default="US", max_length=8)),
                (
                    "overwrite_policy",
                    models.CharField(
                        choices=[
                            ("missing_only", "missing only"),
                            ("ask", "ask before overwrite"),
                            ("replace_unlocked", "replace unlocked fields"),
                        ],
                        default="missing_only",
                        max_length=32,
                    ),
                ),
                (
                    "provider_order",
                    models.JSONField(blank=True, default=apps.catalog.models.default_remote_metadata_provider_order),
                ),
            ],
            options={
                "verbose_name_plural": "remote metadata settings",
            },
        ),
        migrations.CreateModel(
            name="MetadataEnrichmentJob",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "pending"),
                            ("running", "running"),
                            ("done", "done"),
                            ("error", "error"),
                            ("canceled", "canceled"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("find", "find"),
                            ("refresh", "refresh"),
                            ("fix_match", "fix match"),
                        ],
                        default="find",
                        max_length=32,
                    ),
                ),
                (
                    "media_scope",
                    models.CharField(
                        choices=[
                            ("mixed", "mixed"),
                            ("audio", "audio"),
                            ("video", "video"),
                        ],
                        default="mixed",
                        max_length=16,
                    ),
                ),
                ("provider_key", models.CharField(blank=True, default="", max_length=64)),
                (
                    "overwrite_policy",
                    models.CharField(
                        choices=[
                            ("missing_only", "missing only"),
                            ("ask", "ask before overwrite"),
                            ("replace_unlocked", "replace unlocked fields"),
                        ],
                        default="missing_only",
                        max_length=32,
                    ),
                ),
                ("target_track_ids", models.JSONField(blank=True, default=list)),
                ("candidate_count", models.PositiveIntegerField(default=0)),
                ("updated_count", models.PositiveIntegerField(default=0)),
                ("result_payload", models.JSONField(blank=True, default=dict)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True, default="")),
                (
                    "library",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="metadata_enrichment_jobs",
                        to="library.library",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="metadata_enrichment_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="metadataenrichmentjob",
            index=models.Index(fields=["status", "created_at"], name="metadata_enrich_status_idx"),
        ),
        migrations.AddIndex(
            model_name="metadataenrichmentjob",
            index=models.Index(fields=["media_scope", "created_at"], name="metadata_enrich_scope_idx"),
        ),
    ]
