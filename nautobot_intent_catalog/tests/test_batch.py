"""Django-free contract tests for desired-state batch request decoding."""

import unittest

from nautobot_intent_catalog.batch import BatchValidationError, apply_batch, decode_batch, plan_batch


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
                {"op": "delete", "kind": "intent_source", "key": {"slug": "a"}, "values": {}},
                {"op": "delete", "kind": "intent_source", "key": {"slug": "a"}, "values": {}},
            ]})

    def test_plan_is_deterministic(self):
        document = {"dry_run": True, "operations": [
            {"op": "delete", "kind": "intent_source", "key": {"slug": "a"}, "values": {}},
        ]}
        self.assertEqual(plan_batch(document).as_dict(), plan_batch(document).as_dict())


try:
    from django.test import TestCase
    from nautobot_intent_catalog.models import IntentSource
except ImportError:
    pass
else:
    class BatchRuntimeTests(TestCase):
        def test_dry_run_does_not_write_and_apply_creates_one_row(self):
            document = {"dry_run": True, "operations": [
                {"op": "upsert", "kind": "intent_source", "key": {"slug": "batch-source"}, "values": {}},
            ]}
            before = IntentSource.objects.filter(slug="batch-source").count()
            self.assertEqual(plan_batch(document).as_dict()["totals"]["create"], 1)
            self.assertEqual(IntentSource.objects.filter(slug="batch-source").count(), before)
            result = apply_batch({**document, "dry_run": False}).as_dict()
            self.assertTrue(result["transaction"]["committed"])
            self.assertEqual(IntentSource.objects.filter(slug="batch-source").count(), before + 1)

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

        def test_apply_rolls_back_everything_when_full_clean_fails(self):
            document = {"dry_run": False, "operations": [
                {"op": "upsert", "kind": "intent_source", "key": {"slug": "rollback-source"}, "values": {}},
                {"op": "upsert", "kind": "desired_node", "key": {"slug": "bad-node"},
                 "values": {"name": "bad-node", "node_type": "not-a-choice", "lifecycle": "planned"}},
            ]}
            result = apply_batch(document).as_dict()
            self.assertEqual(result["transaction"]["status"], "rolled_back")
            self.assertFalse(IntentSource.objects.filter(slug="rollback-source").exists())
