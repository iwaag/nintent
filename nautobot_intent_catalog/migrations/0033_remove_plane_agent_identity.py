"""Drop the Plane half of an agent's identity (`refactor` p3 step 2).

Plane is being retired. An agent's messaging identity is its Zulip bot user
id and nothing else, so the declared `plane_user_id` and the three observed
Plane columns have no source and no consumer left. The data is disposable
experimental state in a private environment; nothing is migrated.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nautobot_intent_catalog", "0032_observedagentregistration"),
    ]

    operations = [
        migrations.RemoveField(model_name="desiredagent", name="plane_user_id"),
        migrations.RemoveField(model_name="observedagentregistration", name="plane_present"),
        migrations.RemoveField(model_name="observedagentregistration", name="plane_user_id"),
        migrations.RemoveField(model_name="observedagentregistration", name="plane_role"),
    ]
