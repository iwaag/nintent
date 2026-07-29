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
    def test_endpoint_projection_includes_gateway_address(self) -> None:
        self.assertIn("gateway_address", jobs.DESIRED_ENDPOINT_UPDATE_FIELD_NAMES)

    def test_validated_upsert_split_is_idempotent_for_matching_update_fields(self) -> None:
        row = _FakeObject(pk="existing-id", value="same")
        model = _fake_model([row])

        result = jobs._validated_upsert_split(
            model, {"key": "identity"}, {"value": "same"}, {"value": "same"}
        )

        self.assertIs(result, row)
        self.assertFalse(row.cleaned)
        self.assertFalse(row.saved)

    def test_validated_upsert_split_validates_before_create_or_update(self) -> None:
        existing = _FakeObject(pk="existing-id", value="old")
        update_model = _fake_model([existing])

        updated = jobs._validated_upsert_split(
            update_model, {"key": "identity"}, {"value": "new"}, {"value": "new"}
        )

        self.assertTrue(updated.cleaned)
        self.assertTrue(updated.saved)

        create_model = _fake_model([])
        created = jobs._validated_upsert_split(
            create_model, {"key": "identity"}, {"value": "new"}, {"value": "new"}
        )
        self.assertTrue(created.cleaned)
        self.assertTrue(created.saved)

    def test_validated_upsert_split_never_touches_a_preserved_field(self) -> None:
        # `update_fields` deliberately omits `lifecycle` (DesiredNode ownership split); a
        # differing YAML-side value must never reach the object at all.
        existing = _FakeObject(pk="existing-id", name="old", lifecycle="approved")
        model = _fake_model([existing])

        jobs._validated_upsert_split(
            model,
            {"key": "identity"},
            {"name": "new", "lifecycle": "active"},
            {"name": "new"},
        )

        self.assertEqual(existing.name, "new")
        self.assertEqual(existing.lifecycle, "approved")

    def test_validated_upsert_split_raises_on_locked_field_disagreement(self) -> None:
        existing = _FakeObject(pk="existing-id", name="renamed", lifecycle="active")
        model = _fake_model([existing])

        with self.assertRaises(ValueError):
            jobs._validated_upsert_split(
                model,
                {"key": "identity"},
                {"name": "prometheus", "lifecycle": "active"},
                {"lifecycle": "active"},
                locked_fields={"name": "prometheus"},
            )

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


class ImportSourceInfoAndCountsTests(unittest.TestCase):
    def test_import_counts_by_root_covers_every_canonical_root(self) -> None:
        load_result = SimpleNamespace(
            intent_sources=[1, 2],
            desired_nodes=[1],
            desired_endpoints=[],
            desired_ip_ranges=[1, 2, 3],
            desired_compute_platforms=[],
            desired_compute_instances=[],
            desired_services=[1, 2, 3, 4, 5, 6],
            desired_service_placements=[1],
            desired_node_operational_overrides=[],
        )

        counts = jobs._import_counts_by_root(load_result)

        self.assertEqual(
            counts,
            {
                "intent_sources": 2,
                "desired_nodes": 1,
                "desired_endpoints": 0,
                "desired_ip_ranges": 3,
                "desired_compute_platforms": 0,
                "desired_compute_instances": 0,
                "desired_services": 6,
                "desired_service_placements": 1,
                "desired_node_operational_overrides": 0,
            },
        )

    def test_project_returns_only_requested_keys_json_safe(self) -> None:
        class _Id:
            def __str__(self) -> str:
                return "uuid-value"

        row = {"name": "agpc", "lifecycle": "active", "pk": _Id(), "extra": "ignored"}

        self.assertEqual(
            jobs._project(row, {"name": None, "lifecycle": None}),
            {"name": "agpc", "lifecycle": "active"},
        )
        self.assertEqual(jobs._project(None, {"name": None}), {})


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
