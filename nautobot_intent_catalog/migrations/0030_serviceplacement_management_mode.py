from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nautobot_intent_catalog", "0029_workflowepisode"),
    ]

    operations = [
        migrations.AddField(
            model_name="desiredserviceplacement",
            name="management_mode",
            field=models.CharField(
                choices=[("nctl_managed", "nctl managed"), ("manual", "Manual")],
                default="nctl_managed",
                max_length=32,
            ),
        ),
    ]
