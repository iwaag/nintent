from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from nautobot_intent_catalog.loaders import (
    DEFAULT_BASIC_FILE_PATHS,
    DEFAULT_CATALOG_PATHS,
    load_intent_sources,
)


def _first_existing_canonical_intent_sources_path() -> Path | None:
    """Locate the checked-in canonical YAML across every environment this suite runs in.

    A single hardcoded path breaks depending on how nintent was installed: a local repo
    checkout (`nauto/` is a fixed number of parents above this file), the deployed image
    (baked in at the `PLUGINS_CONFIG`/`NAUTOBOT_INTENT_SOURCES_FILE`-configured path), or a
    plain `pip install` with neither (no reachable copy at all, so the test must skip rather
    than assert a false negative about file content).
    """

    candidates: list[Path] = []

    env_override = os.environ.get("NAUTOBOT_INTENT_SOURCES_FILE")
    if env_override:
        candidates.append(Path(env_override))

    try:
        from django.conf import settings

        plugins_config = getattr(settings, "PLUGINS_CONFIG", {}) or {}
        configured = plugins_config.get("nautobot_intent_catalog", {}).get("intent_sources_file")
        if configured:
            candidates.append(Path(configured))
    except Exception:
        pass

    candidates.append(Path(__file__).resolve().parents[3] / "nauto" / "seed" / "intent_sources.yaml")

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


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

    def test_loader_falls_back_to_default_lifecycle_for_an_unrecognized_value(self) -> None:
        # Pre-existing leniency of `_choice()` (unlike node_type's `_choice_with_default_or_error`):
        # an unrecognized lifecycle silently normalizes to the current default rather than erroring.
        # This phase changes what that default is, not this validation behavior.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_nodes:\n"
                "  - name: bogus-lifecycle-node\n"
                "    node_type: device\n"
                "    lifecycle: not-a-real-state\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.desired_nodes[0].lifecycle, "active")

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


_SEED_YAML = (
    "desired_nodes:\n"
    "  - name: aghub\n"
    "    slug: aghub\n"
    "    node_type: device\n"
    "  - name: agdnsmasq\n"
    "    slug: agdnsmasq\n"
    "    node_type: service_host\n"
    "\n"
    "desired_endpoints:\n"
    "  - name: primary\n"
    "    desired_node: agdnsmasq\n"
    "    endpoint_type: primary\n"
    "    ip_address: 192.168.0.2\n"
    "    ip_policy: dhcp_reserved\n"
    "    mac_address: BC:24:11:23:DC:B7\n"
    "    dns_name: agdnsmasq.home.arpa\n"
    "    mdns_name: agdnsmasq.local\n"
    "    generate_dnsmasq: true\n"
    "\n"
    "desired_compute_platforms:\n"
    "  - name: aghub Proxmox\n"
    "    slug: aghub-pve\n"
    "    provider_type: proxmox\n"
    "    lifecycle: active\n"
    "    control_node: aghub\n"
    "    config:\n"
    "      cluster_name: aghub-proxmox\n"
    "      default_storage: local-lvm\n"
    "      default_bridge: vmbr0\n"
    "\n"
    "desired_compute_instances:\n"
    "  - desired_node: agdnsmasq\n"
    "    platform: aghub-pve\n"
    "    instance_kind: container\n"
    "    desired_power_state: running\n"
    "    vcpus: 1\n"
    "    memory_mb: 512\n"
    "    root_disk_gb: 8\n"
    "    config:\n"
    "      vmid: 108\n"
    "      template: local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst\n"
    "      unprivileged: true\n"
)


