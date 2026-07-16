"""Add nctl-written reconciliation status fields to DesiredNode and DesiredService."""

from django.db import migrations, models


RECONCILIATION_STATUS_CHOICES = (
    ("converged", "Converged"),
    ("drifting", "Drifting"),
    ("converging", "Converging"),
    ("unknown", "Unknown"),
)


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_intent_catalog", "0008_remove_proto_drift_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="desirednode",
            name="reconciliation_status",
            field=models.CharField(
                blank=True,
                choices=RECONCILIATION_STATUS_CHOICES,
                help_text=(
                    "Derived cache of the last nctl dashboard run. Written by nctl over REST; "
                    "not editable here."
                ),
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="desirednode",
            name="reconciliation_checked_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Timestamp of the last nctl dashboard run that wrote reconciliation_status.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="desiredservice",
            name="reconciliation_status",
            field=models.CharField(
                blank=True,
                choices=RECONCILIATION_STATUS_CHOICES,
                help_text=(
                    "Derived cache of the last nctl dashboard run. Written by nctl over REST; "
                    "not editable here."
                ),
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="desiredservice",
            name="reconciliation_checked_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Timestamp of the last nctl dashboard run that wrote reconciliation_status.",
                null=True,
            ),
        ),
    ]
