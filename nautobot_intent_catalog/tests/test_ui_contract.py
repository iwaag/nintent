"""Tests proving the read-only UI interface contract and route manifests for Phase 3/4.

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

assert len(REMOVED_UI_ROUTE_NAMES) == 38, len(REMOVED_UI_ROUTE_NAMES)

# Literal URL prefix (relative to `/plugins/intent-catalog/`) for each retained model's list
# route, and whether that model ever had a removed `.../add/` route (DesiredDependency rows are
# only ever produced by analysis, so it never had one).
MODEL_URL_PREFIXES = {
    "intentsource_list": ("sources", True),
    "desiredservice_list": ("services", True),
    "desireddependency_list": ("dependencies", False),
    "desirednode_list": ("nodes", True),
    "desiredendpoint_list": ("endpoints", True),
    "desiredcomputeplatform_list": ("compute-platforms", True),
    "desiredcomputeinstance_list": ("compute-instances", True),
    "desiredserviceplacement_list": ("placements", True),
    "desirednodeoperationaloverride_list": ("operational-overrides", True),
    "braindumpdocument_list": ("braindumps", True),
    "desirediprange_list": ("ip-ranges", True),
}


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

    def test_removed_literal_paths_404_for_every_family(self):
        """Every former `.../add/`, `.../<pk>/edit/`, `.../<pk>/delete/` path 404s.

        Runs unauthenticated (Nautobot's LoginRequiredMiddleware still returns a redirect to
        login, not a 404, for a URL that *does* resolve -- so a passing 404 here proves the URL
        genuinely fails to resolve, independent of auth). `source_yaml_list`/`source_list`/
        `desiredhost_quick_add` literal aliases are covered directly below.
        """
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        dummy_pk = "00000000-0000-0000-0000-000000000000"
        from django.test import Client

        client = Client()
        for list_name, (prefix, has_add) in MODEL_URL_PREFIXES.items():
            base = f"/plugins/intent-catalog/{prefix}"
            paths = [f"{base}/{dummy_pk}/edit/", f"{base}/{dummy_pk}/delete/"]
            if has_add:
                paths.append(f"{base}/add/")
            for path in paths:
                with self.subTest(path=path):
                    self.assertEqual(client.get(path).status_code, 404)

    def test_removed_utility_paths_404(self):
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        from django.test import Client

        client = Client()
        for path in (
            "/plugins/intent-catalog/sources/yaml/",
            "/plugins/intent-catalog/nodes/quick-add/",
        ):
            with self.subTest(path=path):
                self.assertEqual(client.get(path).status_code, 404)

    def test_tables_have_no_action_or_toggle_columns(self):
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        import nautobot_intent_catalog.tables as tables_module

        self.assertFalse(hasattr(tables_module, "TABLE_ACTION_BUTTONS"))
        self.assertFalse(hasattr(tables_module, "ButtonsColumn"))
        self.assertFalse(hasattr(tables_module, "ToggleColumn"))

    def test_navigation_only_links_the_eleven_retained_lists(self):
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        linked = {
            item.link
            for tab in navigation.menu_items
            for group in tab.groups
            for item in group.items
        }
        expected = {
            reverse(f"plugins:nautobot_intent_catalog:{name}")
            for name in RETAINED_UI_ROUTE_NAMES
            if name.endswith("_list")
        }
        self.assertEqual(linked, expected)


if HAS_DJANGO:
    from nautobot_intent_catalog import models as _models
    from nautobot_intent_catalog.tests.factories import (
        make_braindump,
        make_desired_compute_instance,
        make_desired_compute_platform,
        make_desired_dependency,
        make_desired_endpoint,
        make_desired_ip_range,
        make_desired_node,
        make_desired_node_operational_override,
        make_desired_service,
        make_desired_service_placement,
        make_intent_source,
    )

    # One entry per retained model: list/detail route names, the model class, its factory, and
    # a distinctive field expected to render on both the list (htmx) and detail page.
    RUNTIME_MODEL_MATRIX = [
        {
            "list": "intentsource_list",
            "detail": "intentsource",
            "model": _models.IntentSource,
            "factory": make_intent_source,
            "label_field": "name",
        },
        {
            "list": "desiredservice_list",
            "detail": "desiredservice",
            "model": _models.DesiredService,
            "factory": make_desired_service,
            "label_field": "display_name",
        },
        {
            "list": "desireddependency_list",
            "detail": "desireddependency",
            "model": _models.DesiredDependency,
            "factory": make_desired_dependency,
            "label_field": "name",
        },
        {
            "list": "desirednode_list",
            "detail": "desirednode",
            "model": _models.DesiredNode,
            "factory": make_desired_node,
            "label_field": "name",
        },
        {
            "list": "desiredendpoint_list",
            "detail": "desiredendpoint",
            "model": _models.DesiredEndpoint,
            "factory": make_desired_endpoint,
            "label_field": "name",
        },
        {
            "list": "desiredcomputeplatform_list",
            "detail": "desiredcomputeplatform",
            "model": _models.DesiredComputePlatform,
            "factory": make_desired_compute_platform,
            "label_field": "name",
        },
        {
            "list": "desiredcomputeinstance_list",
            "detail": "desiredcomputeinstance",
            "model": _models.DesiredComputeInstance,
            "factory": make_desired_compute_instance,
            # Rendered as its humanized choice label ("Container"), not the raw stored value
            # ("container").
            "label_field": "get_instance_kind_display",
        },
        {
            "list": "desiredserviceplacement_list",
            "detail": "desiredserviceplacement",
            "model": _models.DesiredServicePlacement,
            "factory": make_desired_service_placement,
            "label_field": "instance_name",
        },
        {
            "list": "desirednodeoperationaloverride_list",
            "detail": "desirednodeoperationaloverride",
            "model": _models.DesiredNodeOperationalOverride,
            "factory": make_desired_node_operational_override,
            "label_field": "desired_node",
        },
        {
            "list": "braindumpdocument_list",
            "detail": "braindumpdocument",
            "model": _models.BrainDumpDocument,
            "factory": make_braindump,
            "label_field": "title",
        },
        {
            "list": "desirediprange_list",
            "detail": "desirediprange",
            "model": _models.DesiredIPRange,
            "factory": make_desired_ip_range,
            "label_field": "name",
        },
    ]

    class UIRuntimeRenderTests(TestCase):
        """Runtime fixture/render matrix: every retained list/detail pair renders (item 4/5)."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                *[
                    f"nautobot_intent_catalog.view_{entry['model']._meta.model_name}"
                    for entry in RUNTIME_MODEL_MATRIX
                ]
            )

        def test_every_retained_list_and_detail_renders(self):
            for entry in RUNTIME_MODEL_MATRIX:
                with self.subTest(model=entry["model"].__name__):
                    instance = entry["factory"]()
                    label = None
                    if entry["label_field"]:
                        label = getattr(instance, entry["label_field"])
                        if callable(label):
                            label = label()
                        label = str(label)

                    list_url = reverse(f"plugins:nautobot_intent_catalog:{entry['list']}")
                    list_response = self.client.get(list_url, HTTP_HX_REQUEST="true")
                    self.assertEqual(list_response.status_code, 200)
                    if label is not None:
                        self.assertContains(list_response, label)

                    detail_response = self.client.get(instance.get_absolute_url())
                    self.assertEqual(detail_response.status_code, 200)
                    if label is not None:
                        self.assertContains(detail_response, label)

    class UINonMutationRuntimeTests(TestCase):
        """Per-model view-only permission grant; retained pages reject/ignore POST mutations."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                *[
                    f"nautobot_intent_catalog.view_{entry['model']._meta.model_name}"
                    for entry in RUNTIME_MODEL_MATRIX
                ]
            )

        def test_post_to_retained_list_pages_does_not_mutate(self):
            for entry in RUNTIME_MODEL_MATRIX:
                with self.subTest(model=entry["model"].__name__):
                    before_count = entry["model"].objects.count()
                    url = reverse(f"plugins:nautobot_intent_catalog:{entry['list']}")
                    response = self.client.post(url, {"data": "mutation-test"})
                    # List views must either reject POST (405) or not alter domain rows.
                    self.assertIn(response.status_code, (status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_200_OK))
                    self.assertEqual(entry["model"].objects.count(), before_count)

        def test_post_to_retained_detail_pages_does_not_mutate_the_row(self):
            for entry in RUNTIME_MODEL_MATRIX:
                with self.subTest(model=entry["model"].__name__):
                    instance = entry["factory"]()
                    before = {
                        field.name: getattr(instance, field.name)
                        for field in entry["model"]._meta.fields
                        if field.name not in ("last_updated",)
                    }
                    response = self.client.post(instance.get_absolute_url(), {"data": "mutation-test"})
                    self.assertIn(response.status_code, (status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_200_OK))
                    instance.refresh_from_db()
                    after = {
                        field.name: getattr(instance, field.name)
                        for field in entry["model"]._meta.fields
                        if field.name not in ("last_updated",)
                    }
                    self.assertEqual(before, after)

    class UIMissingPermissionRuntimeTests(TestCase):
        """A user with zero nintent permissions is denied every retained list/detail page."""

        def test_list_and_detail_require_their_own_view_permission(self):
            for entry in RUNTIME_MODEL_MATRIX:
                with self.subTest(model=entry["model"].__name__):
                    instance = entry["factory"]()
                    list_url = reverse(f"plugins:nautobot_intent_catalog:{entry['list']}")
                    self.assertIn(
                        self.client.get(list_url, HTTP_HX_REQUEST="true").status_code,
                        (status.HTTP_403_FORBIDDEN, 302),
                    )
                    self.assertIn(
                        self.client.get(instance.get_absolute_url()).status_code,
                        (status.HTTP_403_FORBIDDEN, 302),
                    )