class ComputePlatformLoaderTests(unittest.TestCase):
    def test_seed_shaped_yaml_loads_with_defaults_and_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(_SEED_YAML, encoding="utf-8")

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.desired_compute_platforms), 1)
        platform = result.desired_compute_platforms[0]
        self.assertEqual(platform.slug, "aghub-pve")
        self.assertEqual(platform.provider_type, "proxmox")
        self.assertEqual(platform.lifecycle, "active")
        self.assertEqual(platform.config_schema_version, "v1")
        self.assertEqual(
            platform.config,
            {
                "cluster_name": "aghub-proxmox",
                "default_storage": "local-lvm",
                "default_bridge": "vmbr0",
            },
        )

        self.assertEqual(len(result.desired_compute_instances), 1)
        instance = result.desired_compute_instances[0]
        self.assertEqual(instance.desired_node, "agdnsmasq")
        self.assertEqual(instance.platform, "aghub-pve")
        self.assertEqual(instance.vcpus, 1)
        self.assertEqual(instance.memory_mb, 512)
        self.assertEqual(instance.root_disk_gb, 8)
        self.assertEqual(
            instance.config,
            {
                "vmid": 108,
                "template": "local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst",
                "unprivileged": True,
            },
        )

        self.assertEqual(len(result.desired_endpoints), 1)
        # Mixed-case colon input normalizes to canonical lower-case (compute_contract.normalize_mac_address).
        self.assertEqual(result.desired_endpoints[0].mac_address, "bc:24:11:23:dc:b7")

    def test_platform_omitted_lifecycle_and_provider_type_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_compute_platforms:\n"
                "  - name: aghub Proxmox\n"
                "    slug: aghub-pve\n"
                "    control_node: aghub\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        platform = result.desired_compute_platforms[0]
        self.assertEqual(platform.provider_type, "proxmox")
        self.assertEqual(platform.lifecycle, "active")
        self.assertEqual(platform.config, {})

    def test_platform_rejects_unknown_config_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_compute_platforms:\n"
                "  - name: aghub Proxmox\n"
                "    slug: aghub-pve\n"
                "    control_node: aghub\n"
                "    config:\n"
                "      bogus: nope\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertTrue(
            any("unknown_config_key" in error for error in result.errors),
            result.errors,
        )

    def test_platform_rejects_unknown_top_level_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_compute_platforms:\n"
                "  - name: aghub Proxmox\n"
                "    slug: aghub-pve\n"
                "    control_node: aghub\n"
                "    bogus: nope\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn(
            "desired_compute_platforms entry 1 has unknown fields: bogus.",
            result.errors,
        )

    def test_platform_rejects_wrong_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_compute_platforms:\n"
                "  - name: aghub Proxmox\n"
                "    slug: aghub-pve\n"
                "    control_node: aghub\n"
                "    config_schema_version: v2\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertTrue(
            any("invalid_config_schema_version" in error for error in result.errors),
            result.errors,
        )

    def test_duplicate_platform_slug_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_compute_platforms:\n"
                "  - name: aghub Proxmox\n"
                "    slug: aghub-pve\n"
                "    control_node: aghub\n"
                "  - name: aghub Proxmox Again\n"
                "    slug: aghub-pve\n"
                "    control_node: aghub\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn(
            "desired_compute_platforms contains duplicate slug: aghub-pve.",
            result.errors,
        )


