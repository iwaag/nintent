from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nautobot_intent_catalog", "0027_desiredworkspace"),
    ]

    operations = [
        migrations.RemoveField(model_name="desirednodeoperationaloverride", name="declared_host_os"),
    ]
