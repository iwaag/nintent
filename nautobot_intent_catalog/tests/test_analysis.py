from __future__ import annotations

import unittest

from nautobot_intent_catalog.analysis import FetchedFile, analyze_intent_sources
from nautobot_intent_catalog.loaders import IntentSourceEntry


class FakeFetcher:
    def __init__(
        self,
        catalog_file: FetchedFile | None = None,
        basic_files: list[FetchedFile] | None = None,
        default_branch: str | None = "main",
    ) -> None:
        self.catalog_file = catalog_file
        self.basic_files = basic_files or []
        self.default_branch_value = default_branch
        self.default_branch_calls = 0
        self.fetch_first_calls = 0
        self.fetch_many_calls = 0

    def default_branch(self, intent_source: IntentSourceEntry) -> str | None:
        self.default_branch_calls += 1
        return self.default_branch_value

    def fetch_first(self, intent_source: IntentSourceEntry, paths: list[str], refs: list[str]) -> FetchedFile | None:
        self.fetch_first_calls += 1
        return self.catalog_file

    def fetch_many(self, intent_source: IntentSourceEntry, paths: list[str], refs: list[str]) -> list[FetchedFile]:
        self.fetch_many_calls += 1
        return self.basic_files


class AnalysisTests(unittest.TestCase):
    def test_manual_url_less_intent_source_does_not_crash_analysis(self) -> None:
        """Found live in interface_contract/p1 Step 8: `urlparse(None)` silently switches to
        bytes mode instead of raising, and `_source_name()`'s `.strip("/")` then crashed with a
        bytes/str TypeError for any enabled manual (URL-less) IntentSource -- e.g. the live
        "Manual" source Phase 0 confirmed exists and is enabled. Every Analyze run would have
        failed against real data."""

        intent_source = IntentSourceEntry(slug="manual", source_type="manual", url=None, enabled=True)
        fetcher = FakeFetcher(default_branch=None)

        result = analyze_intent_sources([intent_source], fetch_timeout=1, fetcher=fetcher)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.source_analyses[0]["status"], "insufficient")

    def test_disabled_intent_source_is_skipped_without_fetch(self) -> None:
        intent_source = IntentSourceEntry(url="https://github.com/example/service", enabled=False)
        fetcher = FakeFetcher()

        result = analyze_intent_sources([intent_source], fetch_timeout=1, fetcher=fetcher)

        self.assertEqual(result.source_analyses[0]["status"], "skipped")
        self.assertEqual(result.source_analyses[0]["reasons"], ["intent_source_disabled"])
        self.assertEqual(result.desired_services, [])
        self.assertEqual(fetcher.default_branch_calls, 0)
        self.assertEqual(fetcher.fetch_first_calls, 0)
        self.assertEqual(fetcher.fetch_many_calls, 0)

    def test_missing_catalog_is_insufficient(self) -> None:
        intent_source = IntentSourceEntry(
            url="https://github.com/example/service",
            catalog_paths=["catalog-info.yaml"],
            basic_file_paths=["README.md"],
        )
        fetcher = FakeFetcher(
            catalog_file=None,
            basic_files=[FetchedFile(path="README.md", ref="main", text="# Service", source="fake")],
        )

        result = analyze_intent_sources([intent_source], fetch_timeout=1, fetcher=fetcher)

        analysis = result.source_analyses[0]
        self.assertEqual(analysis["status"], "insufficient")
        self.assertEqual(analysis["reasons"], ["catalog_info_missing"])
        self.assertEqual(analysis["fetched_basic_files"], ["README.md"])
        self.assertEqual(result.desired_services, [])

    def test_service_component_generates_desired_service(self) -> None:
        intent_source = IntentSourceEntry(
            url="https://github.com/example/Example.Service",
            owner="platform",
            catalog_paths=["catalog-info.yaml"],
            basic_file_paths=[],
        )
        catalog = FetchedFile(
            path="catalog-info.yaml",
            ref="main",
            source="fake",
            text=(
                "apiVersion: backstage.io/v1alpha1\n"
                "kind: Component\n"
                "metadata:\n"
                "  name: Example.Service\n"
                "  title: Example Service\n"
                "spec:\n"
                "  type: service\n"
                "  lifecycle: production\n"
                "  owner: ignored-by-explicit-owner\n"
            ),
        )
        fetcher = FakeFetcher(catalog_file=catalog)

        result = analyze_intent_sources([intent_source], fetch_timeout=1, fetcher=fetcher)

        analysis = result.source_analyses[0]
        self.assertEqual(analysis["status"], "catalog_parsed")
        self.assertEqual(analysis["generated_service_count"], 1)
        self.assertEqual(result.desired_services[0]["name"], "example-service")
        self.assertEqual(result.desired_services[0]["display_name"], "Example Service")
        self.assertEqual(result.desired_services[0]["role"], "service")
        self.assertEqual(result.desired_services[0]["catalog"]["owner"], "platform")
        self.assertEqual(result.desired_services[0]["dependencies"], [])
        self.assertEqual(analysis["dependency_count"], 0)
        self.assertEqual(analysis["unresolved_dependencies"], [])

    def test_non_service_component_does_not_generate_desired_service(self) -> None:
        intent_source = IntentSourceEntry(
            url="https://github.com/example/library",
            catalog_paths=["catalog-info.yaml"],
            basic_file_paths=[],
        )
        catalog = FetchedFile(
            path="catalog-info.yaml",
            ref="main",
            source="fake",
            text=(
                "apiVersion: backstage.io/v1alpha1\n"
                "kind: Component\n"
                "metadata:\n"
                "  name: Example Library\n"
                "spec:\n"
                "  type: library\n"
                "  lifecycle: production\n"
            ),
        )
        fetcher = FakeFetcher(catalog_file=catalog)

        result = analyze_intent_sources([intent_source], fetch_timeout=1, fetcher=fetcher)

        self.assertEqual(result.source_analyses[0]["status"], "insufficient")
        self.assertEqual(
            result.source_analyses[0]["reasons"],
            ["catalog_info_found_but_no_service_component"],
        )
        self.assertEqual(result.desired_services, [])

    def test_depends_on_entries_are_normalized(self) -> None:
        intent_source = IntentSourceEntry(
            url="https://github.com/example/service",
            catalog_paths=["catalog-info.yaml"],
            basic_file_paths=[],
        )
        catalog = FetchedFile(
            path="catalog-info.yaml",
            ref="main",
            source="fake",
            text=(
                "apiVersion: backstage.io/v1alpha1\n"
                "kind: Component\n"
                "metadata:\n"
                "  name: Example Service\n"
                "spec:\n"
                "  type: service\n"
                "  lifecycle: production\n"
                "  dependsOn:\n"
                "    - resource:default/minio-s3\n"
                "    - resource:default/postgresql\n"
                "    - component:default/keycloak\n"
            ),
        )
        fetcher = FakeFetcher(catalog_file=catalog)

        result = analyze_intent_sources([intent_source], fetch_timeout=1, fetcher=fetcher)

        dependencies = result.desired_services[0]["dependencies"]
        self.assertEqual(
            dependencies,
            [
                {
                    "raw_ref": "resource:default/minio-s3",
                    "kind": "resource",
                    "namespace": "default",
                    "name": "minio-s3",
                    "dependency_type": "resource",
                    "resolution_status": "unresolved",
                },
                {
                    "raw_ref": "resource:default/postgresql",
                    "kind": "resource",
                    "namespace": "default",
                    "name": "postgresql",
                    "dependency_type": "resource",
                    "resolution_status": "unresolved",
                },
                {
                    "raw_ref": "component:default/keycloak",
                    "kind": "component",
                    "namespace": "default",
                    "name": "keycloak",
                    "dependency_type": "component",
                    "resolution_status": "unresolved",
                },
            ],
        )
        analysis = result.source_analyses[0]
        self.assertEqual(analysis["dependency_count"], 3)
        self.assertEqual(analysis["component_dependency_count"], 1)
        self.assertEqual(analysis["resource_dependency_count"], 2)
        self.assertEqual(
            analysis["unresolved_dependencies"],
            [
                "component:default/keycloak",
                "resource:default/minio-s3",
                "resource:default/postgresql",
            ],
        )
        self.assertIn("backstage_dependencies_found", result.desired_services[0]["analysis"]["reasons"])

    def test_dependency_shorthand_refs_default_to_component_and_default_namespace(self) -> None:
        intent_source = IntentSourceEntry(
            url="https://github.com/example/service",
            catalog_paths=["catalog-info.yaml"],
            basic_file_paths=[],
        )
        catalog = FetchedFile(
            path="catalog-info.yaml",
            ref="main",
            source="fake",
            text=(
                "apiVersion: backstage.io/v1alpha1\n"
                "kind: Component\n"
                "metadata:\n"
                "  name: Example Service\n"
                "spec:\n"
                "  type: service\n"
                "  dependsOn:\n"
                "    - component:keycloak\n"
                "    - identity/auth-api\n"
                "    - redis\n"
            ),
        )
        fetcher = FakeFetcher(catalog_file=catalog)

        result = analyze_intent_sources([intent_source], fetch_timeout=1, fetcher=fetcher)

        self.assertEqual(
            result.desired_services[0]["dependencies"],
            [
                {
                    "raw_ref": "component:keycloak",
                    "kind": "component",
                    "namespace": "default",
                    "name": "keycloak",
                    "dependency_type": "component",
                    "resolution_status": "unresolved",
                },
                {
                    "raw_ref": "identity/auth-api",
                    "kind": "component",
                    "namespace": "identity",
                    "name": "auth-api",
                    "dependency_type": "component",
                    "resolution_status": "unresolved",
                },
                {
                    "raw_ref": "redis",
                    "kind": "component",
                    "namespace": "default",
                    "name": "redis",
                    "dependency_type": "component",
                    "resolution_status": "unresolved",
                },
            ],
        )

    def test_malformed_dependency_refs_are_reported_without_failing_analysis(self) -> None:
        intent_source = IntentSourceEntry(
            url="https://github.com/example/service",
            catalog_paths=["catalog-info.yaml"],
            basic_file_paths=[],
        )
        catalog = FetchedFile(
            path="catalog-info.yaml",
            ref="main",
            source="fake",
            text=(
                "apiVersion: backstage.io/v1alpha1\n"
                "kind: Component\n"
                "metadata:\n"
                "  name: Example Service\n"
                "spec:\n"
                "  type: service\n"
                "  dependsOn:\n"
                "    - resource:default/minio-s3\n"
                "    - ''\n"
                "    - component:default/keycloak/extra\n"
            ),
        )
        fetcher = FakeFetcher(catalog_file=catalog)

        result = analyze_intent_sources([intent_source], fetch_timeout=1, fetcher=fetcher)

        service = result.desired_services[0]
        self.assertEqual(len(service["dependencies"]), 1)
        self.assertEqual(service["dependencies"][0]["raw_ref"], "resource:default/minio-s3")
        self.assertIn("backstage_dependency_refs_malformed", service["analysis"]["reasons"])
        self.assertEqual(
            service["analysis"]["malformed_dependencies"],
            [
                {"raw_ref": "", "reason": "invalid_entity_ref"},
                {"raw_ref": "component:default/keycloak/extra", "reason": "invalid_entity_ref"},
            ],
        )
        self.assertEqual(result.source_analyses[0]["dependency_count"], 1)
        self.assertEqual(
            result.source_analyses[0]["malformed_dependencies"],
            service["analysis"]["malformed_dependencies"],
        )


if __name__ == "__main__":
    unittest.main()
