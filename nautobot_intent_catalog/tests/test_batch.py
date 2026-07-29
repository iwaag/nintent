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
