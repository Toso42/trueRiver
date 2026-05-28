from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TagDefinition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("scope", models.CharField(choices=[("track", "track"), ("album", "album"), ("artist", "artist")], max_length=16)),
                ("key", models.SlugField(max_length=128)),
                ("label", models.CharField(max_length=255)),
                ("value_type", models.CharField(choices=[("text", "text"), ("number", "number"), ("bool", "bool"), ("date", "date")], default="text", max_length=16)),
                ("allow_multiple", models.BooleanField(default=True)),
                ("description", models.TextField(blank=True, default="")),
            ],
            options={
                "ordering": ["scope", "key"],
            },
        ),
        migrations.CreateModel(
            name="TagValue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("value_text", models.TextField(blank=True, default="")),
                ("value_number", models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True)),
                ("value_bool", models.BooleanField(blank=True, null=True)),
                ("value_date", models.DateField(blank=True, null=True)),
                ("normalized_key", models.CharField(blank=True, default="", max_length=255)),
                ("definition", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="values", to="tags.tagdefinition")),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="TrackTagAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tag_value", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="track_assignments", to="tags.tagvalue")),
                ("track", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tag_assignments", to="catalog.track")),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.AddConstraint(
            model_name="tagdefinition",
            constraint=models.UniqueConstraint(fields=("scope", "key"), name="uniq_tag_definition_scope_key"),
        ),
        migrations.AddConstraint(
            model_name="tracktagassignment",
            constraint=models.UniqueConstraint(fields=("track", "tag_value"), name="uniq_track_tag_assignment"),
        ),
    ]
