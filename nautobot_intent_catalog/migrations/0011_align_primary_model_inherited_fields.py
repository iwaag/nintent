"""Align migration state with Nautobot 3.1 PrimaryModel inherited fields."""

from __future__ import annotations

import uuid

import django.core.serializers.json
from django.db import migrations, models
import nautobot.core.models.fields


_MODELS = (
    "desireddependency",
    "desiredendpoint",
    "desirediprange",
    "desirednode",
    "desirednodeoperationaloverride",
    "desiredservice",
    "desiredserviceplacement",
    "intentsource",
)


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "0142_remove_scheduledjob_approval_required"),
        ("nautobot_intent_catalog", "0010_operational_overrides_and_provenance"),
    ]

    operations = [
        *(
            migrations.AddField(
                model_name=model_name,
                name="tags",
                field=nautobot.core.models.fields.TagsField(
                    through="extras.TaggedItem",
                    to="extras.Tag",
                ),
            )
            for model_name in _MODELS
        ),
        *(
            operation
            for model_name in _MODELS
            for operation in (
                migrations.AlterField(
                    model_name=model_name,
                    name="_custom_field_data",
                    field=models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                    ),
                ),
                migrations.AlterField(
                    model_name=model_name,
                    name="id",
                    field=models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
            )
        ),
    ]
