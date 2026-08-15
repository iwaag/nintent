"""Django-free contract tests for desired-state batch request decoding."""

import sys
import types
import unittest

from nautobot_intent_catalog.batch import BatchValidationError, _orm_values, apply_batch, decode_batch, plan_batch


class BatchDecodeTests(unittest.TestCase):
    def test_accepts_partial_upsert_document(self):
        dry_run, operations = decode_batch({"dry_run": True, "operations": [
            {"op": "upsert", "kind": "desired_node", "key": {"slug": "node-a"},
             "values": {"lifecycle": "active"}},
        ]})
        self.assertTrue(dry_run)
        self.assertEqual(operations[0].values, {"lifecycle": "active"})

    def test_rejects_unknown_kind_and_duplicate_identity(self):
        with self.assertRaises(BatchValidationError):
            decode_batch({"dry_run": True, "operations": [
                {"op": "upsert", "kind": "unknown", "key": {}, "values": {}},
            ]})
        with self.assertRaises(BatchValidationError):
            decode_batch({"dry_run": True, "operations": [
                {"op": "delete", "kind": "desired_service", "key": {"slug": "a"}, "values": {}},
                {"op": "delete", "kind": "desired_service", "key": {"slug": "a"}, "values": {}},
            ]})

    def test_plan_is_deterministic(self):
        document = {"dry_run": True, "operations": [
            {"op": "delete", "kind": "desired_service", "key": {"slug": "a"}, "values": {}},
        ]}
        self.assertEqual(plan_batch(document).as_dict(), plan_batch(document).as_dict())

    def test_rejects_a_key_that_is_not_the_declared_identity(self):
        for case, key in (
            ("wrong name", {"name": "example-service"}),
            ("superset", {"slug": "example-service", "namespace": "default"}),
            ("empty value", {"slug": ""}),
        ):
            with self.subTest(case=case), self.assertRaises(BatchValidationError):
                decode_batch({"dry_run": True, "operations": [
                    {"op": "upsert", "kind": "desired_service", "key": key,
                     "values": {"name": "example-service", "slug": "example-service"}},
                ]})

    def test_identity_key_order_is_insignificant(self):
        for key in (
            {"desired_node": "agdnsmasq", "name": "primary", "endpoint_type": "primary"},
            {"desired_node": "agdnsmasq", "endpoint_type": "primary", "name": "primary"},
            {"endpoint_type": "primary", "name": "primary", "desired_node": "agdnsmasq"},
        ):
            with self.subTest(order=tuple(key)):
                _, operations = decode_batch({"dry_run": True, "operations": [
                    {"op": "upsert", "kind": "desired_endpoint", "key": key,
                     "values": {"gateway_address": "192.168.50.1"}},
                ]})
                self.assertEqual(set(operations[0].key), {"desired_node", "name", "endpoint_type"})

    def test_identity_error_names_the_expected_keys(self):
        with self.assertRaises(BatchValidationError) as ctx:
            decode_batch({"dry_run": True, "operations": [
                {"op": "upsert", "kind": "desired_endpoint",
                 "key": {"desired_node": "agdnsmasq", "name": "primary"},
                 "values": {"gateway_address": "192.168.50.1"}},
            ]})
        self.assertIn("expected non-empty keys (desired_node, name, endpoint_type)", str(ctx.exception))

    def test_values_may_repeat_identity_fields_with_equal_values(self):
        # `nctl desired export` emits every writable field, so identity fields
        # legally appear in both key and values with identical values.
        _, operations = decode_batch({"dry_run": True, "operations": [
            {"op": "upsert", "kind": "desired_endpoint",
             "key": {"desired_node": "agstudio", "name": "primary", "endpoint_type": "primary"},
             "values": {"desired_node": "agstudio", "name": "primary", "endpoint_type": "primary",
                        "ip_policy": "external"}},
        ]})
        self.assertEqual(operations[0].values["desired_node"], "agstudio")

    def test_rejects_identity_field_repeated_with_a_different_value(self):
        with self.assertRaises(BatchValidationError) as ctx:
            decode_batch({"dry_run": True, "operations": [
                {"op": "upsert", "kind": "desired_node", "key": {"slug": "node-a"},
                 "values": {"slug": "node-b", "name": "node-b"}},
            ]})
        self.assertIn("identity field", str(ctx.exception))

    def test_desired_service_binding_envelope_accepts_dict_identity_and_rejects_unknown_fields(self):
        dry_run, operations = decode_batch({"dry_run": True, "operations": [
            {"op": "upsert", "kind": "desired_service_binding",
             "key": {"consumer_placement": {"desired_service": "llm-consumer", "instance_name": "aghub"},
                      "binding_name": "llm_provider"},
             "values": {"provider_service": "ollama"}},
        ]})
        self.assertTrue(dry_run)
        self.assertEqual(operations[0].values, {"provider_service": "ollama"})

        with self.assertRaises(BatchValidationError):
            decode_batch({"dry_run": True, "operations": [
                {"op": "upsert", "kind": "desired_service_binding",
                 "key": {"consumer_placement": {"desired_service": "llm-consumer", "instance_name": "aghub"},
                          "binding_name": "llm_provider"},
                 "values": {"resolution_status": "resolved"}},
            ]})

    def test_desired_workspace_envelope_accepts_known_fields_and_rejects_unknown_ones(self):
        dry_run, operations = decode_batch({"dry_run": True, "operations": [
            {"op": "upsert", "kind": "desired_workspace", "key": {"slug": "pj-voxel3dprint"},
             "values": {"name": "pj-voxel3dprint", "lifecycle": "active",
                        "source_remote_url": "https://github.com/iwaag/pj-voxel3dprint.git",
                        "desired_node": "agpc", "expected_path": "/home/eiji/projects/pj-voxel3dprint",
                        "desired_presence": "present"}},
        ]})
        self.assertTrue(dry_run)
        self.assertEqual(operations[0].kind, "desired_workspace")

        with self.assertRaises(BatchValidationError):
            decode_batch({"dry_run": True, "operations": [
                {"op": "upsert", "kind": "desired_workspace", "key": {"slug": "pj-voxel3dprint"},
                 "values": {"desired_branch": "main"}},
            ]})

    def test_actual_link_references_resolve_reject_unknown_and_allow_null(self):
        class Query:
            def __init__(self, value):
                self.value = value
            def first(self):
                return self.value
        class Manager:
            def filter(self, *, pk):
                return Query(types.SimpleNamespace(pk=pk) if pk == "known-device" else None)

        dcim = types.ModuleType("nautobot.dcim.models")
        dcim.Device = types.SimpleNamespace(objects=Manager())
        prior = sys.modules.get("nautobot.dcim.models")
        sys.modules["nautobot.dcim.models"] = dcim
        try:
            self.assertEqual(_orm_values("desired_node", {"realized_device": "known-device"}, {})["realized_device"].pk, "known-device")
            self.assertIsNone(_orm_values("desired_node", {"realized_device": None}, {})["realized_device"])
            with self.assertRaisesRegex(BatchValidationError, "unresolved realized_device reference"):
                _orm_values("desired_node", {"realized_device": "unknown-device"}, {})
        finally:
            if prior is None:
                del sys.modules["nautobot.dcim.models"]
            else:
                sys.modules["nautobot.dcim.models"] = prior


