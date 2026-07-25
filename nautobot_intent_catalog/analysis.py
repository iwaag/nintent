"""Analyze Git-backed intent sources from lightweight catalog metadata."""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import yaml

from .loaders import IntentSourceEntry

DEFAULT_REFS = ("HEAD", "main", "master")
MAX_FETCH_BYTES = 512_000


@dataclass(frozen=True)
class FetchedFile:
    """One lightweight repository file fetched for analysis."""

    path: str
    ref: str
    text: str
    source: str


@dataclass(frozen=True)
class CatalogDependency:
    """One normalized Backstage dependency reference."""

    raw_ref: str
    kind: str
    namespace: str
    name: str
    dependency_type: str
    resolution_status: str = "unresolved"


@dataclass(frozen=True)
class IntentSourceAnalysisResult:
    """Analysis output for a set of intent source entries."""

    generated_at: str
    source_analyses: list[dict[str, Any]] = field(default_factory=list)
    desired_services: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML-friendly representation."""

        return asdict(self)


def analyze_intent_sources(
    intent_sources: list[IntentSourceEntry],
    fetch_timeout: float,
    fetcher: Any | None = None,
) -> IntentSourceAnalysisResult:
    """Analyze intent source catalog files and return dry-run desired services."""

    active_fetcher = fetcher or RepositoryFileFetcher(timeout=fetch_timeout)
    analyses = []
    desired_services = []
    errors = []

    for intent_source in intent_sources:
        try:
            analysis, services = analyze_intent_source(active_fetcher, intent_source)
        except Exception as exc:  # pragma: no cover - defensive per-repository isolation.
            analysis = {
                "source": _source_name(intent_source.url),
                "url": intent_source.url,
                "enabled": intent_source.enabled,
                "status": "error",
                "reasons": ["analysis_error"],
                "error": str(exc),
            }
            services = []
            errors.append(f"{intent_source.url}: {exc}")
        analyses.append(analysis)
        desired_services.extend(services)

    return IntentSourceAnalysisResult(
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_analyses=analyses,
        desired_services=desired_services,
        errors=errors,
    )


def analyze_intent_source(
    fetcher: Any,
    intent_source: IntentSourceEntry,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Analyze one intent source using a fetcher-compatible object."""

    source_name = _source_name(intent_source.url)
    if not intent_source.enabled:
        return (
            {
                "source": source_name,
                "url": intent_source.url,
                "enabled": False,
                "status": "skipped",
                "reasons": ["intent_source_disabled"],
                "checked_files": [],
            },
            [],
        )

    default_branch = fetcher.default_branch(intent_source)
    refs = _intent_source_refs(intent_source, default_branch)
    catalog_file = fetcher.fetch_first(intent_source, intent_source.catalog_paths, refs)
    basic_files = fetcher.fetch_many(intent_source, intent_source.basic_file_paths, refs)
    checked_files = sorted({*intent_source.catalog_paths, *intent_source.basic_file_paths})

    if catalog_file is None:
        return (
            {
                "source": source_name,
                "url": intent_source.url,
                "enabled": True,
                "status": "insufficient",
                "reasons": ["catalog_info_missing"],
                "default_branch": default_branch,
                "refs_tried": refs,
                "checked_files": checked_files,
                "fetched_basic_files": [file.path for file in basic_files],
                "next_action": "manual_review_or_deeper_scan",
            },
            [],
        )

    entities = _catalog_entities(catalog_file)
    services = [
        service
        for entity in entities
        if (service := _entity_to_desired_service(entity, intent_source, catalog_file)) is not None
    ]
    dependency_summary = _service_dependency_summary(services)
    status = "catalog_parsed" if services else "insufficient"
    reasons = ["desired_services_generated"] if services else ["catalog_info_found_but_no_service_component"]
    return (
        {
            "source": source_name,
            "url": intent_source.url,
            "enabled": True,
            "status": status,
            "reasons": reasons,
            "default_branch": default_branch,
            "ref": catalog_file.ref,
            "catalog_path": catalog_file.path,
            "checked_files": checked_files,
            "fetched_basic_files": [file.path for file in basic_files],
            "catalog_entity_count": len(entities),
            "generated_service_count": len(services),
            **dependency_summary,
        },
        services,
    )


