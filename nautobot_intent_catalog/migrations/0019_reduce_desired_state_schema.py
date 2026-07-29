"""Remove fields outside the current desired-state control loop."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nautobot_intent_catalog", "0018_braindumpdocument_status"),
    ]

    operations = [
        migrations.RemoveConstraint("desiredcomputeplatform", "dcp_provider_type_proxmox"),
        migrations.RemoveConstraint("desiredcomputeplatform", "dcp_config_schema_v1"),
        migrations.RemoveConstraint("desiredcomputeinstance", "dci_config_schema_v1"),
        migrations.RemoveField("intentsource", "name"),
        migrations.RemoveField("intentsource", "source_type"),
        migrations.RemoveField("intentsource", "url"),
        migrations.RemoveField("intentsource", "ref"),
        migrations.RemoveField("intentsource", "enabled"),
        migrations.RemoveField("intentsource", "owner"),
        migrations.RemoveField("intentsource", "description"),
        migrations.RemoveField("intentsource", "source_config"),
        migrations.RemoveField("intentsource", "last_import_status"),
        migrations.RemoveField("intentsource", "last_imported_at"),
        migrations.RemoveField("intentsource", "last_import_summary"),
        migrations.RemoveField("desiredservice", "display_name"),
        migrations.RemoveField("desiredservice", "source_ref"),
        migrations.RemoveField("desiredservice", "source_catalog_path"),
        migrations.RemoveField("desiredservice", "catalog_kind"),
        migrations.RemoveField("desiredservice", "catalog_owner"),
        migrations.RemoveField("desiredservice", "catalog_lifecycle"),
        migrations.RemoveField("desiredservice", "prefers_gpu"),
        migrations.RemoveField("desiredservice", "min_memory_gb"),
        migrations.RemoveField("desiredservice", "requirements"),
        migrations.RemoveField("desiredservice", "analysis_provenance"),
        migrations.RemoveField("desiredservice", "notes"),
        migrations.RemoveField("desiredservice", "last_analyzed_at"),
        migrations.RemoveField("desirednode", "description"),
        migrations.RemoveField("desirednode", "intent_source"),
        migrations.RemoveField("desirednode", "realized_device_source"),
        migrations.RemoveField("desirednode", "notes"),
        migrations.RemoveField("desiredendpoint", "dns_name_source"),
        migrations.RemoveField("desiredendpoint", "mdns_name_source"),
        migrations.RemoveField("desiredendpoint", "realized_ip_address_source"),
        migrations.RemoveField("desiredendpoint", "description"),
        migrations.RemoveField("desirediprange", "description"),
        migrations.RemoveField("desiredcomputeplatform", "provider_type"),
        migrations.RemoveField("desiredcomputeplatform", "config_schema_version"),
        migrations.RemoveField("desiredcomputeplatform", "realized_cluster_source"),
        migrations.RemoveField("desiredcomputeinstance", "config_schema_version"),
        migrations.RemoveField("desiredcomputeinstance", "realized_vm_source"),
        migrations.RemoveField("desiredserviceplacement", "instance_role"),
        migrations.RemoveField("desiredserviceplacement", "assignment_source"),
        migrations.RemoveField("desiredserviceplacement", "reason"),
    ]
