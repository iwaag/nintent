import django.core.serializers.json
import django.db.models.deletion
import nautobot.core.models.fields
import nautobot.extras.models.mixins
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("extras", "0142_remove_scheduledjob_approval_required"),
        ("nautobot_intent_catalog", "0030_serviceplacement_management_mode"),
    ]

    operations = [
        migrations.CreateModel(
            name="DesiredAgent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("_custom_field_data", models.JSONField(blank=True, default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder)),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=255, unique=True)),
                ("lifecycle", models.CharField(default="proposed", max_length=64)),
                ("zulip_user_id", models.PositiveIntegerField(blank=True, null=True)),
                ("plane_user_id", models.CharField(blank=True, default="", max_length=255)),
                ("desired_zulip_channels", models.JSONField(blank=True, default=list)),
                (
                    "desired_service_placement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="desired_agents",
                        to="nautobot_intent_catalog.desiredserviceplacement",
                    ),
                ),
                (
                    "desired_workspace",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="desired_agents",
                        to="nautobot_intent_catalog.desiredworkspace",
                    ),
                ),
                ("tags", nautobot.core.models.fields.TagsField(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "desired agent",
                "verbose_name_plural": "desired agents",
                "ordering": ("name",),
            },
            bases=(
                nautobot.extras.models.mixins.DataComplianceModelMixin,
                nautobot.extras.models.mixins.DynamicGroupMixin,
                nautobot.extras.models.mixins.NotesMixin,
                models.Model,
            ),
        ),
        migrations.AddConstraint(
            model_name="desiredagent",
            constraint=models.CheckConstraint(
                condition=models.expressions.RawSQL("jsonb_typeof(desired_zulip_channels) = 'array'", (), output_field=models.BooleanField()),
                name="nic_agent_channels_array",
            ),
        ),
    ]
