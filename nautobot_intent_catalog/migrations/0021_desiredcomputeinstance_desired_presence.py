# Generated manually for the Phase 1 desired-presence contract.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nautobot_intent_catalog", "0020_alter_intentsource_options")]

    operations = [
        migrations.AddField(
            model_name="desiredcomputeinstance",
            name="desired_presence",
            field=models.CharField(
                choices=[("present", "Present"), ("absent", "Absent")],
                default="present",
                max_length=16,
            ),
        ),
    ]
