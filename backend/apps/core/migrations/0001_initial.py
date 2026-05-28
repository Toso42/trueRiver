from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="OperationLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operation", models.CharField(choices=[("create", "create"), ("read", "read"), ("update", "update"), ("delete", "delete"), ("action", "action")], max_length=16)),
                ("object_id", models.CharField(max_length=64)),
                ("timestamp", models.DateTimeField(default=django.utils.timezone.now)),
                ("path", models.CharField(blank=True, default="", max_length=255)),
                ("http_method", models.CharField(blank=True, default="", max_length=16)),
                ("changes", models.JSONField(blank=True, null=True)),
                ("content_type", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="contenttypes.contenttype")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-timestamp", "-id"],
            },
        ),
    ]
