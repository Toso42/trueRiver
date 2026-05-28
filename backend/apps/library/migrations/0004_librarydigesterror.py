from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0003_librarydigestjob"),
    ]

    operations = [
        migrations.CreateModel(
            name="LibraryDigestError",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("relative_path", models.CharField(blank=True, default="", max_length=2048)),
                ("absolute_path", models.CharField(max_length=4096)),
                ("filename", models.CharField(max_length=512)),
                ("message", models.TextField(blank=True, default="")),
                ("error_type", models.CharField(blank=True, default="", max_length=128)),
                ("digest_job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="error_records", to="library.librarydigestjob")),
                ("library", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="digest_errors", to="library.library")),
                ("media_file", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="digest_errors", to="library.mediafile")),
            ],
            options={
                "ordering": ["relative_path", "filename", "created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="librarydigesterror",
            index=models.Index(fields=["digest_job"], name="digest_error_job_idx"),
        ),
    ]
