"""Nautobot-runtime tests proving the removal of the dashboard-derived reconciliation cache.

Guarded by the same ``try/except ImportError`` pattern as ``test_braindump.py`` so this module is
harmless to import during local Django-free test discovery; the real cases only execute under
Nautobot's own test runner (``nautobot-server test
nautobot_intent_catalog.tests.test_remove_unused_surfaces``), which provisions and migrates its
own disposable database.

Each test name states the exact removed or retained contract from
``devdocs/big/remove_unused_surfaces/p3/plan.md`` Section 5.4, not a generic "page rendered"
check.
"""

from __future__ import annotations

try:
    from django.urls import NoReverseMatch, reverse
    from rest_framework import status

    from nautobot.core.testing import TestCase
    from nautobot.core.testing.api import APITestCase

    from nautobot_intent_catalog import IntentCatalogConfig, navigation
    from nautobot_intent_catalog.filters import DesiredNodeFilterSet, DesiredServiceFilterSet
    from nautobot_intent_catalog.models import (
        DesiredComputePlatform,
        DesiredNode,
        DesiredService,
        IntentSource,
    )
    from nautobot_intent_catalog.tables import DesiredNodeTable, DesiredServiceTable
except ImportError:  # pragma: no cover - Nautobot/Django are unavailable in local unit tests.
    pass
