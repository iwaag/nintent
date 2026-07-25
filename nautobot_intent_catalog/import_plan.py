"""Pure, Django-free read-only planning engine shared by Import and Analyze.

`plan_upsert()` is the one create/update/unchanged/conflict decision function used by every
root in both Jobs (plan.md Section 5.2/6.2). It never touches the ORM -- callers supply
pre-fetched existing rows as plain dicts -- so it is exercised directly by unit tests without a
live database, and the exact same function drives preview and apply (structural
preview/apply parity, plan Section 5.4/6.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CANONICAL_IMPORT_ROOTS = (
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


@dataclass(frozen=True)
class PlannedObject:
    """One planned row. `changed_fields` holds `{old, new}` pairs for `update`,
    `{new}`-only entries for `create`, and is empty for `unchanged`/`conflict`."""

    model: str
    root: str
    identity: dict[str, Any]
    action: str  # create | update | unchanged | conflict
    changed_fields: dict[str, Any] = field(default_factory=dict)
    preserved_fields: list[str] = field(default_factory=list)
    conflict_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "root": self.root,
            "identity": self.identity,
            "action": self.action,
            "changed_fields": self.changed_fields,
            "preserved_fields": self.preserved_fields,
        }


def plan_upsert(
    *,
    model: str,
    root: str,
    identity: dict[str, Any],
    create_fields: dict[str, Any],
    update_fields: dict[str, Any],
    existing_matches: list[dict[str, Any]],
    locked_fields: dict[str, Any] | None = None,
) -> PlannedObject:
    """Return one deterministic create/update/unchanged/conflict decision.

    `existing_matches` are plain dicts keyed by the union of `create_fields` (a real DB row
    projected to those keys). `update_fields` is the subset of `create_fields` an existing row
    may have overwritten; the remaining keys are reported as `preserved_fields` and are never
    compared against the current DB value. `locked_fields` (a further subset of `create_fields`,
    disjoint from `update_fields`) additionally *blocks* the whole row with `conflict` if the
    YAML-declared value disagrees with the stored value -- used only where silent preservation
    would hide an operator/analysis-owned disagreement (e.g. `DesiredService`
    `name`/`slug`/`display_name`, plan Section 5.3).
    """

    if len(existing_matches) > 1:
        return PlannedObject(
            model=model,
            root=root,
            identity=identity,
            action="conflict",
            conflict_reason=f"identity matched {len(existing_matches)} existing rows (expected 0 or 1)",
        )

    if not existing_matches:
        return PlannedObject(
            model=model,
            root=root,
            identity=identity,
            action="create",
            changed_fields={key: {"old": None, "new": value} for key, value in create_fields.items()},
        )

    existing = existing_matches[0]

    for key, value in (locked_fields or {}).items():
        if existing.get(key) != value:
            return PlannedObject(
                model=model,
                root=root,
                identity=identity,
                action="conflict",
                conflict_reason=(
                    f"{key} is not YAML-updatable on an existing row "
                    f"(existing={existing.get(key)!r}, yaml={value!r})"
                ),
            )

    changed = {}
    for key, value in update_fields.items():
        if existing.get(key) != value:
            changed[key] = {"old": existing.get(key), "new": value}

    preserved = sorted(set(create_fields) - set(update_fields) - set(locked_fields or {}))

    if not changed:
        return PlannedObject(
            model=model,
            root=root,
            identity=identity,
            action="unchanged",
            preserved_fields=preserved,
        )

    return PlannedObject(
        model=model,
        root=root,
        identity=identity,
        action="update",
        changed_fields=changed,
        preserved_fields=preserved,
    )


def unresolved_reference(model: str, root: str, identity: dict[str, Any], reason: str) -> PlannedObject:
    """A reference (e.g. `desired_node` slug) that is neither an existing row nor planned for
    creation in this same batch. Always a `conflict` -- plan Section 5.2 forbids planning or
    applying a row built on an unresolved reference."""

    return PlannedObject(model=model, root=root, identity=identity, action="conflict", conflict_reason=reason)


def totals(objects: list[PlannedObject]) -> dict[str, int]:
    counts = {"create": 0, "update": 0, "unchanged": 0, "conflict": 0}
    for obj in objects:
        counts[obj.action] += 1
    return counts


def build_artifact(
    *,
    schema_version: str,
    mode: str,
    source: dict[str, Any],
    roots: tuple[str, ...],
    counts_by_root: dict[str, int],
    objects: list[PlannedObject],
    errors: list[str],
    apply_requested: bool,
    attempted: bool,
    committed: bool,
    transaction_status: str,
    transaction_error: str | None,
    confirmation_status: str,
    confirmation_mismatches: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the one deterministic, versioned artifact shape shared by preview and apply.

    Object/conflict lists are sorted by `(root, identity)` so the JSON is byte-for-byte
    reproducible for identical input (plan Section 5.4/6.4 determinism requirement).
    """

    ordered_objects = sorted(objects, key=lambda obj: (roots.index(obj.root), _identity_sort_key(obj.identity)))
    conflicts = [obj.as_dict() | {"reason": obj.conflict_reason} for obj in ordered_objects if obj.action == "conflict"]
    non_conflicts = [obj.as_dict() for obj in ordered_objects if obj.action != "conflict"]

    return {
        "schema_version": schema_version,
        "mode": mode,
        "source": source,
        "scope": {"roots": list(roots), "counts_by_root": counts_by_root},
        "objects": non_conflicts,
        "conflicts": conflicts,
        "errors": list(errors),
        "totals": totals(ordered_objects),
        "writes": {
            "requested": apply_requested,
            "attempted": attempted,
            "committed": committed,
        },
        "transaction": {"status": transaction_status, "error": transaction_error},
        "confirmation": {"status": confirmation_status, "mismatches": confirmation_mismatches},
    }


