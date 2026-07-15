"""Filter sets for Intent Catalog models."""

from __future__ import annotations

try:
    import django_filters
    from nautobot.apps.filters import NautobotFilterSet

    from .models import (
        DesiredDependency,
        DesiredEndpoint,
        DesiredIPRange,
        DesiredNode,
        DesiredNodeOperationalConfig,
        DesiredService,
        DesiredServicePlacement,
        IntentSource,
    )
except ImportError:  # pragma: no cover - Nautobot/Django are unavailable in local unit tests.
    pass
else:

    class IntentSourceFilterSet(NautobotFilterSet):
        """Filters for intent sources."""

        q = django_filters.CharFilter(method="search", label="Search")

        class Meta:
            model = IntentSource
            fields = ("id", "name", "slug", "source_type", "url", "enabled", "owner", "last_import_status")

        def search(self, queryset, name, value):
            if not value.strip():
                return queryset
            return (
                queryset.filter(name__icontains=value)
                | queryset.filter(slug__icontains=value)
                | queryset.filter(url__icontains=value)
            )


    class DesiredServiceFilterSet(NautobotFilterSet):
        """Filters for desired services."""

        q = django_filters.CharFilter(method="search", label="Search")

        class Meta:
            model = DesiredService
            fields = (
                "id",
                "name",
                "slug",
                "service_type",
                "lifecycle",
                "intent_source",
                "catalog_owner",
            )

        def search(self, queryset, name, value):
            if not value.strip():
                return queryset
            return queryset.filter(name__icontains=value) | queryset.filter(display_name__icontains=value)


    class DesiredDependencyFilterSet(NautobotFilterSet):
        """Filters for desired dependencies."""

        q = django_filters.CharFilter(method="search", label="Search")

        class Meta:
            model = DesiredDependency
            fields = (
                "id",
                "source_service",
                "dependency_kind",
                "namespace",
                "name",
                "dependency_type",
                "resolution_status",
                "resolved_service",
            )

        def search(self, queryset, name, value):
            if not value.strip():
                return queryset
            return queryset.filter(name__icontains=value) | queryset.filter(raw_ref__icontains=value)


    class DesiredNodeFilterSet(NautobotFilterSet):
        """Filters for desired nodes."""

        q = django_filters.CharFilter(method="search", label="Search")

        class Meta:
            model = DesiredNode
            fields = (
                "id",
                "name",
                "slug",
                "node_type",
                "lifecycle",
                "role",
                "intent_source",
                "realized_device",
                "realized_vm",
            )

        def search(self, queryset, name, value):
            if not value.strip():
                return queryset
            return queryset.filter(name__icontains=value) | queryset.filter(slug__icontains=value)


    class DesiredEndpointFilterSet(NautobotFilterSet):
        """Filters for desired endpoints."""

        q = django_filters.CharFilter(method="search", label="Search")

        class Meta:
            model = DesiredEndpoint
            fields = (
                "id",
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
            )

        def search(self, queryset, name, value):
            if not value.strip():
                return queryset
            return (
                queryset.filter(name__icontains=value)
                | queryset.filter(ip_address__icontains=value)
                | queryset.filter(dns_name__icontains=value)
                | queryset.filter(mdns_name__icontains=value)
                | queryset.filter(vpn_dns_name__icontains=value)
            )


    class DesiredServicePlacementFilterSet(NautobotFilterSet):
        """Filters for explicit desired service placements."""

        q = django_filters.CharFilter(method="search", label="Search")

        class Meta:
            model = DesiredServicePlacement
            fields = (
                "id",
                "desired_service",
                "desired_node",
                "desired_endpoint",
                "instance_name",
                "desired_state",
                "instance_role",
                "deployment_profile",
                "config_schema_version",
                "assignment_source",
            )

        def search(self, queryset, name, value):
            if not value.strip():
                return queryset
            return (
                queryset.filter(instance_name__icontains=value)
                | queryset.filter(instance_role__icontains=value)
                | queryset.filter(deployment_profile__icontains=value)
            )


    class DesiredNodeOperationalConfigFilterSet(NautobotFilterSet):
        """Filters for desired node execution policy."""

        q = django_filters.CharFilter(method="search", label="Search")

        class Meta:
            model = DesiredNodeOperationalConfig
            fields = (
                "id",
                "desired_node",
                "actual_state_policy",
                "expected_host_os",
                "declared_host_os",
                "connection_path",
                "local_endpoint",
                "tailscale_endpoint",
                "ansible_port",
                "power_control",
                "is_laptop",
            )

        def search(self, queryset, name, value):
            if not value.strip():
                return queryset
            return queryset.filter(desired_node__name__icontains=value) | queryset.filter(
                desired_node__slug__icontains=value
            )

    class DesiredIPRangeFilterSet(NautobotFilterSet):
        """Filters for desired IP ranges."""

        q = django_filters.CharFilter(method="search", label="Search")

        class Meta:
            model = DesiredIPRange
            fields = (
                "id",
                "name",
                "slug",
                "start_address",
                "end_address",
                "range_policy",
                "lifecycle",
                "generate_dnsmasq",
            )

        def search(self, queryset, name, value):
            if not value.strip():
                return queryset
            return (
                queryset.filter(name__icontains=value)
                | queryset.filter(slug__icontains=value)
                | queryset.filter(start_address__icontains=value)
                | queryset.filter(end_address__icontains=value)
            )
