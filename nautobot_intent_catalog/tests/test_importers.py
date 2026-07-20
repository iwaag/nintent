from __future__ import annotations

from types import SimpleNamespace
import unittest

from nautobot_intent_catalog.importers import (
    dependency_key,
    desired_endpoint_defaults,
    desired_endpoint_identity,
    desired_ip_range_defaults,
    desired_ip_range_identity,
    desired_node_defaults,
    desired_node_identity,
    desired_node_operational_override_defaults,
    desired_node_operational_override_identity,
    desired_service_defaults,
    desired_service_dependencies,
    desired_service_entry_defaults,
    desired_service_entry_identity,
    desired_service_identity,
    desired_service_placement_defaults,
    desired_service_placement_identity,
    intent_source_defaults,
)
from nautobot_intent_catalog.loaders import (
    DesiredEndpointEntry,
    DesiredIPRangeEntry,
    DesiredNodeEntry,
    DesiredNodeOperationalOverrideEntry,
    DesiredServiceEntry,
    DesiredServicePlacementEntry,
    IntentSourceEntry,
)


class ImporterTests(unittest.TestCase):
    def test_intent_source_defaults_normalize_loader_fields(self) -> None:
        source = IntentSourceEntry(
            url="https://github.com/example/service",
            enabled=False,
            ref="main",
            owner="platform",
            service_hint="service",
            catalog_paths=["catalog-info.yaml"],
            basic_file_paths=["README.md"],
            raw_url_template="https://example.test/{ref}/{path}",
        )

        self.assertEqual(
            intent_source_defaults(source),
            {
                "name": "service",
                "slug": "service",
                "source_type": "git_repository",
                "enabled": False,
                "ref": "main",
                "owner": "platform",
                "description": None,
                "source_config": {
                    "service_hint": "service",
                    "catalog_paths": ["catalog-info.yaml"],
                    "basic_file_paths": ["README.md"],
                    "catalog_paths_defaulted": False,
                    "basic_file_paths_defaulted": False,
                    "raw_url_template": "https://example.test/{ref}/{path}",
                },
            },
        )

    def test_desired_service_identity_and_defaults_use_catalog_shape(self) -> None:
        service = {
            "name": "storage-service",
            "display_name": "Storage Service",
            "role": "service",
            "prefers_gpu": False,
            "intent_source": {
                "url": "https://github.com/example/storage",
                "ref": "main",
                "catalog_path": "catalog-info.yaml",
            },
            "catalog": {
                "kind": "Component",
                "namespace": "default",
                "metadata_name": "storage",
                "spec_type": "service",
                "owner": "platform",
                "lifecycle": "production",
            },
            "analysis": {
                "status": "catalog_derived",
                "confidence": "medium",
                "reasons": ["backstage_component_catalog_found"],
            },
        }

        self.assertEqual(
            desired_service_identity(service),
            {
                "catalog_namespace": "default",
                "catalog_metadata_name": "storage",
                "service_type": "service",
            },
        )
        defaults = desired_service_defaults(service)
        self.assertEqual(defaults["name"], "storage-service")
        self.assertEqual(defaults["slug"], "storage-service")
        self.assertEqual(defaults["source_ref"], "main")
        self.assertEqual(defaults["catalog_owner"], "platform")
        self.assertEqual(defaults["requirements"]["analysis_reasons"], ["backstage_component_catalog_found"])

    def test_desired_service_dependencies_drop_malformed_rows(self) -> None:
        service = {
            "dependencies": [
                {
                    "raw_ref": "resource:default/postgresql",
                    "kind": "resource",
                    "namespace": "default",
                    "name": "postgresql",
                    "dependency_type": "resource",
                    "resolution_status": "unresolved",
                },
                {"raw_ref": "", "kind": "", "namespace": "default", "name": ""},
            ]
        }

        dependencies = desired_service_dependencies(service)

        self.assertEqual(len(dependencies), 1)
        self.assertEqual(dependency_key(dependencies[0]), ("resource", "default", "postgresql"))

    def test_desired_node_identity_and_defaults(self) -> None:
        node = DesiredNodeEntry(
            name="Edge Router 1",
            slug="edge-router-1",
            node_type="virtual_machine",
            accepted_actual_types=["virtual_machine"],
            lifecycle="approved",
            role="edge",
            expected_spec={"cpu": 2},
            notes="planned replacement",
        )

        self.assertEqual(desired_node_identity(node), {"slug": "edge-router-1"})
        self.assertEqual(
            desired_node_defaults(node, intent_source_id="source-id"),
            {
                "name": "Edge Router 1",
                "node_type": "virtual_machine",
                "accepted_actual_types": ["virtual_machine"],
                "lifecycle": "approved",
                "role": "edge",
                "description": None,
                "expected_spec": {"cpu": 2},
                "notes": "planned replacement",
                "intent_source_id": "source-id",
            },
        )

    def test_desired_endpoint_identity_and_defaults(self) -> None:
        endpoint = DesiredEndpointEntry(
            name="mgmt",
            desired_node="edge-router-1",
            endpoint_type="management",
            ip_address="192.0.2.10/32",
            ip_policy="dhcp_reserved",
            dns_name="edge-router-1.example.test",
            protocol="https",
            port=443,
            generate_dnsmasq=True,
        )

        self.assertEqual(
            desired_endpoint_identity(endpoint, desired_node_id="node-id"),
            {
                "desired_node_id": "node-id",
                "name": "mgmt",
                "endpoint_type": "management",
            },
        )
        self.assertEqual(
            desired_endpoint_defaults(endpoint),
            {
                "ip_address": "192.0.2.10/32",
                "dns_name": "edge-router-1.example.test",
                "dns_name_source": "intent",
                "mdns_name": None,
                "mdns_name_source": None,
                "vpn_dns_name": None,
                "protocol": "https",
                "port": 443,
                "generate_dnsmasq": True,
                "ip_policy": "dhcp_reserved",
                "dnsmasq_record_type": "host_record",
                "description": None,
            },
        )

    def test_desired_endpoint_defaults_reject_missing_ip_policy_for_ip_intent(self) -> None:
        endpoint = DesiredEndpointEntry(
            name="mgmt",
            desired_node="edge-router-1",
            endpoint_type="management",
            ip_address="192.0.2.10/32",
        )

        with self.assertRaisesRegex(ValueError, "requires ip_policy"):
            desired_endpoint_defaults(endpoint)

    def test_primary_desired_endpoint_defaults_missing_names_from_resolved_node(self) -> None:
        # ip_policy="external" here mirrors what loaders._parse_desired_endpoint already
        # resolves for a no-address entry before it reaches desired_endpoint_defaults;
        # the importer is a pure projection and no longer supplies a second fallback.
        endpoint = DesiredEndpointEntry(
            name="primary",
            desired_node="pc1",
            endpoint_type="primary",
            ip_policy="external",
            dns_name=None,
            mdns_name=" ",
        )
        desired_node = SimpleNamespace(name="PC1.local")

        self.assertEqual(
            desired_endpoint_defaults(endpoint, desired_node=desired_node),
            {
                "ip_address": None,
                "dns_name": "pc1.home.arpa",
                "dns_name_source": "derived",
                "mdns_name": "pc1.local",
                "mdns_name_source": "derived",
                "vpn_dns_name": None,
                "protocol": None,
                "port": None,
                "generate_dnsmasq": False,
                "ip_policy": "external",
                "dnsmasq_record_type": "host_record",
                "description": None,
            },
        )

    def test_primary_desired_endpoint_defaults_preserve_explicit_names(self) -> None:
        endpoint = DesiredEndpointEntry(
            name="primary",
            desired_node="pc1",
            endpoint_type="primary",
            dns_name="custom.example.test",
            mdns_name="custom.local",
        )
        desired_node = SimpleNamespace(name="PC1.local")

        defaults = desired_endpoint_defaults(endpoint, desired_node=desired_node)

        self.assertEqual(defaults["dns_name"], "custom.example.test")
        self.assertEqual(defaults["mdns_name"], "custom.local")

    def test_non_primary_desired_endpoint_defaults_do_not_auto_fill_names(self) -> None:
        endpoint = DesiredEndpointEntry(
            name="mgmt",
            desired_node="pc1",
            endpoint_type="management",
        )
        desired_node = SimpleNamespace(name="PC1.local")

        defaults = desired_endpoint_defaults(endpoint, desired_node=desired_node)

        self.assertIsNone(defaults["dns_name"])
        self.assertIsNone(defaults["mdns_name"])

    def test_desired_ip_range_identity_and_defaults(self) -> None:
        ip_range = DesiredIPRangeEntry(
            name="home-dynamic-dhcp",
            slug="home-dynamic-dhcp",
            start_address="192.168.0.200",
            end_address="192.168.0.250",
            range_policy="dhcp_dynamic_pool",
            lifecycle="active",
            generate_dnsmasq=True,
            dnsmasq_options={"lease_time": "12h"},
            description="Home DHCP dynamic pool",
        )

        self.assertEqual(desired_ip_range_identity(ip_range), {"slug": "home-dynamic-dhcp"})
        self.assertEqual(
            desired_ip_range_defaults(ip_range),
            {
                "name": "home-dynamic-dhcp",
                "start_address": "192.168.0.200",
                "end_address": "192.168.0.250",
                "range_policy": "dhcp_dynamic_pool",
                "lifecycle": "active",
                "generate_dnsmasq": True,
                "dnsmasq_options": {"lease_time": "12h"},
                "description": "Home DHCP dynamic pool",
            },
        )

    def test_placement_identity_and_defaults_are_separate_from_service_analysis(self) -> None:
        placement = DesiredServicePlacementEntry(
            desired_service={
                "intent_source": "infrastructure",
                "catalog_namespace": "default",
                "catalog_metadata_name": "dnsmasq",
                "service_type": "service",
            },
            instance_name="primary",
            desired_node="agdns01",
            desired_endpoint={"name": "primary", "endpoint_type": "primary"},
            desired_state="active",
            instance_role="primary",
            deployment_profile="dnsmasq",
            config_schema_version="1",
            config={"dhcp_authoritative": True},
            assignment_source="yaml",
            reason="primary DNS",
        )

        self.assertEqual(
            desired_service_placement_identity(placement, "service-id"),
            {"desired_service_id": "service-id", "instance_name": "primary"},
        )
        self.assertEqual(
            desired_service_placement_defaults(placement, "node-id", "endpoint-id"),
            {
                "desired_node_id": "node-id",
                "desired_endpoint_id": "endpoint-id",
                "desired_state": "active",
                "instance_role": "primary",
                "deployment_profile": "dnsmasq",
                "config_schema_version": "1",
                "config": {"dhcp_authoritative": True},
                "assignment_source": "yaml",
                "reason": "primary DNS",
            },
        )
        self.assertNotIn("placements", desired_service_defaults({"name": "dnsmasq"}))

    def test_operational_override_identity_and_defaults(self) -> None:
        operational = DesiredNodeOperationalOverrideEntry(
            desired_node="agmac01",
            declared_host_os=None,
            connection_path="local",
            local_endpoint=None,
            tailscale_endpoint=None,
            ansible_port=22,
            power_control="macos_sleep",
            is_laptop=True,
        )

        self.assertEqual(
            desired_node_operational_override_identity(operational, "node-id"),
            {"desired_node_id": "node-id"},
        )
        self.assertEqual(
            desired_node_operational_override_defaults(operational, None, None),
            {
                "declared_host_os": None,
                "connection_path": "local",
                "local_endpoint_id": None,
                "tailscale_endpoint_id": None,
                "ansible_port": 22,
                "power_control": "macos_sleep",
                "is_laptop": True,
            },
        )

    def test_intent_source_defaults_for_manual_source(self) -> None:
        source = IntentSourceEntry(
            slug="infrastructure",
            name="Infrastructure",
            source_type="manual",
            enabled=True,
        )

        defaults = intent_source_defaults(source)

        self.assertEqual(defaults["slug"], "infrastructure")
        self.assertEqual(defaults["name"], "Infrastructure")
        self.assertEqual(defaults["source_type"], "manual")
        self.assertNotIn("url", defaults)

    def test_desired_service_entry_identity_and_defaults(self) -> None:
        entry = DesiredServiceEntry(
            intent_source="infrastructure",
            catalog_metadata_name="prometheus",
            service_type="service",
            name="prometheus",
            slug="prometheus",
            display_name="Prometheus",
            catalog_namespace="default",
            lifecycle="active",
            catalog_owner="platform",
            min_memory_gb=2.0,
            notes="fixed service",
        )

        self.assertEqual(
            desired_service_entry_identity(entry, "source-id"),
            {
                "intent_source_id": "source-id",
                "catalog_namespace": "default",
                "catalog_metadata_name": "prometheus",
                "service_type": "service",
            },
        )
        self.assertEqual(
            desired_service_entry_defaults(entry),
            {
                "name": "prometheus",
                "slug": "prometheus",
                "display_name": "Prometheus",
                "lifecycle": "active",
                "source_ref": None,
                "source_catalog_path": None,
                "catalog_kind": None,
                "catalog_owner": "platform",
                "catalog_lifecycle": None,
                "prefers_gpu": False,
                "min_memory_gb": 2.0,
                "requirements": {},
                "notes": "fixed service",
            },
        )

    def test_intent_source_defaults_manual_falls_back_to_slug_name(self) -> None:
        source = IntentSourceEntry(slug="infrastructure", source_type="manual")

        defaults = intent_source_defaults(source)

        self.assertEqual(defaults["slug"], "infrastructure")
        self.assertEqual(defaults["name"], "infrastructure")
        self.assertEqual(defaults["source_type"], "manual")


if __name__ == "__main__":
    unittest.main()
