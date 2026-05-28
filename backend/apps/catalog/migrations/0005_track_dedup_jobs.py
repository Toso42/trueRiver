import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_track_version_candidate_decisions"),
        ("library", "0007_savedplaylist_savedplaylistentry"),
    ]

    operations = [
        migrations.CreateModel(
            name="TrackDedupJob",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("pending", "pending"), ("running", "running"), ("done", "done"), ("error", "error"), ("canceled", "canceled")], default="pending", max_length=16)),
                ("mode", models.CharField(choices=[("candidate_scan", "candidate scan")], default="candidate_scan", max_length=32)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("full_throttle_until", models.DateTimeField(blank=True, null=True)),
                ("scanned_count", models.BigIntegerField(default=0)),
                ("candidate_count", models.BigIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
                ("library", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dedup_jobs", to="library.library")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TrackDedupCandidate",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("fingerprint", models.CharField(db_index=True, max_length=128, unique=True)),
                ("status", models.CharField(choices=[("pending", "pending"), ("accepted", "accepted"), ("rejected", "rejected")], default="pending", max_length=16)),
                ("title", models.CharField(blank=True, default="", max_length=512)),
                ("score", models.DecimalField(decimal_places=2, default=0, max_digits=4)),
                ("reasons", models.JSONField(blank=True, default=list)),
                ("track_ids", models.JSONField(blank=True, default=list)),
                ("notes", models.TextField(blank=True, default="")),
                ("job", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="candidates", to="catalog.trackdedupjob")),
                ("library", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dedup_candidates", to="library.library")),
            ],
            options={
                "ordering": ["-score", "title", "-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="trackdedupcandidate",
            index=models.Index(fields=["library", "status"], name="dedup_candidate_status_idx"),
        ),
    ]
