"""Table definitions for Intent Catalog models."""

from __future__ import annotations

try:
    import django_tables2 as tables
    from django.utils.html import format_html
    from nautobot.apps.tables import BaseTable, ButtonsColumn, ToggleColumn

    from .models import (
        BrainDumpDocument,
        DesiredDependency,
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
    TABLE_ACTION_BUTTONS = ("edit", "delete")

    RECONCILIATION_BADGE_CLASSES = {
        "converged": "label-success",
        "drifting": "label-danger",
        "converging": "label-warning",
        "unknown": "label-default",
    }

    def _render_reconciliation_status(record):
        """Render reconciliation_status as a colored Bootstrap label."""

        status = record.reconciliation_status
        if not status:
            return "—"
        css_class = RECONCILIATION_BADGE_CLASSES.get(status, "label-default")
        label = record.get_reconciliation_status_display() or status
        return format_html('<span class="label {}">{}</span>', css_class, label)


    class IntentSourceTable(BaseTable):
        """Intent source list table."""

        pk = ToggleColumn()
        name = tables.LinkColumn()
        actions = ButtonsColumn(IntentSource, buttons=TABLE_ACTION_BUTTONS)

        class Meta(BaseTable.Meta):
            model = IntentSource
            fields = (
                "pk",
                "name",
                "source_type",
                "url",
                "enabled",
                "owner",
                "last_import_status",
                "last_imported_at",
                "actions",
            )
            default_columns = (
                "pk",
                "name",
                "source_type",
                "url",
                "enabled",
                "owner",
                "last_import_status",
                "last_imported_at",
                "actions",
            )
    class DesiredServiceTable(BaseTable):
        """Desired service list table."""

        pk = ToggleColumn()
        name = tables.LinkColumn()
        intent_source = tables.LinkColumn()
        dependency_count = tables.Column(empty_values=(), verbose_name="Dependencies")
        reconciliation_status = tables.Column(empty_values=(), verbose_name="Reconciliation")
        actions = ButtonsColumn(DesiredService, buttons=TABLE_ACTION_BUTTONS)

        def render_dependency_count(self, record):
            """Return dependency count for display."""

            return record.dependencies.count()

        def render_reconciliation_status(self, record):
            """Return the reconciliation status badge, nctl's derived cache of the last run."""

            return _render_reconciliation_status(record)

        class Meta(BaseTable.Meta):
            model = DesiredService
            fields = (
                "pk",
                "name",
                "display_name",
                "service_type",
                "lifecycle",
                "intent_source",
                "catalog_owner",
                "dependency_count",
                "reconciliation_status",
                "actions",
            )
            default_columns = (
                "pk",
                "name",
                "display_name",
                "service_type",
                "lifecycle",
                "intent_source",
                "catalog_owner",
                "dependency_count",
                "reconciliation_status",
                "actions",
            )


    class DesiredDependencyTable(BaseTable):
        """Desired dependency list table."""

        pk = ToggleColumn()
        source_service = tables.LinkColumn()
        resolved_service = tables.LinkColumn()
        actions = ButtonsColumn(DesiredDependency, buttons=TABLE_ACTION_BUTTONS)

        class Meta(BaseTable.Meta):
            model = DesiredDependency
            fields = (
                "pk",
                "source_service",
                "dependency_kind",
                "namespace",
                "name",
                "resolution_status",
                "resolved_service",
                "actions",
            )
            default_columns = (
                "pk",
                "source_service",
                "dependency_kind",
                "namespace",
                "name",
                "resolution_status",
                "resolved_service",
                "actions",
            )


    class DesiredNodeTable(BaseTable):
        """Desired node list table."""

        pk = ToggleColumn()
        name = tables.LinkColumn()
        intent_source = tables.LinkColumn()
        realized_device = tables.LinkColumn()
        realized_vm = tables.LinkColumn()
        endpoint_count = tables.Column(empty_values=(), verbose_name="Endpoints")
        reconciliation_status = tables.Column(empty_values=(), verbose_name="Reconciliation")
        actions = ButtonsColumn(DesiredNode, buttons=TABLE_ACTION_BUTTONS)

        def render_endpoint_count(self, record):
            """Return endpoint count for display."""

            return record.desired_endpoints.count()

        def render_reconciliation_status(self, record):
            """Return the reconciliation status badge, nctl's derived cache of the last run."""

            return _render_reconciliation_status(record)

        class Meta(BaseTable.Meta):
            model = DesiredNode
            fields = (
                "pk",
                "name",
                "node_type",
                "accepted_actual_types",
                "lifecycle",
                "role",
                "intent_source",
                "realized_device",
                "realized_vm",
                "endpoint_count",
                "reconciliation_status",
                "actions",
            )
            default_columns = (
                "pk",
                "name",
                "node_type",
                "lifecycle",
                "role",
                "intent_source",
                "endpoint_count",
                "reconciliation_status",
                "actions",
            )


    class DesiredEndpointTable(BaseTable):
        """Desired endpoint list table."""

        pk = ToggleColumn()
        name = tables.LinkColumn()
        desired_node = tables.LinkColumn()
        realized_ip_address = tables.LinkColumn()
        actions = ButtonsColumn(DesiredEndpoint, buttons=TABLE_ACTION_BUTTONS)

        class Meta(BaseTable.Meta):
            model = DesiredEndpoint
            fields = (
                "pk",
                "name",
                "desired_node",
                "endpoint_type",
                "ip_address",
                "ip_policy",
                "dns_name",
                "protocol",
                "port",
                "generate_dnsmasq",
                "dnsmasq_record_type",
                "realized_ip_address",
                "actions",
            )
            default_columns = (
                "pk",
                "name",
                "desired_node",
                "endpoint_type",
                "ip_address",
                "ip_policy",
                "dns_name",
                "protocol",
                "port",
                "generate_dnsmasq",
                "actions",
            )


    class DesiredServicePlacementTable(BaseTable):
        """Explicit desired service placement list table."""

        pk = ToggleColumn()
        instance_name = tables.LinkColumn()
        desired_service = tables.LinkColumn()
        desired_node = tables.LinkColumn()
        desired_endpoint = tables.LinkColumn()
        actions = ButtonsColumn(DesiredServicePlacement, buttons=TABLE_ACTION_BUTTONS)

        class Meta(BaseTable.Meta):
            model = DesiredServicePlacement
            fields = (
                "pk",
                "desired_service",
                "instance_name",
                "desired_node",
                "desired_endpoint",
                "desired_state",
                "instance_role",
                "deployment_profile",
                "config_schema_version",
                "assignment_source",
                "actions",
            )
            default_columns = fields


    class DesiredNodeOperationalOverrideTable(BaseTable):
        """Desired node operational override list table."""

        pk = ToggleColumn()
        desired_node = tables.LinkColumn()
        declared_host_os = tables.LinkColumn()
        actions = ButtonsColumn(DesiredNodeOperationalOverride, buttons=TABLE_ACTION_BUTTONS)

        class Meta(BaseTable.Meta):
            model = DesiredNodeOperationalOverride
            fields = (
                "pk",
                "desired_node",
                "declared_host_os",
                "connection_path",
                "ansible_port",
                "power_control",
                "is_laptop",
                "actions",
            )
            default_columns = fields


    class BrainDumpDocumentTable(BaseTable):
        """Braindump document list table.

        Uses ``select_related("alignment_review")`` in the view queryset so review
        presence/timestamp does not add an N+1 query per row.
        """

        pk = ToggleColumn()
        title = tables.LinkColumn()
        last_updated = tables.Column(verbose_name="Braindump updated")
        review = tables.Column(empty_values=(), verbose_name="Review")
        actions = ButtonsColumn(BrainDumpDocument, buttons=TABLE_ACTION_BUTTONS)

        def render_review(self, record):
            """Show the review's own update time, or Unreviewed if there is none."""

            review = getattr(record, "alignment_review", None)
            if review is None:
                return "Unreviewed"
            return review.last_updated

        class Meta(BaseTable.Meta):
            model = BrainDumpDocument
            fields = (
                "pk",
                "title",
                "authorship",
                "last_updated",
                "review",
                "actions",
            )
            default_columns = fields


    class DesiredIPRangeTable(BaseTable):
        """Desired IP range list table."""

        pk = ToggleColumn()
        name = tables.LinkColumn()
        actions = ButtonsColumn(DesiredIPRange, buttons=TABLE_ACTION_BUTTONS)

        class Meta(BaseTable.Meta):
            model = DesiredIPRange
            fields = (
                "pk",
                "name",
                "slug",
                "start_address",
                "end_address",
                "range_policy",
                "lifecycle",
                "generate_dnsmasq",
                "actions",
            )
            default_columns = (
                "pk",
                "name",
                "start_address",
                "end_address",
                "range_policy",
                "lifecycle",
                "generate_dnsmasq",
                "actions",
            )