try:
    from django.test import TestCase
    from django.core.exceptions import ValidationError
    from nautobot_intent_catalog.models import DesiredComputeInstance, DesiredEndpoint, DesiredNode, DesiredServiceBinding, DesiredServicePlacement, DesiredWorkspace
    from nautobot_intent_catalog.tests.factories import (
        TEST_BINDING_PROFILE,
        make_desired_compute_instance,
        make_desired_compute_platform,
        make_desired_endpoint,
        make_desired_node,
        make_desired_service,
        make_desired_service_binding,
        make_desired_service_placement,
    )
except ImportError:
    pass
else:

    def _make_resolvable_provider(*, protocol="http", port=11434, dns_name=None):
        """Build a DesiredService with exactly one active placement and a usable endpoint."""
        node = make_desired_node()
        endpoint = make_desired_endpoint(
            desired_node=node, protocol=protocol, port=port, dns_name=dns_name or f"{node.slug}.local"
        )
        service = make_desired_service()
        placement = make_desired_service_placement(
            desired_service=service, desired_node=node, desired_endpoint=endpoint, deployment_profile="default"
        )
        return service, placement
    class BatchRuntimeTests(TestCase):
        def _active_lxc_document(self, *, mac_address="02:00:00:00:00:01"):
            platform = make_desired_compute_platform(
                lifecycle="active",
                config={"default_storage": "local-lvm", "default_bridge": "vmbr0"},
            )
            endpoint_values = {
                "ip_policy": "static",
                "ip_address": "192.0.2.101/24",
                "gateway_address": "192.0.2.1",
                "mdns_name": "batch-lxc.local",
            }
            if mac_address is not None:
                endpoint_values["mac_address"] = mac_address
            return {
                "dry_run": False,
                "operations": [
                    {"op": "upsert", "kind": "desired_node", "key": {"slug": "batch-lxc"},
                     "values": {"name": "batch-lxc", "node_type": "container", "lifecycle": "active"}},
                    {"op": "upsert", "kind": "desired_endpoint",
                     "key": {"desired_node": "batch-lxc", "name": "primary", "endpoint_type": "primary"},
                     "values": endpoint_values},
                    {"op": "upsert", "kind": "desired_compute_instance", "key": {"desired_node": "batch-lxc"},
                     "values": {"platform": platform.slug, "instance_kind": "container", "desired_power_state": "running",
                                "vcpus": 1, "memory_mb": 512, "root_disk_gb": 8,
                                "config": {"vmid": 101, "template": "local:vztmpl/example.tar.zst", "unprivileged": True}}},
                ],
            }

        def test_active_lxc_without_mac_rolls_back_with_primary_endpoint_reason(self):
            result = apply_batch(self._active_lxc_document(mac_address=None)).as_dict()

            self.assertEqual(result["transaction"]["status"], "rolled_back")
            self.assertIn("compute_primary_endpoint_missing", result["transaction"]["error"])
            self.assertFalse(DesiredNode.objects.filter(slug="batch-lxc").exists())
            self.assertFalse(DesiredEndpoint.objects.filter(name="primary", mdns_name="batch-lxc.local").exists())
            self.assertFalse(DesiredComputeInstance.objects.filter(config__vmid=101).exists())

        def test_active_lxc_with_mac_commits_all_three_rows_atomically(self):
            result = apply_batch(self._active_lxc_document()).as_dict()

            self.assertEqual(result["transaction"]["status"], "committed")
            node = DesiredNode.objects.get(slug="batch-lxc")
            endpoint = DesiredEndpoint.objects.get(desired_node=node, name="primary")
            instance = DesiredComputeInstance.objects.get(desired_node=node)
            self.assertEqual(endpoint.mac_address, "02:00:00:00:00:01")
            self.assertEqual(instance.config["vmid"], 101)

        def test_dry_run_does_not_write_and_apply_creates_one_service(self):
            document = {"dry_run": True, "operations": [
                {"op": "upsert", "kind": "desired_service", "key": {"slug": "batch-service"},
                 "values": {"name": "batch-service", "lifecycle": "active"}},
            ]}
            from nautobot_intent_catalog.models import DesiredService
            before = DesiredService.objects.filter(slug="batch-service").count()
            self.assertEqual(plan_batch(document).as_dict()["totals"]["create"], 1)
            self.assertEqual(DesiredService.objects.filter(slug="batch-service").count(), before)
            result = apply_batch({**document, "dry_run": False}).as_dict()
            self.assertTrue(result["transaction"]["committed"])
            self.assertEqual(DesiredService.objects.filter(slug="batch-service").count(), before + 1)

        def test_export_shaped_create_with_identity_fields_repeated_in_values_commits(self):
            # Regression: the export document repeats identity fields inside values;
            # the create path used to raise TypeError (duplicate keyword argument),
            # rolling back the whole batch with HTTP 409.
            document = {"dry_run": False, "operations": [
                {"op": "upsert", "kind": "desired_node", "key": {"slug": "export-node"},
                 "values": {"name": "export-node", "slug": "export-node",
                            "node_type": "device", "lifecycle": "planned"}},
                {"op": "upsert", "kind": "desired_endpoint",
                 "key": {"desired_node": "export-node", "name": "primary", "endpoint_type": "primary"},
                 "values": {"desired_node": "export-node", "name": "primary", "endpoint_type": "primary",
                            "ip_policy": "external"}},
            ]}
            result = apply_batch(document).as_dict()
            self.assertEqual(result["transaction"]["status"], "committed")
            node = DesiredNode.objects.get(slug="export-node")
            self.assertTrue(DesiredEndpoint.objects.filter(desired_node=node, name="primary").exists())

        def test_reference_resolves_from_an_earlier_batch_operation(self):
            document = {"dry_run": False, "operations": [
                {"op": "upsert", "kind": "desired_node", "key": {"slug": "batch-node"},
                 "values": {"name": "batch-node", "node_type": "device", "lifecycle": "planned"}},
                {"op": "upsert", "kind": "desired_endpoint",
                 "key": {"desired_node": "batch-node", "name": "primary", "endpoint_type": "primary"},
                 "values": {"ip_policy": "external"}},
            ]}
            result = apply_batch(document).as_dict()
            self.assertTrue(result["transaction"]["committed"])
            self.assertEqual(result["totals"]["create"], 2)

        def test_preview_and_apply_resolve_mixed_existing_and_batch_references(self):
            platform = make_desired_compute_platform()
            document = {"dry_run": True, "operations": [
                {"op": "upsert", "kind": "desired_node", "key": {"slug": "mixed-node"},
                 "values": {"name": "mixed-node", "node_type": "container", "lifecycle": "planned"}},
                {"op": "upsert", "kind": "desired_endpoint",
                 "key": {"desired_node": "mixed-node", "name": "primary", "endpoint_type": "primary"},
                 "values": {"ip_policy": "external"}},
                {"op": "upsert", "kind": "desired_compute_instance", "key": {"desired_node": "mixed-node"},
                 "values": {"platform": platform.slug, "instance_kind": "container", "vcpus": 1,
                            "memory_mb": 512, "root_disk_gb": 8,
                            "config": {"template": "local:vztmpl/example.tar.zst", "unprivileged": True}}},
            ]}
            preview = plan_batch(document).as_dict()
            self.assertEqual(preview["totals"]["create"], 3)
            self.assertEqual(preview["totals"]["conflict"], 0)
            self.assertFalse(DesiredNode.objects.filter(slug="mixed-node").exists())

            result = apply_batch({**document, "dry_run": False}).as_dict()
            self.assertTrue(result["transaction"]["committed"])
            node = DesiredNode.objects.get(slug="mixed-node")
            self.assertTrue(DesiredEndpoint.objects.filter(desired_node=node, name="primary").exists())
            self.assertTrue(DesiredComputeInstance.objects.filter(desired_node=node, platform=platform).exists())

        def test_missing_references_remain_individual_conflicts(self):
            node = DesiredNode.objects.create(name="existing-node", slug="existing-node", lifecycle="planned")
            document = {"dry_run": True, "operations": [
                {"op": "upsert", "kind": "desired_compute_instance", "key": {"desired_node": "missing-node"},
                 "values": {"platform": "missing-platform", "instance_kind": "container", "vcpus": 1,
                            "memory_mb": 512, "root_disk_gb": 8, "config": {}}},
                {"op": "upsert", "kind": "desired_compute_instance", "key": {"desired_node": node.slug},
                 "values": {"platform": "missing-platform", "instance_kind": "container", "vcpus": 1,
                            "memory_mb": 512, "root_disk_gb": 8, "config": {}}},
            ]}
            result = plan_batch(document).as_dict()
            self.assertEqual(result["totals"]["conflict"], 2)
            self.assertIn("unresolved desired_node reference: 'missing-node'", result["operations"][0]["reason"])
            self.assertIn("unresolved platform reference: 'missing-platform'", result["operations"][1]["reason"])

        def test_apply_rolls_back_everything_when_full_clean_fails(self):
            document = {"dry_run": False, "operations": [
                {"op": "upsert", "kind": "desired_node", "key": {"slug": "bad-node"},
                 "values": {"name": "bad-node", "node_type": "not-a-choice", "lifecycle": "planned"}},
            ]}
            result = apply_batch(document).as_dict()
            self.assertEqual(result["transaction"]["status"], "rolled_back")
            self.assertFalse(DesiredNode.objects.filter(slug="bad-node").exists())

        def test_compute_instance_desired_presence_defaults_to_present(self):
            instance = make_desired_compute_instance()
            self.assertEqual(instance.desired_presence, "present")

        def test_atomic_retire_and_absent_batch_commits(self):
            instance = make_desired_compute_instance()
            node = instance.desired_node
            original_platform_id = instance.platform_id
            original_vcpus = instance.vcpus
            document = {
                "dry_run": False,
                "operations": [
                    {
                        "op": "upsert",
                        "kind": "desired_compute_instance",
                        "key": {"desired_node": node.slug},
                        "values": {"desired_presence": "absent"},
                    },
                    {
                        "op": "upsert",
                        "kind": "desired_node",
                        "key": {"slug": node.slug},
                        "values": {"lifecycle": "retired"},
                    },
                ],
            }
            preview = plan_batch({**document, "dry_run": True}).as_dict()
            self.assertEqual([item["action"] for item in preview["operations"]], ["update", "update"])
            self.assertIn("platform", preview["operations"][0]["preserved_fields"])
            self.assertIn("name", preview["operations"][1]["preserved_fields"])

            result = apply_batch(document).as_dict()
            instance.refresh_from_db()
            node.refresh_from_db()
            self.assertEqual(result["transaction"]["status"], "committed")
            self.assertEqual(node.lifecycle, "retired")
            self.assertEqual(instance.desired_presence, "absent")
            self.assertEqual(instance.platform_id, original_platform_id)
            self.assertEqual(instance.vcpus, original_vcpus)

        def test_absent_without_retirement_rolls_back(self):
            instance = make_desired_compute_instance()
            node = instance.desired_node
            result = apply_batch(
                {
                    "dry_run": False,
                    "operations": [
                        {
                            "op": "upsert",
                            "kind": "desired_compute_instance",
                            "key": {"desired_node": node.slug},
                            "values": {"desired_presence": "absent"},
                        }
                    ],
                }
            ).as_dict()
            instance.refresh_from_db()
            self.assertEqual(result["transaction"]["status"], "rolled_back")
            self.assertEqual(instance.desired_presence, "present")
            self.assertIn("desired_presence", result["transaction"]["error"])

        def test_unknown_desired_presence_is_an_ordinary_validation_error(self):
            instance = make_desired_compute_instance()
            instance.desired_presence = "unknown"
            with self.assertRaises(ValidationError) as ctx:
                instance.full_clean()
            self.assertIn("desired_presence", ctx.exception.message_dict)

        def test_absent_rejects_every_non_retired_effective_lifecycle(self):
            instance = make_desired_compute_instance()
            for lifecycle in ("active", "approved", "planned", "deprecated"):
                with self.subTest(lifecycle=lifecycle):
                    instance.desired_node.lifecycle = lifecycle
                    instance.platform.lifecycle = lifecycle
                    instance.desired_presence = "absent"
                    with self.assertRaises(ValidationError) as ctx:
                        instance.full_clean()
                    self.assertIn("desired_presence", ctx.exception.message_dict)

        def test_desired_workspace_create_required_fields_are_enforced(self):
            node = make_desired_node()
            document = {"dry_run": True, "operations": [
                {"op": "upsert", "kind": "desired_workspace", "key": {"slug": "pj-voxel3dprint"},
                 "values": {"name": "pj-voxel3dprint", "desired_node": node.slug}},
            ]}
            result = plan_batch(document).as_dict()
            self.assertEqual(result["operations"][0]["action"], "conflict")
            self.assertIn("expected_path", result["operations"][0]["reason"])
            self.assertIn("source_remote_url", result["operations"][0]["reason"])

        def test_desired_workspace_batch_apply_creates_and_is_readable(self):
            node = make_desired_node()
            document = {"dry_run": False, "operations": [
                {"op": "upsert", "kind": "desired_workspace", "key": {"slug": "pj-voxel3dprint"},
                 "values": {"name": "pj-voxel3dprint", "lifecycle": "active",
                            "source_remote_url": "https://github.com/iwaag/pj-voxel3dprint.git",
                            "desired_node": node.slug, "expected_path": "/home/eiji/projects/pj-voxel3dprint",
                            "desired_presence": "present"}},
            ]}
            result = apply_batch(document).as_dict()
            self.assertTrue(result["transaction"]["committed"])
            workspace = DesiredWorkspace.objects.get(slug="pj-voxel3dprint")
            self.assertEqual(workspace.desired_node_id, node.pk)
            self.assertEqual(workspace.expected_path, "/home/eiji/projects/pj-voxel3dprint")

        def test_deleting_a_node_with_a_desired_workspace_is_blocked_in_the_plan(self):
            node = make_desired_node()
            workspace = DesiredWorkspace.objects.create(
                name="pj-voxel3dprint", slug="pj-voxel3dprint",
                source_remote_url="https://github.com/iwaag/pj-voxel3dprint.git",
                desired_node=node, expected_path="/home/eiji/projects/pj-voxel3dprint",
            )
            document = {"dry_run": True, "operations": [
                {"op": "delete", "kind": "desired_node", "key": {"slug": node.slug}, "values": {}},
            ]}
            result = plan_batch(document).as_dict()
            self.assertEqual(result["operations"][0]["action"], "conflict")
            self.assertIn(f"desired_workspace:{workspace.pk}", result["operations"][0]["reason"])

        def test_retiring_a_node_with_a_desired_workspace_is_rejected(self):
            node = make_desired_node()
            DesiredWorkspace.objects.create(
                name="pj-voxel3dprint", slug="pj-voxel3dprint",
                source_remote_url="https://github.com/iwaag/pj-voxel3dprint.git",
                desired_node=node, expected_path="/home/eiji/projects/pj-voxel3dprint",
            )
            node.lifecycle = DesiredNode.LIFECYCLE_RETIRED
            with self.assertRaises(ValidationError) as ctx:
                node.full_clean()
            self.assertIn("lifecycle", ctx.exception.message_dict)

    class ServiceBindingPerRowValidationTests(TestCase):
        """Step 2 per-row checks: idea-A section 4.7 binding-name declaration, old-key refusal."""

        def test_declared_binding_name_on_a_declared_profile_saves(self):
            binding = make_desired_service_binding()
            self.assertEqual(binding.binding_name, "llm_provider")

        def test_undeclared_binding_name_is_rejected(self):
            placement = make_desired_service_placement(deployment_profile=TEST_BINDING_PROFILE)
            binding = DesiredServiceBinding(
                consumer_placement=placement, binding_name="not-declared", provider_service=make_desired_service()
            )
            with self.assertRaises(ValidationError) as ctx:
                binding.full_clean()
            self.assertIn("binding_name", ctx.exception.message_dict)

        def test_binding_name_declared_elsewhere_is_rejected_on_a_profile_without_it(self):
            placement = make_desired_service_placement(deployment_profile="default")
            binding = DesiredServiceBinding(
                consumer_placement=placement, binding_name="llm_provider", provider_service=make_desired_service()
            )
            with self.assertRaises(ValidationError) as ctx:
                binding.full_clean()
            self.assertIn("binding_name", ctx.exception.message_dict)

        def test_declared_profile_placement_config_refuses_the_old_key(self):
            placement = DesiredServicePlacement(
                desired_service=make_desired_service(),
                desired_node=make_desired_service_placement(deployment_profile=TEST_BINDING_PROFILE).desired_node,
                instance_name="second-instance",
                deployment_profile=TEST_BINDING_PROFILE,
                config_schema_version="1",
                config={"llm_provider_service": "ollama"},
            )
            with self.assertRaises(ValidationError) as ctx:
                placement.full_clean()
            self.assertIn("config", ctx.exception.message_dict)
            self.assertIn("llm_provider_service", ctx.exception.message_dict["config"][0])

        def test_declared_profile_placement_config_without_the_old_key_saves(self):
            placement = make_desired_service_placement(deployment_profile=TEST_BINDING_PROFILE, config={"other_key": "value"})
            self.assertEqual(placement.config, {"other_key": "value"})

        def test_apply_batch_creates_a_binding_via_the_batch_endpoint(self):
            placement = make_desired_service_placement(deployment_profile=TEST_BINDING_PROFILE)
            service, _provider_placement = _make_resolvable_provider()
            document = {
                "dry_run": False,
                "operations": [
                    {
                        "op": "upsert",
                        "kind": "desired_service_binding",
                        "key": {
                            "consumer_placement": {
                                "desired_service": placement.desired_service.slug,
                                "instance_name": placement.instance_name,
                            },
                            "binding_name": "llm_provider",
                        },
                        "values": {"provider_service": service.slug},
                    },
                ],
            }
            result = apply_batch(document).as_dict()
            self.assertEqual(result["transaction"]["status"], "committed")
            binding = DesiredServiceBinding.objects.get(consumer_placement=placement, binding_name="llm_provider")
            self.assertEqual(binding.provider_service_id, service.pk)

        def test_apply_batch_rejects_reintroducing_the_old_config_key(self):
            placement = make_desired_service_placement(deployment_profile=TEST_BINDING_PROFILE)
            document = {
                "dry_run": False,
                "operations": [
                    {
                        "op": "upsert",
                        "kind": "desired_service_placement",
                        "key": {"desired_service": placement.desired_service.slug, "instance_name": placement.instance_name},
                        "values": {"config": {"llm_provider_service": "ollama"}},
                    },
                ],
            }
            result = apply_batch(document).as_dict()
            self.assertEqual(result["transaction"]["status"], "rolled_back")
            self.assertIn("llm_provider_service", result["transaction"]["error"])

    class ServiceBindingGraphInvariantTests(TestCase):
        """Step 3: final-state idea-A section 4/8 invariants, enforced inside apply_batch."""

        @staticmethod
        def _trigger_validation(service):
            """A trivially valid no-op apply, just to run the post-write graph validator."""
            document = {
                "dry_run": False,
                "operations": [
                    {"op": "upsert", "kind": "desired_service", "key": {"slug": service.slug},
                     "values": {"lifecycle": service.lifecycle}},
                ],
            }
            return apply_batch(document).as_dict()

        def test_fully_resolvable_binding_commits(self):
            service, _placement = _make_resolvable_provider()
            consumer = make_desired_service_placement(deployment_profile=TEST_BINDING_PROFILE)
            make_desired_service_binding(consumer_placement=consumer, provider_service=service)

            result = self._trigger_validation(service)
            self.assertEqual(result["transaction"]["status"], "committed")

        def test_ambiguous_provider_is_rejected(self):
            service, placement_a = _make_resolvable_provider()
            _service_b, placement_b = _make_resolvable_provider()
            placement_b.desired_service = service
            placement_b.full_clean()
            placement_b.save()
            consumer = make_desired_service_placement(deployment_profile=TEST_BINDING_PROFILE)
            make_desired_service_binding(consumer_placement=consumer, provider_service=service)

            result = self._trigger_validation(service)
            self.assertEqual(result["transaction"]["status"], "rolled_back")
            self.assertIn("ambiguous", result["transaction"]["error"])
            self.assertIn(placement_a.instance_name, result["transaction"]["error"])
            self.assertIn(placement_b.instance_name, result["transaction"]["error"])

        def test_unusable_endpoint_is_rejected(self):
            service = make_desired_service()
            placement = make_desired_service_placement(desired_service=service)  # no desired_endpoint
            consumer = make_desired_service_placement(deployment_profile=TEST_BINDING_PROFILE)
            make_desired_service_binding(consumer_placement=consumer, provider_service=service)

            result = self._trigger_validation(service)
            self.assertEqual(result["transaction"]["status"], "rolled_back")
            self.assertIn("unresolved provider binding", result["transaction"]["error"])
            self.assertIn(placement.desired_service.slug, result["transaction"]["error"])

        def test_self_reference_is_rejected(self):
            service, placement = _make_resolvable_provider()
            placement.deployment_profile = TEST_BINDING_PROFILE
            placement.full_clean()
            placement.save()
            make_desired_service_binding(consumer_placement=placement, provider_service=service)

            result = self._trigger_validation(service)
            self.assertEqual(result["transaction"]["status"], "rolled_back")
            self.assertIn("own consumer placement", result["transaction"]["error"])

        def test_cycle_is_rejected(self):
            service_1, placement_1 = _make_resolvable_provider()
            service_2, placement_2 = _make_resolvable_provider()
            placement_1.deployment_profile = TEST_BINDING_PROFILE
            placement_1.full_clean()
            placement_1.save()
            placement_2.deployment_profile = TEST_BINDING_PROFILE
            placement_2.full_clean()
            placement_2.save()
            make_desired_service_binding(consumer_placement=placement_1, provider_service=service_2)
            make_desired_service_binding(consumer_placement=placement_2, provider_service=service_1)

            result = self._trigger_validation(service_1)
            self.assertEqual(result["transaction"]["status"], "rolled_back")
            self.assertIn("cycle", result["transaction"]["error"])

        def test_retiring_a_provider_with_an_inbound_binding_is_rejected_with_the_inbound_set(self):
            service, placement = _make_resolvable_provider()
            consumer = make_desired_service_placement(deployment_profile=TEST_BINDING_PROFILE)
            make_desired_service_binding(consumer_placement=consumer, provider_service=service)
            committed = self._trigger_validation(service)
            self.assertEqual(committed["transaction"]["status"], "committed")

            document = {
                "dry_run": False,
                "operations": [
                    {"op": "upsert", "kind": "desired_service", "key": {"slug": service.slug},
                     "values": {"lifecycle": "retired"}},
                ],
            }
            result = apply_batch(document).as_dict()
            self.assertEqual(result["transaction"]["status"], "rolled_back")
            error = result["transaction"]["error"]
            self.assertIn("provider:", error)
            self.assertIn(service.slug, error)
            self.assertIn(
                f"{consumer.desired_node.slug} / {consumer.desired_service.slug} / llm_provider", error
            )
            service.refresh_from_db()
            self.assertEqual(service.lifecycle, "active")

        def test_deactivating_the_sole_active_provider_placement_is_rejected(self):
            service, placement = _make_resolvable_provider()
            consumer = make_desired_service_placement(deployment_profile=TEST_BINDING_PROFILE)
            make_desired_service_binding(consumer_placement=consumer, provider_service=service)
            committed = self._trigger_validation(service)
            self.assertEqual(committed["transaction"]["status"], "committed")

            document = {
                "dry_run": False,
                "operations": [
                    {"op": "upsert", "kind": "desired_service_placement",
                     "key": {"desired_service": service.slug, "instance_name": placement.instance_name},
                     "values": {"desired_state": "disabled"}},
                ],
            }
            result = apply_batch(document).as_dict()
            self.assertEqual(result["transaction"]["status"], "rolled_back")
            self.assertIn("unresolved provider binding", result["transaction"]["error"])
            placement.refresh_from_db()
            self.assertEqual(placement.desired_state, "active")

        def test_deleting_a_provider_service_with_an_inbound_binding_is_blocked_in_the_plan(self):
            service, _placement = _make_resolvable_provider()
            consumer = make_desired_service_placement(deployment_profile=TEST_BINDING_PROFILE)
            binding = make_desired_service_binding(consumer_placement=consumer, provider_service=service)

            document = {
                "dry_run": True,
                "operations": [
                    {"op": "delete", "kind": "desired_service", "key": {"slug": service.slug}, "values": {}},
                ],
            }
            result = plan_batch(document).as_dict()
            self.assertEqual(result["operations"][0]["action"], "conflict")
            self.assertIn(f"desired_service_binding:{binding.pk}", result["operations"][0]["reason"])
