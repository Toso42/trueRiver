import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0002_artist_profile_images"),
    ]

    operations = [
        migrations.CreateModel(
            name="TrackVersionGroup",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=512)),
                ("sort_title", models.CharField(blank=True, default="", max_length=512)),
                ("fingerprint", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("serving_mode", models.CharField(choices=[("primary", "primary"), ("all", "all"), ("disabled", "disabled")], default="primary", max_length=16)),
                ("notes", models.TextField(blank=True, default="")),
            ],
            options={
                "ordering": ["sort_title", "title", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="TrackVersionMembership",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("primary", "primary"), ("alternate", "alternate"), ("live", "live"), ("remix", "remix"), ("remaster", "remaster"), ("edit", "edit"), ("instrumental", "instrumental"), ("unknown", "unknown")], default="alternate", max_length=32)),
                ("label", models.CharField(blank=True, default="", max_length=255)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_default", models.BooleanField(default=False)),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="catalog.trackversiongroup")),
                ("track", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="version_memberships", to="catalog.track")),
            ],
            options={
                "ordering": ["group", "sort_order", "created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="trackversionmembership",
            constraint=models.UniqueConstraint(fields=("group", "track"), name="uniq_track_version_membership"),
        ),
    ]
