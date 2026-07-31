from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nautobot_intent_catalog", "0023_desiredservice_slug_unique"),
    ]

    operations = [
        migrations.RemoveField(model_name="desiredservice", name="service_type"),
        migrations.RemoveField(model_name="desiredservice", name="intent_source"),
        migrations.RemoveField(model_name="desiredservice", name="catalog_namespace"),
        migrations.RemoveField(model_name="desiredservice", name="catalog_metadata_name"),
        migrations.DeleteModel(name="IntentSource"),
    ]
