import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("library", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Album",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=255)),
                ("sort_title", models.CharField(blank=True, default="", max_length=255)),
                ("release_year", models.IntegerField(blank=True, null=True)),
                ("triver_notes", models.TextField(blank=True, default="")),
            ],
            options={
                "ordering": ["sort_title", "title"],
            },
        ),
        migrations.CreateModel(
            name="Artist",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("sort_name", models.CharField(blank=True, default="", max_length=255)),
                ("triver_notes", models.TextField(blank=True, default="")),
            ],
            options={
                "ordering": ["sort_name", "name"],
            },
        ),
        migrations.CreateModel(
            name="Track",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("canonical_title", models.CharField(max_length=512)),
                ("canonical_sort_title", models.CharField(blank=True, default="", max_length=512)),
                ("release_year", models.IntegerField(blank=True, null=True)),
                ("disc_number", models.IntegerField(blank=True, null=True)),
                ("track_number", models.IntegerField(blank=True, null=True)),
                ("duration_seconds", models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ("metadata_state", models.CharField(choices=[("clean", "clean"), ("modified", "modified"), ("pending_write", "pending_write"), ("synced", "synced"), ("error", "error")], default="clean", max_length=16)),
                ("last_error", models.TextField(blank=True, default="")),
                ("album", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tracks", to="catalog.album")),
                ("primary_file", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="primary_for_tracks", to="library.mediafile")),
            ],
            options={
                "ordering": ["canonical_sort_title", "canonical_title"],
            },
        ),
        migrations.CreateModel(
            name="MediaTransformJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("destination_relative_path", models.CharField(max_length=2048)),
                ("destination_format", models.CharField(blank=True, default="", max_length=32)),
                ("status", models.CharField(choices=[("pending", "pending"), ("running", "running"), ("done", "done"), ("error", "error")], default="pending", max_length=16)),
                ("last_error", models.TextField(blank=True, default="")),
                ("requested_profile", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="library.fileformatprofile")),
                ("source_file", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transform_jobs", to="library.mediafile")),
            ],
        ),
        migrations.CreateModel(
            name="MetadataWritebackJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("target_format", models.CharField(blank=True, default="native", max_length=32)),
                ("write_native_tags", models.BooleanField(default=True)),
                ("export_triver_sidecar", models.BooleanField(default=True)),
                ("status", models.CharField(choices=[("pending", "pending"), ("running", "running"), ("done", "done"), ("error", "error")], default="pending", max_length=16)),
                ("last_error", models.TextField(blank=True, default="")),
                ("media_file", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="writeback_jobs", to="library.mediafile")),
                ("track", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="writeback_jobs", to="catalog.track")),
            ],
        ),
        migrations.CreateModel(
            name="TrackMetadataOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(blank=True, default="", max_length=512)),
                ("album_title", models.CharField(blank=True, default="", max_length=512)),
                ("release_year", models.IntegerField(blank=True, null=True)),
                ("disc_number", models.IntegerField(blank=True, null=True)),
                ("track_number", models.IntegerField(blank=True, null=True)),
                ("comment", models.TextField(blank=True, default="")),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("track", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="override", to="catalog.track")),
            ],
        ),
        migrations.CreateModel(
            name="TrackSourceMetadata",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("extractor_name", models.CharField(default="mutagen", max_length=64)),
                ("extractor_version", models.CharField(blank=True, default="", max_length=64)),
                ("raw_title", models.CharField(blank=True, default="", max_length=512)),
                ("raw_album", models.CharField(blank=True, default="", max_length=512)),
                ("raw_year", models.IntegerField(blank=True, null=True)),
                ("raw_track_number", models.CharField(blank=True, default="", max_length=64)),
                ("raw_disc_number", models.CharField(blank=True, default="", max_length=64)),
                ("raw_artists_display", models.JSONField(blank=True, default=list)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("media_file", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="extracted_metadata", to="library.mediafile")),
                ("track", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="source_metadata", to="catalog.track")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TrackArtistCredit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("role", models.CharField(choices=[("primary", "primary"), ("featured", "featured"), ("composer", "composer"), ("conductor", "conductor"), ("performer", "performer")], default="primary", max_length=32)),
                ("credit_order", models.PositiveIntegerField(default=0)),
                ("credited_name", models.CharField(blank=True, default="", max_length=255)),
                ("is_primary", models.BooleanField(default=False)),
                ("artist", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="track_credits", to="catalog.artist")),
                ("track", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="artist_credits", to="catalog.track")),
            ],
            options={
                "ordering": ["credit_order", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="artist",
            constraint=models.UniqueConstraint(fields=("name", "sort_name"), name="uniq_artist_name_sort_name"),
        ),
        migrations.AddConstraint(
            model_name="trackartistcredit",
            constraint=models.UniqueConstraint(fields=("track", "artist", "role", "credit_order"), name="uniq_track_artist_credit"),
        ),
    ]
