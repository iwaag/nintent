"""Helpers for importing catalog source and analysis output into models."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

from .loaders import (
    DesiredComputeInstanceEntry,
    DesiredComputePlatformEntry,
    DesiredEndpointEntry,
    DesiredIPRangeEntry,
    DesiredNodeEntry,
    DesiredNodeOperationalOverrideEntry,
    DesiredServiceEntry,
    DesiredServicePlacementEntry,
    IntentSourceEntry,
)


SOURCE_CONFIG_FIELDS = (
    "service_hint",
    "catalog_paths",
    "basic_file_paths",
    "catalog_paths_defaulted",
    "basic_file_paths_defaulted",
    "raw_url_template",
)


def intent_source_defaults(source: IntentSourceEntry) -> dict[str, Any]:
    """Return model defaults for an intent source loader entry.

    Git sources derive name/slug from the ``url`` when unset; manual sources are
    identified by an explicit ``slug``.
    """

    data = asdict(source)
    if source.source_type == "git_repository":
        name = data.get("service_hint") or source.name or _name_from_url(source.url)
        slug = source.slug or _slug_from_text(name or source.url)
    else:
        name = source.name or data.get("service_hint") or source.slug
        slug = source.slug
    return {
        "name": name,
        "slug": slug,
        "source_type": source.source_type,
        "enabled": data["enabled"],
        "ref": data["ref"],
        "owner": data["owner"],
        "description": None,
        "source_config": {field: data[field] for field in SOURCE_CONFIG_FIELDS},
    }


def desired_service_identity(service: dict[str, Any], intent_source_id: Any | None = None) -> dict[str, Any]:
    """Return the stable identity fields for an analyzed desired service."""

    catalog = _mapping(service.get("catalog"))
    identity = {
        "catalog_namespace": str(catalog.get("namespace") or "default"),
        "catalog_metadata_name": str(catalog.get("metadata_name") or service.get("name") or ""),
        "service_type": _service_type(catalog.get("spec_type") or service.get("role")),
    }
    if intent_source_id is not None:
        identity["intent_source_id"] = intent_source_id
    return identity


_ANALYSIS_PROVENANCE_KEYS = {"status", "confidence", "reasons", "warnings", "malformed_dependencies"}


def analysis_provenance_defaults(analysis: dict[str, Any]) -> dict[str, Any]:
    """Return the closed `DesiredService.analysis_provenance` shape for one analysis result.

    Fails closed on any key `analysis.py` doesn't yet know about, rather than silently
    absorbing it -- this is the internal contract boundary between `analysis.py` (producer)
    and the model (Phase 4 Decision 6), not user input, so an unexpected key is a real
    analysis.py/importers.py drift bug to catch immediately.
    """

    unknown = set(analysis) - _ANALYSIS_PROVENANCE_KEYS
    if unknown:
        raise ValueError(f"Unexpected analysis provenance keys: {sorted(unknown)}")
    return {
        "status": _optional_str(analysis.get("status")),
        "confidence": _optional_str(analysis.get("confidence")),
        "reasons": _list(analysis.get("reasons")),
        "warnings": _analysis_warnings(analysis),
    }


def _catalog_service_fields(service: dict[str, Any]) -> dict[str, Any]:
    """Source/catalog-derived fields an analysis refresh may touch (Phase 4 Step 4.3 item 1).

    Deliberately excludes `requirements`, `lifecycle`, `notes`, `name`, `slug`, and
    `display_name` -- those become operator territory once a service row exists, and must
    never be silently reset by a later `AnalyzeIntentSources` run.
    """

    catalog = _mapping(service.get("catalog"))
    source = _mapping(service.get("intent_source"))
    name = str(service.get("name") or "")
    return {
        "source_ref": _optional_str(source.get("ref")),
        "source_catalog_path": _optional_str(source.get("catalog_path")),
        "catalog_kind": _optional_str(catalog.get("kind")),
        "catalog_namespace": str(catalog.get("namespace") or "default"),
        "catalog_metadata_name": str(catalog.get("metadata_name") or name),
        "catalog_owner": _optional_str(catalog.get("owner")),
        "catalog_lifecycle": _optional_str(catalog.get("lifecycle")),
        "prefers_gpu": bool(service.get("prefers_gpu", False)),
        "min_memory_gb": service.get("min_memory_gb"),
    }


def desired_service_create_defaults(service: dict[str, Any]) -> dict[str, Any]:
    """Return model defaults for a newly analyzed desired service (creation only).

    `requirements` starts `{}` -- it is operator/catalog intent (Phase 4 Decision 6), not an
    analysis output, so nothing here ever seeds it from the analyzed source.
    """

    analysis = _mapping(service.get("analysis"))
    name = str(service.get("name") or "")
    service_type = _service_type(_mapping(service.get("catalog")).get("spec_type") or service.get("role"))
    return {
        "name": name,
        "slug": _slug_from_text(name),
        "display_name": str(service.get("display_name") or name),
        "service_type": service_type,
        "lifecycle": "proposed",
        **_catalog_service_fields(service),
        "requirements": {},
        "analysis_provenance": analysis_provenance_defaults(analysis),
        "notes": _optional_str(service.get("notes")),
    }


def desired_service_update_fields(service: dict[str, Any]) -> dict[str, Any]:
    """Return the fields an `AnalyzeIntentSources` refresh may overwrite on an existing service.

    Matches only "source/catalog fields ... and analysis_provenance" (p4/plan.md Step 4.3 item
    1): operator-owned `requirements`, `lifecycle`, `notes`, `name`, `slug`, and `display_name`
    are never touched by a refresh, only by manual edit.
    """

    analysis = _mapping(service.get("analysis"))
    return {
        **_catalog_service_fields(service),
        "analysis_provenance": analysis_provenance_defaults(analysis),
    }


def desired_service_entry_identity(entry: DesiredServiceEntry, intent_source_id: Any) -> dict[str, Any]:
    """Return the stable identity fields for a manually-declared desired service."""

    return {
        "intent_source_id": intent_source_id,
        "catalog_namespace": entry.catalog_namespace,
        "catalog_metadata_name": entry.catalog_metadata_name,
        "service_type": entry.service_type,
    }


def desired_service_entry_defaults(entry: DesiredServiceEntry) -> dict[str, Any]:
    """Return model defaults for a manually-declared desired service loader entry."""

    return {
        "name": entry.name,
        "slug": entry.slug,
        "display_name": entry.display_name,
        "lifecycle": entry.lifecycle,
        "source_ref": entry.source_ref,
        "source_catalog_path": entry.source_catalog_path,
        "catalog_kind": entry.catalog_kind,
        "catalog_owner": entry.catalog_owner,
        "catalog_lifecycle": entry.catalog_lifecycle,
        "prefers_gpu": entry.prefers_gpu,
        "min_memory_gb": entry.min_memory_gb,
        "requirements": {},
        "notes": entry.notes,
    }


def desired_service_entry_update_fields(entry: DesiredServiceEntry) -> dict[str, Any]:
    """Return the fields Import may overwrite on an *existing* manually-declared DesiredService.

    Only `lifecycle` and `notes` are YAML-update-owned (plan.md interface_contract/p1 Section
    5.3): `requirements` has no YAML input field and must never be reset to `{}` on re-import;
    `name`/`slug`/`display_name` are handled separately by
    `desired_service_entry_locked_fields()` (a disagreement there is a conflict, not a silent
    preserve); every other field (`source_ref`, `source_catalog_path`, `catalog_kind`,
    `catalog_owner`, `catalog_lifecycle`, `prefers_gpu`, `min_memory_gb`) is
    Analyze-Job-owned and must survive a re-import unchanged.
    """

    return {"lifecycle": entry.lifecycle, "notes": entry.notes}


def desired_service_entry_locked_fields(entry: DesiredServiceEntry) -> dict[str, Any]:
    """Return the DesiredService fields that block as a `conflict` rather than being silently
    preserved or overwritten when an existing row disagrees (plan.md Section 5.3)."""

    return {"name": entry.name, "slug": entry.slug, "display_name": entry.display_name}


def dependency_defaults(dependency: dict[str, Any]) -> dict[str, Any]:
    """Return model defaults for a normalized dependency."""

    dependency_kind = str(dependency.get("dependency_kind") or dependency.get("kind") or "")
    return {
        "dependency_kind": dependency_kind,
        "namespace": str(dependency.get("namespace") or "default"),
        "name": str(dependency.get("name") or ""),
        "raw_ref": str(dependency.get("raw_ref") or ""),
        "dependency_type": str(dependency.get("dependency_type") or dependency_kind),
        "resolution_status": str(dependency.get("resolution_status") or "unresolved"),
    }


def dependency_key(dependency: dict[str, Any]) -> tuple[str, str, str]:
    """Return the natural key for one dependency under a source service."""

    defaults = dependency_defaults(dependency)
    return defaults["dependency_kind"], defaults["namespace"], defaults["name"]


def desired_service_dependencies(service: dict[str, Any]) -> list[dict[str, Any]]:
    """Return dependency rows from an analyzed desired service, dropping malformed empty entries."""

    dependencies = service.get("dependencies")
    if not isinstance(dependencies, list):
        return []
    return [
        dependency_defaults(dependency)
        for dependency in dependencies
        if isinstance(dependency, dict)
        and dependency.get("kind")
        and dependency.get("namespace")
        and dependency.get("name")
    ]


def plan_dependency_sync(
    existing: list[dict[str, Any]],
    service: dict[str, Any],
) -> dict[str, Any]:
    """Pure natural-key diff plan for one service's dependencies (Phase 4 Step 4.3 items 3-4).

    `existing` is a list of dicts with at least `dependency_kind`/`namespace`/`name` (the
    natural key, matching `nic_unique_dependency_ref`) plus `raw_ref`/`dependency_type` for
    each currently-stored row. Returns a plan with:

    - `create`: full `dependency_defaults()` dicts for keys not currently stored
      (`resolution_status` always `unresolved` for a brand new key);
    - `update`: `{"key": key, "raw_ref": ..., "dependency_type": ...}` for retained keys whose
      *source-owned* fields changed -- `notes`/`resolution_status`/`resolved_service` are
      deliberately absent here so the caller never overwrites them;
    - `unchanged_keys`: retained keys needing no write at all;
    - `delete_keys`: keys stored today but absent from this analysis run.

    Raises `ValueError` before returning any plan if the incoming analysis contains duplicate
    normalized keys -- the caller must reject the whole batch rather than silently keep one.
    """

    incoming = desired_service_dependencies(service)
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for dependency in incoming:
        key = dependency_key(dependency)
        if key in seen:
            raise ValueError(f"Duplicate dependency key in analyzed source: {key!r}")
        seen[key] = dependency

    existing_by_key = {dependency_key(row): row for row in existing}

    create: list[dict[str, Any]] = []
    update: list[dict[str, Any]] = []
    unchanged_keys: list[tuple[str, str, str]] = []
    for key, dependency in seen.items():
        if key not in existing_by_key:
            create.append(dependency_defaults(dependency))
            continue
        current = existing_by_key[key]
        if current.get("raw_ref") != dependency["raw_ref"] or current.get("dependency_type") != dependency["dependency_type"]:
            update.append({"key": key, "raw_ref": dependency["raw_ref"], "dependency_type": dependency["dependency_type"]})
        else:
            unchanged_keys.append(key)

    delete_keys = [key for key in existing_by_key if key not in seen]

    return {"create": create, "update": update, "unchanged_keys": unchanged_keys, "delete_keys": delete_keys}


def desired_node_identity(node: DesiredNodeEntry) -> dict[str, Any]:
    """Return the stable identity fields for a desired node."""

    return {"slug": node.slug}


def desired_node_defaults(node: DesiredNodeEntry, intent_source_id: Any | None = None) -> dict[str, Any]:
    """Return model defaults for a desired node loader entry."""

    defaults = {
        "name": node.name,
        "node_type": node.node_type,
        "accepted_actual_types": node.accepted_actual_types,
        "lifecycle": node.lifecycle,
        "role": node.role,
        "description": node.description,
        "expected_spec": node.expected_spec,
        "notes": node.notes,
        "intent_source_id": intent_source_id,
    }
    return defaults


def desired_node_update_fields(node: DesiredNodeEntry, intent_source_id: Any | None = None) -> dict[str, Any]:
    """Return the fields Import may overwrite on an *existing* DesiredNode.

    Excludes `lifecycle` (create-only per plan.md interface_contract/p1 Section 5.3 -- a later
    `nctl lifecycle` transition must survive re-import) and any realized link/source, which
    `desired_node_defaults()` never included in the first place.
    """

    defaults = desired_node_defaults(node, intent_source_id=intent_source_id)
    defaults.pop("lifecycle", None)
    return defaults


def desired_endpoint_identity(endpoint: DesiredEndpointEntry, desired_node_id: Any) -> dict[str, Any]:
    """Return the stable identity fields for a desired endpoint."""

    return {
        "desired_node_id": desired_node_id,
        "name": endpoint.name,
        "endpoint_type": endpoint.endpoint_type,
    }


def desired_endpoint_defaults(endpoint: DesiredEndpointEntry, desired_node: Any | None = None) -> dict[str, Any]:
    """Return model defaults for a desired endpoint loader entry.

    An omitted `dns_name`/`mdns_name` stays omitted -- Import never synthesizes a hidden
    default for either field (plan.md interface_contract/p1 Section 4.3): the checked-in YAML
    is the single explicit source of desired DNS/mDNS intent, not a Quick-Host-Add-era
    convenience default computed from the node name.
    """

    if endpoint.ip_address and not endpoint.ip_policy:
        raise ValueError("Desired endpoint with ip_address requires ip_policy.")

    dns_name = _optional_str(endpoint.dns_name)
    mdns_name = _optional_str(endpoint.mdns_name)
    dns_name_was_explicit = dns_name is not None
    mdns_name_was_explicit = mdns_name is not None

    return {
        "ip_address": endpoint.ip_address,
        "mac_address": endpoint.mac_address,
        "dns_name": dns_name,
        "dns_name_source": "intent" if dns_name_was_explicit else ("derived" if dns_name else None),
        "mdns_name": mdns_name,
        "mdns_name_source": "intent" if mdns_name_was_explicit else ("derived" if mdns_name else None),
        "vpn_dns_name": endpoint.vpn_dns_name,
        "protocol": endpoint.protocol,
        "port": endpoint.port,
        "generate_dnsmasq": endpoint.generate_dnsmasq,
        # loaders._parse_desired_endpoint already resolves a real ip_policy
        # (explicit or the no-address/no-policy "external" default) before an
        # entry reaches here; this is a pure projection, not a second default.
        "ip_policy": endpoint.ip_policy,
        "dnsmasq_record_type": endpoint.dnsmasq_record_type,
        "description": endpoint.description,
    }


def desired_compute_platform_identity(platform: DesiredComputePlatformEntry) -> dict[str, Any]:
    """Return the stable identity fields for a desired compute platform."""

    return {"slug": platform.slug}


def desired_compute_platform_defaults(platform: DesiredComputePlatformEntry, control_node_id: Any) -> dict[str, Any]:
    """Return model defaults for a desired compute platform loader entry."""

    return {
        "name": platform.name,
        "provider_type": platform.provider_type,
        "lifecycle": platform.lifecycle,
        "control_node_id": control_node_id,
        "config_schema_version": platform.config_schema_version,
        "config": platform.config,
    }


def desired_compute_instance_identity(desired_node_id: Any) -> dict[str, Any]:
    """Return the stable one-to-one identity for a desired compute instance."""

    return {"desired_node_id": desired_node_id}


def desired_compute_instance_defaults(instance: DesiredComputeInstanceEntry, platform_id: Any) -> dict[str, Any]:
    """Return model defaults for a desired compute instance loader entry."""

    return {
        "platform_id": platform_id,
        "instance_kind": instance.instance_kind,
        "desired_power_state": instance.desired_power_state,
        "vcpus": instance.vcpus,
        "memory_mb": instance.memory_mb,
        "root_disk_gb": instance.root_disk_gb,
        "config_schema_version": instance.config_schema_version,
        "config": instance.config,
    }


def desired_ip_range_identity(ip_range: DesiredIPRangeEntry) -> dict[str, Any]:
    """Return the stable identity fields for a desired IP range."""

    return {"slug": ip_range.slug}


def desired_ip_range_defaults(ip_range: DesiredIPRangeEntry) -> dict[str, Any]:
    """Return model defaults for a desired IP range loader entry."""

    return {
        "name": ip_range.name,
        "start_address": ip_range.start_address,
        "end_address": ip_range.end_address,
        "range_policy": ip_range.range_policy,
        "lifecycle": ip_range.lifecycle,
        "generate_dnsmasq": ip_range.generate_dnsmasq,
        "dnsmasq_options": ip_range.dnsmasq_options,
        "description": ip_range.description,
    }


def desired_service_placement_identity(
    placement: DesiredServicePlacementEntry,
    desired_service_id: Any,
) -> dict[str, Any]:
    """Return the stable identity for one service instance."""

    return {
        "desired_service_id": desired_service_id,
        "instance_name": placement.instance_name,
    }


def desired_service_placement_defaults(
    placement: DesiredServicePlacementEntry,
    desired_node_id: Any,
    desired_endpoint_id: Any | None,
) -> dict[str, Any]:
    """Return placement-owned values without introducing Ansible group semantics."""

    return {
        "desired_node_id": desired_node_id,
        "desired_endpoint_id": desired_endpoint_id,
        "desired_state": placement.desired_state,
        "instance_role": placement.instance_role,
        "deployment_profile": placement.deployment_profile,
        "config_schema_version": placement.config_schema_version,
        "config": placement.config,
        "assignment_source": placement.assignment_source,
        "reason": placement.reason,
    }


def desired_node_operational_override_identity(
    operational_override: DesiredNodeOperationalOverrideEntry,
    desired_node_id: Any,
) -> dict[str, Any]:
    """Return the one-to-one identity for a desired node operational override."""

    return {"desired_node_id": desired_node_id}


def desired_node_operational_override_defaults(
    operational_override: DesiredNodeOperationalOverrideEntry,
    local_endpoint_id: Any | None,
    tailscale_endpoint_id: Any | None,
) -> dict[str, Any]:
    """Return only explicit override values."""

    return {
        "declared_host_os": operational_override.declared_host_os,
        "connection_path": operational_override.connection_path,
        "local_endpoint_id": local_endpoint_id,
        "tailscale_endpoint_id": tailscale_endpoint_id,
        "ansible_port": operational_override.ansible_port,
        "power_control": operational_override.power_control,
        "is_laptop": operational_override.is_laptop,
    }


def _analysis_warnings(analysis: dict[str, Any]) -> list[Any]:
    warnings = []
    raw_warnings = analysis.get("warnings")
    if isinstance(raw_warnings, list):
        warnings.extend(raw_warnings)
    malformed_dependencies = analysis.get("malformed_dependencies")
    if malformed_dependencies:
        warnings.append({"malformed_dependencies": malformed_dependencies})
    return warnings


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _service_type(value: Any) -> str:
    normalized = str(value or "service").strip().lower().replace("-", "_")
    return normalized if normalized in {"service", "website", "worker", "database", "queue", "storage", "agent"} else "other"


def _name_from_url(url: str) -> str:
    parsed = urlparse(url)
    path_name = parsed.path.rstrip("/").rsplit("/", maxsplit=1)[-1]
    if path_name:
        return path_name.removesuffix(".git")
    return parsed.netloc or url


def _slug_from_text(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "intent-source"
