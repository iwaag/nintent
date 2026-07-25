"""Pure, Django-free helpers for the Analyze Intent Sources read-only plan (plan.md Section 6.2).

Kept separate from `import_plan.py` because Analyze's dependency-deletion guard is specific to
one analyzed service's own completeness, not a generic upsert decision.
"""

from __future__ import annotations

from typing import Any

from .import_plan import PlannedObject
from .importers import dependency_key


def is_dependency_scope_complete(service: dict[str, Any]) -> bool:
    """A service's dependency set may only drive a `delete` action when this analysis of it
    was itself successful and complete (plan.md Section 6.2/6.3): a service with no `analysis`
    block, or with any `malformed_dependencies`, never authorizes deleting a retained dependency
    for that same service -- create/update/unchanged are still reported normally.
    """

    analysis = service.get("analysis")
    if not isinstance(analysis, dict):
        return False
    return not analysis.get("malformed_dependencies")


def dependency_planned_objects(
    *,
    desired_service_identity: dict[str, Any],
    dependency_plan: dict[str, Any],
    scope_complete: bool,
) -> list[PlannedObject]:
    """Convert one service's `plan_dependency_sync()` result into `PlannedObject`s.

    `delete_keys` are only converted into `delete` actions when `scope_complete` is true;
    otherwise they are reported as `unchanged` (no destructive action from an incomplete scope).
    """

    objects: list[PlannedObject] = []

    for dependency in dependency_plan["create"]:
        key = dependency_key(dependency)
        objects.append(
            PlannedObject(
                model="DesiredDependency",
                root="desired_dependencies",
                identity=_dependency_identity(desired_service_identity, key),
                action="create",
                changed_fields={field: {"old": None, "new": value} for field, value in dependency.items()},
            )
        )

    for change in dependency_plan["update"]:
        objects.append(
            PlannedObject(
                model="DesiredDependency",
                root="desired_dependencies",
                identity=_dependency_identity(desired_service_identity, change["key"]),
                action="update",
                changed_fields={
                    "raw_ref": {"new": change["raw_ref"]},
                    "dependency_type": {"new": change["dependency_type"]},
                },
            )
        )

    for key in dependency_plan["unchanged_keys"]:
        objects.append(
            PlannedObject(
                model="DesiredDependency",
                root="desired_dependencies",
                identity=_dependency_identity(desired_service_identity, key),
                action="unchanged",
                preserved_fields=["resolution_status", "resolved_service", "notes"],
            )
        )

    for key in dependency_plan["delete_keys"]:
        identity = _dependency_identity(desired_service_identity, key)
        if scope_complete:
            objects.append(
                PlannedObject(
                    model="DesiredDependency", root="desired_dependencies", identity=identity, action="delete"
                )
            )
        else:
            objects.append(
                PlannedObject(
                    model="DesiredDependency",
                    root="desired_dependencies",
                    identity=identity,
                    action="unchanged",
                    preserved_fields=["resolution_status", "resolved_service", "notes"],
                )
            )

    return objects


def _dependency_identity(desired_service_identity: dict[str, Any], key: tuple[str, str, str]) -> dict[str, Any]:
    kind, namespace, name = key
    return {
        "desired_service": desired_service_identity,
        "dependency_kind": kind,
        "namespace": namespace,
        "name": name,
    }
