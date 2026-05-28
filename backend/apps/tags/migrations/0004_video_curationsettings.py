import apps.tags.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tags", "0003_albumtagassignment_artisttagassignment_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="VideoCurationSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("row_order", models.JSONField(blank=True, default=apps.tags.models.default_video_curation_row_order)),
            ],
            options={
                "verbose_name_plural": "video curation settings",
            },
        ),
    ]
