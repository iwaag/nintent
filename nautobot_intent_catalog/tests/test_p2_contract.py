"""Nautobot-runtime and unit tests proving the Phase 2 REST & GraphQL interface contraction.

Guarded by `try/except ImportError` so it can run under both local Django-free test discovery
and Nautobot's test runner (`nautobot-server test nautobot_intent_catalog.tests.test_p2_contract`).
"""

from __future__ import annotations

import unittest

try:
    from django.urls import reverse
    from rest_framework import status
    from nautobot.core.testing.api import APITestCase
    from nautobot.extras.registry import registry

    from nautobot_intent_catalog.api import views as api_views
    from nautobot_intent_catalog.api import serializers as api_serializers
    from nautobot_intent_catalog import models
except ImportError:  # pragma: no cover
    HAS_DJANGO = False
else:
    HAS_DJANGO = True


class StaticPhase2ContractTests(unittest.TestCase):
    """Static checks for Phase 2 contracts that do not require Django/Nautobot DB runtime."""

    def test_intent_source_has_no_graphql_decorator(self):
        """IntentSource must NOT be registered with GraphQL in Phase 2."""
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        graphql_models = registry.get("model_features", {}).get("graphql", {}).get("nautobot_intent_catalog", [])
        self.assertNotIn(
            "intentsource",
            graphql_models,
            "intentsource is still registered in GraphQL model_features registry",
        )

    def test_retained_models_have_graphql_decorator(self):
        """All 11 retained models must keep GraphQL registration."""
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        graphql_models = registry.get("model_features", {}).get("graphql", {}).get("nautobot_intent_catalog", [])
        retained_model_names = [
            "desirednode",
            "desiredendpoint",
            "desirediprange",
            "desirednodeoperationaloverride",
            "desiredservice",
            "desireddependency",
            "desiredserviceplacement",
            "desiredcomputeplatform",
            "desiredcomputeinstance",
            "braindumpdocument",
            "alignmentreview",
        ]
        for name in retained_model_names:
            with self.subTest(model=name):
                self.assertIn(
                    name,
                    graphql_models,
                    f"{name} lost GraphQL registration in model_features registry",
                )

    def test_removed_serializers_are_absent(self):
        """DesiredService, DesiredEndpoint, compute serializers must be deleted."""
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        for name in [
            "DesiredServiceSerializer",
            "DesiredEndpointSerializer",
            "DesiredComputePlatformSerializer",
            "DesiredComputeInstanceSerializer",
        ]:
            with self.subTest(name=name):
                self.assertFalse(
                    hasattr(api_serializers, name),
                    f"{name} should be deleted in Phase 2",
                )

    def test_removed_viewsets_are_absent(self):
        """DesiredService, DesiredEndpoint, compute ViewSets must be deleted."""
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        for name in [
            "DesiredServiceViewSet",
            "DesiredEndpointViewSet",
            "DesiredComputePlatformViewSet",
            "DesiredComputeInstanceViewSet",
        ]:
            with self.subTest(name=name):
                self.assertFalse(
                    hasattr(api_views, name),
                    f"{name} should be deleted in Phase 2",
                )

    def test_no_serializer_uses_all_fields(self):
        """No retained REST serializer may use fields = '__all__'."""
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        for name in ["DesiredNodeSerializer", "BrainDumpDocumentSerializer", "AlignmentReviewSerializer"]:
            serializer_cls = getattr(api_serializers, name, None)
            if serializer_cls and hasattr(serializer_cls, "Meta"):
                self.assertNotEqual(
                    getattr(serializer_cls.Meta, "fields", None),
                    "__all__",
                    f"{name} is using fields = '__all__'",
                )


if HAS_DJANGO:

    class Phase2APIRouteTests(APITestCase):
        """Runtime tests for REST routes and method permissions under Nautobot test runner."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                "nautobot_intent_catalog.view_desirednode",
                "nautobot_intent_catalog.add_desirednode",
                "nautobot_intent_catalog.change_desirednode",
                "nautobot_intent_catalog.view_braindumpdocument",
                "nautobot_intent_catalog.add_braindumpdocument",
                "nautobot_intent_catalog.change_braindumpdocument",
                "nautobot_intent_catalog.delete_braindumpdocument",
                "nautobot_intent_catalog.view_alignmentreview",
                "nautobot_intent_catalog.add_alignmentreview",
                "nautobot_intent_catalog.change_alignmentreview",
                "nautobot_intent_catalog.delete_alignmentreview",
            )

        def test_removed_rest_collections_return_404(self):
            for endpoint in ["services", "endpoints", "compute-platforms", "compute-instances"]:
                with self.subTest(endpoint=endpoint):
                    url = f"/api/plugins/intent-catalog/{endpoint}/"
                    response = self.client.get(url, **self.header)
                    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        def test_node_post_returns_405(self):
            url = reverse("plugins-api:nautobot_intent_catalog-api:desirednode-list")
            response = self.client.post(
                url, {"name": "test-node", "slug": "test-node"}, format="json", **self.header
            )
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