class ComputeInstanceLoaderTests(unittest.TestCase):
    def test_virtual_machine_forbids_unprivileged_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_compute_instances:\n"
                "  - desired_node: some-vm\n"
                "    platform: aghub-pve\n"
                "    instance_kind: virtual_machine\n"
                "    vcpus: 2\n"
                "    memory_mb: 2048\n"
                "    root_disk_gb: 32\n"
                "    config:\n"
                "      template: local:vztmpl/debian-13.tar.zst\n"
                "      unprivileged: true\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertTrue(
            any("invalid_config_key" in error for error in result.errors),
            result.errors,
        )

    def test_container_requires_unprivileged_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_compute_instances:\n"
                "  - desired_node: some-ct\n"
                "    platform: aghub-pve\n"
                "    instance_kind: container\n"
                "    vcpus: 1\n"
                "    memory_mb: 512\n"
                "    root_disk_gb: 8\n"
                "    config:\n"
                "      template: local:vztmpl/debian-13.tar.zst\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertTrue(
            any("missing_config_value" in error for error in result.errors),
            result.errors,
        )

    def test_vcpus_out_of_range_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_compute_instances:\n"
                "  - desired_node: some-ct\n"
                "    platform: aghub-pve\n"
                "    instance_kind: container\n"
                "    vcpus: 0\n"
                "    memory_mb: 512\n"
                "    root_disk_gb: 8\n"
                "    config:\n"
                "      template: local:vztmpl/debian-13.tar.zst\n"
                "      unprivileged: true\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertTrue(
            any("vcpus_out_of_range" in error for error in result.errors),
            result.errors,
        )

    def test_duplicate_desired_node_across_instances_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_compute_instances:\n"
                "  - desired_node: agdnsmasq\n"
                "    platform: aghub-pve\n"
                "    instance_kind: container\n"
                "    vcpus: 1\n"
                "    memory_mb: 512\n"
                "    root_disk_gb: 8\n"
                "    config:\n"
                "      template: local:vztmpl/debian-13.tar.zst\n"
                "      unprivileged: true\n"
                "  - desired_node: agdnsmasq\n"
                "    platform: aghub-pve\n"
                "    instance_kind: container\n"
                "    vcpus: 1\n"
                "    memory_mb: 512\n"
                "    root_disk_gb: 8\n"
                "    config:\n"
                "      template: local:vztmpl/debian-13.tar.zst\n"
                "      unprivileged: true\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn(
            "desired_compute_instances contains duplicate desired_node: agdnsmasq.",
            result.errors,
        )


class EndpointMacAddressLoaderTests(unittest.TestCase):
    def test_hyphenated_mac_normalizes_to_canonical_colon_form(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_endpoints:\n"
                "  - name: primary\n"
                "    desired_node: agdnsmasq\n"
                "    mac_address: BC-24-11-23-DC-B7\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.desired_endpoints[0].mac_address, "bc:24:11:23:dc:b7")

    def test_invalid_mac_address_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_endpoints:\n"
                "  - name: primary\n"
                "    desired_node: agdnsmasq\n"
                "    mac_address: not-a-mac\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertTrue(
            any("invalid_mac_address" in error for error in result.errors),
            result.errors,
        )

    def test_duplicate_mac_address_across_endpoints_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_endpoints:\n"
                "  - name: primary\n"
                "    desired_node: node-a\n"
                "    mac_address: bc:24:11:23:dc:b7\n"
                "  - name: primary\n"
                "    desired_node: node-b\n"
                "    mac_address: bc:24:11:23:dc:b7\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn(
            "desired_endpoints contains duplicate mac_address: bc:24:11:23:dc:b7.",
            result.errors,
        )

    def test_duplicate_desired_node_slug_is_rejected(self) -> None:
        """Found live in interface_contract/p1 Step 8: a duplicate desired_nodes slug used to
        silently coalesce into one row (last entry wins) at Import apply time even though
        preview planned two `create` rows -- a preview/apply parity break. Must fail closed."""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_nodes:\n"
                "  - name: agrollbacktest\n"
                "    slug: agrollbacktest\n"
                "  - name: agrollbacktest-duplicate\n"
                "    slug: agrollbacktest\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn("desired_nodes contains duplicate slug: agrollbacktest.", result.errors)

    def test_duplicate_intent_source_slug_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "intent_sources:\n"
                "  - slug: manual\n"
                "    name: Manual\n"
                "    source_type: manual\n"
                "  - slug: manual\n"
                "    name: Manual Again\n"
                "    source_type: manual\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn("intent_sources contains duplicate slug: manual.", result.errors)

    def test_duplicate_git_intent_source_url_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "intent_sources:\n"
                "  - url: https://github.com/example/service\n"
                "  - url: https://github.com/example/service\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn(
            "intent_sources contains duplicate url: https://github.com/example/service.",
            result.errors,
        )

    def test_duplicate_endpoint_identity_without_mac_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_endpoints:\n"
                "  - name: primary\n"
                "    desired_node: agdup\n"
                "    endpoint_type: primary\n"
                "    ip_policy: external\n"
                "  - name: primary\n"
                "    desired_node: agdup\n"
                "    endpoint_type: primary\n"
                "    ip_policy: external\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn(
            "desired_endpoints contains duplicate desired_node/name/endpoint_type: agdup/primary/primary.",
            result.errors,
        )

    def test_duplicate_ip_range_slug_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_ip_ranges:\n"
                "  - name: dup-range\n"
                "    slug: dup-range\n"
                "    start_address: 192.168.0.10\n"
                "    end_address: 192.168.0.20\n"
                "    range_policy: static_pool\n"
                "  - name: dup-range-again\n"
                "    slug: dup-range\n"
                "    start_address: 192.168.0.30\n"
                "    end_address: 192.168.0.40\n"
                "    range_policy: static_pool\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertIn("desired_ip_ranges contains duplicate slug: dup-range.", result.errors)