class RepositoryFileFetcher:
    """Fetch selected files from a repository without cloning the repository."""

    def __init__(self, timeout: float):
        self.timeout = timeout

    def default_branch(self, intent_source: IntentSourceEntry) -> str | None:
        github = _github_owner_repo(intent_source.url)
        if github:
            owner, repo = github
            try:
                text, _ = _request_text(f"https://api.github.com/repos/{owner}/{repo}", self.timeout)
                data = json.loads(text)
                branch = data.get("default_branch")
                return str(branch) if branch else None
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
                return None

        gitlab = _gitlab_project_path(intent_source.url)
        if gitlab:
            host, project_path = gitlab
            project_id = quote(project_path, safe="")
            try:
                text, _ = _request_text(f"https://{host}/api/v4/projects/{project_id}", self.timeout)
                data = json.loads(text)
                branch = data.get("default_branch")
                return str(branch) if branch else None
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
                return None

        return None

    def fetch_first(self, intent_source: IntentSourceEntry, paths: list[str], refs: list[str]) -> FetchedFile | None:
        for path in paths:
            for ref in refs:
                fetched = self.fetch_file(intent_source, path, ref)
                if fetched is not None:
                    return fetched
        return None

    def fetch_many(self, intent_source: IntentSourceEntry, paths: list[str], refs: list[str]) -> list[FetchedFile]:
        fetched_files = []
        for path in paths:
            for ref in refs:
                fetched = self.fetch_file(intent_source, path, ref)
                if fetched is not None:
                    fetched_files.append(fetched)
                    break
        return fetched_files

    def fetch_file(self, intent_source: IntentSourceEntry, path: str, ref: str) -> FetchedFile | None:
        try:
            if intent_source.raw_url_template:
                return self._fetch_raw_template(intent_source, path, ref)

            github = _github_owner_repo(intent_source.url)
            if github:
                return self._fetch_github(github[0], github[1], path, ref)

            gitlab = _gitlab_project_path(intent_source.url)
            if gitlab:
                return self._fetch_gitlab(gitlab[0], gitlab[1], path, ref)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, KeyError):
            return None
        return None

    def _fetch_raw_template(self, intent_source: IntentSourceEntry, path: str, ref: str) -> FetchedFile:
        url = intent_source.raw_url_template.format(ref=quote(ref, safe=""), path=quote(path))
        text, _ = _request_text(url, self.timeout)
        return FetchedFile(path=path, ref=ref, text=text, source=url)

    def _fetch_github(self, owner: str, repo: str, path: str, ref: str) -> FetchedFile:
        api_path = quote(path)
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{api_path}?ref={quote(ref, safe='')}"
        text, _ = _request_text(url, self.timeout, {"Accept": "application/vnd.github+json"})
        data = json.loads(text)
        if isinstance(data, list) or data.get("type") != "file":
            raise ValueError("GitHub contents response did not describe a file")
        if data.get("encoding") == "base64" and isinstance(data.get("content"), str):
            raw = base64.b64decode(data["content"], validate=False)
            if len(raw) > MAX_FETCH_BYTES:
                raise ValueError(f"file exceeded {MAX_FETCH_BYTES} bytes")
            file_text = raw.decode("utf-8", errors="replace")
        elif data.get("download_url"):
            file_text, _ = _request_text(str(data["download_url"]), self.timeout)
        else:
            raise ValueError("GitHub file did not include content")
        return FetchedFile(path=path, ref=ref, text=file_text, source=url)

    def _fetch_gitlab(self, host: str, project_path: str, path: str, ref: str) -> FetchedFile:
        project_id = quote(project_path, safe="")
        file_path = quote(path, safe="")
        url = f"https://{host}/api/v4/projects/{project_id}/repository/files/{file_path}/raw?ref={quote(ref, safe='')}"
        text, _ = _request_text(url, self.timeout)
        return FetchedFile(path=path, ref=ref, text=text, source=url)


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_plain_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain_value(item) for key, item in sorted(value.items())}
    return str(value)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "service"


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "nautobot-intent-catalog-analysis",
    }
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    return headers


