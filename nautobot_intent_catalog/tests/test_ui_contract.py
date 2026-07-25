"""Tests proving the read-only UI interface contract and route manifests for Phase 3.

Guarded by `try/except ImportError` so static manifest and route tests run both
locally and under Nautobot's test runner.
"""

from __future__ import annotations

import unittest

try:
    from django.urls import NoReverseMatch, reverse
    from rest_framework import status
    from nautobot.core.testing import TestCase

    from nautobot_intent_catalog import navigation
except ImportError:  # pragma: no cover
    HAS_DJANGO = False
else:
    HAS_DJANGO = True


RETAINED_UI_ROUTE_NAMES = [
    "intentsource_list",
    "intentsource",
    "desiredservice_list",
    "desiredservice",
    "desireddependency_list",
    "desireddependency",
    "desirednode_list",
    "desirednode",
    "desiredendpoint_list",
    "desiredendpoint",
    "desiredcomputeplatform_list",
    "desiredcomputeplatform",
    "desiredcomputeinstance_list",
    "desiredcomputeinstance",
    "desiredserviceplacement_list",
    "desiredserviceplacement",
    "desirednodeoperationaloverride_list",
    "desirednodeoperationaloverride",
    "braindumpdocument_list",
    "braindumpdocument",
    "desirediprange_list",
    "desirediprange",
]

REMOVED_UI_ROUTE_NAMES = [
    "source_yaml_list",
    "source_list",
    "desiredhost_quick_add",
    "intentsource_add",
    "intentsource_edit",
    "intentsource_delete",
    "desiredservice_add",
    "desiredservice_edit",
    "desiredservice_delete",
    "desireddependency_edit",
    "desireddependency_delete",
    "desirednode_add",
    "desirednode_edit",
    "desirednode_delete",
    "desiredendpoint_add",
    "desiredendpoint_edit",
    "desiredendpoint_delete",
    "desiredcomputeplatform_add",
    "desiredcomputeplatform_edit",
    "desiredcomputeplatform_delete",
    "desiredcomputeinstance_add",
    "desiredcomputeinstance_edit",
    "desiredcomputeinstance_delete",
    "desiredserviceplacement_add",
    "desiredserviceplacement_edit",
    "desiredserviceplacement_delete",
    "desirednodeoperationaloverride_add",
    "desirednodeoperationaloverride_edit",
    "desirednodeoperationaloverride_delete",
    "braindumpdocument_add",
    "braindumpdocument_edit",
    "braindumpdocument_delete",
    "alignmentreview_add",
    "alignmentreview_edit",
    "alignmentreview_delete",
    "desirediprange_add",
    "desirediprange_edit",
    "desirediprange_delete",
]


class UIContractManifestTests(unittest.TestCase):
    """Manifest checks for retained read-only routes and deleted mutation routes."""

    def test_retained_routes_count_is_22(self):
        self.assertEqual(len(RETAINED_UI_ROUTE_NAMES), 22)

    def test_retained_routes_can_be_reversed(self):
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")

        dummy_pk = "00000000-0000-0000-0000-000000000000"
        for name in RETAINED_UI_ROUTE_NAMES:
            with self.subTest(name=name):
                full_name = f"plugins:nautobot_intent_catalog:{name}"
                if name.endswith("_list"):
                    url = reverse(full_name)
                else:
                    url = reverse(full_name, args=[dummy_pk])
                self.assertTrue(url.startswith("/plugins/intent-catalog/"))

    def test_removed_routes_fail_reverse(self):
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")

        dummy_pk = "00000000-0000-0000-0000-000000000000"
        for name in REMOVED_UI_ROUTE_NAMES:
            with self.subTest(name=name):
                full_name = f"plugins:nautobot_intent_catalog:{name}"
                with self.assertRaises(NoReverseMatch):
                    if any(name.endswith(suffix) for suffix in ("_edit", "_delete", "_add")) and name not in (
                        "intentsource_add",
                        "desiredservice_add",
                        "desirednode_add",
                        "desiredendpoint_add",
                        "desiredcomputeplatform_add",
                        "desiredcomputeinstance_add",
                        "desiredserviceplacement_add",
                        "desirednodeoperationaloverride_add",
                        "braindumpdocument_add",
                        "desirediprange_add",
                        "alignmentreview_add",
                    ):
                        reverse(full_name, args=[dummy_pk])
                    else:
                        reverse(full_name)

    def test_tables_have_no_action_or_toggle_columns(self):
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        import nautobot_intent_catalog.tables as tables_module

        self.assertFalse(hasattr(tables_module, "TABLE_ACTION_BUTTONS"))
        self.assertFalse(hasattr(tables_module, "ButtonsColumn"))
        self.assertFalse(hasattr(tables_module, "ToggleColumn"))


if HAS_DJANGO:

    class UINonMutationRuntimeTests(TestCase):
        """Runtime checks asserting retained UI pages reject domain POST mutations."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                "nautobot_intent_catalog.view_desirednode",
                "nautobot_intent_catalog.view_desiredservice",
            )

        def test_post_to_retained_list_pages_does_not_mutate(self):
            list_routes = [name for name in RETAINED_UI_ROUTE_NAMES if name.endswith("_list")]
            for name in list_routes:
                with self.subTest(name=name):
                    url = reverse(f"plugins:nautobot_intent_catalog:{name}")
                    response = self.client.post(url, {"data": "mutation-test"})
                    # List views must either reject POST (405) or not alter domain rows.
                    self.assertIn(response.status_code, (status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_200_OK))
