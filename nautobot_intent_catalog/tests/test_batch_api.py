"""Desired-state batch REST endpoint contract tests."""

from __future__ import annotations

import unittest

from nautobot_intent_catalog.api.yaml_input import YAMLDocumentError, YAML_MEDIA_TYPES, load_yaml_document


class YAMLInputTests(unittest.TestCase):
    """Keep YAML media-type and error behavior independent of Django."""

    def test_supported_media_types_and_mapping_document(self):
        self.assertEqual(YAML_MEDIA_TYPES, ("application/yaml", "text/yaml", "application/x-yaml"))
        self.assertEqual(load_yaml_document("dry_run: true\noperations: []\n"), {"dry_run": True, "operations": []})

    def test_rejects_syntax_error_and_non_mapping_document(self):
        with self.assertRaises(YAMLDocumentError):
            load_yaml_document("operations: [")
        with self.assertRaises(YAMLDocumentError):
            load_yaml_document("- not\n- an object\n")


try:
    from rest_framework import status
    from nautobot.core.testing.api import APITestCase

    from nautobot_intent_catalog import models
except ImportError:  # pragma: no cover
    HAS_DJANGO = False
else:
    HAS_DJANGO = True


if HAS_DJANGO:

    class DesiredStateBatchAPITests(APITestCase):
        """Exercise the public endpoint through Nautobot's real authentication stack."""

        endpoint_url = "/api/plugins/intent-catalog/desired-state/batch/"

        def setUp(self):
            super().setUp()
            self.add_permissions(
                "nautobot_intent_catalog.view_desirednode",
                "nautobot_intent_catalog.add_desirednode",
                "nautobot_intent_catalog.change_desirednode",
                "nautobot_intent_catalog.delete_desirednode",
                "nautobot_intent_catalog.view_desiredendpoint",
                "nautobot_intent_catalog.add_desiredendpoint",
                "nautobot_intent_catalog.change_desiredendpoint",
                "nautobot_intent_catalog.delete_desiredendpoint",
            )

        @staticmethod
        def node_upsert(slug, *, lifecycle="active"):
            return {
                "op": "upsert", "kind": "desired_node", "key": {"slug": slug},
                "values": {"name": slug, "node_type": "device", "lifecycle": lifecycle},
            }

        def test_authentication_dry_run_and_read_only_token(self):
            document = {"dry_run": True, "operations": [self.node_upsert("api-preview")]}
            self.assertIn(
                self.client.post(self.endpoint_url, document, format="json").status_code,
                {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
            )
            response = self.client.post(self.endpoint_url, document, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["transaction"]["status"], "dry_run")
            self.assertFalse(models.DesiredNode.objects.filter(slug="api-preview").exists())

            self.token.write_enabled = False
            self.token.save(update_fields=["write_enabled"])
            response = self.client.post(
                self.endpoint_url, {**document, "dry_run": False}, format="json", **self.header
            )
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertFalse(models.DesiredNode.objects.filter(slug="api-preview").exists())

        def test_mixed_kind_apply_commits_and_conflict_is_atomic(self):
            update_node = models.DesiredNode.objects.create(name="api-update", slug="api-update", lifecycle="active")
            delete_node = models.DesiredNode.objects.create(name="api-delete", slug="api-delete")
            models.DesiredEndpoint.objects.create(desired_node=delete_node, name="primary", endpoint_type="primary")
            document = {"dry_run": False, "operations": [
                self.node_upsert("api-create"),
                self.node_upsert("api-update", lifecycle="deprecated"),
                {"op": "delete", "kind": "desired_endpoint",
                 "key": {"desired_node": "api-delete", "name": "primary", "endpoint_type": "primary"}, "values": {}},
            ]}
            response = self.client.post(self.endpoint_url, document, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["transaction"]["status"], "committed")
            self.assertTrue(models.DesiredNode.objects.filter(slug="api-create").exists())
            update_node.refresh_from_db()
            self.assertEqual(update_node.lifecycle, "deprecated")
            self.assertFalse(models.DesiredEndpoint.objects.filter(desired_node=delete_node).exists())

            conflict = {"dry_run": False, "operations": [
                {"op": "upsert", "kind": "desired_endpoint",
                 "key": {"desired_node": "missing-node", "name": "primary", "endpoint_type": "primary"},
                 "values": {"ip_policy": "external"}},
            ]}
            response = self.client.post(self.endpoint_url, conflict, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            self.assertEqual(response.data["transaction"]["status"], "blocked")
            self.assertFalse(models.DesiredEndpoint.objects.filter(desired_node__slug="missing-node").exists())

        def test_yaml_json_and_invalid_request_contract(self):
            document = {"dry_run": True, "operations": [self.node_upsert("api-yaml")]}
            json_response = self.client.post(self.endpoint_url, document, format="json", **self.header)
            yaml_response = self.client.post(
                self.endpoint_url,
                "dry_run: true\noperations:\n  - op: upsert\n    kind: desired_node\n    key: {slug: api-yaml}\n"
                "    values: {name: api-yaml, node_type: device, lifecycle: active}\n",
                content_type="application/yaml",
                **self.header,
            )
            self.assertEqual(yaml_response.status_code, status.HTTP_200_OK)
            self.assertEqual(yaml_response.data, json_response.data)
            self.assertEqual(
                self.client.post(self.endpoint_url, "operations: [", content_type="text/yaml", **self.header).status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertEqual(
                self.client.post(self.endpoint_url, {"dry_run": True, "operations": [
                    {"op": "upsert", "kind": "desired_node", "key": {"slug": "bad"}, "values": {"unknown": 1}},
                ]}, format="json", **self.header).status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertEqual(
                self.client.post(self.endpoint_url, "dry_run: true", content_type="text/plain", **self.header).status_code,
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )
            self.assertEqual(self.client.get(self.endpoint_url, **self.header).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
