"""Views for the Nautobot Intent Catalog App."""

try:
    from nautobot.apps.views import ObjectListView, ObjectView

    from .filters import (
        BrainDumpDocumentFilterSet,
        DesiredComputeInstanceFilterSet,
        DesiredComputePlatformFilterSet,
        DesiredDependencyFilterSet,
        DesiredEndpointFilterSet,
        DesiredIPRangeFilterSet,
        DesiredNodeFilterSet,
        DesiredNodeOperationalOverrideFilterSet,
        DesiredServiceFilterSet,
        DesiredServicePlacementFilterSet,
        IntentSourceFilterSet,
    )
    from .models import (
        BrainDumpDocument,
        DesiredComputeInstance,
        DesiredComputePlatform,
        DesiredDependency,
        DesiredEndpoint,
        DesiredIPRange,
        DesiredNode,
        DesiredNodeOperationalOverride,
        DesiredService,
        DesiredServicePlacement,
        IntentSource,
    )
    from .tables import (
        BrainDumpDocumentTable,
        DesiredComputeInstanceTable,
        DesiredComputePlatformTable,
        DesiredDependencyTable,
        DesiredEndpointTable,
        DesiredIPRangeTable,
        DesiredNodeTable,
        DesiredNodeOperationalOverrideTable,
        DesiredServiceTable,
        DesiredServicePlacementTable,
        IntentSourceTable,
    )
except ImportError:  # pragma: no cover - Nautobot is unavailable in local unit tests.
    pass
else:

    class IntentSourceListView(ObjectListView):
        """List DB-backed intent source records."""

        queryset = IntentSource.objects.all()
        filterset = IntentSourceFilterSet
        table = IntentSourceTable


    class IntentSourceView(ObjectView):
        """Show one intent source record."""

        queryset = IntentSource.objects.all()


    class DesiredServiceListView(ObjectListView):
        """List desired service records."""

        queryset = DesiredService.objects.select_related("intent_source")
        filterset = DesiredServiceFilterSet
        table = DesiredServiceTable


    class DesiredServiceView(ObjectView):
        """Show one desired service record."""

        queryset = DesiredService.objects.select_related("intent_source")


    class DesiredDependencyListView(ObjectListView):
        """List desired dependency records."""

        queryset = DesiredDependency.objects.select_related("source_service", "resolved_service")
        filterset = DesiredDependencyFilterSet
        table = DesiredDependencyTable


    class DesiredDependencyView(ObjectView):
        """Show one desired dependency record."""

        queryset = DesiredDependency.objects.select_related("source_service", "resolved_service")


    class DesiredNodeListView(ObjectListView):
        """List desired node records."""

        queryset = DesiredNode.objects.select_related("realized_device")
        filterset = DesiredNodeFilterSet
        table = DesiredNodeTable


    class DesiredNodeView(ObjectView):
        """Show one desired node record."""

        queryset = DesiredNode.objects.select_related(
            "realized_device"
        ).prefetch_related("controlled_compute_platforms", "desired_compute_instance")


    class DesiredEndpointListView(ObjectListView):
        """List desired endpoint records."""

        queryset = DesiredEndpoint.objects.select_related("desired_node", "realized_ip_address")
        filterset = DesiredEndpointFilterSet
        table = DesiredEndpointTable


    class DesiredEndpointView(ObjectView):
        """Show one desired endpoint record."""

        queryset = DesiredEndpoint.objects.select_related("desired_node", "realized_ip_address")


    class DesiredComputePlatformListView(ObjectListView):
        """List desired compute platform records."""

        queryset = DesiredComputePlatform.objects.select_related("control_node", "realized_cluster")
        filterset = DesiredComputePlatformFilterSet
        table = DesiredComputePlatformTable


    class DesiredComputePlatformView(ObjectView):
        """Show one desired compute platform record."""

        queryset = DesiredComputePlatform.objects.select_related(
            "control_node", "realized_cluster"
        ).prefetch_related("desired_compute_instances")


    class DesiredComputeInstanceListView(ObjectListView):
        """List desired compute instance records."""

        queryset = DesiredComputeInstance.objects.select_related("desired_node", "platform", "realized_vm")
        filterset = DesiredComputeInstanceFilterSet
        table = DesiredComputeInstanceTable


    class DesiredComputeInstanceView(ObjectView):
        """Show one desired compute instance record."""

        queryset = DesiredComputeInstance.objects.select_related("desired_node", "platform", "realized_vm")

        def get_extra_context(self, request, instance):
            from .compute_contract import effective_lifecycle
            from .models import _resolve_compute_effective_value

            return {
                "effective_lifecycle": effective_lifecycle(
                    instance.desired_node.lifecycle, instance.platform.lifecycle
                ),
                "effective_storage": _resolve_compute_effective_value(
                    instance, instance_key="storage", platform_key="default_storage"
                ),
                "effective_bridge": _resolve_compute_effective_value(
                    instance, instance_key="bridge", platform_key="default_bridge"
                ),
            }


    class DesiredServicePlacementListView(ObjectListView):
        """List explicit desired service placements."""

        queryset = DesiredServicePlacement.objects.select_related(
            "desired_service",
            "desired_node",
            "desired_endpoint",
        )
        filterset = DesiredServicePlacementFilterSet
        table = DesiredServicePlacementTable


    class DesiredServicePlacementView(ObjectView):
        """Show one explicit desired service placement."""

        queryset = DesiredServicePlacement.objects.select_related(
            "desired_service",
            "desired_node",
            "desired_endpoint",
        )


    class DesiredNodeOperationalOverrideListView(ObjectListView):
        """List desired node operational overrides."""

        queryset = DesiredNodeOperationalOverride.objects.select_related(
            "desired_node",
            "local_endpoint",
            "tailscale_endpoint",
        )
        filterset = DesiredNodeOperationalOverrideFilterSet
        table = DesiredNodeOperationalOverrideTable


    class DesiredNodeOperationalOverrideView(ObjectView):
        """Show one desired node operational override."""

        queryset = DesiredNodeOperationalOverride.objects.select_related(
            "desired_node",
            "local_endpoint",
            "tailscale_endpoint",
        )


    class DesiredIPRangeListView(ObjectListView):
        """List desired IP range records."""

        queryset = DesiredIPRange.objects.all()
        filterset = DesiredIPRangeFilterSet
        table = DesiredIPRangeTable


    class DesiredIPRangeView(ObjectView):
        """Show one desired IP range record."""

        queryset = DesiredIPRange.objects.all()


    class BrainDumpDocumentListView(ObjectListView):
        """List Braindump documents.

        ``select_related("alignment_review")`` avoids one query per row for the
        table's review-presence column.
        """

        queryset = BrainDumpDocument.objects.select_related("alignment_review")
        filterset = BrainDumpDocumentFilterSet
        table = BrainDumpDocumentTable


    class BrainDumpDocumentView(ObjectView):
        """Show one Braindump and its current Alignment Review, in separate panels."""

        queryset = BrainDumpDocument.objects.select_related("alignment_review")
