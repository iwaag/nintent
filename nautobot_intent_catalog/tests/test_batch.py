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

    def test_rejects_the_removed_legacy_desired_service_identity(self):
        with self.assertRaises(BatchValidationError):
            decode_batch({"dry_run": True, "operations": [
                {
                    "op": "upsert",
                    "kind": "desired_service",
                    "key": {
                        "intent" + "_source": "manual",
                        "catalog" + "_namespace": "default",
                        "catalog" + "_metadata_name": "example-service",
                        "service" + "_type": "service",
                    },
                    "values": {"name": "example-service", "slug": "example-service"},
                },
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
    from nautobot_intent_catalog.models import DesiredComputeInstance, DesiredEndpoint, DesiredNode
    from nautobot_intent_catalog.tests.factories import make_desired_compute_instance, make_desired_compute_platform
except ImportError:
    pass
else:
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