def _request_text(url: str, timeout: float, headers: dict[str, str] | None = None) -> tuple[str, int]:
    request_headers = dict(_headers())
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers, method="GET")
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_FETCH_BYTES + 1)
    if len(raw) > MAX_FETCH_BYTES:
        raise ValueError(f"response exceeded {MAX_FETCH_BYTES} bytes")
    return raw.decode("utf-8", errors="replace"), len(raw)


def _github_owner_repo(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.netloc.lower() != "github.com":
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None
    repo = parts[1].removesuffix(".git")
    return parts[0], repo


def _gitlab_project_path(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    parsed = urlparse(url)
    if "gitlab" not in parsed.netloc.lower():
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None
    if parts[-1].endswith(".git"):
        parts[-1] = parts[-1].removesuffix(".git")
    return parsed.netloc, "/".join(parts)


def _intent_source_refs(intent_source: IntentSourceEntry, default_branch: str | None) -> list[str]:
    refs = []
    if intent_source.ref:
        refs.append(intent_source.ref)
    if default_branch:
        refs.append(default_branch)
    refs.extend(DEFAULT_REFS)
    deduped = []
    for ref in refs:
        if ref and ref not in deduped:
            deduped.append(ref)
    return deduped


def _catalog_entities(catalog_file: FetchedFile) -> list[dict[str, Any]]:
    entities = []
    for doc in yaml.safe_load_all(catalog_file.text):
        if not isinstance(doc, dict):
            continue
        entities.append(_plain_value(doc))
    return entities


def _parse_dependency_ref(raw_ref: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Normalize a Backstage entity reference used in spec.dependsOn."""

    if not isinstance(raw_ref, str):
        return None, {"raw_ref": str(raw_ref), "reason": "invalid_entity_ref"}

    raw_ref = raw_ref.strip()
    if not raw_ref:
        return None, {"raw_ref": raw_ref, "reason": "invalid_entity_ref"}

    kind = "component"
    entity_ref = raw_ref
    if ":" in raw_ref:
        kind_part, entity_ref = raw_ref.split(":", 1)
        kind_part = kind_part.strip().lower()
        if not kind_part:
            return None, {"raw_ref": raw_ref, "reason": "invalid_entity_ref"}
        kind = kind_part

    entity_ref = entity_ref.strip()
    if not entity_ref or entity_ref.count("/") > 1:
        return None, {"raw_ref": raw_ref, "reason": "invalid_entity_ref"}

    namespace = "default"
    name = entity_ref
    if "/" in entity_ref:
        namespace, name = [part.strip() for part in entity_ref.split("/", 1)]

    kind = kind.strip().lower()
    namespace = namespace.strip().lower()
    name = name.strip()
    if not kind or not namespace or not name:
        return None, {"raw_ref": raw_ref, "reason": "invalid_entity_ref"}

    dependency = CatalogDependency(
        raw_ref=raw_ref,
        kind=kind,
        namespace=namespace,
        name=name,
        dependency_type=kind,
    )
    return asdict(dependency), None


def _entity_dependencies(entity: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entity_spec = entity.get("spec") if isinstance(entity.get("spec"), dict) else {}
    depends_on = entity_spec.get("dependsOn")
    if depends_on is None:
        return [], []
    if isinstance(depends_on, str):
        depends_on = [depends_on]
    if not isinstance(depends_on, list):
        return [], [{"raw_ref": str(depends_on), "reason": "depends_on_must_be_list"}]

    dependencies = []
    malformed = []
    for raw_ref in depends_on:
        dependency, error = _parse_dependency_ref(raw_ref)
        if dependency is not None:
            dependencies.append(dependency)
        if error is not None:
            malformed.append(error)
    return dependencies, malformed


def _service_dependency_summary(services: list[dict[str, Any]]) -> dict[str, Any]:
    dependencies = [
        dependency
        for service in services
        for dependency in service.get("dependencies", [])
        if isinstance(dependency, dict)
    ]
    malformed = [
        malformed_dependency
        for service in services
        for malformed_dependency in service.get("analysis", {}).get("malformed_dependencies", [])
        if isinstance(malformed_dependency, dict)
    ]
    kinds = sorted({str(dependency.get("kind")) for dependency in dependencies if dependency.get("kind")})
    summary = {
        "dependency_count": len(dependencies),
        "unresolved_dependencies": sorted(
            {
                str(dependency["raw_ref"])
                for dependency in dependencies
                if dependency.get("resolution_status") == "unresolved" and dependency.get("raw_ref")
            }
        ),
        "malformed_dependencies": malformed,
    }
    for kind in kinds:
        summary[f"{kind}_dependency_count"] = sum(
            1 for dependency in dependencies if dependency.get("kind") == kind
        )
    return summary


def _entity_to_desired_service(
    entity: dict[str, Any],
    intent_source: IntentSourceEntry,
    catalog_file: FetchedFile,
) -> dict[str, Any] | None:
    kind = str(entity.get("kind") or "")
    metadata = entity.get("metadata") if isinstance(entity.get("metadata"), dict) else {}
    entity_spec = entity.get("spec") if isinstance(entity.get("spec"), dict) else {}
    component_type = str(entity_spec.get("type") or "").lower()
    if kind.lower() != "component" or component_type not in {"service", "website", "worker"}:
        return None

    raw_name = str(metadata.get("name") or intent_source.service_hint or "")
    if not raw_name:
        return None
    name = _slugify(raw_name)
    display_name = str(metadata.get("title") or raw_name)
    owner = intent_source.owner or entity_spec.get("owner")
    description = metadata.get("description")
    notes = description if isinstance(description, str) and description else "Generated from Backstage catalog metadata."
    dependencies, malformed_dependencies = _entity_dependencies(entity)
    analysis_reasons = ["backstage_component_catalog_found"]
    if dependencies:
        analysis_reasons.append("backstage_dependencies_found")
    if malformed_dependencies:
        analysis_reasons.append("backstage_dependency_refs_malformed")
    analysis = {
        "status": "catalog_derived",
        "confidence": "medium",
        "reasons": analysis_reasons,
    }
    if malformed_dependencies:
        analysis["malformed_dependencies"] = malformed_dependencies

    service = {
        "name": name,
        "display_name": display_name,
        "role": component_type,
        "required": True,
        "min_instances": 1,
        "max_instances": 1,
        "prefers_gpu": False,
        "protocol": "http",
        "intent_source": {
            "url": intent_source.url,
            "ref": catalog_file.ref,
            "catalog_path": catalog_file.path,
        },
        "dependencies": dependencies,
        "catalog": {
            "kind": kind,
            "metadata_name": metadata.get("name"),
            "spec_type": entity_spec.get("type"),
            "lifecycle": entity_spec.get("lifecycle"),
            "owner": owner,
            "system": entity_spec.get("system"),
        },
        "analysis": analysis,
        "notes": notes,
    }
    return _plain_value(service)


def _source_name(url: str | None) -> str:
    # A manual (URL-less) IntentSource -- e.g. the live "Manual" source Phase 0 confirmed -- has
    # url=None. `urlparse(None)` silently switches to its bytes-mode code path rather than
    # raising, which crashes `.strip("/")` two lines below with a bytes/str TypeError; found
    # live in the interface_contract/p1 Step 8 disposable proof, where this was previously
    # untested against a real manual+enabled IntentSource.
    if not url:
        return ""
    parsed = urlparse(url)
    path = parsed.path.strip("/").removesuffix(".git")
    return path.split("/")[-1] if path else parsed.netloc
