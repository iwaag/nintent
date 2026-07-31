from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nautobot_intent_catalog", "0022_remove_desireddependency"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="desiredservice",
            name="nic_unique_desired_service_entity",
        ),
        migrations.AlterField(
            model_name="desiredservice",
            name="slug",
            field=models.SlugField(max_length=255, unique=True),
        ),
    ]
