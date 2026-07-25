"""Load intent source input data for display."""

from __future__ import annotations

import os
import ipaddress
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .compute_contract import (
    ComputeContractError,
    normalize_mac_address,
    validate_config_schema_version,
    validate_instance_config,
    validate_memory_mb,
    validate_platform_config,
    validate_provider_type,
    validate_root_disk_gb,
    validate_vcpus,
)
from .intent_contract import (
    ContractError,
    canonical_json,
    validate_desired_service_reference,
    validate_endpoint_reference,
)

CANONICAL_ROOTS = (
    "intent_sources",
    "desired_nodes",
    "desired_endpoints",
    "desired_ip_ranges",
    "desired_compute_platforms",
    "desired_compute_instances",
    "desired_services",
    "desired_service_placements",
    "desired_node_operational_overrides",
)

DEFAULT_INTENT_SOURCES_ENV = "NAUTOBOT_INTENT_SOURCES_FILE"
DEFAULT_CATALOG_PATHS = ("catalog-info.yaml", "backstage/catalog-info.yaml")
DEFAULT_BASIC_FILE_PATHS = (
    "README.md",
    "readme.md",
    "package.json",
    "docker-compose.yml",
    "compose.yaml",
    "Chart.yaml",
)


@dataclass(frozen=True)
class IntentSourceEntry:
    """One intent source row normalized for display.

    Git sources are identified by ``url``; manual (URL-less) sources are
    identified by ``slug``.
    """

    url: str | None = None
    slug: str | None = None
    name: str | None = None
    source_type: str = "git_repository"
    enabled: bool = True
    ref: str | None = None
    owner: str | None = None
    service_hint: str | None = None
    catalog_paths: list[str] = field(default_factory=list)
    basic_file_paths: list[str] = field(default_factory=list)
    catalog_paths_defaulted: bool = False
    basic_file_paths_defaulted: bool = False
    raw_url_template: str | None = None


@dataclass(frozen=True)
class DesiredNodeEntry:
    """One desired node row normalized from YAML."""

    name: str
    slug: str
    node_type: str = "device"
    accepted_actual_types: list[str] = field(default_factory=list)
    lifecycle: str = "active"
    role: str | None = None
    description: str | None = None
    expected_spec: dict[str, Any] = field(default_factory=dict)
    intent_source: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class DesiredEndpointEntry:
    """One desired endpoint row normalized from YAML."""

    name: str
    desired_node: str
    endpoint_type: str = "primary"
    ip_address: str | None = None
    mac_address: str | None = None
    dns_name: str | None = None
    mdns_name: str | None = None
    vpn_dns_name: str | None = None
    protocol: str | None = None
    port: int | None = None
    generate_dnsmasq: bool = False
    ip_policy: str | None = None
    dnsmasq_record_type: str = "host_record"
    description: str | None = None


@dataclass(frozen=True)
class DesiredIPRangeEntry:
    """One desired IP range row normalized from YAML."""

    name: str
    slug: str
    start_address: str
    end_address: str
    range_policy: str
    lifecycle: str = "planned"
    generate_dnsmasq: bool = False
    dnsmasq_options: dict[str, Any] = field(default_factory=dict)
    description: str | None = None


@dataclass(frozen=True)
class DesiredComputePlatformEntry:
    """One desired compute platform row normalized from YAML."""

    name: str
    slug: str
    control_node: str
    provider_type: str = "proxmox"
    lifecycle: str = "active"
    config_schema_version: str = "v1"
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DesiredComputeInstanceEntry:
    """One desired compute instance row normalized from YAML."""

    desired_node: str
    platform: str
    instance_kind: str
    vcpus: int
    memory_mb: int
    root_disk_gb: int
    desired_power_state: str = "running"
    config_schema_version: str = "v1"
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DesiredServiceEntry:
    """One manually-declared desired service normalized from YAML.

    Identity is ``(intent_source slug, catalog_namespace, catalog_metadata_name,
    service_type)``, mirroring the model's unique constraint.
    """

    intent_source: str
    catalog_metadata_name: str
    service_type: str
    name: str
    slug: str
    display_name: str
    catalog_namespace: str = "default"
    lifecycle: str = "proposed"
    catalog_kind: str | None = None
    catalog_owner: str | None = None
    catalog_lifecycle: str | None = None
    source_ref: str | None = None
    source_catalog_path: str | None = None
    prefers_gpu: bool = False
    min_memory_gb: float | None = None
    notes: str | None = None


@dataclass(frozen=True)
class DesiredServicePlacementEntry:
    """One explicit desired service placement normalized from YAML."""

    desired_service: dict[str, str]
    instance_name: str
    desired_node: str
    desired_endpoint: dict[str, str] | None
    desired_state: str
    instance_role: str | None
    deployment_profile: str
    config_schema_version: str
    config: dict[str, Any]
    assignment_source: str
    reason: str | None


@dataclass(frozen=True)
class DesiredNodeOperationalOverrideEntry:
    """One optional desired-node operation override normalized from YAML."""

    desired_node: str
    declared_host_os: str | None
    connection_path: str | None
    local_endpoint: dict[str, str] | None
    tailscale_endpoint: dict[str, str] | None
    ansible_port: int | None
    power_control: str | None
    is_laptop: bool | None


