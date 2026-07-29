"""In-memory desired-state batch planning and atomic application."""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import asdict
from typing import Any


SCHEMA_VERSION = "nintent.desired-state-batch.v1"
KIND_ORDER = (
    "intent_source", "desired_node", "desired_ip_range", "desired_endpoint",
    "desired_compute_platform", "desired_compute_instance", "desired_service",
    "desired_dependency", "desired_service_placement", "desired_node_operational_override",
)


class BatchValidationError(ValueError):
    """A deterministic request-document validation failure."""


@dataclass(frozen=True)
class Operation:
    index: int
    op: str
    kind: str
    key: dict[str, Any]
    values: dict[str, Any]


@dataclass
class BatchResult:
    operations: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    transaction: dict[str, Any] = field(default_factory=lambda: {"status": "planned", "committed": False})

    def as_dict(self) -> dict[str, Any]:
        ordered = sorted(self.operations, key=lambda item: item["index"])
        totals = {name: 0 for name in ("create", "update", "delete", "unchanged", "conflict")}
        for item in ordered:
            totals[item["action"]] += 1
        return {"schema_version": SCHEMA_VERSION, "operations": ordered, "errors": self.errors,
                "totals": totals, "transaction": self.transaction}


_KEYS = {
    "intent_source": ("slug",), "desired_node": ("slug",), "desired_ip_range": ("slug",),
    "desired_endpoint": ("desired_node", "name", "endpoint_type"),
    "desired_compute_platform": ("slug",), "desired_compute_instance": ("desired_node",),
    "desired_service": ("intent_source", "catalog_namespace", "catalog_metadata_name", "service_type"),
    "desired_dependency": ("source_service", "dependency_kind", "namespace", "name"),
    "desired_service_placement": ("desired_service", "instance_name"),
    "desired_node_operational_override": ("desired_node",),
}

_FIELDS = {
    "intent_source": {"slug"},
    "desired_node": {"name", "slug", "node_type", "lifecycle", "role", "accepted_actual_types", "expected_spec", "realized_device"},
    "desired_ip_range": {"name", "slug", "start_address", "end_address", "range_policy", "lifecycle", "generate_dnsmasq", "dnsmasq_options"},
    "desired_endpoint": {"desired_node", "name", "endpoint_type", "ip_address", "gateway_address", "ip_policy", "mac_address", "dns_name", "mdns_name", "vpn_dns_name", "protocol", "port", "generate_dnsmasq", "dnsmasq_record_type", "realized_ip_address"},
    "desired_compute_platform": {"name", "slug", "lifecycle", "control_node", "config", "realized_cluster"},
    "desired_compute_instance": {"desired_node", "platform", "instance_kind", "desired_power_state", "vcpus", "memory_mb", "root_disk_gb", "config", "realized_vm"},
    "desired_service": {"intent_source", "name", "slug", "service_type", "lifecycle", "catalog_namespace", "catalog_metadata_name"},
    "desired_dependency": {"source_service", "dependency_kind", "namespace", "name", "raw_ref", "dependency_type", "resolution_status", "resolved_service", "notes"},
    "desired_service_placement": {"desired_service", "desired_node", "desired_endpoint", "instance_name", "desired_state", "deployment_profile", "config_schema_version", "config"},
    "desired_node_operational_override": {"desired_node", "declared_host_os", "connection_path", "local_endpoint", "tailscale_endpoint", "ansible_port", "power_control", "is_laptop"},
}

