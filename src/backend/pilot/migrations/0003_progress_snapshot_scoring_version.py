from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pilot", "0002_frozen_posting_recommendations")]

    operations = [
        # Label existing snapshots without recomputing their historical scores.
        migrations.AddField(
            model_name="progresssnapshot", name="scoring_version",
            field=models.CharField(default="padded_top3_v1", max_length=32),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="progresssnapshot", name="scoring_version",
            field=models.CharField(default="reported_top3_v2", max_length=32),
        ),
    ]