def totals_by_model_and_action(objects: list[PlannedObject]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for obj in objects:
        per_model = result.setdefault(obj.model, {"create": 0, "update": 0, "delete": 0, "unchanged": 0, "conflict": 0})
        per_model[obj.action] += 1
    return result


def build_analysis_artifact(
    *,
    schema_version: str,
    mode: str,
    selected_sources: list[dict[str, Any]],
    inputs: list[dict[str, Any]],
    objects: list[PlannedObject],
    errors: list[str],
    apply_requested: bool,
    attempted: bool,
    committed: bool,
    transaction_status: str,
    transaction_error: str | None,
    confirmation_status: str,
    confirmation_mismatches: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the one deterministic, versioned Analyze artifact shape (plan Section 6.4).

    Deliberately a different top-level shape than `build_artifact()` (Import): no `scope`/
    `source`, `selected_sources`/`inputs` instead, and `totals_by_model_and_action` instead of a
    flat `totals`. Per-object dicts omit `root` (not part of the Analyze artifact contract).
    """

    ordered_objects = sorted(objects, key=lambda obj: (obj.model, _identity_sort_key(obj.identity)))
    conflicts = [
        {"model": obj.model, "identity": obj.identity, "action": obj.action, "reason": obj.conflict_reason}
        for obj in ordered_objects
        if obj.action == "conflict"
    ]
    non_conflicts = [
        {
            "model": obj.model,
            "identity": obj.identity,
            "action": obj.action,
            "changed_fields": obj.changed_fields,
            "preserved_fields": obj.preserved_fields,
        }
        for obj in ordered_objects
        if obj.action != "conflict"
    ]

    return {
        "schema_version": schema_version,
        "mode": mode,
        "selected_sources": selected_sources,
        "inputs": inputs,
        "objects": non_conflicts,
        "conflicts": conflicts,
        "errors": list(errors),
        "totals_by_model_and_action": totals_by_model_and_action(ordered_objects),
        "writes": {
            "requested": apply_requested,
            "attempted": attempted,
            "committed": committed,
        },
        "transaction": {"status": transaction_status, "error": transaction_error},
        "confirmation": {"status": confirmation_status, "mismatches": confirmation_mismatches},
    }


def _identity_sort_key(identity: dict[str, Any]) -> tuple:
    return tuple(sorted((str(k), str(v)) for k, v in identity.items()))
