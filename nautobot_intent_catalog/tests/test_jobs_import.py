from __future__ import annotations

import unittest
from types import SimpleNamespace

from nautobot_intent_catalog import jobs


class _FakeObject:
    def __init__(self, **values):
        self.pk = values.pop("pk", None)
        self.cleaned = False
        self.saved = False
        for key, value in values.items():
            setattr(self, key, value)

    def full_clean(self):
        self.cleaned = True

    def save(self):
        self.saved = True
        self.pk = self.pk or "created-id"


class _FakeQuerySet:
    def __init__(self, rows):
        self.rows = list(rows)

    def count(self):
        return len(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def get(self):
        if len(self.rows) != 1:
            raise LookupError("not exactly one row")
        return self.rows[0]


class _FakeManager:
    def __init__(self, rows):
        self.rows = rows
        self.last_filter = None

    def filter(self, **values):
        self.last_filter = values
        return _FakeQuerySet(self.rows)


def _fake_model(rows):
    class FakeModel(_FakeObject):
        objects = _FakeManager(rows)

    return FakeModel


class StrictImportHelperTests(unittest.TestCase):
    def test_validated_upsert_is_idempotent_for_matching_defaults(self) -> None:
        row = _FakeObject(pk="existing-id", value="same")
        model = _fake_model([row])

        status, result = jobs._validated_upsert(model, {"key": "identity"}, {"value": "same"})

        self.assertEqual(status, "unchanged")
        self.assertIs(result, row)
        self.assertFalse(row.cleaned)
        self.assertFalse(row.saved)

    def test_validated_upsert_validates_before_create_or_update(self) -> None:
        existing = _FakeObject(pk="existing-id", value="old")
        update_model = _fake_model([existing])

        status, _result = jobs._validated_upsert(
            update_model,
            {"key": "identity"},
            {"value": "new"},
        )

        self.assertEqual(status, "updated")
        self.assertTrue(existing.cleaned)
        self.assertTrue(existing.saved)

        create_model = _fake_model([])
        status, created = jobs._validated_upsert(
            create_model,
            {"key": "identity"},
            {"value": "new"},
        )
        self.assertEqual(status, "created")
        self.assertTrue(created.cleaned)
        self.assertTrue(created.saved)

    def test_endpoint_resolution_is_always_scoped_to_selected_node(self) -> None:
        endpoint = SimpleNamespace(pk="endpoint-id")
        model = _fake_model([endpoint])
        original = getattr(jobs, "DesiredEndpoint", None)
        jobs.DesiredEndpoint = model
        node = SimpleNamespace(pk="node-id")
        try:
            result = jobs._resolve_desired_endpoint(
                node,
                {"name": "primary", "endpoint_type": "primary"},
                required=True,
            )
        finally:
            if original is None:
                del jobs.DesiredEndpoint
            else:
                jobs.DesiredEndpoint = original

        self.assertIs(result, endpoint)
        self.assertEqual(
            model.objects.last_filter,
            {"desired_node": node, "name": "primary", "endpoint_type": "primary"},
        )

    def test_service_resolution_uses_the_complete_qualified_identity(self) -> None:
        service = SimpleNamespace(pk="service-id")
        model = _fake_model([service])
        original = getattr(jobs, "DesiredService", None)
        jobs.DesiredService = model
        reference = {
            "intent_source": "infrastructure",
            "catalog_namespace": "default",
            "catalog_metadata_name": "dnsmasq",
            "service_type": "service",
        }
        try:
            result = jobs._resolve_desired_service(reference)
        finally:
            if original is None:
                del jobs.DesiredService
            else:
                jobs.DesiredService = original

        self.assertIs(result, service)
        self.assertEqual(
            model.objects.last_filter,
            {
                "intent_source__slug": "infrastructure",
                "catalog_namespace": "default",
                "catalog_metadata_name": "dnsmasq",
                "service_type": "service",
            },
        )


class ValidatedUpsertDiffTests(unittest.TestCase):
    def test_create_reports_every_field_with_old_none(self) -> None:
        model = _fake_model([])

        status, obj, changed = jobs._validated_upsert_diff(
            model,
            {"slug": "aghub-pve"},
            {"name": "aghub Proxmox", "lifecycle": "active"},
        )

        self.assertEqual(status, "created")
        self.assertEqual(obj.name, "aghub Proxmox")
        self.assertEqual(
            changed,
            {
                "name": {"old": None, "new": "aghub Proxmox"},
                "lifecycle": {"old": None, "new": "active"},
            },
        )

    def test_update_reports_only_the_changed_fields(self) -> None:
        existing = _FakeObject(pk="existing-id", name="old name", lifecycle="active")
        model = _fake_model([existing])

        status, obj, changed = jobs._validated_upsert_diff(
            model,
            {"slug": "aghub-pve"},
            {"name": "new name", "lifecycle": "active"},
        )

        self.assertEqual(status, "updated")
        self.assertEqual(changed, {"name": {"old": "old name", "new": "new name"}})
        self.assertIs(obj, existing)

    def test_unchanged_reports_an_empty_diff(self) -> None:
        existing = _FakeObject(pk="existing-id", name="same", lifecycle="active")
        model = _fake_model([existing])

        status, obj, changed = jobs._validated_upsert_diff(
            model,
            {"slug": "aghub-pve"},
            {"name": "same", "lifecycle": "active"},
        )

        self.assertEqual(status, "unchanged")
        self.assertEqual(changed, {})
        self.assertFalse(existing.cleaned)
        self.assertFalse(existing.saved)


class ResolveDesiredComputePlatformTests(unittest.TestCase):
    def test_resolution_is_scoped_by_slug(self) -> None:
        platform = SimpleNamespace(pk="platform-id")
        model = _fake_model([platform])
        original = getattr(jobs, "DesiredComputePlatform", None)
        jobs.DesiredComputePlatform = model
        try:
            result = jobs._resolve_desired_compute_platform("aghub-pve")
        finally:
            if original is None:
                del jobs.DesiredComputePlatform
            else:
                jobs.DesiredComputePlatform = original

        self.assertIs(result, platform)
        self.assertEqual(model.objects.last_filter, {"slug": "aghub-pve"})


class JsonSafeTests(unittest.TestCase):
    def test_json_safe_converts_non_primitive_values_to_strings(self) -> None:
        class _Id:
            def __str__(self) -> str:
                return "abc-123"

        result = jobs._json_safe({"a": [1, _Id(), None, True], "b": {"c": _Id()}})

        self.assertEqual(result, {"a": [1, "abc-123", None, True], "b": {"c": "abc-123"}})


if __name__ == "__main__":
    unittest.main()
