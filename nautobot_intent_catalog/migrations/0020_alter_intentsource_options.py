from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("nautobot_intent_catalog", "0019_reduce_desired_state_schema")]
    operations = [
        migrations.AlterModelOptions(
            name="intentsource",
            options={"ordering": ("slug",), "verbose_name": "intent source", "verbose_name_plural": "intent sources"},
        ),
    ]