_CREATE_REQUIRED = {
    "intent_source": {"slug"}, "desired_node": {"name", "node_type", "lifecycle"},
    "desired_ip_range": {"name", "start_address", "end_address", "range_policy"},
    "desired_endpoint": {"desired_node", "name", "endpoint_type"},
    "desired_compute_platform": {"name", "lifecycle", "control_node", "config"},
    "desired_compute_instance": {"desired_node", "platform", "instance_kind", "vcpus", "memory_mb", "root_disk_gb", "config"},
    "desired_service": {"intent_source", "name", "slug", "service_type", "catalog_namespace", "catalog_metadata_name"},
    "desired_dependency": {"source_service", "dependency_kind", "namespace", "name", "raw_ref", "dependency_type"},
    "desired_service_placement": {"desired_service", "desired_node", "instance_name", "deployment_profile", "config_schema_version", "config"},
    "desired_node_operational_override": {"desired_node"},
}


def decode_batch(document: dict[str, Any]) -> tuple[bool, list[Operation]]:
    """Validate the HTTP-independent envelope and return immutable operations."""
    if not isinstance(document, dict):
        raise BatchValidationError("document must be an object")
    if set(document) != {"dry_run", "operations"}:
        raise BatchValidationError("document keys must be exactly dry_run and operations")
    if not isinstance(document["dry_run"], bool) or not isinstance(document["operations"], list):
        raise BatchValidationError("dry_run must be boolean and operations must be a list")
    operations: list[Operation] = []
    seen: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for index, raw in enumerate(document["operations"]):
        if not isinstance(raw, dict) or set(raw) != {"op", "kind", "key", "values"}:
            raise BatchValidationError(f"operations[{index}] must contain op, kind, key, values")
        op, kind, key, values = raw["op"], raw["kind"], raw["key"], raw["values"]
        if op not in {"upsert", "delete"} or kind not in _KEYS or not isinstance(key, dict) or not isinstance(values, dict):
            raise BatchValidationError(f"operations[{index}] has invalid op, kind, key, or values")
        if tuple(key) != _KEYS[kind] or any(not value for value in key.values()):
            raise BatchValidationError(f"operations[{index}].key is not the identity for {kind}")
        if op == "delete" and values:
            raise BatchValidationError(f"operations[{index}].values must be empty for delete")
        unknown = set(values) - _FIELDS[kind]
        if unknown:
            raise BatchValidationError(f"operations[{index}].values has unknown fields: {', '.join(sorted(unknown))}")
        duplicate_key = (kind, tuple(sorted((name, repr(value)) for name, value in key.items())))
        if duplicate_key in seen:
            raise BatchValidationError(f"operations[{index}] duplicates an earlier {kind} identity")
        seen.add(duplicate_key)
        operations.append(Operation(index, op, kind, dict(key), dict(values)))
    return document["dry_run"], operations


def plan_batch(document: dict[str, Any]) -> BatchResult:
    """Plan a decoded desired-state batch without writing to the ORM."""
    dry_run, operations = decode_batch(document)
    result = BatchResult(transaction={"status": "dry_run" if dry_run else "planned", "committed": False})
    try:
        models = _models()
    except (ImportError, AttributeError):
        models = None
    deleted_pks = _planned_delete_pks(operations, models) if models else {}
    planned_keys = {(operation.kind, _identity_key(operation.key)) for operation in operations if operation.op == "upsert"}
    for operation in operations:
        if models is None:
            action, reason = ("unchanged", None) if operation.op == "delete" else ("conflict", "Django is not configured")
            result.operations.append(_planned(operation, action, reason=reason))
            continue
        model = models[operation.kind]
        try:
            try:
                row = _find(model, operation.kind, operation.key)
            except BatchValidationError:
                if _references_are_planned(operation, planned_keys):
                    row = None
                else:
                    raise
            if operation.op == "delete":
                blockers = _delete_blockers(operation.kind, row, deleted_pks) if row else []
                result.operations.append(_planned(operation, "conflict" if blockers else ("delete" if row else "unchanged"),
                                                reason=f"blocked by: {', '.join(blockers)}" if blockers else None))
            elif row is None:
                missing = sorted(_CREATE_REQUIRED[operation.kind] - set(operation.values) - set(operation.key))
                result.operations.append(_planned(operation, "conflict" if missing else "create",
                                                reason=f"missing required fields: {', '.join(missing)}" if missing else None))
            else:
                changed = {name: {"old": getattr(row, f"{name}_id", getattr(row, name, None)), "new": value}
                           for name, value in operation.values.items()
                           if getattr(row, name, None) != value}
                result.operations.append(_planned(operation, "update" if changed else "unchanged", changed=changed,
                                                preserved=sorted(_FIELDS[operation.kind] - set(operation.values))))
        except Exception as exc:  # planner reports one bad operation without aborting peers
            result.operations.append(_planned(operation, "conflict", reason=str(exc)))
    return result