else:

    def _make_intent_source(**overrides):
        defaults = {"name": "Test Source", "slug": "test-source"}
        defaults.update(overrides)
        return IntentSource.objects.create(**defaults)

    def _make_node(**overrides):
        defaults = {"name": "Test Node", "slug": "test-node"}
        defaults.update(overrides)
        return DesiredNode.objects.create(**defaults)

    def _make_service(intent_source, **overrides):
        defaults = {
            "name": "test-service",
            "slug": "test-service",
            "display_name": "Test Service",
            "intent_source": intent_source,
            "catalog_metadata_name": "test-service",
        }
        defaults.update(overrides)
        return DesiredService.objects.create(**defaults)

    class ModelFieldRemovalTests(TestCase):
        """Item 1/2: neither model retains the four fields or the duplicated constants/choices."""

        def test_desired_node_has_no_reconciliation_fields(self):
            field_names = {f.name for f in DesiredNode._meta.get_fields()}
            self.assertNotIn("reconciliation_status", field_names)
            self.assertNotIn("reconciliation_checked_at", field_names)

        def test_desired_service_has_no_reconciliation_fields(self):
            field_names = {f.name for f in DesiredService._meta.get_fields()}
            self.assertNotIn("reconciliation_status", field_names)
            self.assertNotIn("reconciliation_checked_at", field_names)

        def test_desired_node_has_no_reconciliation_constants(self):
            for attr in (
                "RECONCILIATION_CONVERGED",
                "RECONCILIATION_DRIFTING",
                "RECONCILIATION_CONVERGING",
                "RECONCILIATION_UNKNOWN",
                "RECONCILIATION_STATUS_CHOICES",
            ):
                self.assertFalse(hasattr(DesiredNode, attr), f"DesiredNode.{attr} still present")

        def test_desired_service_has_no_reconciliation_constants(self):
            for attr in (
                "RECONCILIATION_CONVERGED",
                "RECONCILIATION_DRIFTING",
                "RECONCILIATION_CONVERGING",
                "RECONCILIATION_UNKNOWN",
                "RECONCILIATION_STATUS_CHOICES",
            ):
                self.assertFalse(hasattr(DesiredService, attr), f"DesiredService.{attr} still present")

    class FilterMetadataTests(TestCase):
        """Item 3: filter metadata omits reconciliation_status."""

        def test_desired_node_filterset_has_no_reconciliation_status(self):
            self.assertNotIn("reconciliation_status", DesiredNodeFilterSet.Meta.fields)
            self.assertNotIn("reconciliation_status", DesiredNodeFilterSet.base_filters)

        def test_desired_service_filterset_has_no_reconciliation_status(self):
            self.assertNotIn("reconciliation_status", DesiredServiceFilterSet.Meta.fields)
            self.assertNotIn("reconciliation_status", DesiredServiceFilterSet.base_filters)

    class TableColumnTests(TestCase):
        """Item 4: table base columns, configured fields, and default columns omit the cache."""

        def test_desired_node_table_has_no_reconciliation_column(self):
            self.assertNotIn("reconciliation_status", DesiredNodeTable.base_columns)
            self.assertNotIn("reconciliation_status", DesiredNodeTable.Meta.fields)
            self.assertNotIn("reconciliation_status", DesiredNodeTable.Meta.default_columns)

        def test_desired_service_table_has_no_reconciliation_column(self):
            self.assertNotIn("reconciliation_status", DesiredServiceTable.base_columns)
            self.assertNotIn("reconciliation_status", DesiredServiceTable.Meta.fields)
            self.assertNotIn("reconciliation_status", DesiredServiceTable.Meta.default_columns)

        def test_no_reconciliation_badge_helpers_remain(self):
            import nautobot_intent_catalog.tables as tables_module

            self.assertFalse(hasattr(tables_module, "RECONCILIATION_BADGE_CLASSES"))
            self.assertFalse(hasattr(tables_module, "_render_reconciliation_status"))

    class NodeServiceUITests(TestCase):
        """Items 5-6: real list/detail pages render 200 and omit cache labels/dashboard link."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                "nautobot_intent_catalog.view_desirednode",
                "nautobot_intent_catalog.view_desiredservice",
            )
            self.source = _make_intent_source()
            self.node = _make_node(name="UI Test Node", slug="ui-test-node")
            self.service = _make_service(self.source, name="ui-test-service", slug="ui-test-service")

        def test_node_list_page_renders_and_has_no_reconciliation_or_dashboard_text(self):
            response = self.client.get(
                reverse("plugins:nautobot_intent_catalog:desirednode_list"), HTTP_HX_REQUEST="true"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            body = response.content.decode()
            self.assertIn("UI Test Node", body)
            self.assertNotIn("Reconciliation", body)
            self.assertNotIn("view dashboard", body)

        def test_node_detail_page_renders_and_has_no_reconciliation_or_dashboard_text(self):
            response = self.client.get(
                reverse("plugins:nautobot_intent_catalog:desirednode", args=[self.node.pk])
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            body = response.content.decode()
            self.assertIn("UI Test Node", body)
            self.assertNotIn("Reconciliation Status", body)
            self.assertNotIn("Reconciliation Checked At", body)
            self.assertNotIn("view dashboard", body)

        def test_service_list_page_renders_and_has_no_reconciliation_or_dashboard_text(self):
            response = self.client.get(
                reverse("plugins:nautobot_intent_catalog:desiredservice_list"), HTTP_HX_REQUEST="true"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            body = response.content.decode()
            self.assertIn("ui-test-service", body)
            self.assertNotIn("Reconciliation", body)
            self.assertNotIn("view dashboard", body)

        def test_service_detail_page_renders_and_has_no_reconciliation_or_dashboard_text(self):
            response = self.client.get(
                reverse("plugins:nautobot_intent_catalog:desiredservice", args=[self.service.pk])
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            body = response.content.decode()
            self.assertIn("ui-test-service", body)
            self.assertNotIn("Reconciliation Status", body)
            self.assertNotIn("Reconciliation Checked At", body)
            self.assertNotIn("view dashboard", body)

    class DashboardRedirectRemovalTests(TestCase):
        """Item 7: dashboard_redirect cannot be reversed and the old direct path 404s."""

        def test_dashboard_redirect_route_name_is_not_reversible(self):
            with self.assertRaises(NoReverseMatch):
                reverse("plugins:nautobot_intent_catalog:dashboard_redirect")

        def test_direct_dashboard_path_returns_404(self):
            response = self.client.get("/plugins/intent-catalog/dashboard/")
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    class NavigationTests(TestCase):
        """Item 8: navigation retains Quick Host Add and has no nctl Dashboard item."""

        def test_operational_tools_group_has_quick_host_add_and_no_dashboard_item(self):
            tab = navigation.menu_items[0]
            operational_tools = next(g for g in tab.groups if g.name == "Operational Tools")
            item_names = [item.name for item in operational_tools.items]
            self.assertIn("Quick Host Add", item_names)
            self.assertNotIn("nctl Dashboard", item_names)

        def test_navigation_module_has_no_dashboard_url_helper(self):
            self.assertFalse(hasattr(navigation, "_configured_dashboard_url"))

    class AppConfigTests(TestCase):
        """Item 9: App defaults contain no dashboard_url."""

        def test_default_settings_has_no_dashboard_url(self):
            self.assertNotIn("dashboard_url", IntentCatalogConfig.default_settings)

    class RestApiTests(APITestCase):
        """Contracted REST API checks: nodes incidental GET + PATCH, removed endpoints 404."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                "nautobot_intent_catalog.view_desirednode",
                "nautobot_intent_catalog.change_desirednode",
            )
            self.source = _make_intent_source(slug="rest-test-source")
            self.node = _make_node(name="REST Test Node", slug="rest-test-node")
            self.nodes_url = reverse("plugins-api:nautobot_intent_catalog-api:desirednode-list")

        def test_node_list_and_detail_omit_removed_fields(self):
            list_response = self.client.get(self.nodes_url, **self.header)
            self.assertEqual(list_response.status_code, status.HTTP_200_OK)
            rows = {r["id"]: r for r in list_response.data["results"]}
            self.assertIn(str(self.node.pk), rows)
            for row in list_response.data["results"]:
                self.assertNotIn("reconciliation_status", row)
                self.assertNotIn("reconciliation_checked_at", row)

            detail_response = self.client.get(f"{self.nodes_url}{self.node.pk}/", **self.header)
            self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
            self.assertNotIn("reconciliation_status", detail_response.data)
            self.assertNotIn("reconciliation_checked_at", detail_response.data)

        def test_node_options_metadata_omits_removed_fields(self):
            response = self.client.options(self.nodes_url, **self.header)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        def test_node_patch_update_still_works(self):
            """Node PATCH lifecycle update works."""

            update_response = self.client.patch(
                f"{self.nodes_url}{self.node.pk}/",
                {"lifecycle": "retired"},
                format="json",
                **self.header,
            )
            self.assertEqual(update_response.status_code, status.HTTP_200_OK)
            self.assertEqual(update_response.data["lifecycle"], "retired")

    class GraphQLTests(APITestCase):
        """Items 12-13: supported reads work; explicit old-field queries fail validation."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                "nautobot_intent_catalog.view_desirednode",
                "nautobot_intent_catalog.view_desiredservice",
            )
            self.source = _make_intent_source(slug="graphql-test-source")
            self.node = _make_node(name="GraphQL Test Node", slug="graphql-test-node")
            _make_service(self.source, name="graphql-test-service", slug="graphql-test-service")
            self.api_url = reverse("graphql-api")

        def test_supported_node_query_returns_non_empty_results(self):
            query = "query { desired_nodes { id name slug } }"
            response = self.client.post(self.api_url, {"query": query}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertNotIn("errors", response.data)
            names = [n["name"] for n in response.data["data"]["desired_nodes"]]
            self.assertIn("GraphQL Test Node", names)

        def test_supported_service_query_returns_non_empty_results(self):
            query = "query { desired_services { id name slug } }"
            response = self.client.post(self.api_url, {"query": query}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertNotIn("errors", response.data)
            names = [s["name"] for s in response.data["data"]["desired_services"]]
            self.assertIn("graphql-test-service", names)

        def test_explicit_reconciliation_status_field_fails_node_validation(self):
            query = "query { desired_nodes { id reconciliation_status } }"
            response = self.client.post(self.api_url, {"query": query}, format="json", **self.header)
            self.assertIn("errors", response.data)

        def test_explicit_reconciliation_checked_at_field_fails_service_validation(self):
            query = "query { desired_services { id reconciliation_checked_at } }"
            response = self.client.post(self.api_url, {"query": query}, format="json", **self.header)
            self.assertIn("errors", response.data)

    class RetainedRoutesTests(TestCase):
        """Item 15: compute/Braindump routes are not accidentally removed."""

        def test_compute_and_braindump_routes_still_reverse(self):
            for name in (
                "desiredcomputeplatform_list",
                "desiredcomputeinstance_list",
                "braindumpdocument_list",
            ):
                with self.subTest(name=name):
                    reverse(f"plugins:nautobot_intent_catalog:{name}")

        def test_navigation_retains_desired_state_and_braindump_groups(self):
            tab = navigation.menu_items[0]
            group_names = [g.name for g in tab.groups]
            self.assertIn("Braindump", group_names)
            self.assertIn("Desired State", group_names)

    class ComputeUIRegistrationTests(TestCase):
        """Item 15 (plan §7 Step 6.7): VM Phase 3 compute UI registration still loads."""

        def setUp(self):
            super().setUp()
            self.add_permissions("nautobot_intent_catalog.view_desiredcomputeplatform")
            self.control_node = _make_node(name="Compute Control Node", slug="compute-control-node")
            self.platform = DesiredComputePlatform.objects.create(
                name="Compute Test Platform",
                slug="compute-test-platform",
                control_node=self.control_node,
            )

        def test_compute_platform_list_page_renders(self):
            response = self.client.get(
                reverse("plugins:nautobot_intent_catalog:desiredcomputeplatform_list"),
                HTTP_HX_REQUEST="true",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("Compute Test Platform", response.content.decode())

    class ComputeAPIRegistrationTests(APITestCase):
        """Item 15 (plan §7 Step 6.7): VM Phase 3 compute GraphQL registration still loads."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                "nautobot_intent_catalog.view_desiredcomputeplatform",
                "nautobot_intent_catalog.view_desiredcomputeinstance",
            )
            self.control_node = _make_node(name="Compute Control Node", slug="compute-control-node")
            self.platform = DesiredComputePlatform.objects.create(
                name="Compute Test Platform",
                slug="compute-test-platform",
                control_node=self.control_node,
            )

        def test_compute_platform_graphql_query_returns_real_row(self):
            query = "query { desired_compute_platforms { id name } }"
            response = self.client.post(
                reverse("graphql-api"), {"query": query}, format="json", **self.header
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertNotIn("errors", response.data)
            names = [p["name"] for p in response.data["data"]["desired_compute_platforms"]]
            self.assertIn("Compute Test Platform", names)