@dataclass(frozen=True)
class IntentSourceLoadResult:
    """Result object returned by the YAML loader."""

    source_path: Path
    intent_sources: list[IntentSourceEntry] = field(default_factory=list)
    desired_nodes: list[DesiredNodeEntry] = field(default_factory=list)
    desired_ip_ranges: list[DesiredIPRangeEntry] = field(default_factory=list)
    desired_endpoints: list[DesiredEndpointEntry] = field(default_factory=list)
    desired_compute_platforms: list[DesiredComputePlatformEntry] = field(default_factory=list)
    desired_compute_instances: list[DesiredComputeInstanceEntry] = field(default_factory=list)
    desired_services: list[DesiredServiceEntry] = field(default_factory=list)
    desired_service_placements: list[DesiredServicePlacementEntry] = field(default_factory=list)
    desired_node_operational_overrides: list[DesiredNodeOperationalOverrideEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def default_intent_sources_file(configured_path: str | Path | None = None) -> Path:
    """Return the default intent source YAML path."""

    if configured_path:
        return _resolve_configured_path(configured_path)

    override = os.environ.get(DEFAULT_INTENT_SOURCES_ENV)
    if override:
        return _resolve_configured_path(override)

    return Path.cwd() / "nauto" / "seed" / "intent_sources.yaml"


def load_default_intent_sources(configured_path: str | Path | None = None) -> IntentSourceLoadResult:
    """Load intent source data from the configured default path."""

    return load_intent_sources(default_intent_sources_file(configured_path))


def load_intent_sources(path: Path) -> IntentSourceLoadResult:
    """Load and normalize intent source entries from a YAML file."""

    source_path = path.expanduser()
    try:
        text = source_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return IntentSourceLoadResult(
            source_path=source_path,
            errors=[f"Intent source file not found: {source_path}"],
        )
    except OSError as exc:
        return IntentSourceLoadResult(
            source_path=source_path,
            errors=[f"Intent source file could not be read: {exc}"],
        )

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        return IntentSourceLoadResult(
            source_path=source_path,
            errors=[f"Intent source YAML is invalid: {exc}"],
        )

    if not isinstance(data, dict):
        return IntentSourceLoadResult(
            source_path=source_path,
            errors=["Intent source root must be a mapping."],
        )

    if "service_repositories" in data:
        return IntentSourceLoadResult(
            source_path=source_path,
            errors=["service_repositories is not supported; rename the top-level key to intent_sources."],
        )
    if "desired_node_operational_configs" in data:
        return IntentSourceLoadResult(
            source_path=source_path,
            errors=[
                "desired_node_operational_configs is not supported; use "
                "desired_node_operational_overrides."
            ],
        )

    unknown_roots = sorted(str(key) for key in data if key not in CANONICAL_ROOTS)
    if unknown_roots:
        return IntentSourceLoadResult(
            source_path=source_path,
            errors=[f"Unknown top-level root(s): {', '.join(unknown_roots)}."],
        )

    intent_sources: list[IntentSourceEntry] = []
    desired_nodes: list[DesiredNodeEntry] = []
    desired_ip_ranges: list[DesiredIPRangeEntry] = []
    desired_endpoints: list[DesiredEndpointEntry] = []
    desired_compute_platforms: list[DesiredComputePlatformEntry] = []
    desired_compute_instances: list[DesiredComputeInstanceEntry] = []
    desired_services: list[DesiredServiceEntry] = []
    desired_service_placements: list[DesiredServicePlacementEntry] = []
    desired_node_operational_overrides: list[DesiredNodeOperationalOverrideEntry] = []
    errors: list[str] = []

    raw_sources, source_errors = _list_section(data, "intent_sources")
    errors.extend(source_errors)
    for index, item in enumerate(raw_sources, start=1):
        entry, entry_errors = _normalize_intent_source_entry(item, index)
        if entry is not None:
            intent_sources.append(entry)
        errors.extend(entry_errors)

    raw_nodes, node_errors = _list_section(data, "desired_nodes")
    errors.extend(node_errors)
    for index, item in enumerate(raw_nodes, start=1):
        entry, entry_errors = _normalize_desired_node_entry(item, index)
        if entry is not None:
            desired_nodes.append(entry)
        errors.extend(entry_errors)

    raw_ip_ranges, ip_range_errors = _list_section(data, "desired_ip_ranges")
    errors.extend(ip_range_errors)
    for index, item in enumerate(raw_ip_ranges, start=1):
        entry, entry_errors = _normalize_desired_ip_range_entry(item, index)
        if entry is not None:
            desired_ip_ranges.append(entry)
        errors.extend(entry_errors)

    raw_endpoints, endpoint_errors = _list_section(data, "desired_endpoints")
    errors.extend(endpoint_errors)
    for index, item in enumerate(raw_endpoints, start=1):
        entry, entry_errors = _normalize_desired_endpoint_entry(item, index)
        if entry is not None:
            desired_endpoints.append(entry)
        errors.extend(entry_errors)

    raw_compute_platforms, compute_platform_errors = _list_section(data, "desired_compute_platforms")
    errors.extend(compute_platform_errors)
    for index, item in enumerate(raw_compute_platforms, start=1):
        entry, entry_errors = _normalize_desired_compute_platform_entry(item, index)
        if entry is not None:
            desired_compute_platforms.append(entry)
        errors.extend(entry_errors)

    raw_compute_instances, compute_instance_errors = _list_section(data, "desired_compute_instances")
    errors.extend(compute_instance_errors)
    for index, item in enumerate(raw_compute_instances, start=1):
        entry, entry_errors = _normalize_desired_compute_instance_entry(item, index)
        if entry is not None:
            desired_compute_instances.append(entry)
        errors.extend(entry_errors)

    raw_services, service_errors = _list_section(data, "desired_services")
    errors.extend(service_errors)
    for index, item in enumerate(raw_services, start=1):
        entry, entry_errors = _normalize_desired_service_entry(item, index)
        if entry is not None:
            desired_services.append(entry)
        errors.extend(entry_errors)

    raw_placements, placement_errors = _list_section(data, "desired_service_placements")
    errors.extend(placement_errors)
    for index, item in enumerate(raw_placements, start=1):
        entry, entry_errors = _normalize_desired_service_placement_entry(item, index)
        if entry is not None:
            desired_service_placements.append(entry)
        errors.extend(entry_errors)

    raw_operational_overrides, operational_errors = _list_section(
        data,
        "desired_node_operational_overrides",
    )
    errors.extend(operational_errors)
    for index, item in enumerate(raw_operational_overrides, start=1):
        entry, entry_errors = _normalize_desired_node_operational_override_entry(item, index)
        if entry is not None:
            desired_node_operational_overrides.append(entry)
        errors.extend(entry_errors)

    errors.extend(_duplicate_endpoint_mac_errors(desired_endpoints))
    errors.extend(_duplicate_compute_platform_errors(desired_compute_platforms))
    errors.extend(_duplicate_compute_instance_errors(desired_compute_instances))
    errors.extend(_duplicate_service_errors(desired_services))
    errors.extend(_duplicate_placement_errors(desired_service_placements))
    errors.extend(_duplicate_operational_override_errors(desired_node_operational_overrides))

    return IntentSourceLoadResult(
        source_path=source_path,
        intent_sources=intent_sources,
        desired_nodes=desired_nodes,
        desired_ip_ranges=desired_ip_ranges,
        desired_endpoints=desired_endpoints,
        desired_compute_platforms=desired_compute_platforms,
        desired_compute_instances=desired_compute_instances,
        desired_services=desired_services,
        desired_service_placements=desired_service_placements,
        desired_node_operational_overrides=desired_node_operational_overrides,
        errors=errors,
    )


def _list_section(data: dict[Any, Any], key: str) -> tuple[list[Any], list[str]]:
    raw_items = data.get(key, [])
    if raw_items is None:
        return [], []
    if not isinstance(raw_items, list):
        return [], [f"{key} must be a list."]
    return raw_items, []


def _normalize_intent_source_entry(item: Any, index: int) -> tuple[IntentSourceEntry | None, list[str]]:
    """Normalize one raw YAML list item.

    Git sources require ``url``; manual (non-Git) sources require ``slug`` and
    may omit ``url``.
    """

    section = f"intent_sources entry {index}"
    if isinstance(item, str):
        item = {"url": item}

    if not isinstance(item, dict):
        return None, [f"Entry {index} must be a URL string or mapping."]

    unknown = sorted(str(key) for key in item if key not in _INTENT_SOURCE_KEYS)
    if unknown:
        return None, [f"{section} has unknown fields: {', '.join(unknown)}."]

    source_type, source_type_error = _choice_with_default_or_error(
        item.get("source_type"),
        _INTENT_SOURCE_TYPES,
        f"{section} source_type",
        "git_repository",
    )
    if source_type_error:
        return None, [source_type_error]

    raw_url = item.get("url")
    slug = _optional_str(item.get("slug"))
    if source_type == "git_repository":
        if not raw_url:
            return None, [f"Entry {index} is missing required field: url."]
    elif not slug:
        return None, [f"{section} is missing required field: slug."]

    if slug and not _SLUG_RE.fullmatch(slug):
        return None, [f"{section} slug must be a lowercase slug."]

    catalog_paths, catalog_paths_defaulted = _string_list_with_default(
        item,
        "catalog_paths",
        DEFAULT_CATALOG_PATHS,
    )
    basic_file_paths, basic_file_paths_defaulted = _string_list_with_default(
        item,
        "basic_file_paths",
        DEFAULT_BASIC_FILE_PATHS,
    )

    return (
        IntentSourceEntry(
            url=str(raw_url) if raw_url else None,
            slug=slug,
            name=_optional_str(item.get("name")),
            source_type=source_type,
            enabled=_as_bool(item.get("enabled", True)),
            ref=_optional_str(item.get("ref")),
            owner=_optional_str(item.get("owner")),
            service_hint=_optional_str(item.get("service_hint")),
            catalog_paths=catalog_paths,
            basic_file_paths=basic_file_paths,
            catalog_paths_defaulted=catalog_paths_defaulted,
            basic_file_paths_defaulted=basic_file_paths_defaulted,
            raw_url_template=_optional_str(item.get("raw_url_template")),
        ),
        [],
    )


def _normalize_desired_node_entry(item: Any, index: int) -> tuple[DesiredNodeEntry | None, list[str]]:
    """Normalize one desired node YAML item."""

    if not isinstance(item, dict):
        return None, [f"desired_nodes entry {index} must be a mapping."]

    name = _optional_str(item.get("name"))
    if not name:
        return None, [f"desired_nodes entry {index} is missing required field: name."]

    slug = _optional_str(item.get("slug")) or _slug_from_text(name, "desired-node")
    expected_spec = item.get("expected_spec") or {}
    if not isinstance(expected_spec, dict):
        return None, [f"desired_nodes entry {index} expected_spec must be a mapping."]

    node_type, node_type_error = _choice_with_default_or_error(
        item.get("node_type"),
        _NODE_TYPES,
        f"desired_nodes entry {index} node_type",
        "device",
    )
    accepted_actual_types, accepted_actual_types_error = _actual_types_or_error(
        item.get("accepted_actual_types"),
        node_type or "device",
        f"desired_nodes entry {index} accepted_actual_types",
    )
    errors = []
    if node_type_error:
        errors.append(node_type_error)
    if accepted_actual_types_error:
        errors.append(accepted_actual_types_error)
    if errors:
        return None, errors

    return (
        DesiredNodeEntry(
            name=name,
            slug=slug,
            node_type=node_type or "device",
            accepted_actual_types=accepted_actual_types,
            lifecycle=_choice(item.get("lifecycle"), _LIFECYCLES, "active"),
            role=_optional_str(item.get("role")),
            description=_optional_str(item.get("description")),
            expected_spec=_plain_mapping(expected_spec),
            intent_source=_optional_str(item.get("intent_source")),
            notes=_optional_str(item.get("notes")),
        ),
        [],
    )


def _normalize_desired_endpoint_entry(item: Any, index: int) -> tuple[DesiredEndpointEntry | None, list[str]]:
    """Normalize one desired endpoint YAML item."""

    if not isinstance(item, dict):
        return None, [f"desired_endpoints entry {index} must be a mapping."]

    name = _optional_str(item.get("name"))
    desired_node = _optional_str(item.get("desired_node"))
    errors = []
    if not name:
        errors.append(f"desired_endpoints entry {index} is missing required field: name.")
    if not desired_node:
        errors.append(f"desired_endpoints entry {index} is missing required field: desired_node.")
    elif not _SLUG_RE.fullmatch(desired_node):
        errors.append(f"desired_endpoints entry {index} desired_node must be a lowercase slug.")
    port, port_error = _optional_port(item.get("port"), index)
    if port_error:
        errors.append(port_error)
    ip_address = _optional_str(item.get("ip_address"))
    raw_ip_policy = item.get("ip_policy")
    ip_policy: str | None = None
    ip_policy_error: str | None = None
    if ip_address or raw_ip_policy is not None:
        ip_policy, ip_policy_error = _choice_or_error(
            raw_ip_policy,
            _IP_POLICIES,
            f"desired_endpoints entry {index} ip_policy",
        )
    if ip_address and raw_ip_policy is None:
        errors.append(f"desired_endpoints entry {index} is missing required field: ip_policy.")
    elif ip_policy_error:
        errors.append(ip_policy_error)
    if ip_policy is None and not ip_address:
        ip_policy = "external"
    mac_address = None
    raw_mac_address = item.get("mac_address")
    if raw_mac_address is not None:
        try:
            mac_address = normalize_mac_address(raw_mac_address)
        except ComputeContractError as exc:
            errors.append(f"desired_endpoints entry {index} mac_address {exc}")
    if errors:
        return None, errors

    return (
        DesiredEndpointEntry(
            name=name or "",
            desired_node=desired_node or "",
            endpoint_type=_choice(item.get("endpoint_type"), _ENDPOINT_TYPES, "primary"),
            ip_address=ip_address,
            mac_address=mac_address,
            dns_name=_optional_str(item.get("dns_name")),
            mdns_name=_optional_str(item.get("mdns_name")),
            vpn_dns_name=_optional_str(item.get("vpn_dns_name")),
            protocol=_optional_str(item.get("protocol")),
            port=port,
            generate_dnsmasq=_as_bool(item.get("generate_dnsmasq", False)),
            ip_policy=ip_policy,
            dnsmasq_record_type=_choice(item.get("dnsmasq_record_type"), _DNSMASQ_RECORD_TYPES, "host_record"),
            description=_optional_str(item.get("description")),
        ),
        [],
    )


def _normalize_desired_service_entry(item: Any, index: int) -> tuple[DesiredServiceEntry | None, list[str]]:
    """Normalize one manually-declared desired service YAML item."""

    section = f"desired_services entry {index}"
    allowed = {
        "intent_source",
        "catalog_namespace",
        "catalog_metadata_name",
        "service_type",
        "name",
        "slug",
        "display_name",
        "lifecycle",
        "catalog_kind",
        "catalog_owner",
        "catalog_lifecycle",
        "source_ref",
        "source_catalog_path",
        "prefers_gpu",
        "min_memory_gb",
        "notes",
    }
    required = {
        "intent_source",
        "catalog_metadata_name",
        "service_type",
        "name",
        "display_name",
    }
    errors = _strict_mapping_errors(item, section, allowed, required)
    if errors:
        return None, errors

    intent_source = _strict_slug(item.get("intent_source"), f"{section} intent_source", errors)
    catalog_metadata_name = _strict_nonempty_string(
        item.get("catalog_metadata_name"),
        f"{section} catalog_metadata_name",
        errors,
    )
    service_type = _strict_choice(item.get("service_type"), _SERVICE_TYPES, f"{section} service_type", errors)
    name = _strict_slug(item.get("name"), f"{section} name", errors)
    display_name = _strict_nonempty_string(item.get("display_name"), f"{section} display_name", errors)

    if "catalog_namespace" in item:
        catalog_namespace = _strict_nonempty_string(
            item.get("catalog_namespace"),
            f"{section} catalog_namespace",
            errors,
        )
    else:
        catalog_namespace = "default"

    if "slug" in item:
        slug = _strict_slug(item.get("slug"), f"{section} slug", errors)
    else:
        slug = _slug_from_text(name, "desired-service") if name else ""

    lifecycle = "proposed"
    if "lifecycle" in item:
        lifecycle = _strict_choice(item.get("lifecycle"), _LIFECYCLES_SERVICE, f"{section} lifecycle", errors)

    catalog_kind = _strict_optional_string(item.get("catalog_kind"), f"{section} catalog_kind", errors)
    catalog_owner = _strict_optional_string(item.get("catalog_owner"), f"{section} catalog_owner", errors)
    catalog_lifecycle = _strict_optional_string(item.get("catalog_lifecycle"), f"{section} catalog_lifecycle", errors)
    source_ref = _strict_optional_string(item.get("source_ref"), f"{section} source_ref", errors)
    source_catalog_path = _strict_optional_string(
        item.get("source_catalog_path"),
        f"{section} source_catalog_path",
        errors,
    )
    notes = _strict_optional_string(item.get("notes"), f"{section} notes", errors)

    prefers_gpu = item.get("prefers_gpu", False)
    if not isinstance(prefers_gpu, bool):
        errors.append(f"{section} prefers_gpu must be a boolean.")
        prefers_gpu = False

    min_memory_gb = _optional_number(item.get("min_memory_gb"), f"{section} min_memory_gb", errors)

    if errors:
        return None, errors

    return (
        DesiredServiceEntry(
            intent_source=intent_source,
            catalog_metadata_name=catalog_metadata_name,
            service_type=service_type,
            name=name,
            slug=slug,
            display_name=display_name,
            catalog_namespace=catalog_namespace,
            lifecycle=lifecycle,
            catalog_kind=catalog_kind,
            catalog_owner=catalog_owner,
            catalog_lifecycle=catalog_lifecycle,
            source_ref=source_ref,
            source_catalog_path=source_catalog_path,
            prefers_gpu=prefers_gpu,
            min_memory_gb=min_memory_gb,
            notes=notes,
        ),
        [],
    )


def _normalize_desired_compute_platform_entry(
    item: Any,
    index: int,
) -> tuple[DesiredComputePlatformEntry | None, list[str]]:
    """Normalize one desired compute platform YAML item.

    Config/provider/schema-version validation reuses the exact Django-free `compute_contract`
    helpers the model/REST/UI layers call, so a load error and a model `ValidationError` never
    diverge on the same input (plan Section 5.8).
    """

    section = f"desired_compute_platforms entry {index}"
    allowed = {
        "name",
        "slug",
        "provider_type",
        "lifecycle",
        "control_node",
        "config_schema_version",
        "config",
    }
    required = {"name", "slug", "control_node"}
    errors = _strict_mapping_errors(item, section, allowed, required)
    if errors:
        return None, errors

    name = _strict_nonempty_string(item.get("name"), f"{section} name", errors)
    slug = _strict_slug(item.get("slug"), f"{section} slug", errors)
    control_node = _strict_slug(item.get("control_node"), f"{section} control_node", errors)
    lifecycle = _strict_choice(item.get("lifecycle", "active"), _LIFECYCLES, f"{section} lifecycle", errors)

    try:
        provider_type = validate_provider_type(item.get("provider_type", "proxmox"))
    except ComputeContractError as exc:
        errors.append(f"{section} {exc}")
        provider_type = "proxmox"

    try:
        config_schema_version = validate_config_schema_version(item.get("config_schema_version"))
    except ComputeContractError as exc:
        errors.append(f"{section} {exc}")
        config_schema_version = "v1"

    try:
        config = validate_platform_config(item.get("config") or {})
    except ComputeContractError as exc:
        errors.append(f"{section} {exc}")
        config = {}

    if errors:
        return None, errors

    return (
        DesiredComputePlatformEntry(
            name=name,
            slug=slug,
            control_node=control_node,
            provider_type=provider_type,
            lifecycle=lifecycle,
            config_schema_version=config_schema_version,
            config=config,
        ),
        [],
    )


def _normalize_desired_compute_instance_entry(
    item: Any,
    index: int,
) -> tuple[DesiredComputeInstanceEntry | None, list[str]]:
    """Normalize one desired compute instance YAML item.

    Bounds/config validation reuses the exact `compute_contract` helpers the model/REST/UI
    layers call (plan Section 5.8); `instance_kind` must resolve before `config` can be
    validated because the allowed config keys are kind-gated.
    """

    section = f"desired_compute_instances entry {index}"
    allowed = {
        "desired_node",
        "platform",
        "instance_kind",
        "desired_power_state",
        "vcpus",
        "memory_mb",
        "root_disk_gb",
        "config_schema_version",
        "config",
    }
    required = {"desired_node", "platform", "instance_kind", "vcpus", "memory_mb", "root_disk_gb"}
    errors = _strict_mapping_errors(item, section, allowed, required)
    if errors:
        return None, errors

    desired_node = _strict_slug(item.get("desired_node"), f"{section} desired_node", errors)
    platform = _strict_slug(item.get("platform"), f"{section} platform", errors)
    instance_kind = _strict_choice(item.get("instance_kind"), _INSTANCE_KINDS, f"{section} instance_kind", errors)
    desired_power_state = _strict_choice(
        item.get("desired_power_state", "running"),
        _POWER_STATES,
        f"{section} desired_power_state",
        errors,
    )

    vcpus = 0
    try:
        vcpus = validate_vcpus(item.get("vcpus"))
    except ComputeContractError as exc:
        errors.append(f"{section} {exc}")

    memory_mb = 0
    try:
        memory_mb = validate_memory_mb(item.get("memory_mb"))
    except ComputeContractError as exc:
        errors.append(f"{section} {exc}")

    root_disk_gb = 0
    try:
        root_disk_gb = validate_root_disk_gb(item.get("root_disk_gb"))
    except ComputeContractError as exc:
        errors.append(f"{section} {exc}")

    try:
        config_schema_version = validate_config_schema_version(item.get("config_schema_version"))
    except ComputeContractError as exc:
        errors.append(f"{section} {exc}")
        config_schema_version = "v1"

    config: dict[str, Any] = {}
    if instance_kind in _INSTANCE_KINDS:
        try:
            config = validate_instance_config(item.get("config") or {}, instance_kind=instance_kind)
        except ComputeContractError as exc:
            errors.append(f"{section} {exc}")

    if errors:
        return None, errors

    return (
        DesiredComputeInstanceEntry(
            desired_node=desired_node,
            platform=platform,
            instance_kind=instance_kind,
            desired_power_state=desired_power_state,
            vcpus=vcpus,
            memory_mb=memory_mb,
            root_disk_gb=root_disk_gb,
            config_schema_version=config_schema_version,
            config=config,
        ),
        [],
    )


def _normalize_desired_service_placement_entry(
    item: Any,
    index: int,
) -> tuple[DesiredServicePlacementEntry | None, list[str]]:
    section = f"desired_service_placements entry {index}"
    allowed = {
        "desired_service",
        "instance_name",
        "desired_node",
        "desired_endpoint",
        "desired_state",
        "instance_role",
        "deployment_profile",
        "config_schema_version",
        "config",
        "assignment_source",
        "reason",
    }
    required = {
        "desired_service",
        "instance_name",
        "desired_node",
        "desired_state",
        "deployment_profile",
        "config_schema_version",
        "config",
        "assignment_source",
    }
    errors = _strict_mapping_errors(item, section, allowed, required)
    if errors:
        return None, errors

    try:
        desired_service = validate_desired_service_reference(item["desired_service"])
    except ContractError as exc:
        errors.append(f"{section} {exc}")
        desired_service = {}

    desired_endpoint = None
    if item.get("desired_endpoint") is not None:
        try:
            desired_endpoint = validate_endpoint_reference(item["desired_endpoint"])
        except ContractError as exc:
            errors.append(f"{section} {exc}")

    instance_name = _strict_slug(item.get("instance_name"), f"{section} instance_name", errors)
    desired_node = _strict_slug(item.get("desired_node"), f"{section} desired_node", errors)
    deployment_profile = _strict_slug(
        item.get("deployment_profile"),
        f"{section} deployment_profile",
        errors,
    )
    config_schema_version = _strict_nonempty_string(
        item.get("config_schema_version"),
        f"{section} config_schema_version",
        errors,
    )
    desired_state = _strict_choice(
        item.get("desired_state"),
        _PLACEMENT_STATES,
        f"{section} desired_state",
        errors,
    )
    assignment_source = _strict_choice(
        item.get("assignment_source"),
        _ASSIGNMENT_SOURCES,
        f"{section} assignment_source",
        errors,
    )
    config = item.get("config")
    if not isinstance(config, dict):
        errors.append(f"{section} config must be a mapping.")
        config = {}
    else:
        try:
            canonical_json(config)
        except ContractError as exc:
            errors.append(f"{section} config must be JSON-compatible with string mapping keys: {exc}")

    instance_role = _strict_optional_string(item.get("instance_role"), f"{section} instance_role", errors)
    reason = _strict_optional_string(item.get("reason"), f"{section} reason", errors)
    if errors:
        return None, errors
    return (
        DesiredServicePlacementEntry(
            desired_service=desired_service,
            instance_name=instance_name,
            desired_node=desired_node,
            desired_endpoint=desired_endpoint,
            desired_state=desired_state,
            instance_role=instance_role,
            deployment_profile=deployment_profile,
            config_schema_version=config_schema_version,
            config=config,
            assignment_source=assignment_source,
            reason=reason,
        ),
        [],
    )


def _normalize_desired_node_operational_override_entry(
    item: Any,
    index: int,
) -> tuple[DesiredNodeOperationalOverrideEntry | None, list[str]]:
    section = f"desired_node_operational_overrides entry {index}"
    allowed = {
        "desired_node",
        "declared_host_os",
        "connection_path",
        "local_endpoint",
        "tailscale_endpoint",
        "ansible_port",
        "power_control",
        "is_laptop",
    }
    required = {"desired_node"}
    errors = _strict_mapping_errors(item, section, allowed, required)
    if errors:
        return None, errors

    desired_node = _strict_slug(item.get("desired_node"), f"{section} desired_node", errors)
    connection_path = _strict_optional_choice(
        item.get("connection_path"),
        _CONNECTION_PATHS,
        f"{section} connection_path",
        errors,
    )
    power_control = _strict_optional_choice(
        item.get("power_control"),
        _POWER_CONTROLS,
        f"{section} power_control",
        errors,
    )
    declared_host_os = _strict_optional_choice(
        item.get("declared_host_os"),
        _DECLARED_HOST_OS,
        f"{section} declared_host_os",
        errors,
    )

    local_endpoint = _optional_endpoint_reference(item.get("local_endpoint"), section, "local_endpoint", errors)
    tailscale_endpoint = _optional_endpoint_reference(
        item.get("tailscale_endpoint"),
        section,
        "tailscale_endpoint",
        errors,
    )
    ansible_port = _strict_optional_port(item.get("ansible_port"), f"{section} ansible_port", errors)
    is_laptop = item.get("is_laptop")
    if is_laptop is not None and not isinstance(is_laptop, bool):
        errors.append(f"{section} is_laptop must be a boolean.")

    if connection_path == "tailscale" and tailscale_endpoint is None:
        errors.append(f"{section} tailscale connection requires tailscale_endpoint.")
    if connection_path == "tailscale" and local_endpoint is not None:
        errors.append(f"{section} tailscale connection forbids local_endpoint.")
    if tailscale_endpoint is not None and connection_path != "tailscale":
        errors.append(f"{section} tailscale_endpoint requires connection_path=tailscale.")
    if local_endpoint is not None and connection_path not in (None, "local"):
        errors.append(f"{section} local_endpoint permits only connection_path=local.")
    if declared_host_os == "haos" and power_control not in (None, "none"):
        errors.append(f"{section} HAOS permits only power_control=none.")
    if not any(
        (
            declared_host_os,
            connection_path,
            local_endpoint,
            tailscale_endpoint,
            ansible_port,
            power_control not in (None, "none"),
            is_laptop is True,
        )
    ):
        errors.append(f"{section} must contain at least one non-default override.")

    if errors:
        return None, errors
    return (
        DesiredNodeOperationalOverrideEntry(
            desired_node=desired_node,
            declared_host_os=declared_host_os,
            connection_path=connection_path,
            local_endpoint=local_endpoint,
            tailscale_endpoint=tailscale_endpoint,
            ansible_port=ansible_port,
            power_control=power_control,
            is_laptop=is_laptop,
        ),
        [],
    )


def _normalize_desired_ip_range_entry(item: Any, index: int) -> tuple[DesiredIPRangeEntry | None, list[str]]:
    """Normalize one desired IP range YAML item."""

    if not isinstance(item, dict):
        return None, [f"desired_ip_ranges entry {index} must be a mapping."]

    name = _optional_str(item.get("name"))
    slug = _optional_str(item.get("slug"))
    start_address = _optional_str(item.get("start_address"))
    end_address = _optional_str(item.get("end_address"))
    errors = []
    if not name:
        errors.append(f"desired_ip_ranges entry {index} is missing required field: name.")
    if not slug:
        errors.append(f"desired_ip_ranges entry {index} is missing required field: slug.")
    if not start_address:
        errors.append(f"desired_ip_ranges entry {index} is missing required field: start_address.")
    if not end_address:
        errors.append(f"desired_ip_ranges entry {index} is missing required field: end_address.")

    range_policy, range_policy_error = _choice_or_error(
        item.get("range_policy"),
        _RANGE_POLICIES,
        f"desired_ip_ranges entry {index} range_policy",
    )
    if range_policy_error:
        errors.append(range_policy_error)

    lifecycle, lifecycle_error = _choice_or_error(
        item.get("lifecycle", "planned"),
        _LIFECYCLES,
        f"desired_ip_ranges entry {index} lifecycle",
    )
    if lifecycle_error:
        errors.append(lifecycle_error)

    if start_address:
        errors.extend(_address_errors(start_address, f"desired_ip_ranges entry {index} start_address"))
    if end_address:
        errors.extend(_address_errors(end_address, f"desired_ip_ranges entry {index} end_address"))

    dnsmasq_options = item.get("dnsmasq_options") or {}
    if not isinstance(dnsmasq_options, dict):
        errors.append(f"desired_ip_ranges entry {index} dnsmasq_options must be a mapping.")

    if errors:
        return None, errors

    return (
        DesiredIPRangeEntry(
            name=name or "",
            slug=slug or "",
            start_address=start_address or "",
            end_address=end_address or "",
            range_policy=range_policy or "static_pool",
            lifecycle=lifecycle or "planned",
            generate_dnsmasq=_as_bool(item.get("generate_dnsmasq", False)),
            dnsmasq_options=_plain_mapping(dnsmasq_options),
            description=_optional_str(item.get("description")),
        ),
        [],
    )


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def _string_list_with_default(item: dict[Any, Any], key: str, default: tuple[str, ...]) -> tuple[list[str], bool]:
    if key not in item or item.get(key) is None:
        return list(default), True
    return _string_list(item.get(key)), False


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _optional_port(value: Any, index: int) -> tuple[int | None, str | None]:
    if value is None or value == "":
        return None, None
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None, f"desired_endpoints entry {index} port must be an integer."
    if port < 1 or port > 65535:
        return None, f"desired_endpoints entry {index} port must be between 1 and 65535."
    return port, None


def _choice(value: Any, allowed: set[str], default: str) -> str:
    normalized = str(value or default).strip().lower().replace("-", "_")
    return normalized if normalized in allowed else default


def _choice_or_error(value: Any, allowed: set[str], field_name: str) -> tuple[str | None, str | None]:
    if value is None or value == "":
        return None, f"{field_name} is missing required field."
    normalized = str(value).strip().lower().replace("-", "_")
    if normalized in allowed:
        return normalized, None
    return None, f"{field_name} must be one of: {', '.join(sorted(allowed))}."


def _choice_with_default_or_error(
    value: Any,
    allowed: set[str],
    field_name: str,
    default: str,
) -> tuple[str | None, str | None]:
    if value is None or value == "":
        return default, None
    return _choice_or_error(value, allowed, field_name)


def _actual_types_or_error(value: Any, node_type: str, field_name: str) -> tuple[list[str], str | None]:
    if value is None:
        return list(_ACTUAL_TYPE_DEFAULTS[node_type]), None
    if not isinstance(value, list):
        return [], f"{field_name} must be a list."

    actual_types = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return [], f"{field_name} must contain non-empty strings."
        normalized = item.strip().lower().replace("-", "_")
        if normalized not in _ACTUAL_TYPES:
            return [], f"{field_name} must be one of: {', '.join(sorted(_ACTUAL_TYPES))}."
        if normalized not in actual_types:
            actual_types.append(normalized)
    return actual_types, None


def _strict_mapping_errors(
    value: Any,
    section: str,
    allowed: set[str],
    required: set[str],
) -> list[str]:
    if not isinstance(value, dict):
        return [f"{section} must be a mapping."]
    unknown = sorted(str(key) for key in value if key not in allowed)
    missing = sorted(key for key in required if key not in value)
    errors = []
    if unknown:
        errors.append(f"{section} has unknown fields: {', '.join(unknown)}.")
    if missing:
        errors.append(f"{section} is missing required fields: {', '.join(missing)}.")
    return errors


def _strict_nonempty_string(value: Any, field_name: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field_name} must be a non-empty string.")
        return ""
    return value.strip()


def _strict_optional_string(value: Any, field_name: str, errors: list[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{field_name} must be a string or null.")
        return None
    return value.strip() or None


def _strict_slug(value: Any, field_name: str, errors: list[str]) -> str:
    normalized = _strict_nonempty_string(value, field_name, errors)
    if normalized and not _SLUG_RE.fullmatch(normalized):
        errors.append(f"{field_name} must be a lowercase slug.")
    return normalized


def _strict_choice(value: Any, allowed: set[str], field_name: str, errors: list[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        errors.append(f"{field_name} must be one of: {', '.join(sorted(allowed))}.")
        return ""
    return value


def _strict_optional_choice(
    value: Any,
    allowed: set[str],
    field_name: str,
    errors: list[str],
) -> str | None:
    if value is None:
        return None
    return _strict_choice(value, allowed, field_name, errors) or None


def _strict_optional_port(value: Any, field_name: str, errors: list[str]) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        errors.append(f"{field_name} must be an integer between 1 and 65535.")
        return None
    return value


def _optional_endpoint_reference(
    value: Any,
    section: str,
    field_name: str,
    errors: list[str],
) -> dict[str, str] | None:
    if value is None:
        return None
    try:
        return validate_endpoint_reference(value)
    except ContractError as exc:
        errors.append(f"{section} {field_name} {exc}")
        return None


def _optional_number(value: Any, field_name: str, errors: list[str]) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field_name} must be a number.")
        return None
    if value < 0:
        errors.append(f"{field_name} must not be negative.")
        return None
    return float(value)


def _duplicate_service_errors(entries: list[DesiredServiceEntry]) -> list[str]:
    seen = set()
    errors = []
    for entry in entries:
        key = (
            entry.intent_source,
            entry.catalog_namespace,
            entry.catalog_metadata_name,
            entry.service_type,
        )
        if key in seen:
            errors.append(
                "desired_services contains duplicate "
                "(intent_source, catalog_namespace, catalog_metadata_name, service_type): "
                f"{entry.intent_source}/{entry.catalog_namespace}/{entry.catalog_metadata_name}/{entry.service_type}."
            )
        seen.add(key)
    return errors


def _duplicate_placement_errors(entries: list[DesiredServicePlacementEntry]) -> list[str]:
    seen = set()
    errors = []
    for entry in entries:
        service_key = tuple(sorted(entry.desired_service.items()))
        key = (service_key, entry.instance_name)
        if key in seen:
            errors.append(
                "desired_service_placements contains duplicate desired_service and instance_name: "
                f"{entry.instance_name}."
            )
        seen.add(key)
    return errors


def _duplicate_endpoint_mac_errors(entries: list[DesiredEndpointEntry]) -> list[str]:
    seen: dict[str, None] = {}
    errors = []
    for entry in entries:
        if not entry.mac_address:
            continue
        if entry.mac_address in seen:
            errors.append(f"desired_endpoints contains duplicate mac_address: {entry.mac_address}.")
        seen[entry.mac_address] = None
    return errors


def _duplicate_compute_platform_errors(entries: list[DesiredComputePlatformEntry]) -> list[str]:
    seen: set[str] = set()
    errors = []
    for entry in entries:
        if entry.slug in seen:
            errors.append(f"desired_compute_platforms contains duplicate slug: {entry.slug}.")
        seen.add(entry.slug)
    return errors


def _duplicate_compute_instance_errors(entries: list[DesiredComputeInstanceEntry]) -> list[str]:
    seen: set[str] = set()
    errors = []
    for entry in entries:
        if entry.desired_node in seen:
            errors.append(
                f"desired_compute_instances contains duplicate desired_node: {entry.desired_node}."
            )
        seen.add(entry.desired_node)
    return errors


def _duplicate_operational_override_errors(entries: list[DesiredNodeOperationalOverrideEntry]) -> list[str]:
    seen = set()
    errors = []
    for entry in entries:
        if entry.desired_node in seen:
            errors.append(
                "desired_node_operational_overrides contains duplicate desired_node: "
                f"{entry.desired_node}."
            )
        seen.add(entry.desired_node)
    return errors


def _address_errors(value: str, field_name: str) -> list[str]:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return [f"{field_name} must be a valid IP address."]
    return []


def _plain_mapping(value: dict[Any, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()}


def _slug_from_text(value: str, fallback: str) -> str:
    slug = "-".join(part for part in str(value).lower().replace("_", "-").split() if part)
    slug = "".join(char if char.isalnum() or char == "-" else "-" for char in slug).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or fallback


def _resolve_configured_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return Path.cwd() / path


_INTENT_SOURCE_TYPES = {"git_repository", "manual"}
_INTENT_SOURCE_KEYS = {
    "url",
    "slug",
    "name",
    "source_type",
    "enabled",
    "ref",
    "owner",
    "service_hint",
    "catalog_paths",
    "basic_file_paths",
    "raw_url_template",
}
_NODE_TYPES = {"device", "virtual_machine", "container", "service_host"}
_ACTUAL_TYPES = {"device", "virtual_machine", "container"}
_ACTUAL_TYPE_DEFAULTS = {
    "device": ("device",),
    "virtual_machine": ("virtual_machine",),
    "container": ("container",),
    "service_host": ("device", "virtual_machine", "container"),
}
_LIFECYCLES = {"planned", "approved", "active", "deprecated", "retired"}
_LIFECYCLES_SERVICE = _LIFECYCLES | {"proposed"}
_INSTANCE_KINDS = {"container", "virtual_machine"}
_POWER_STATES = {"running", "stopped"}
_SERVICE_TYPES = {"service", "website", "worker", "database", "queue", "storage", "agent", "other"}
_ENDPOINT_TYPES = {"primary", "management", "service", "vpn", "mdns", "other"}
_DNSMASQ_RECORD_TYPES = {"host_record", "address", "cname"}
_IP_POLICIES = {"static", "dhcp_reserved", "external"}
_RANGE_POLICIES = {"static_pool", "dhcp_reservable_pool", "dhcp_dynamic_pool", "excluded"}
_PLACEMENT_STATES = {"active", "disabled"}
_ASSIGNMENT_SOURCES = {"manual", "yaml", "policy", "generated"}
_ACTUAL_STATE_POLICIES = {"required", "declared"}
_EXPECTED_HOST_OS = {"linux", "macos"}
_DECLARED_HOST_OS = {"haos"}
_CONNECTION_PATHS = {"local", "tailscale"}
_POWER_CONTROLS = {"none", "wol", "macos_sleep"}
_POWER_BY_PLATFORM = {
    "linux": {"none", "wol"},
    "macos": {"none", "macos_sleep"},
    "haos": {"none"},
}
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