def apply_batch(document: dict[str, Any]) -> BatchResult:
    """Plan first; Django-backed application is added by the runtime adapter."""
    result = plan_batch(document)
    if document["dry_run"]:
        return result
    if result.errors or any(item["action"] == "conflict" for item in result.operations):
        result.transaction = {"status": "blocked", "committed": False}
        return result
    from django.db import transaction
    models = _models()
    by_index = {item["index"]: item for item in result.operations}
    try:
        with transaction.atomic():
            operations = decode_batch(document)[1]
            upserts = [item for item in operations if item.op == "upsert"]
            deletes = [item for item in operations if item.op == "delete"]
            ordered = sorted(upserts, key=lambda item: (KIND_ORDER.index(item.kind), item.index))
            ordered += sorted(deletes, key=lambda item: (-KIND_ORDER.index(item.kind), item.index))
            for operation in ordered:
                item = by_index[operation.index]
                model = models[operation.kind]
                row = _find(model, operation.kind, operation.key)
                if item["action"] == "delete":
                    row.delete()
                elif item["action"] in {"create", "update"}:
                    values = _orm_values(operation.kind, operation.values, models)
                    if row is None:
                        row = model(**_orm_values(operation.kind, operation.key, models), **values)
                    else:
                        for name, value in values.items():
                            setattr(row, name, value)
                    row.full_clean()
                    row.save()
    except Exception as exc:  # transaction guarantees all-or-nothing
        result.transaction = {"status": "rolled_back", "committed": False, "error": f"{type(exc).__name__}: {exc}"}
        return result
    result.transaction = {"status": "committed", "committed": True}
    return result


def document_from_load_result(load_result: Any, *, dry_run: bool) -> dict[str, Any]:
    """Map legacy YAML roots to non-destructive upsert operations for the Job."""
    roots = {
        "intent_source": load_result.intent_sources,
        "desired_node": load_result.desired_nodes,
        "desired_ip_range": load_result.desired_ip_ranges,
        "desired_endpoint": load_result.desired_endpoints,
        "desired_compute_platform": load_result.desired_compute_platforms,
        "desired_compute_instance": load_result.desired_compute_instances,
        "desired_service": load_result.desired_services,
        "desired_service_placement": load_result.desired_service_placements,
        "desired_node_operational_override": load_result.desired_node_operational_overrides,
    }
    operations = []
    for kind in KIND_ORDER:
        for entry in roots.get(kind, []):
            values = asdict(entry)
            key = {name: values.pop(name) for name in _KEYS[kind]}
            operations.append({"op": "upsert", "kind": kind, "key": key, "values": values})
    return {"dry_run": dry_run, "operations": operations}


def _planned(operation: Operation, action: str, *, changed: dict[str, Any] | None = None,
             preserved: list[str] | None = None, reason: str | None = None) -> dict[str, Any]:
    return {"index": operation.index, "op": operation.op, "kind": operation.kind, "identity": operation.key,
            "action": action, "changed_fields": changed or {}, "preserved_fields": preserved or [], "reason": reason}


