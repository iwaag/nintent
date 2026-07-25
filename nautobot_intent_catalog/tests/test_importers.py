from __future__ import annotations

from types import SimpleNamespace
import unittest

from nautobot_intent_catalog.importers import (
    analysis_provenance_defaults,
    dependency_key,
    desired_compute_instance_defaults,
    desired_compute_instance_identity,
    desired_compute_platform_defaults,
    desired_compute_platform_identity,
    desired_endpoint_defaults,
    desired_endpoint_identity,
    desired_ip_range_defaults,
    desired_ip_range_identity,
    desired_node_defaults,
    desired_node_identity,
    desired_node_operational_override_defaults,
    desired_node_operational_override_identity,
    desired_service_create_defaults,
    desired_service_dependencies,
    desired_service_entry_defaults,
    desired_service_entry_identity,
    desired_service_identity,
    desired_service_placement_defaults,
    desired_service_placement_identity,
    desired_service_update_fields,
    intent_source_defaults,
    plan_dependency_sync,
)
from nautobot_intent_catalog.loaders import (
    DesiredComputeInstanceEntry,
    DesiredComputePlatformEntry,
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
        defaults = desired_service_create_defaults(service)
        self.assertEqual(defaults["name"], "storage-service")
        self.assertEqual(defaults["slug"], "storage-service")
        self.assertEqual(defaults["source_ref"], "main")
        self.assertEqual(defaults["catalog_owner"], "platform")
        self.assertEqual(defaults["requirements"], {})
        self.assertEqual(
            defaults["analysis_provenance"]["reasons"], ["backstage_component_catalog_found"]
        )

    def test_desired_service_update_fields_excludes_operator_owned_fields(self) -> None:
        service = {
            "name": "storage-service",
            "catalog": {"namespace": "default", "metadata_name": "storage", "spec_type": "service", "owner": "platform-v2"},
            "intent_source": {"ref": "main"},
            "analysis": {"status": "catalog_derived", "confidence": "high", "reasons": ["updated"]},
        }

        update_fields = desired_service_update_fields(service)

        self.assertEqual(update_fields["catalog_owner"], "platform-v2")
        self.assertEqual(update_fields["analysis_provenance"]["confidence"], "high")
        for operator_owned in ("requirements", "lifecycle", "notes", "name", "slug", "display_name"):
            self.assertNotIn(operator_owned, update_fields)

    def test_analysis_provenance_defaults_rejects_unknown_keys(self) -> None:
        with self.assertRaises(ValueError):
            analysis_provenance_defaults({"status": "ok", "unexpected_key": True})

    def test_plan_dependency_sync_creates_updates_deletes_and_preserves_unchanged(self) -> None:
        service = {
            "dependencies": [
                {"kind": "resource", "namespace": "default", "name": "postgresql", "raw_ref": "resource:default/postgresql", "dependency_type": "resource"},
                {"kind": "component", "namespace": "default", "name": "cache", "raw_ref": "component:default/cache", "dependency_type": "component"},
            ]
        }
        existing = [
            {
                "dependency_kind": "resource",
                "namespace": "default",
                "name": "postgresql",
                "raw_ref": "resource:default/postgresql-old",
                "dependency_type": "resource",
            },
            {
                "dependency_kind": "component",
                "namespace": "default",
                "name": "gone",
                "raw_ref": "component:default/gone",
                "dependency_type": "component",
            },
        ]

        plan = plan_dependency_sync(existing=existing, service=service)

        self.assertEqual(len(plan["create"]), 1)
        self.assertEqual(dependency_key(plan["create"][0]), ("component", "default", "cache"))
        self.assertEqual(
            plan["update"],
            [{"key": ("resource", "default", "postgresql"), "raw_ref": "resource:default/postgresql", "dependency_type": "resource"}],
        )
        self.assertEqual(plan["delete_keys"], [("component", "default", "gone")])
        self.assertEqual(plan["unchanged_keys"], [])

    def test_plan_dependency_sync_identical_reanalysis_is_fully_unchanged(self) -> None:
        service = {
            "dependencies": [
                {"kind": "resource", "namespace": "default", "name": "postgresql", "raw_ref": "resource:default/postgresql", "dependency_type": "resource"},
            ]
        }
        existing = [
            {
                "dependency_kind": "resource",
                "namespace": "default",
                "name": "postgresql",
                "raw_ref": "resource:default/postgresql",
                "dependency_type": "resource",
            }
        ]

        plan = plan_dependency_sync(existing=existing, service=service)

        self.assertEqual(plan, {"create": [], "update": [], "unchanged_keys": [("resource", "default", "postgresql")], "delete_keys": []})

    def test_plan_dependency_sync_update_never_touches_notes_or_resolution(self) -> None:
        # `existing` rows carry only the natural key plus source-owned raw_ref/dependency_type
        # (the caller reads exactly these from the ORM); the plan's "update" entries mirror
        # that shape, so notes/resolution_status/resolved_service on the real row are simply
        # never part of what this function tells the caller to write.
        service = {
            "dependencies": [
                {"kind": "resource", "namespace": "default", "name": "postgresql", "raw_ref": "resource:default/postgresql-v2", "dependency_type": "resource"},
            ]
        }
        existing = [
            {
                "dependency_kind": "resource",
                "namespace": "default",
                "name": "postgresql",
                "raw_ref": "resource:default/postgresql",
                "dependency_type": "resource",
            }
        ]

        plan = plan_dependency_sync(existing=existing, service=service)

        self.assertEqual(len(plan["update"]), 1)
        self.assertEqual(set(plan["update"][0]), {"key", "raw_ref", "dependency_type"})

    def test_plan_dependency_sync_rejects_duplicate_incoming_keys(self) -> None:
        service = {
            "dependencies": [
                {"kind": "resource", "namespace": "default", "name": "postgresql", "raw_ref": "a", "dependency_type": "resource"},
                {"kind": "resource", "namespace": "default", "name": "postgresql", "raw_ref": "b", "dependency_type": "resource"},
            ]
        }

        with self.assertRaisesRegex(ValueError, "Duplicate dependency key"):
            plan_dependency_sync(existing=[], service=service)

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
                "mac_address": None,
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
                "mac_address": None,
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
        self.assertNotIn("placements", desired_service_create_defaults({"name": "dnsmasq"}))

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

    def test_desired_compute_platform_identity_and_defaults(self) -> None:
        platform = DesiredComputePlatformEntry(
            name="aghub Proxmox",
            slug="aghub-pve",
            control_node="aghub",
            provider_type="proxmox",
            lifecycle="active",
            config_schema_version="v1",
            config={"cluster_name": "aghub-proxmox", "default_storage": "local-lvm"},
        )

        self.assertEqual(desired_compute_platform_identity(platform), {"slug": "aghub-pve"})
        self.assertEqual(
            desired_compute_platform_defaults(platform, control_node_id="node-id"),
            {
                "name": "aghub Proxmox",
                "provider_type": "proxmox",
                "lifecycle": "active",
                "control_node_id": "node-id",
                "config_schema_version": "v1",
                "config": {"cluster_name": "aghub-proxmox", "default_storage": "local-lvm"},
            },
        )

    def test_desired_compute_instance_identity_and_defaults(self) -> None:
        instance = DesiredComputeInstanceEntry(
            desired_node="agdnsmasq",
            platform="aghub-pve",
            instance_kind="container",
            desired_power_state="running",
            vcpus=1,
            memory_mb=512,
            root_disk_gb=8,
            config_schema_version="v1",
            config={"vmid": 108, "template": "local:vztmpl/x.tar.zst", "unprivileged": True},
        )

        self.assertEqual(
            desired_compute_instance_identity("node-id"),
            {"desired_node_id": "node-id"},
        )
        self.assertEqual(
            desired_compute_instance_defaults(instance, platform_id="platform-id"),
            {
                "platform_id": "platform-id",
                "instance_kind": "container",
                "desired_power_state": "running",
                "vcpus": 1,
                "memory_mb": 512,
                "root_disk_gb": 8,
                "config_schema_version": "v1",
                "config": {"vmid": 108, "template": "local:vztmpl/x.tar.zst", "unprivileged": True},
            },
        )


class OwnershipSplitTests(unittest.TestCase):
    """Plan.md Section 5.3/Step 1 items 6-9: existing-row updates must touch only the
    YAML-owned subset of fields. These target new functions added in Step 4; they fail with
    ImportError against the pre-Phase-1 `importers` module."""

    def test_desired_node_update_fields_excludes_lifecycle(self) -> None:
        from nautobot_intent_catalog.importers import desired_node_update_fields

        node = DesiredNodeEntry(name="agexample", slug="agexample", lifecycle="active")
        update_fields = desired_node_update_fields(node)

        self.assertNotIn("lifecycle", update_fields)
        self.assertIn("name", update_fields)
        self.assertNotIn("realized_device", update_fields)
        self.assertNotIn("realized_device_source", update_fields)

    def test_desired_node_create_defaults_still_includes_lifecycle(self) -> None:
        node = DesiredNodeEntry(name="agexample", slug="agexample", lifecycle="active")
        self.assertEqual(desired_node_defaults(node)["lifecycle"], "active")

    def test_desired_service_entry_update_fields_excludes_operator_and_analysis_fields(self) -> None:
        from nautobot_intent_catalog.importers import desired_service_entry_update_fields

        entry = DesiredServiceEntry(
            intent_source="infrastructure",
            catalog_metadata_name="prometheus",
            service_type="service",
            name="prometheus",
            slug="prometheus",
            display_name="Prometheus",
            lifecycle="active",
            notes="hello",
        )
        update_fields = desired_service_entry_update_fields(entry)

        self.assertEqual(set(update_fields), {"lifecycle", "notes"})
        self.assertEqual(update_fields["lifecycle"], "active")

    def test_desired_service_entry_locked_fields_covers_identity_display(self) -> None:
        from nautobot_intent_catalog.importers import desired_service_entry_locked_fields

        entry = DesiredServiceEntry(
            intent_source="infrastructure",
            catalog_metadata_name="prometheus",
            service_type="service",
            name="prometheus",
            slug="prometheus",
            display_name="Prometheus",
        )
        locked_fields = desired_service_entry_locked_fields(entry)

        self.assertEqual(
            locked_fields,
            {"name": "prometheus", "slug": "prometheus", "display_name": "Prometheus"},
        )

    def test_desired_service_entry_defaults_never_resets_requirements_field(self) -> None:
        entry = DesiredServiceEntry(
            intent_source="infrastructure",
            catalog_metadata_name="prometheus",
            service_type="service",
            name="prometheus",
            slug="prometheus",
            display_name="Prometheus",
        )
        # `requirements` has no YAML input field (plan Section 5.3); the create-time default
        # of `{}` is fine on create, but it must never appear in the *update*-owned set.
        from nautobot_intent_catalog.importers import desired_service_entry_update_fields

        self.assertNotIn("requirements", desired_service_entry_update_fields(entry))


class ImportPlanEngineTests(unittest.TestCase):
    """Plan.md Section 5.2/Step 1 item 6: create/update/unchanged/conflict classification,
    duplicate existing rows, and preserved-field reporting for the shared planner engine."""

    def test_no_existing_match_plans_create_with_all_fields(self) -> None:
        from nautobot_intent_catalog.import_plan import plan_upsert

        planned = plan_upsert(
            model="DesiredIPRange",
            root="desired_ip_ranges",
            identity={"slug": "dhcp-reserved"},
            create_fields={"name": "dhcp-reserved", "lifecycle": "planned"},
            update_fields={"name": "dhcp-reserved", "lifecycle": "planned"},
            existing_matches=[],
        )

        self.assertEqual(planned.action, "create")
        self.assertEqual(planned.changed_fields["name"], {"old": None, "new": "dhcp-reserved"})

    def test_matching_existing_row_is_unchanged(self) -> None:
        from nautobot_intent_catalog.import_plan import plan_upsert

        planned = plan_upsert(
            model="DesiredIPRange",
            root="desired_ip_ranges",
            identity={"slug": "dhcp-reserved"},
            create_fields={"name": "dhcp-reserved"},
            update_fields={"name": "dhcp-reserved"},
            existing_matches=[{"name": "dhcp-reserved"}],
        )

        self.assertEqual(planned.action, "unchanged")

    def test_differing_update_owned_field_plans_update_with_old_new(self) -> None:
        from nautobot_intent_catalog.import_plan import plan_upsert

        planned = plan_upsert(
            model="DesiredIPRange",
            root="desired_ip_ranges",
            identity={"slug": "dhcp-reserved"},
            create_fields={"name": "dhcp-reserved"},
            update_fields={"name": "dhcp-reserved-renamed"},
            existing_matches=[{"name": "dhcp-reserved"}],
        )

        self.assertEqual(planned.action, "update")
        self.assertEqual(
            planned.changed_fields["name"],
            {"old": "dhcp-reserved", "new": "dhcp-reserved-renamed"},
        )

    def test_duplicate_existing_rows_is_conflict(self) -> None:
        from nautobot_intent_catalog.import_plan import plan_upsert

        planned = plan_upsert(
            model="DesiredNode",
            root="desired_nodes",
            identity={"slug": "agexample"},
            create_fields={"name": "agexample"},
            update_fields={"name": "agexample"},
            existing_matches=[{"name": "agexample"}, {"name": "agexample-dup"}],
        )

        self.assertEqual(planned.action, "conflict")

    def test_lifecycle_preserved_on_update_reports_it_as_preserved_not_changed(self) -> None:
        from nautobot_intent_catalog.import_plan import plan_upsert

        planned = plan_upsert(
            model="DesiredNode",
            root="desired_nodes",
            identity={"slug": "agpc"},
            create_fields={"name": "agpc", "lifecycle": "active"},
            update_fields={"name": "agpc"},
            existing_matches=[{"name": "agpc", "lifecycle": "approved"}],
        )

        self.assertEqual(planned.action, "unchanged")
        self.assertIn("lifecycle", planned.preserved_fields)

    def test_locked_field_disagreement_blocks_as_conflict_not_silent_overwrite(self) -> None:
        from nautobot_intent_catalog.import_plan import plan_upsert

        planned = plan_upsert(
            model="DesiredService",
            root="desired_services",
            identity={"catalog_metadata_name": "prometheus"},
            create_fields={"name": "prometheus", "lifecycle": "active"},
            update_fields={"lifecycle": "active"},
            existing_matches=[{"name": "prometheus-renamed", "lifecycle": "active"}],
            locked_fields={"name": "prometheus"},
        )

        self.assertEqual(planned.action, "conflict")
        self.assertIsNotNone(planned.conflict_reason)

    def test_preview_engine_performs_no_orm_mutation(self) -> None:
        """The planner is pure Python -- it never calls save/update/delete/bulk_create on
        anything; this test documents that guarantee structurally (Step 1 item 10): the
        `existing_matches` argument is a plain list of dicts, not a queryset or model
        instance, so there is no mutation method for the engine to reach."""

        from nautobot_intent_catalog.import_plan import plan_upsert

        existing_matches = [{"name": "agpc"}]
        plan_upsert(
            model="DesiredNode",
            root="desired_nodes",
            identity={"slug": "agpc"},
            create_fields={"name": "agpc"},
            update_fields={"name": "agpc"},
            existing_matches=existing_matches,
        )
        self.assertIsInstance(existing_matches[0], dict)
        self.assertFalse(hasattr(existing_matches[0], "save"))


if __name__ == "__main__":
    unittest.main()
