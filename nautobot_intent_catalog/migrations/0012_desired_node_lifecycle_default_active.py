"""Default new DesiredNode rows to lifecycle 'active' (Better Usability Phase 3).

Django default-only AlterField: it changes what future INSERTs use when the
field is omitted, not any existing row. No RunPython, bulk update, or
trigger. Existing 'planned' rows are reviewed and promoted individually with
`nctl lifecycle <slug> active`, never by this migration.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_intent_catalog", "0011_align_primary_model_inherited_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="desirednode",
            name="lifecycle",
            field=models.CharField(
                choices=[
                    ("planned", "Planned"),
                    ("approved", "Approved"),
                    ("active", "Active"),
                    ("deprecated", "Deprecated"),
                    ("retired", "Retired"),
                ],
                default="active",
                max_length=64,
            ),
        ),
    ]
