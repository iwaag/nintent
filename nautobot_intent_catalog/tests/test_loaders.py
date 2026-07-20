from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nautobot_intent_catalog.loaders import (
    DEFAULT_BASIC_FILE_PATHS,
    DEFAULT_CATALOG_PATHS,
    load_intent_sources,
)


class LoaderTests(unittest.TestCase):
    def test_loader_applies_analysis_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "intent_sources:\n"
                "  - url: https://github.com/example/service\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.intent_sources), 1)
        intent_source = result.intent_sources[0]
        self.assertEqual(intent_source.catalog_paths, list(DEFAULT_CATALOG_PATHS))
        self.assertEqual(intent_source.basic_file_paths, list(DEFAULT_BASIC_FILE_PATHS))
        self.assertTrue(intent_source.catalog_paths_defaulted)
        self.assertTrue(intent_source.basic_file_paths_defaulted)

    def test_loader_preserves_explicit_empty_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "intent_sources:\n"
                "  - url: https://github.com/example/service\n"
                "    catalog_paths: []\n"
                "    basic_file_paths: []\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        intent_source = result.intent_sources[0]
        self.assertEqual(intent_source.catalog_paths, [])
        self.assertEqual(intent_source.basic_file_paths, [])
        self.assertFalse(intent_source.catalog_paths_defaulted)
        self.assertFalse(intent_source.basic_file_paths_defaulted)

    def test_loader_does_not_accept_old_service_repositories_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "service_repositories:\n"
                "  - url: https://github.com/example/service\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(
            result.errors,
            ["service_repositories is not supported; rename the top-level key to intent_sources."],
        )
        self.assertEqual(result.intent_sources, [])

    def test_loader_normalizes_desired_nodes_and_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_nodes:\n"
                "  - name: Edge Router 1\n"
                "    node_type: virtual-machine\n"
                "    lifecycle: approved\n"
                "    role: edge\n"
                "    expected_spec:\n"
                "      cpu: 2\n"
                "desired_endpoints:\n"
                "  - name: mgmt\n"
                "    desired_node: edge-router-1\n"
                "    endpoint_type: management\n"
                "    ip_address: 192.0.2.10/32\n"
                "    ip_policy: dhcp_reserved\n"
                "    dns_name: edge-router-1.example.test\n"
                "    protocol: https\n"
                "    port: 443\n"
                "    generate_dnsmasq: true\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.desired_nodes), 1)
        self.assertEqual(result.desired_nodes[0].slug, "edge-router-1")
        self.assertEqual(result.desired_nodes[0].node_type, "virtual_machine")
        self.assertEqual(result.desired_nodes[0].accepted_actual_types, ["virtual_machine"])
        self.assertEqual(result.desired_nodes[0].expected_spec, {"cpu": 2})
        self.assertEqual(len(result.desired_endpoints), 1)
        self.assertEqual(result.desired_endpoints[0].desired_node, "edge-router-1")
        self.assertEqual(result.desired_endpoints[0].port, 443)
        self.assertTrue(result.desired_endpoints[0].generate_dnsmasq)
        self.assertEqual(result.desired_endpoints[0].ip_policy, "dhcp_reserved")

    def test_loader_reads_desired_node_accepted_actual_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_nodes:\n"
                "  - name: dnsmasq-main\n"
                "    node_type: service_host\n"
                "    accepted_actual_types:\n"
                "      - device\n"
                "      - virtual-machine\n"
                "      - device\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.desired_nodes[0].accepted_actual_types, ["device", "virtual_machine"])

    def test_loader_defaults_service_host_accepted_actual_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_nodes:\n"
                "  - name: dnsmasq-main\n"
                "    node_type: service_host\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.desired_nodes[0].accepted_actual_types, ["device", "virtual_machine", "container"])
        self.assertEqual(result.desired_nodes[0].lifecycle, "active")

    def test_loader_preserves_explicit_planned_desired_node_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_nodes:\n"
                "  - name: staged-node\n"
                "    node_type: device\n"
                "    lifecycle: planned\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.desired_nodes[0].lifecycle, "planned")

    def test_loader_reports_invalid_desired_node_actual_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_nodes:\n"
                "  - name: dnsmasq-main\n"
                "    accepted_actual_types:\n"
                "      - appliance\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(
            result.errors,
            ["desired_nodes entry 1 accepted_actual_types must be one of: container, device, virtual_machine."],
        )

    def test_loader_reports_invalid_desired_node_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_nodes:\n"
                "  - name: dnsmasq-main\n"
                "    node_type: network\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(
            result.errors,
            ["desired_nodes entry 1 node_type must be one of: container, device, service_host, virtual_machine."],
        )

    def test_loader_normalizes_desired_ip_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_ip_ranges:\n"
                "  - name: home-dynamic-dhcp\n"
                "    slug: home-dynamic-dhcp\n"
                "    start_address: 192.168.0.200\n"
                "    end_address: 192.168.0.250\n"
                "    range_policy: dhcp-dynamic-pool\n"
                "    lifecycle: active\n"
                "    generate_dnsmasq: true\n"
                "    dnsmasq_options:\n"
                "      lease_time: 12h\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.desired_ip_ranges), 1)
        ip_range = result.desired_ip_ranges[0]
        self.assertEqual(ip_range.slug, "home-dynamic-dhcp")
        self.assertEqual(ip_range.range_policy, "dhcp_dynamic_pool")
        self.assertEqual(ip_range.lifecycle, "active")
        self.assertTrue(ip_range.generate_dnsmasq)
        self.assertEqual(ip_range.dnsmasq_options, {"lease_time": "12h"})

    def test_loader_requires_endpoint_ip_policy_for_ip_intent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_nodes:\n"
                "  - name: Edge Router 1\n"
                "    slug: edge-router-1\n"
                "desired_endpoints:\n"
                "  - name: mgmt\n"
                "    desired_node: edge-router-1\n"
                "    ip_address: 192.0.2.10/32\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(
            result.errors,
            ["desired_endpoints entry 1 is missing required field: ip_policy."],
        )

    def test_loader_reports_invalid_desired_ip_range(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_ip_ranges:\n"
                "  - name: bad-range\n"
                "    slug: bad-range\n"
                "    start_address: not-an-ip\n"
                "    end_address: 192.168.0.250\n"
                "    range_policy: dynamic\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(
            result.errors,
            [
                "desired_ip_ranges entry 1 range_policy must be one of: dhcp_dynamic_pool, dhcp_reservable_pool, excluded, static_pool.",
                "desired_ip_ranges entry 1 start_address must be a valid IP address.",
            ],
        )

    def test_loader_defers_endpoint_database_reference_to_importer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_endpoints:\n"
                "  - name: mgmt\n"
                "    desired_node: missing-node\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.desired_endpoints[0].desired_node, "missing-node")

    def test_loader_normalizes_placement_and_operational_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_service_placements:\n"
                "  - desired_service:\n"
                "      intent_source: infrastructure\n"
                "      catalog_namespace: default\n"
                "      catalog_metadata_name: dnsmasq\n"
                "      service_type: service\n"
                "    instance_name: primary\n"
                "    desired_node: agdns01\n"
                "    desired_endpoint:\n"
                "      name: primary\n"
                "      endpoint_type: primary\n"
                "    desired_state: active\n"
                "    instance_role: primary\n"
                "    deployment_profile: dnsmasq\n"
                "    config_schema_version: '1'\n"
                "    assignment_source: yaml\n"
                "    config:\n"
                "      dhcp_authoritative: true\n"
                "desired_node_operational_overrides:\n"
                "  - desired_node: agdns01\n"
                "    connection_path: tailscale\n"
                "    tailscale_endpoint:\n"
                "      name: vpn\n"
                "      endpoint_type: vpn\n"
                "    ansible_port: 22\n"
                "    power_control: wol\n"
                "    is_laptop: false\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        placement = result.desired_service_placements[0]
        self.assertEqual(placement.desired_service["intent_source"], "infrastructure")
        self.assertEqual(placement.desired_endpoint, {"name": "primary", "endpoint_type": "primary"})
        self.assertEqual(placement.config, {"dhcp_authoritative": True})
        operational = result.desired_node_operational_overrides[0]
        self.assertEqual(operational.tailscale_endpoint, {"name": "vpn", "endpoint_type": "vpn"})

    def test_loader_rejects_unqualified_and_unknown_placement_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_service_placements:\n"
                "  - desired_service: dnsmasq\n"
                "    instance_name: primary\n"
                "    desired_node: agdns01\n"
                "    desired_state: active\n"
                "    deployment_profile: dnsmasq\n"
                "    config_schema_version: '1'\n"
                "    assignment_source: yaml\n"
                "    config: []\n"
                "    ansible_group: dnsmasq_server\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(
            result.errors,
            ["desired_service_placements entry 1 has unknown fields: ansible_group."],
        )

    def test_loader_rejects_unqualified_service_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_service_placements:\n"
                "  - desired_service: dnsmasq\n"
                "    instance_name: primary\n"
                "    desired_node: agdns01\n"
                "    desired_state: active\n"
                "    deployment_profile: dnsmasq\n"
                "    config_schema_version: '1'\n"
                "    assignment_source: yaml\n"
                "    config: {}\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(len(result.errors), 1)
        self.assertIn("invalid_service_reference", result.errors[0])

    def test_loader_rejects_invalid_operational_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_node_operational_overrides:\n"
                "  - desired_node: ha01\n"
                "    declared_host_os: haos\n"
                "    connection_path: local\n"
                "    power_control: wol\n"
                "    is_laptop: 'false'\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn(
            "desired_node_operational_overrides entry 1 is_laptop must be a boolean.",
            result.errors,
        )
        self.assertIn(
            "desired_node_operational_overrides entry 1 HAOS permits only power_control=none.",
            result.errors,
        )

    def test_loader_rejects_removed_operational_config_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text("desired_node_operational_configs: []\n", encoding="utf-8")
            result = load_intent_sources(path)
        self.assertEqual(
            result.errors,
            [
                "desired_node_operational_configs is not supported; use "
                "desired_node_operational_overrides."
            ],
        )


    def test_loader_accepts_manual_intent_source_without_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "intent_sources:\n"
                "  - slug: infrastructure\n"
                "    name: Infrastructure\n"
                "    source_type: manual\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.intent_sources), 1)
        source = result.intent_sources[0]
        self.assertIsNone(source.url)
        self.assertEqual(source.slug, "infrastructure")
        self.assertEqual(source.name, "Infrastructure")
        self.assertEqual(source.source_type, "manual")

    def test_loader_requires_slug_for_manual_intent_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "intent_sources:\n"
                "  - source_type: manual\n"
                "    name: Infrastructure\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn(
            "intent_sources entry 1 is missing required field: slug.",
            result.errors,
        )

    def test_loader_still_requires_url_for_git_intent_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "intent_sources:\n"
                "  - name: service\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn("Entry 1 is missing required field: url.", result.errors)

    def test_loader_parses_desired_services_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "intent_sources:\n"
                "  - slug: infrastructure\n"
                "    source_type: manual\n"
                "desired_services:\n"
                "  - intent_source: infrastructure\n"
                "    catalog_metadata_name: prometheus\n"
                "    service_type: service\n"
                "    name: prometheus\n"
                "    display_name: Prometheus\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.desired_services), 1)
        service = result.desired_services[0]
        self.assertEqual(service.intent_source, "infrastructure")
        self.assertEqual(service.catalog_metadata_name, "prometheus")
        self.assertEqual(service.service_type, "service")
        self.assertEqual(service.name, "prometheus")
        self.assertEqual(service.display_name, "Prometheus")
        self.assertEqual(service.slug, "prometheus")
        self.assertEqual(service.catalog_namespace, "default")
        self.assertEqual(service.lifecycle, "proposed")

    def test_loader_requires_desired_service_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_services:\n"
                "  - intent_source: infrastructure\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn(
            "desired_services entry 1 is missing required fields: "
            "catalog_metadata_name, display_name, name, service_type.",
            result.errors,
        )

    def test_loader_rejects_unknown_desired_service_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_services:\n"
                "  - intent_source: infrastructure\n"
                "    catalog_metadata_name: prometheus\n"
                "    service_type: service\n"
                "    name: prometheus\n"
                "    display_name: Prometheus\n"
                "    bogus: nope\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn(
            "desired_services entry 1 has unknown fields: bogus.",
            result.errors,
        )

    def test_loader_detects_duplicate_desired_services(self) -> None:
        entry = (
            "  - intent_source: infrastructure\n"
            "    catalog_metadata_name: prometheus\n"
            "    service_type: service\n"
            "    name: prometheus\n"
            "    display_name: Prometheus\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text("desired_services:\n" + entry + entry, encoding="utf-8")

            result = load_intent_sources(path)

        self.assertIn(
            "desired_services contains duplicate "
            "(intent_source, catalog_namespace, catalog_metadata_name, service_type): "
            "infrastructure/default/prometheus/service.",
            result.errors,
        )

    def test_loader_rejects_unknown_intent_source_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "intent_sources:\n"
                "  - slug: infrastructure\n"
                "    source_type: manual\n"
                "    bogus: nope\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn(
            "intent_sources entry 1 has unknown fields: bogus.",
            result.errors,
        )


if __name__ == "__main__":
    unittest.main()
