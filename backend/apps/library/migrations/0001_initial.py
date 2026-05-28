import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FileFormatProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=64, unique=True)),
                ("container", models.CharField(max_length=32)),
                ("codec", models.CharField(blank=True, default="", max_length=64)),
                ("is_lossless", models.BooleanField(default=False)),
                ("writeback_supported", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, default="")),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Library",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=128, unique=True)),
                ("slug", models.SlugField(max_length=128, unique=True)),
                ("ingest_path", models.CharField(max_length=1024)),
                ("digest_path", models.CharField(max_length=1024)),
                ("normalize_path", models.CharField(max_length=1024)),
                ("enabled", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("last_discovery_at", models.DateTimeField(blank=True, null=True)),
                ("last_digest_sync_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="LibraryScanJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("pending", "pending"), ("discovering", "discovering"), ("processing", "processing"), ("done", "done"), ("error", "error"), ("canceled", "canceled")], default="pending", max_length=16)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("discovered_count", models.BigIntegerField(default=0)),
                ("queued_count", models.BigIntegerField(default=0)),
                ("processed_count", models.BigIntegerField(default=0)),
                ("skipped_count", models.BigIntegerField(default=0)),
                ("error_count", models.BigIntegerField(default=0)),
                ("removed_count", models.BigIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
                ("library", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scan_jobs", to="library.library")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="MediaFile",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("relative_path", models.CharField(max_length=2048)),
                ("absolute_path", models.CharField(max_length=4096)),
                ("path_hash", models.CharField(db_index=True, max_length=64)),
                ("filename", models.CharField(max_length=512)),
                ("extension", models.CharField(blank=True, default="", max_length=32)),
                ("media_kind", models.CharField(blank=True, default="audio", max_length=32)),
                ("mime_type", models.CharField(blank=True, default="", max_length=128)),
                ("size", models.BigIntegerField(default=0)),
                ("mtime", models.DateTimeField(blank=True, null=True)),
                ("inode", models.CharField(blank=True, default="", max_length=64)),
                ("content_hash", models.CharField(blank=True, default="", max_length=128)),
                ("status", models.CharField(choices=[("discovered", "discovered"), ("indexed", "indexed"), ("modified", "modified"), ("pending_write", "pending_write"), ("synced", "synced"), ("error", "error"), ("missing", "missing")], default="discovered", max_length=16)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("removed_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True, default="")),
                ("library", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="media_files", to="library.library")),
            ],
            options={
                "ordering": ["relative_path"],
            },
        ),
        migrations.CreateModel(
            name="LibraryScanSkip",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("relative_path", models.CharField(blank=True, default="", max_length=2048)),
                ("absolute_path", models.CharField(max_length=4096)),
                ("filename", models.CharField(max_length=512)),
                ("extension", models.CharField(blank=True, default="", max_length=32)),
                ("size", models.BigIntegerField(blank=True, null=True)),
                ("reason_code", models.CharField(choices=[("unsupported_extension", "unsupported_extension"), ("artwork_asset", "artwork_asset"), ("playlist_asset", "playlist_asset"), ("cue_sheet", "cue_sheet"), ("diagnostic_file", "diagnostic_file"), ("ignored_system_file", "ignored_system_file"), ("unknown_extension", "unknown_extension"), ("stat_failed", "stat_failed"), ("not_a_file", "not_a_file"), ("permission_denied", "permission_denied"), ("unknown_error", "unknown_error")], max_length=64)),
                ("reason_detail", models.TextField(blank=True, default="")),
                ("library", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scan_skips", to="library.library")),
                ("scan_job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="skip_records", to="library.libraryscanjob")),
            ],
            options={
                "ordering": ["relative_path", "filename", "created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="mediafile",
            constraint=models.UniqueConstraint(fields=("library", "relative_path"), name="uniq_media_file_per_library_path"),
        ),
        migrations.AddIndex(
            model_name="mediafile",
            index=models.Index(fields=["library", "path_hash"], name="mediafile_library_hash_idx"),
        ),
        migrations.AddIndex(
            model_name="mediafile",
            index=models.Index(fields=["library", "status"], name="mediafile_library_status_idx"),
        ),
        migrations.AddIndex(
            model_name="mediafile",
            index=models.Index(fields=["mtime", "size"], name="mediafile_mtime_size_idx"),
        ),
        migrations.AddIndex(
            model_name="libraryscanskip",
            index=models.Index(fields=["scan_job", "reason_code"], name="scan_skip_job_reason_idx"),
        ),
    ]
