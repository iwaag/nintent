from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nautobot_intent_catalog", "0015_compute_platform_instance_and_endpoint_mac")]

    operations = [
        migrations.AddField(
            model_name="desiredendpoint",
            name="gateway_address",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
    ]