def _models() -> dict[str, Any]:
    from . import models
    return {"intent_source": models.IntentSource, "desired_node": models.DesiredNode,
            "desired_ip_range": models.DesiredIPRange, "desired_endpoint": models.DesiredEndpoint,
            "desired_compute_platform": models.DesiredComputePlatform, "desired_compute_instance": models.DesiredComputeInstance,
            "desired_service": models.DesiredService, "desired_dependency": models.DesiredDependency,
            "desired_service_placement": models.DesiredServicePlacement,
            "desired_node_operational_override": models.DesiredNodeOperationalOverride}


_REFERENCE_KIND = {"desired_node": "desired_node", "control_node": "desired_node", "platform": "desired_compute_platform",
                   "intent_source": "intent_source", "source_service": "desired_service", "resolved_service": "desired_service",
                   "desired_service": "desired_service", "desired_endpoint": "desired_endpoint",
                   "local_endpoint": "desired_endpoint", "tailscale_endpoint": "desired_endpoint"}


def _find(model: Any, kind: str, key: dict[str, Any]) -> Any | None:
    return model.objects.filter(**_orm_values(kind, key, _models())).first()


def _orm_values(kind: str, values: dict[str, Any], models: dict[str, Any]) -> dict[str, Any]:
    resolved = {}
    for name, value in values.items():
        if name not in _REFERENCE_KIND or value is None:
            resolved[name] = value
            continue
        target_kind = _REFERENCE_KIND[name]
        target = _find(models[target_kind], target_kind, value if isinstance(value, dict) else {"slug": value})
        if target is None:
            raise BatchValidationError(f"unresolved {name} reference: {value!r}")
        resolved[name] = target
    return resolved


_DELETE_BLOCKERS = {
    "intent_source": (("desired_services", "desired_service"),),
    "desired_node": (("desired_endpoints", "desired_endpoint"), ("controlled_compute_platforms", "desired_compute_platform"),
                     ("desired_compute_instance", "desired_compute_instance"), ("service_placements", "desired_service_placement"),
                     ("operational_override", "desired_node_operational_override")),
    "desired_endpoint": (("service_placements", "desired_service_placement"), ("local_operational_overrides", "desired_node_operational_override"),
                         ("tailscale_operational_overrides", "desired_node_operational_override")),
    "desired_compute_platform": (("desired_compute_instances", "desired_compute_instance"),),
    "desired_service": (("dependencies", "desired_dependency"), ("resolved_by_dependencies", "desired_dependency"),
                        ("placements", "desired_service_placement")),
}


def _planned_delete_pks(operations: list[Operation], models: dict[str, Any]) -> dict[str, set[Any]]:
    result: dict[str, set[Any]] = {}
    for operation in operations:
        if operation.op != "delete":
            continue
        row = _find(models[operation.kind], operation.kind, operation.key)
        if row is not None:
            result.setdefault(operation.kind, set()).add(row.pk)
    return result


def _delete_blockers(kind: str, row: Any, deleted_pks: dict[str, set[Any]]) -> list[str]:
    if row is None:
        return []
    blockers = []
    for relation, related_kind in _DELETE_BLOCKERS.get(kind, ()):
        try:
            related = getattr(row, relation, None)
        except Exception:  # absent reverse one-to-one relation
            related = None
        rows = related.all() if hasattr(related, "all") else ([related] if related is not None else [])
        remaining = [item for item in rows if item.pk not in deleted_pks.get(related_kind, set())]
        blockers.extend(f"{related_kind}:{item.pk}" for item in remaining)
    return sorted(blockers)


def _identity_key(key: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((name, repr(value)) for name, value in key.items()))


def _references_are_planned(operation: Operation, planned_keys: set[tuple[str, tuple[tuple[str, str], ...]]]) -> bool:
    for name, value in {**operation.key, **operation.values}.items():
        target_kind = _REFERENCE_KIND.get(name)
        if target_kind is None or value is None:
            continue
        reference = value if isinstance(value, dict) else {"slug": value}
        if (target_kind, _identity_key(reference)) not in planned_keys:
            return False
    return True