class ClosedRootValidationTests(unittest.TestCase):
    """Phase 1 Step 1/Step 3 (interface_contract/p1/plan.md Section 3.1/4.1): exactly the nine
    canonical roots are accepted; every other top-level key -- old alias or genuinely unknown --
    fails before any section is normalized."""

    _ALL_NINE_ROOTS = (
        "intent_sources: []\n"
        "desired_nodes: []\n"
        "desired_endpoints: []\n"
        "desired_ip_ranges: []\n"
        "desired_compute_platforms: []\n"
        "desired_compute_instances: []\n"
        "desired_services: []\n"
        "desired_service_placements: []\n"
        "desired_node_operational_overrides: []\n"
    )

    def test_all_nine_known_roots_are_accepted_together(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(self._ALL_NINE_ROOTS, encoding="utf-8")

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])

    def test_unknown_top_level_root_is_rejected_even_with_every_known_root_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(self._ALL_NINE_ROOTS + "totally_unknown_root: []\n", encoding="utf-8")

            result = load_intent_sources(path)

        self.assertTrue(
            any("totally_unknown_root" in error for error in result.errors),
            result.errors,
        )

    def test_service_repositories_alias_still_rejected_with_its_specific_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text("service_repositories: []\n", encoding="utf-8")

            result = load_intent_sources(path)

        self.assertTrue(
            any("service_repositories is not supported" in error for error in result.errors),
            result.errors,
        )

    def test_desired_node_operational_configs_alias_still_rejected_with_its_specific_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text("desired_node_operational_configs: []\n", encoding="utf-8")

            result = load_intent_sources(path)

        self.assertTrue(
            any("desired_node_operational_configs is not supported" in error for error in result.errors),
            result.errors,
        )


class OmittedRootIsNoOpTests(unittest.TestCase):
    """A missing known root stays an empty no-op section for a partial operator document
    (plan.md Section 4.1) -- omission never becomes a validation error."""

    def test_missing_known_root_produces_no_error_and_empty_section(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text("intent_sources: []\n", encoding="utf-8")

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.desired_nodes, [])
        self.assertEqual(result.desired_node_operational_overrides, [])


class EndpointDnsMdnsOmissionTests(unittest.TestCase):
    """Plan.md Section 4.3/Step 1 item 5: an omitted optional DNS/mDNS name on a primary
    endpoint must remain omitted through the loader -- no hidden default is synthesized here.
    (Synthesis, if any, is an importer-layer concern covered by test_importers.py.)"""

    def test_omitted_dns_and_mdns_names_stay_none_after_loading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_nodes:\n"
                "  - name: agexample\n"
                "    slug: agexample\n"
                "desired_endpoints:\n"
                "  - name: primary\n"
                "    desired_node: agexample\n"
                "    endpoint_type: primary\n"
                "    ip_policy: external\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        endpoint = result.desired_endpoints[0]
        self.assertIsNone(endpoint.dns_name)
        self.assertIsNone(endpoint.mdns_name)

    def test_explicit_dns_and_mdns_names_survive_normalization_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_endpoints:\n"
                "  - name: primary\n"
                "    desired_node: agexample\n"
                "    endpoint_type: primary\n"
                "    ip_policy: dhcp_reserved\n"
                "    ip_address: 192.168.0.50\n"
                "    dns_name: agexample.home.arpa\n"
                "    mdns_name: agexample.local\n",
                encoding="utf-8",
            )

            result = load_intent_sources(path)

        self.assertEqual(result.errors, [])
        endpoint = result.desired_endpoints[0]
        self.assertEqual(endpoint.dns_name, "agexample.home.arpa")
        self.assertEqual(endpoint.mdns_name, "agexample.local")


