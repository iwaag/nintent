"""Contract checks for the remaining read APIs and the sole batch writer."""

from __future__ import annotations

import unittest

try:
    from django.urls import NoReverseMatch, reverse
    from rest_framework import status
    from nautobot.core.testing.api import APITestCase
    from nautobot.extras.registry import registry

    from nautobot_intent_catalog import models
    from nautobot_intent_catalog.api import serializers as api_serializers
    from nautobot_intent_catalog.api import views as api_views
except ImportError:  # pragma: no cover
    HAS_DJANGO = False
else:
    HAS_DJANGO = True


class StaticAPIContractTests(unittest.TestCase):
    def test_desired_state_mutation_viewsets_and_serializers_are_absent(self):
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        for name in ("DesiredNodeViewSet", "DesiredComputePlatformViewSet", "DesiredComputeInstanceViewSet"):
            self.assertFalse(hasattr(api_views, name), name)
        for name in ("DesiredNodeSerializer", "DesiredComputePlatformSerializer", "DesiredComputeInstanceSerializer"):
            self.assertFalse(hasattr(api_serializers, name), name)

    def test_removed_desired_routes_cannot_be_reversed(self):
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        for model in ("desirednode", "desiredcomputeplatform", "desiredcomputeinstance"):
            with self.subTest(model=model):
                with self.assertRaises(NoReverseMatch):
                    reverse(f"plugins-api:nautobot_intent_catalog-api:{model}-list")

    def test_retained_models_stay_in_graphql(self):
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        graphql_models = registry.get("model_features", {}).get("graphql", {}).get("nautobot_intent_catalog", [])
        for name in ("desirednode", "desiredendpoint", "desiredcomputeplatform", "desiredcomputeinstance"):
            self.assertIn(name, graphql_models)


if HAS_DJANGO:
    class APIContractRouteTests(APITestCase):
        def setUp(self):
            super().setUp()
            self.add_permissions("nautobot_intent_catalog.view_desirednode")

        def test_removed_desired_rest_routes_return_404(self):
            for endpoint in ("nodes", "compute-platforms", "compute-instances"):
                with self.subTest(endpoint=endpoint):
                    response = self.client.patch(
                        f"/api/plugins/intent-catalog/{endpoint}/00000000-0000-0000-0000-000000000000/",
                        {}, format="json", **self.header,
                    )
                    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    class GraphQLContractTests(APITestCase):
        def setUp(self):
            super().setUp()
            self.add_permissions("nautobot_intent_catalog.view_desirednode")
            self.api_url = reverse("graphql-api")

        def test_graphql_reads_desired_nodes_after_rest_removal(self):
            models.DesiredNode.objects.create(name="gql-node", slug="gql-node")
            response = self.client.post(self.api_url, {"query": "query { desired_nodes { name slug } }"}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertNotIn("errors", response.data)
            self.assertIn("gql-node", {row["slug"] for row in response.data["data"]["desired_nodes"]})
