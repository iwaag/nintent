"""In-memory desired-state batch planning and atomic application."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SCHEMA_VERSION = "nintent.desired-state-batch.v1"
KIND_ORDER = (
    "desired_node", "desired_ip_range", "desired_endpoint",
    "desired_compute_platform", "desired_compute_instance", "desired_service",
    "desired_service_placement", "desired_service_binding", "desired_node_operational_override",
    "desired_workspace",
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
    "desired_node": ("slug",), "desired_ip_range": ("slug",),
    "desired_endpoint": ("desired_node", "name", "endpoint_type"),
    "desired_compute_platform": ("slug",), "desired_compute_instance": ("desired_node",),
    "desired_service": ("slug",),
    "desired_service_placement": ("desired_service", "instance_name"),
    "desired_service_binding": ("consumer_placement", "binding_name"),
    "desired_node_operational_override": ("desired_node",),
    "desired_workspace": ("slug",),
}

_FIELDS = {
    "desired_node": {"name", "slug", "node_type", "lifecycle", "role", "accepted_actual_types", "expected_spec", "realized_device"},
    "desired_ip_range": {"name", "slug", "start_address", "end_address", "range_policy", "lifecycle", "generate_dnsmasq", "dnsmasq_options"},
    "desired_endpoint": {"desired_node", "name", "endpoint_type", "ip_address", "gateway_address", "ip_policy", "mac_address", "dns_name", "mdns_name", "vpn_dns_name", "protocol", "port", "generate_dnsmasq", "dnsmasq_record_type", "realized_ip_address"},
    "desired_compute_platform": {"name", "slug", "lifecycle", "control_node", "config", "realized_cluster"},
    "desired_compute_instance": {"desired_node", "platform", "instance_kind", "desired_power_state", "desired_presence", "vcpus", "memory_mb", "root_disk_gb", "config", "realized_vm"},
    "desired_service": {"name", "slug", "lifecycle"},
    "desired_service_placement": {"desired_service", "desired_node", "desired_endpoint", "instance_name", "desired_state", "deployment_profile", "config_schema_version", "config"},
    "desired_service_binding": {"consumer_placement", "binding_name", "provider_service"},
    "desired_node_operational_override": {"desired_node", "connection_path", "local_endpoint", "tailscale_endpoint", "ansible_port", "power_control", "is_laptop"},
    "desired_workspace": {"name", "slug", "lifecycle", "source_remote_url", "desired_node", "expected_path", "desired_presence"},
}

_CREATE_REQUIRED = {
    "desired_node": {"name", "node_type", "lifecycle"},
    "desired_ip_range": {"name", "start_address", "end_address", "range_policy"},
    "desired_endpoint": {"desired_node", "name", "endpoint_type"},
    "desired_compute_platform": {"name", "lifecycle", "control_node", "config"},
    "desired_compute_instance": {"desired_node", "platform", "instance_kind", "vcpus", "memory_mb", "root_disk_gb", "config"},
    "desired_service": {"name", "slug"},
    "desired_service_placement": {"desired_service", "desired_node", "instance_name", "deployment_profile", "config_schema_version", "config"},
    "desired_service_binding": {"consumer_placement", "binding_name", "provider_service"},
    "desired_node_operational_override": {"desired_node"},
    "desired_workspace": {"name", "slug", "source_remote_url", "desired_node", "expected_path"},
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
    references = _PlannedReferenceResolver(operations, models) if models else None
    for operation in operations:
        if models is None:
            action, reason = ("unchanged", None) if operation.op == "delete" else ("conflict", "Django is not configured")
            result.operations.append(_planned(operation, action, reason=reason))
            continue
        model = models[operation.kind]
        try:
            missing_reference = references.missing_reference(operation)
            if missing_reference is not None:
                raise BatchValidationError(f"unresolved {missing_reference[0]} reference: {missing_reference[1]!r}")
            row = _find(model, operation.kind, operation.key) if references.identity_exists(operation) else None
            if operation.op == "delete":
                blockers = _delete_blockers(operation.kind, row, deleted_pks) if row else []
                result.operations.append(_planned(operation, "conflict" if blockers else ("delete" if row else "unchanged"),
                                                reason=f"blocked by: {', '.join(blockers)}" if blockers else None))
            elif row is None:
                missing = sorted(_CREATE_REQUIRED[operation.kind] - set(operation.values) - set(operation.key))
                result.operations.append(_planned(operation, "conflict" if missing else "create",
                                                reason=f"missing required fields: {', '.join(missing)}" if missing else None))
            else:
                changed = {
                    name: {"old": getattr(row, f"{name}_id", getattr(row, name, None)), "new": value}
                    for name, value in operation.values.items()
                    if _value_differs(row, name, value, models)
                }
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
            _validate_service_binding_graph(models)
    except Exception as exc:  # transaction guarantees all-or-nothing
        result.transaction = {"status": "rolled_back", "committed": False, "error": f"{type(exc).__name__}: {exc}"}
        return result
    result.transaction = {"status": "committed", "committed": True}
    return result


def _planned(operation: Operation, action: str, *, changed: dict[str, Any] | None = None,
             preserved: list[str] | None = None, reason: str | None = None) -> dict[str, Any]:
    return {"index": operation.index, "op": operation.op, "kind": operation.kind, "identity": operation.key,
            "action": action, "changed_fields": changed or {}, "preserved_fields": preserved or [], "reason": reason}


def _models() -> dict[str, Any]:
    from . import models
    return {"desired_node": models.DesiredNode,
            "desired_ip_range": models.DesiredIPRange, "desired_endpoint": models.DesiredEndpoint,
            "desired_compute_platform": models.DesiredComputePlatform, "desired_compute_instance": models.DesiredComputeInstance,
            "desired_service": models.DesiredService,
            "desired_service_placement": models.DesiredServicePlacement,
            "desired_service_binding": models.DesiredServiceBinding,
            "desired_node_operational_override": models.DesiredNodeOperationalOverride,
            "desired_workspace": models.DesiredWorkspace}


_ACTUAL_REFERENCE_MODELS = {
    "realized_device": ("nautobot.dcim.models", "Device"),
    "realized_ip_address": ("nautobot.ipam.models", "IPAddress"),
    "realized_cluster": ("nautobot.virtualization.models", "Cluster"),
    "realized_vm": ("nautobot.virtualization.models", "VirtualMachine"),
}


_REFERENCE_KIND = {"desired_node": "desired_node", "control_node": "desired_node", "platform": "desired_compute_platform",
                   "desired_service": "desired_service", "desired_endpoint": "desired_endpoint",
                   "local_endpoint": "desired_endpoint", "tailscale_endpoint": "desired_endpoint",
                   "consumer_placement": "desired_service_placement", "provider_service": "desired_service"}


def _find(model: Any, kind: str, key: dict[str, Any]) -> Any | None:
    return model.objects.filter(**_orm_values(kind, key, _models())).first()


def _orm_values(kind: str, values: dict[str, Any], models: dict[str, Any]) -> dict[str, Any]:
    resolved = {}
    for name, value in values.items():
        if name in _ACTUAL_REFERENCE_MODELS:
            if value is None:
                resolved[name] = None
                continue
            module_name, model_name = _ACTUAL_REFERENCE_MODELS[name]
            module = __import__(module_name, fromlist=[model_name])
            target = getattr(module, model_name).objects.filter(pk=value).first()
            if target is None:
                raise BatchValidationError(f"unresolved {name} reference: {value!r}")
            resolved[name] = target
            continue
        if name not in _REFERENCE_KIND or value is None:
            resolved[name] = value
            continue
        target_kind = _REFERENCE_KIND[name]
        target = _find(models[target_kind], target_kind, value if isinstance(value, dict) else {"slug": value})
        if target is None:
            raise BatchValidationError(f"unresolved {name} reference: {value!r}")
        resolved[name] = target
    return resolved


def _value_differs(row: Any, name: str, value: Any, models: dict[str, Any]) -> bool:
    """Compare relationship inputs by primary key, never model-object identity."""
    if name in _ACTUAL_REFERENCE_MODELS:
        if value is None:
            return getattr(row, f"{name}_id") is not None
        resolved = _orm_values("", {name: value}, models)[name]
        return str(getattr(row, f"{name}_id")) != str(resolved.pk)
    if name in _REFERENCE_KIND and value is not None:
        target_kind = _REFERENCE_KIND[name]
        target = _find(models[target_kind], target_kind, value if isinstance(value, dict) else {"slug": value})
        if target is not None:
            return getattr(row, f"{name}_id") != target.pk
    return getattr(row, name, None) != value


_DELETE_BLOCKERS = {
    "desired_node": (("desired_endpoints", "desired_endpoint"), ("controlled_compute_platforms", "desired_compute_platform"),
                     ("desired_compute_instance", "desired_compute_instance"), ("service_placements", "desired_service_placement"),
                     ("operational_override", "desired_node_operational_override"),
                     ("desired_workspaces", "desired_workspace")),
    "desired_endpoint": (("service_placements", "desired_service_placement"), ("local_operational_overrides", "desired_node_operational_override"),
                         ("tailscale_operational_overrides", "desired_node_operational_override")),
    "desired_compute_platform": (("desired_compute_instances", "desired_compute_instance"),),
    "desired_service": (("placements", "desired_service_placement"), ("inbound_bindings", "desired_service_binding")),
    "desired_service_placement": (("service_bindings", "desired_service_binding"),),
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


class _PlannedReferenceResolver:
    """Resolve each planning reference against rows or ordered batch identities."""

    def __init__(self, operations: list[Operation], models: dict[str, Any]):
        self.models = models
        self.upserts = {
            (operation.kind, _identity_key(operation.key))
            for operation in operations
            if operation.op == "upsert"
        }

    def missing_reference(self, operation: Operation) -> tuple[str, Any] | None:
        for name, value in {**operation.key, **operation.values}.items():
            target_kind = _REFERENCE_KIND.get(name)
            if target_kind is None or value is None:
                continue
            reference = _reference_identity(target_kind, value)
            if _find(self.models[target_kind], target_kind, reference) is not None:
                continue
            if ((target_kind, _identity_key(reference)) in self.upserts
                    and KIND_ORDER.index(target_kind) < KIND_ORDER.index(operation.kind)):
                continue
            return name, value
        return None

    def identity_exists(self, operation: Operation) -> bool:
        """Whether every relationship in an operation identity is already queryable."""
        for name, value in operation.key.items():
            target_kind = _REFERENCE_KIND.get(name)
            if target_kind is not None and value is not None:
                if _find(self.models[target_kind], target_kind, _reference_identity(target_kind, value)) is None:
                    return False
        return True


def _reference_identity(target_kind: str, value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if _KEYS[target_kind] != ("slug",):
        raise BatchValidationError(f"reference for {target_kind} must use its full identity")
    return {"slug": value}


def _binding_usable_endpoint(endpoint: Any) -> bool:
    """idea-A section 4.4: address, protocol, and port sufficient to produce the endpoint value."""
    if endpoint is None:
        return False
    if str(endpoint.protocol or "").strip().lower() not in {"http", "https"}:
        return False
    port = endpoint.port
    if not isinstance(port, int) or not 1 <= port <= 65535:
        return False
    return any(
        str(getattr(endpoint, field_name, "") or "").strip()
        for field_name in ("ip_address", "dns_name", "mdns_name")
    )


def _binding_consumer_label(binding: Any) -> str:
    consumer = binding.consumer_placement
    return f"{consumer.desired_node.slug} / {consumer.desired_service.slug} / {binding.binding_name}"


def _binding_provider_label(service: Any, active_placements: list[Any]) -> str:
    if len(active_placements) == 1:
        return f"{service.slug} / {active_placements[0].instance_name}"
    if not active_placements:
        return f"{service.slug} / (no active placement)"
    names = ", ".join(sorted(placement.instance_name for placement in active_placements))
    return f"{service.slug} / (ambiguous: {names})"


def _find_placement_graph_cycle(adjacency: dict[Any, set[Any]], labels: dict[Any, str]) -> str | None:
    """DFS over consumer_placement.pk -> resolved provider placement.pk edges (idea-A section 4.6)."""
    color: dict[Any, int] = {}
    path: list[Any] = []

    def visit(node: Any) -> list[Any] | None:
        color[node] = 1
        path.append(node)
        for neighbor in sorted(adjacency.get(node, ()), key=lambda pk: labels.get(pk, str(pk))):
            state = color.get(neighbor, 0)
            if state == 1:
                return path[path.index(neighbor):] + [neighbor]
            if state == 0:
                found = visit(neighbor)
                if found is not None:
                    return found
        path.pop()
        color[node] = 2
        return None

    for node in sorted(adjacency, key=lambda pk: labels.get(pk, str(pk))):
        if color.get(node, 0) == 0:
            found = visit(node)
            if found is not None:
                return " -> ".join(labels.get(pk, str(pk)) for pk in found)
    return None


def _validate_service_binding_graph(models: dict[str, Any]) -> None:
    """Final-state idea-A section 4/8 invariants, run once after every write in the batch.

    Runs on the state that survives the whole atomic batch, so a batch that removes or retargets
    a binding in the same operation as retiring its provider is not itself a violation (idea-A
    section 8's "unless the same atomic batch removes or retargets them").
    """
    binding_model = models["desired_service_binding"]
    placement_model = models["desired_service_placement"]
    bindings = list(
        binding_model.objects.select_related(
            "consumer_placement", "consumer_placement__desired_node", "consumer_placement__desired_service",
            "provider_service",
        )
    )
    if not bindings:
        return

    active_placements_by_service: dict[Any, list[Any]] = {}
    for placement in placement_model.objects.filter(
        desired_service_id__in={binding.provider_service_id for binding in bindings},
        desired_state=placement_model.STATE_ACTIVE,
    ).select_related("desired_endpoint"):
        active_placements_by_service.setdefault(placement.desired_service_id, []).append(placement)

    errors: list[str] = []
    provider_problem_bindings: dict[Any, list[Any]] = {}
    adjacency: dict[Any, set[Any]] = {}
    labels: dict[Any, str] = {}

    for binding in bindings:
        consumer = binding.consumer_placement
        labels[consumer.pk] = f"{consumer.desired_service.slug}/{consumer.instance_name}"
        if consumer.desired_state != placement_model.STATE_ACTIVE:
            errors.append(f"{_binding_consumer_label(binding)}: consumer placement is not active")
            continue
        if consumer.desired_service.lifecycle != "active":
            errors.append(f"{_binding_consumer_label(binding)}: consumer service is not active")
            continue

        provider = binding.provider_service
        active = active_placements_by_service.get(provider.pk, [])
        if provider.lifecycle != "active" or len(active) != 1:
            provider_problem_bindings.setdefault(provider.pk, []).append(binding)
            continue

        placement = active[0]
        labels[placement.pk] = f"{provider.slug}/{placement.instance_name}"
        if placement.pk == consumer.pk:
            errors.append(f"{_binding_consumer_label(binding)}: binding resolves back to its own consumer placement")
            continue
        if not _binding_usable_endpoint(placement.desired_endpoint):
            provider_problem_bindings.setdefault(provider.pk, []).append(binding)
            continue

        adjacency.setdefault(consumer.pk, set()).add(placement.pk)

    for service_pk, bad_bindings in provider_problem_bindings.items():
        service = bad_bindings[0].provider_service
        active = active_placements_by_service.get(service_pk, [])
        consumers = sorted(_binding_consumer_label(binding) for binding in bad_bindings)
        errors.append(
            "unresolved provider binding:\n"
            f"provider: {_binding_provider_label(service, active)}\n"
            "consumers:\n" + "\n".join(f"  - {consumer}" for consumer in consumers)
        )

    cycle = _find_placement_graph_cycle(adjacency, labels)
    if cycle:
        errors.append(f"service binding graph contains a cycle: {cycle}")

    if errors:
        raise BatchValidationError("; ".join(errors))