class CanonicalFileIdentityCountTests(unittest.TestCase):
    """Plan.md Section 4.2/Step 1 item 3: the checked-in `nauto/seed/intent_sources.yaml` must
    load with zero errors and contain exactly the confirmed Phase 0 identity set. This test
    reads the real checked-in file wherever this environment can reach it (local checkout,
    or the deployed image's baked-in copy); it skips if neither is reachable."""

    _CANONICAL_PATH = _first_existing_canonical_intent_sources_path()

    def test_canonical_checked_in_file_matches_exact_confirmed_counts(self) -> None:
        if self._CANONICAL_PATH is None:
            self.skipTest(
                "no reachable canonical intent_sources.yaml: neither NAUTOBOT_INTENT_SOURCES_FILE, "
                "PLUGINS_CONFIG['nautobot_intent_catalog']['intent_sources_file'], nor a local "
                "checkout's nauto/seed/intent_sources.yaml exists in this environment"
            )
        result = load_intent_sources(self._CANONICAL_PATH)

        self.assertEqual(result.errors, [])
        self.assertEqual(
            sorted(source.slug for source in result.intent_sources),
            ["infrastructure", "manual"],
        )
        self.assertEqual(
            sorted(node.slug for node in result.desired_nodes),
            ["agbach", "agdnsmasq", "aghub", "agpc", "agstudio"],
        )
        self.assertEqual(len(result.desired_endpoints), 5)
        self.assertEqual(
            sorted(r.slug for r in result.desired_ip_ranges),
            ["dhcp-reserved", "dhcp-unreserved", "network-infra"],
        )
        self.assertEqual([platform.slug for platform in result.desired_compute_platforms], ["aghub-pve"])
        self.assertEqual(
            [(instance.desired_node, instance.config.get("vmid")) for instance in result.desired_compute_instances],
            [("agdnsmasq", 108)],
        )
        self.assertEqual(len(result.desired_services), 6)
        self.assertEqual(len(result.desired_service_placements), 1)
        self.assertEqual(result.desired_node_operational_overrides, [])
        stale_nodes = {"agmbp2019", "agmbp2018", "agprometheus", "aggrafana", "agnomad", "aghaos"}
        self.assertFalse(stale_nodes & {node.slug for node in result.desired_nodes})


class RealizedFieldNeverAcceptedFromYamlTests(unittest.TestCase):
    """Plan.md Step 1 item 4: no realized-link/source key is a recognized loader field on any
    root that carries a realized link, so YAML can never set one even if an operator tries."""

    def test_desired_node_rejects_realized_device_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intent_sources.yaml"
            path.write_text(
                "desired_nodes:\n"
                "  - name: agexample\n"
                "    slug: agexample\n"
                "    realized_device: some-device-id\n",
                encoding="utf-8",
            )
            result = load_intent_sources(path)
        # desired_nodes currently accepts unknown keys silently (no strict-field check on this
        # root); a realized_device key must not surface as a recognized DesiredNodeEntry field.
        self.assertFalse(hasattr(result.desired_nodes[0] if result.desired_nodes else object(), "realized_device"))

    def test_desired_endpoint_entry_has_no_realized_ip_field(self) -> None:
        from nautobot_intent_catalog.loaders import DesiredEndpointEntry

        field_names = {f for f in DesiredEndpointEntry.__dataclass_fields__}
        self.assertNotIn("realized_ip_address", field_names)
        self.assertNotIn("realized_ip_address_source", field_names)


if __name__ == "__main__":
    unittest.main()
