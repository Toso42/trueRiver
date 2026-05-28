import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArtistProfileImage",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("relative_path", models.CharField(max_length=2048)),
                ("original_filename", models.CharField(blank=True, default="", max_length=512)),
                ("content_type", models.CharField(blank=True, default="", max_length=128)),
                ("size", models.BigIntegerField(default=0)),
                ("source", models.CharField(choices=[("manual_upload", "manual upload")], default="manual_upload", max_length=32)),
                ("artist", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="profile_images", to="catalog.artist")),
            ],
            options={
                "ordering": ["-created_at", "original_filename"],
            },
        ),
        migrations.AddField(
            model_name="artist",
            name="selected_cover_mode",
            field=models.CharField(choices=[("auto", "auto"), ("album", "album"), ("upload", "upload")], default="auto", max_length=16),
        ),
        migrations.AddField(
            model_name="artist",
            name="selected_cover_album",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="selected_by_artists", to="catalog.album"),
        ),
        migrations.AddField(
            model_name="artist",
            name="selected_profile_image",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="selected_by_artists", to="catalog.artistprofileimage"),
        ),
    ]
