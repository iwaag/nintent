"""Table definitions for Intent Catalog models (read-only inspection tables)."""

from __future__ import annotations

try:
    import django_tables2 as tables
    from nautobot.apps.tables import BaseTable

    from .compute_contract import effective_lifecycle
    from .models import (
        BrainDumpDocument,
        DesiredComputeInstance,
        DesiredComputePlatform,
        DesiredEndpoint,
        DesiredIPRange,
        DesiredNode,
        DesiredNodeOperationalOverride,
        DesiredService,
        DesiredServicePlacement,
        IntentSource,
    )
except ImportError:  # pragma: no cover - Nautobot/Django are unavailable in local unit tests.
    pass
else:

    class IntentSourceTable(BaseTable):
        """Intent source list table."""

        slug = tables.LinkColumn()

        class Meta(BaseTable.Meta):
            model = IntentSource
            fields = (
                "slug",
            )
            default_columns = (
                "slug",
            )


    class DesiredServiceTable(BaseTable):
        """Desired service list table."""

        name = tables.LinkColumn()
        intent_source = tables.LinkColumn()
        class Meta(BaseTable.Meta):
            model = DesiredService
            fields = (
                "name",
                "service_type",
                "lifecycle",
                "intent_source",
            )
            default_columns = (
                "name",
                "service_type",
                "lifecycle",
                "intent_source",
            )


    class DesiredNodeTable(BaseTable):
        """Desired node list table."""

        name = tables.LinkColumn()
        intent_source = tables.LinkColumn()
        realized_device = tables.LinkColumn()
        endpoint_count = tables.Column(empty_values=(), verbose_name="Endpoints")

        def render_endpoint_count(self, record):
            """Return endpoint count for display."""
            return record.desired_endpoints.count()

        class Meta(BaseTable.Meta):
            model = DesiredNode
            fields = (
                "name",
                "node_type",
                "accepted_actual_types",
                "lifecycle",
                "role",
                "intent_source",
                "realized_device",
                "endpoint_count",
            )
            default_columns = (
                "name",
                "node_type",
                "lifecycle",
                "role",
                "intent_source",
                "endpoint_count",
            )


    class DesiredEndpointTable(BaseTable):
        """Desired endpoint list table."""

        name = tables.LinkColumn()
        desired_node = tables.LinkColumn()
        realized_ip_address = tables.LinkColumn()

        class Meta(BaseTable.Meta):
            model = DesiredEndpoint
            fields = (
                "name",
                "desired_node",
                "endpoint_type",
                "ip_address",
                "ip_policy",
                "dns_name",
                "mac_address",
                "protocol",
                "port",
                "generate_dnsmasq",
                "dnsmasq_record_type",
                "realized_ip_address",
            )
            default_columns = (
                "name",
                "desired_node",
                "endpoint_type",
                "ip_address",
                "ip_policy",
                "dns_name",
                "mac_address",
                "protocol",
                "port",
                "generate_dnsmasq",
            )


    class DesiredComputePlatformTable(BaseTable):
        """Desired compute platform list table."""

        name = tables.LinkColumn()
        control_node = tables.LinkColumn()
        realized_cluster = tables.LinkColumn()
        instance_count = tables.Column(empty_values=(), verbose_name="Instances")

        def render_instance_count(self, record):
            return record.desired_compute_instances.count()

        class Meta(BaseTable.Meta):
            model = DesiredComputePlatform
            fields = (
                "name",
                "slug",
                "lifecycle",
                "control_node",
                "realized_cluster",
                "instance_count",
            )
            default_columns = fields


    class DesiredComputeInstanceTable(BaseTable):
        """Desired compute instance list table."""

        desired_node = tables.LinkColumn()
        platform = tables.LinkColumn()
        realized_vm = tables.LinkColumn()
        effective_lifecycle_display = tables.Column(empty_values=(), verbose_name="Effective Lifecycle")

        def render_effective_lifecycle_display(self, record):
            return effective_lifecycle(record.desired_node.lifecycle, record.platform.lifecycle)

        class Meta(BaseTable.Meta):
            model = DesiredComputeInstance
            fields = (
                "desired_node",
                "platform",
                "instance_kind",
                "desired_power_state",
                "desired_presence",
                "effective_lifecycle_display",
                "vcpus",
                "memory_mb",
                "root_disk_gb",
                "realized_vm",
            )
            default_columns = fields


    class DesiredServicePlacementTable(BaseTable):
        """Explicit desired service placement list table."""

        instance_name = tables.LinkColumn()
        desired_service = tables.LinkColumn()
        desired_node = tables.LinkColumn()
        desired_endpoint = tables.LinkColumn()

        class Meta(BaseTable.Meta):
            model = DesiredServicePlacement
            fields = (
                "desired_service",
                "instance_name",
                "desired_node",
                "desired_endpoint",
                "desired_state",
                "deployment_profile",
                "config_schema_version",
            )
            default_columns = fields


    class DesiredNodeOperationalOverrideTable(BaseTable):
        """Desired node operational override list table."""

        desired_node = tables.LinkColumn()
        declared_host_os = tables.LinkColumn()

        class Meta(BaseTable.Meta):
            model = DesiredNodeOperationalOverride
            fields = (
                "desired_node",
                "declared_host_os",
                "connection_path",
                "ansible_port",
                "power_control",
                "is_laptop",
            )
            default_columns = fields


    class BrainDumpDocumentTable(BaseTable):
        """Braindump document list table.

        Uses ``select_related("alignment_review")`` in the view queryset so review
        presence/timestamp does not add an N+1 query per row.
        """

        title = tables.LinkColumn()
        last_updated = tables.Column(verbose_name="Braindump updated")
        review = tables.Column(empty_values=(), verbose_name="Review")

        def render_review(self, record):
            """Show the review's own update time, or Unreviewed if there is none."""
            review = getattr(record, "alignment_review", None)
            if review is None:
                return "Unreviewed"
            return review.last_updated

        class Meta(BaseTable.Meta):
            model = BrainDumpDocument
            fields = (
                "title",
                "authorship",
                "status",
                "last_updated",
                "review",
            )
            default_columns = fields


    class DesiredIPRangeTable(BaseTable):
        """Desired IP range list table."""

        name = tables.LinkColumn()

        class Meta(BaseTable.Meta):
            model = DesiredIPRange
            fields = (
                "name",
                "slug",
                "start_address",
                "end_address",
                "range_policy",
                "lifecycle",
                "generate_dnsmasq",
            )
            default_columns = (
                "name",
                "start_address",
                "end_address",
                "range_policy",
                "lifecycle",
                "generate_dnsmasq",
            )
