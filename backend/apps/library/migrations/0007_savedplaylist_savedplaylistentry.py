from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
        ("library", "0006_metafielddefinition_metanormalizationrule_mediafilemetavalue"),
    ]

    operations = [
        migrations.CreateModel(
            name="SavedPlaylist",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("notes", models.TextField(blank=True, default="")),
                ("library", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="saved_playlists", to="library.library")),
            ],
            options={
                "ordering": ["name", "-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="SavedPlaylistEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("position", models.PositiveIntegerField(default=0)),
                ("playlist", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="library.savedplaylist")),
                ("track", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="saved_playlist_entries", to="catalog.track")),
            ],
            options={
                "ordering": ["position", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="savedplaylist",
            constraint=models.UniqueConstraint(fields=("library", "name"), name="uniq_saved_playlist_library_name"),
        ),
        migrations.AddConstraint(
            model_name="savedplaylistentry",
            constraint=models.UniqueConstraint(fields=("playlist", "position"), name="uniq_saved_playlist_entry_position"),
        ),
    ]
