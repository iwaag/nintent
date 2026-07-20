"""Replace required operational config with optional overrides and provenance."""

import uuid

from django.db import migrations, models
import django.db.models.deletion


def assert_empty_and_backfill_sources(apps, schema_editor):
    OperationalConfig = apps.get_model("nautobot_intent_catalog", "DesiredNodeOperationalConfig")
    old_count = OperationalConfig.objects.count()
    if old_count:
        raise RuntimeError(
            "Phase 2 migration requires zero DesiredNodeOperationalConfig rows; "
            f"found {old_count}. Export/review them before retrying."
        )

    DesiredNode = apps.get_model("nautobot_intent_catalog", "DesiredNode")
    DesiredEndpoint = apps.get_model("nautobot_intent_catalog", "DesiredEndpoint")
    DesiredNode.objects.filter(realized_device__isnull=False).update(realized_device_source="override")
    DesiredNode.objects.filter(realized_vm__isnull=False).update(realized_vm_source="override")
    DesiredEndpoint.objects.filter(dns_name__isnull=False).exclude(dns_name="").update(
        dns_name_source="intent"
    )
    DesiredEndpoint.objects.filter(mdns_name__isnull=False).exclude(mdns_name="").update(
        mdns_name_source="intent"
    )
    DesiredEndpoint.objects.filter(realized_ip_address__isnull=False).update(
        realized_ip_address_source="override"
    )


def clear_sources(apps, schema_editor):
    DesiredNode = apps.get_model("nautobot_intent_catalog", "DesiredNode")
    DesiredEndpoint = apps.get_model("nautobot_intent_catalog", "DesiredEndpoint")
    DesiredNode.objects.update(realized_device_source=None, realized_vm_source=None)
    DesiredEndpoint.objects.update(
        dns_name_source=None,
        mdns_name_source=None,
        realized_ip_address_source=None,
    )


SOURCE_FIELDS = (
    ("desirednode", "realized_device_source", (("derived", "Derived"), ("override", "Override"))),
    ("desirednode", "realized_vm_source", (("derived", "Derived"), ("override", "Override"))),
    ("desiredendpoint", "dns_name_source", (("derived", "Derived"), ("intent", "Intent"))),
    ("desiredendpoint", "mdns_name_source", (("derived", "Derived"), ("intent", "Intent"))),
    (
        "desiredendpoint",
        "realized_ip_address_source",
        (("derived", "Derived"), ("override", "Override")),
    ),
)


class Migration(migrations.Migration):
    dependencies = [("nautobot_intent_catalog", "0009_reconciliation_status")]

    operations = [
        *[
            migrations.AddField(
                model_name=model_name,
                name=field_name,
                field=models.CharField(
                    blank=True,
                    choices=choices,
                    editable=False,
                    max_length=16,
                    null=True,
                ),
            )
            for model_name, field_name, choices in SOURCE_FIELDS
        ],
        migrations.CreateModel(
            name="DesiredNodeOperationalOverride",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("_custom_field_data", models.JSONField(blank=True, default=dict, editable=False)),
                (
                    "declared_host_os",
                    models.CharField(
                        blank=True,
                        choices=[("haos", "Home Assistant OS")],
                        max_length=32,
                        null=True,
                    ),
                ),
                (
                    "connection_path",
                    models.CharField(
                        blank=True,
                        choices=[("local", "Local"), ("tailscale", "Tailscale")],
                        max_length=32,
                        null=True,
                    ),
                ),
                ("ansible_port", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "power_control",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("none", "None"),
                            ("wol", "Wake-on-LAN"),
                            ("macos_sleep", "macOS sleep"),
                        ],
                        max_length=32,
                        null=True,
                    ),
                ),
                ("is_laptop", models.BooleanField(blank=True, null=True)),
                (
                    "desired_node",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="operational_override",
                        to="nautobot_intent_catalog.desirednode",
                    ),
                ),
                (
                    "local_endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="local_operational_overrides",
                        to="nautobot_intent_catalog.desiredendpoint",
                    ),
                ),
                (
                    "tailscale_endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tailscale_operational_overrides",
                        to="nautobot_intent_catalog.desiredendpoint",
                    ),
                ),
            ],
            options={
                "ordering": ("desired_node__name",),
                "verbose_name": "desired node operational override",
                "verbose_name_plural": "desired node operational overrides",
            },
        ),
        migrations.RunPython(assert_empty_and_backfill_sources, clear_sources),
        migrations.DeleteModel(name="DesiredNodeOperationalConfig"),
    ]
