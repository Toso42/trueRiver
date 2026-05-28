from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0005_mediafile_promotion_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="MetaFieldDefinition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255, unique=True)),
                ("normalized_name", models.CharField(db_index=True, max_length=255, unique=True)),
                ("source_family", models.CharField(blank=True, default="any", max_length=32)),
                ("is_user_defined", models.BooleanField(default=False)),
                ("is_indexed", models.BooleanField(default=True)),
                ("description", models.TextField(blank=True, default="")),
            ],
            options={
                "ordering": ["normalized_name", "name"],
            },
        ),
        migrations.CreateModel(
            name="MetaNormalizationRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_family", models.CharField(default="any", max_length=32)),
                ("source_name", models.CharField(max_length=255)),
                ("source_name_normalized", models.CharField(db_index=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("is_system", models.BooleanField(default=False)),
                ("target_field", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="normalization_rules", to="library.metafielddefinition")),
            ],
            options={
                "ordering": ["source_family", "source_name_normalized"],
                "constraints": [
                    models.UniqueConstraint(fields=("source_family", "source_name_normalized"), name="uniq_meta_normalization_rule_source"),
                ],
            },
        ),
        migrations.CreateModel(
            name="MediaFileMetaValue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_family", models.CharField(default="unknown", max_length=32)),
                ("source_name", models.CharField(max_length=255)),
                ("source_name_normalized", models.CharField(db_index=True, max_length=255)),
                ("value_text", models.TextField(blank=True, default="")),
                ("value_order", models.PositiveIntegerField(default=0)),
                ("is_primary", models.BooleanField(default=False)),
                ("field", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="values", to="library.metafielddefinition")),
                ("media_file", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meta_values", to="library.mediafile")),
            ],
            options={
                "ordering": ["field__normalized_name", "value_order", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="mediafilemetavalue",
            index=models.Index(fields=["media_file", "field"], name="media_meta_file_field_idx"),
        ),
        migrations.AddIndex(
            model_name="mediafilemetavalue",
            index=models.Index(fields=["field", "source_family"], name="media_meta_field_family_idx"),
        ),
    ]
