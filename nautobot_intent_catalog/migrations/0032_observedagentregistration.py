import django.core.serializers.json
import django.db.models.deletion
import nautobot.core.models.fields
import nautobot.extras.models.mixins
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("extras", "0142_remove_scheduledjob_approval_required"),
        ("nautobot_intent_catalog", "0031_desiredagent"),
    ]

    operations = [
        migrations.CreateModel(
            name="ObservedAgentRegistration",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("_custom_field_data", models.JSONField(blank=True, default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder)),
                ("observed_at", models.DateTimeField()),
                ("collector", models.CharField(blank=True, default="", max_length=255)),
                ("zulip_present", models.BooleanField(default=False)),
                ("zulip_user_id", models.PositiveIntegerField(blank=True, null=True)),
                ("zulip_is_active", models.BooleanField(default=False)),
                ("zulip_channels", models.JSONField(blank=True, default=list)),
                ("plane_present", models.BooleanField(default=False)),
                ("plane_user_id", models.CharField(blank=True, default="", max_length=255)),
                ("plane_role", models.PositiveSmallIntegerField(blank=True, null=True)),
                (
                    "desired_agent",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="observed_registration",
                        to="nautobot_intent_catalog.desiredagent",
                    ),
                ),
                ("tags", nautobot.core.models.fields.TagsField(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "observed agent registration",
                "verbose_name_plural": "observed agent registrations",
                "ordering": ("desired_agent__name",),
            },
            bases=(
                nautobot.extras.models.mixins.DataComplianceModelMixin,
                nautobot.extras.models.mixins.DynamicGroupMixin,
                nautobot.extras.models.mixins.NotesMixin,
                models.Model,
            ),
        ),
    ]
