from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_intent_catalog", "0021_desiredcomputeinstance_desired_presence"),
    ]

    operations = [
        migrations.DeleteModel(name="DesiredDependency"),
    ]
