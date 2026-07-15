"""Remove persisted proto-drift outputs superseded by nctl."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_intent_catalog", "0007_placement_config_schema_default"),
    ]

    operations = [
        migrations.DeleteModel(name="IntentEvaluation"),
        migrations.DeleteModel(name="DeploymentProfileProjection"),
    ]
