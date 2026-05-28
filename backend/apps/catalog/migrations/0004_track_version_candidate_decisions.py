import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_track_versions"),
    ]

    operations = [
        migrations.CreateModel(
            name="TrackVersionCandidateDecision",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("fingerprint", models.CharField(db_index=True, max_length=128, unique=True)),
                ("status", models.CharField(choices=[("accepted", "accepted"), ("rejected", "rejected")], max_length=16)),
                ("notes", models.TextField(blank=True, default="")),
                ("group", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="candidate_decisions", to="catalog.trackversiongroup")),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
    ]
