"""Nautobot-runtime and unit tests proving the REST & GraphQL interface contract.

Guarded by `try/except ImportError` so it can run under both local Django-free test discovery
and Nautobot's test runner (`nautobot-server test nautobot_intent_catalog.tests.test_api_contract`).
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


class StaticAPIContractTests(unittest.TestCase):
    """Static checks for REST and GraphQL interface contracts without requiring Django/Nautobot DB runtime."""

    def test_intent_source_has_no_graphql_decorator(self):
        """IntentSource must NOT be registered with GraphQL."""
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
        ]:
            with self.subTest(name=name):
                self.assertFalse(
                    hasattr(api_serializers, name),
                    f"{name} should be deleted",
                )

    def test_removed_viewsets_are_absent(self):
        """DesiredService, DesiredEndpoint, compute ViewSets must be deleted."""
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        for name in [
            "DesiredServiceViewSet",
            "DesiredEndpointViewSet",
        ]:
            with self.subTest(name=name):
                self.assertFalse(
                    hasattr(api_views, name),
                    f"{name} should be deleted",
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

    def test_removed_rest_routes_fail_reverse(self):
        """Removed REST collections must fail Django URL reverse lookup."""
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        from django.urls import NoReverseMatch

        removed_names = [
            "plugins-api:nautobot_intent_catalog-api:desiredservice-list",
            "plugins-api:nautobot_intent_catalog-api:desiredservice-detail",
            "plugins-api:nautobot_intent_catalog-api:desiredendpoint-list",
            "plugins-api:nautobot_intent_catalog-api:desiredendpoint-detail",
        ]
        for name in removed_names:
            with self.subTest(name=name):
                with self.assertRaises(NoReverseMatch):
                    if "-detail" in name:
                        reverse(name, kwargs={"pk": "00000000-0000-0000-0000-000000000000"})
                    else:
                        reverse(name)

    def test_retained_rest_routes_reverse(self):
        """Retained REST collections must reverse successfully."""
        if not HAS_DJANGO:
            self.skipTest("Requires django/nautobot")
        retained_list_names = [
            "plugins-api:nautobot_intent_catalog-api:desirednode-list",
            "plugins-api:nautobot_intent_catalog-api:braindumpdocument-list",
            "plugins-api:nautobot_intent_catalog-api:alignmentreview-list",
            "plugins-api:nautobot_intent_catalog-api:desiredcomputeplatform-list",
            "plugins-api:nautobot_intent_catalog-api:desiredcomputeinstance-list",
        ]
        for name in retained_list_names:
            with self.subTest(name=name):
                url = reverse(name)
                self.assertTrue(url.startswith("/api/plugins/intent-catalog/"))


if HAS_DJANGO:

    class APIContractRouteTests(APITestCase):
        """Runtime tests for REST routes and method permissions under Nautobot test runner."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                "nautobot_intent_catalog.view_desirednode",
                "nautobot_intent_catalog.add_desirednode",
                "nautobot_intent_catalog.change_desirednode",
                "nautobot_intent_catalog.delete_desirednode",
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
            for endpoint in ["services", "endpoints"]:
                with self.subTest(endpoint=endpoint):
                    list_url = f"/api/plugins/intent-catalog/{endpoint}/"
                    detail_url = f"/api/plugins/intent-catalog/{endpoint}/00000000-0000-0000-0000-000000000000/"
                    res_list = self.client.get(list_url, **self.header)
                    res_detail = self.client.get(detail_url, **self.header)
                    self.assertEqual(res_list.status_code, status.HTTP_404_NOT_FOUND)
                    self.assertEqual(res_detail.status_code, status.HTTP_404_NOT_FOUND)

        def test_node_disallowed_methods_return_405(self):
            list_url = reverse("plugins-api:nautobot_intent_catalog-api:desirednode-list")

            res_post = self.client.post(list_url, {"name": "test-node", "slug": "test-node"}, format="json", **self.header)
            self.assertEqual(res_post.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

            res_delete_list = self.client.delete(list_url, **self.header)
            self.assertEqual(res_delete_list.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


    class RESTMethodFieldMatrixTests(APITestCase):
        """Complete frozen route/method/response-field/writable-field/invalid-input/zero-write
        matrix for the three retained REST collections (Phase 4 Step 1 item 6)."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                "nautobot_intent_catalog.view_desirednode",
                "nautobot_intent_catalog.change_desirednode",
                # delete_desirednode is granted even though DELETE is disallowed for this
                # ViewSet, so the 405 assertions below prove the method-not-allowed override
                # itself, not merely that the user lacks delete permission (which would 403
                # before ever reaching that code).
                "nautobot_intent_catalog.delete_desirednode",
                "nautobot_intent_catalog.view_braindumpdocument",
                "nautobot_intent_catalog.add_braindumpdocument",
                "nautobot_intent_catalog.change_braindumpdocument",
                "nautobot_intent_catalog.delete_braindumpdocument",
                "nautobot_intent_catalog.view_alignmentreview",
                "nautobot_intent_catalog.add_alignmentreview",
                "nautobot_intent_catalog.change_alignmentreview",
                "nautobot_intent_catalog.delete_alignmentreview",
            )

        def test_desired_node_response_fields_are_exact(self):
            node = models.DesiredNode.objects.create(name="n1", slug="n1")
            url = reverse("plugins-api:nautobot_intent_catalog-api:desirednode-detail", kwargs={"pk": node.pk})
            response = self.client.get(url, **self.header)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(
                set(response.data.keys()),
                {
                    "id", "name", "slug", "node_type", "lifecycle", "role",
                    "realized_device", "realized_device_source", "created", "last_updated",
                    # Universal Nautobot fields added by NautobotModelSerializer regardless of
                    # Meta.fields; not declared by DesiredNodeSerializer itself.
                    "display", "object_type", "notes_url", "custom_fields",
                },
            )

        def test_desired_node_patch_allowed_field_succeeds(self):
            node = models.DesiredNode.objects.create(name="n2", slug="n2", lifecycle="active")
            url = reverse("plugins-api:nautobot_intent_catalog-api:desirednode-detail", kwargs={"pk": node.pk})
            response = self.client.patch(url, {"lifecycle": "deprecated"}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            node.refresh_from_db()
            self.assertEqual(node.lifecycle, "deprecated")

        def test_desired_node_patch_unknown_field_rejected_with_zero_write(self):
            node = models.DesiredNode.objects.create(name="n3", slug="n3", lifecycle="active")
            url = reverse("plugins-api:nautobot_intent_catalog-api:desirednode-detail", kwargs={"pk": node.pk})
            response = self.client.patch(url, {"name": "renamed"}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            node.refresh_from_db()
            self.assertEqual(node.name, "n3")

        def test_desired_node_patch_invalid_lifecycle_rejected_with_zero_write(self):
            node = models.DesiredNode.objects.create(name="n4", slug="n4", lifecycle="active")
            url = reverse("plugins-api:nautobot_intent_catalog-api:desirednode-detail", kwargs={"pk": node.pk})
            response = self.client.patch(url, {"lifecycle": "not-a-real-choice"}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            node.refresh_from_db()
            self.assertEqual(node.lifecycle, "active")

        def test_desired_node_patch_inconsistent_link_source_rejected_with_zero_write(self):
            node = models.DesiredNode.objects.create(name="n5", slug="n5", lifecycle="active")
            url = reverse("plugins-api:nautobot_intent_catalog-api:desirednode-detail", kwargs={"pk": node.pk})
            response = self.client.patch(url, {"realized_device_source": "derived"}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            node.refresh_from_db()
            self.assertIsNone(node.realized_device_id)
            self.assertIsNone(node.realized_device_source)

        def test_desired_node_full_put_delete_and_bulk_patch_return_405(self):
            node = models.DesiredNode.objects.create(name="n6", slug="n6", lifecycle="active")
            detail_url = reverse("plugins-api:nautobot_intent_catalog-api:desirednode-detail", kwargs={"pk": node.pk})
            list_url = reverse("plugins-api:nautobot_intent_catalog-api:desirednode-list")
            self.assertEqual(
                self.client.put(detail_url, {"lifecycle": "active"}, format="json", **self.header).status_code,
                status.HTTP_405_METHOD_NOT_ALLOWED,
            )
            self.assertEqual(self.client.delete(detail_url, **self.header).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
            self.assertEqual(
                self.client.patch(list_url, [{"lifecycle": "active"}], format="json", **self.header).status_code,
                status.HTTP_405_METHOD_NOT_ALLOWED,
            )
            node.refresh_from_db()
            self.assertEqual(node.lifecycle, "active")

        def test_braindump_and_review_put_and_bulk_operations_return_405(self):
            braindump = models.BrainDumpDocument.objects.create(title="t", body="b", authorship="user_direct")
            review = models.AlignmentReview.objects.create(braindump=braindump, summary="s")
            for viewset_name, obj in (("braindumpdocument", braindump), ("alignmentreview", review)):
                detail_url = reverse(f"plugins-api:nautobot_intent_catalog-api:{viewset_name}-detail", kwargs={"pk": obj.pk})
                list_url = reverse(f"plugins-api:nautobot_intent_catalog-api:{viewset_name}-list")
                with self.subTest(viewset=viewset_name):
                    self.assertEqual(
                        self.client.put(detail_url, {}, format="json", **self.header).status_code,
                        status.HTTP_405_METHOD_NOT_ALLOWED,
                    )
                    self.assertEqual(
                        self.client.patch(list_url, [{}], format="json", **self.header).status_code,
                        status.HTTP_405_METHOD_NOT_ALLOWED,
                    )
                    self.assertEqual(self.client.delete(list_url, **self.header).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        def test_braindump_patch_unknown_field_rejected_with_zero_write(self):
            braindump = models.BrainDumpDocument.objects.create(title="orig", body="orig-body", authorship="user_direct")
            detail_url = reverse("plugins-api:nautobot_intent_catalog-api:braindumpdocument-detail", kwargs={"pk": braindump.pk})
            response = self.client.patch(
                detail_url, {"created": "2020-01-01T00:00:00Z"}, format="json", **self.header
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            braindump.refresh_from_db()
            self.assertEqual(braindump.title, "orig")

        def test_review_patch_unknown_field_rejected_with_zero_write(self):
            braindump = models.BrainDumpDocument.objects.create(title="t2", body="b2", authorship="user_direct")
            review = models.AlignmentReview.objects.create(braindump=braindump, summary="orig-summary")
            detail_url = reverse(
                "plugins-api:nautobot_intent_catalog-api:alignmentreview-detail", kwargs={"pk": review.pk}
            )
            response = self.client.patch(
                detail_url, {"braindump": str(braindump.pk), "summary": "new"}, format="json", **self.header
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            review.refresh_from_db()
            self.assertEqual(review.summary, "orig-summary")


    class GraphQLContractTests(APITestCase):
        """IntentSource GraphQL roots fail schema validation; retained roots query successfully
        (Phase 4 Step 1 item 7)."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                "nautobot_intent_catalog.view_desirednode",
                "nautobot_intent_catalog.view_desiredendpoint",
                "nautobot_intent_catalog.view_desirediprange",
                "nautobot_intent_catalog.view_desiredservice",
                "nautobot_intent_catalog.view_desireddependency",
                "nautobot_intent_catalog.view_desiredserviceplacement",
                "nautobot_intent_catalog.view_desiredcomputeplatform",
                "nautobot_intent_catalog.view_desiredcomputeinstance",
                "nautobot_intent_catalog.view_desirednodeoperationaloverride",
                "nautobot_intent_catalog.view_braindumpdocument",
                "nautobot_intent_catalog.view_alignmentreview",
            )
            self.api_url = reverse("graphql-api")

        def test_intent_source_singular_and_plural_queries_fail_schema_validation(self):
            for query in (
                'query { intent_source(id: "00000000-0000-0000-0000-000000000000") { id } }',
                "query { intent_sources { id } }",
            ):
                with self.subTest(query=query):
                    response = self.client.post(self.api_url, {"query": query}, format="json", **self.header)
                    # graphene-django returns 400 (not 200-with-errors) for a query document
                    # that fails schema validation, e.g. an unknown root field.
                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertTrue(response.data.get("errors"))
                    self.assertFalse(response.data.get("data"))

        def test_removed_reconciliation_fields_fail_schema_validation(self):
            for query in (
                "query { desired_nodes { id reconciliation_status } }",
                "query { desired_services { id reconciliation_checked_at } }",
            ):
                with self.subTest(query=query):
                    response = self.client.post(self.api_url, {"query": query}, format="json", **self.header)
                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertTrue(response.data.get("errors"))
                    self.assertFalse(response.data.get("data"))

        def test_every_retained_root_queries_successfully(self):
            node = models.DesiredNode.objects.create(name="gqln", slug="gqln")
            query = """
            query {
              desired_nodes { id name slug }
              desired_endpoints { id }
              desired_ip_ranges { id }
              desired_services { id }
              desired_dependencies { id }
              desired_service_placements { id }
              desired_compute_platforms { id }
              desired_compute_instances { id }
              desired_node_operational_overrides { id }
              braindump_documents { id }
              alignment_reviews { id }
            }
            """
            response = self.client.post(self.api_url, {"query": query}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertNotIn("errors", response.data)
            names = {row["name"] for row in response.data["data"]["desired_nodes"]}
            self.assertIn("gqln", names)
