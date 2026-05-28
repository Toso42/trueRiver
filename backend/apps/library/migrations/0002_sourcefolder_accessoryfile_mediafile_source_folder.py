from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SourceFolder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("relative_path", models.CharField(blank=True, default="", max_length=2048)),
                ("absolute_path", models.CharField(max_length=4096)),
                ("name", models.CharField(max_length=512)),
                ("parent_relative_path", models.CharField(blank=True, default="", max_length=2048)),
                ("path_depth", models.PositiveIntegerField(default=0)),
                ("file_count", models.PositiveIntegerField(default=0)),
                ("audio_file_count", models.PositiveIntegerField(default=0)),
                ("accessory_file_count", models.PositiveIntegerField(default=0)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("removed_at", models.DateTimeField(blank=True, null=True)),
                ("library", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="source_folders", to="library.library")),
            ],
            options={
                "ordering": ["relative_path", "name"],
            },
        ),
        migrations.CreateModel(
            name="AccessoryFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("relative_path", models.CharField(max_length=2048)),
                ("absolute_path", models.CharField(max_length=4096)),
                ("filename", models.CharField(max_length=512)),
                ("extension", models.CharField(blank=True, default="", max_length=32)),
                ("asset_kind", models.CharField(choices=[("artwork", "artwork"), ("playlist", "playlist"), ("cue_sheet", "cue_sheet"), ("diagnostic", "diagnostic"), ("unknown_support", "unknown_support")], max_length=64)),
                ("size", models.BigIntegerField(default=0)),
                ("mtime", models.DateTimeField(blank=True, null=True)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("removed_at", models.DateTimeField(blank=True, null=True)),
                ("library", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="accessory_files", to="library.library")),
                ("source_folder", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="accessory_files", to="library.sourcefolder")),
            ],
            options={
                "ordering": ["relative_path", "filename"],
            },
        ),
        migrations.AddField(
            model_name="mediafile",
            name="source_folder",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="media_files", to="library.sourcefolder"),
        ),
        migrations.AddIndex(
            model_name="sourcefolder",
            index=models.Index(fields=["library", "path_depth"], name="sourcefolder_library_depth_idx"),
        ),
        migrations.AddConstraint(
            model_name="sourcefolder",
            constraint=models.UniqueConstraint(fields=("library", "relative_path"), name="uniq_source_folder_per_library_path"),
        ),
        migrations.AddConstraint(
            model_name="accessoryfile",
            constraint=models.UniqueConstraint(fields=("library", "relative_path"), name="uniq_accessory_file_per_library_path"),
        ),
        migrations.AddIndex(
            model_name="accessoryfile",
            index=models.Index(fields=["library", "asset_kind"], name="accessory_library_kind_idx"),
        ),
    ]
