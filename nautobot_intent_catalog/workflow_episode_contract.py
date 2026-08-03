"""Pure-Python status-transition and raw_data-shape contract for WorkflowEpisode.

Kept Django-free (like ``compute_contract.py``) so the transition table and
namespace validation get real, always-collected unit tests instead of being
skipped under local Django-free discovery.
"""

from __future__ import annotations

from typing import Any

STATUS_CANDIDATE = "candidate"
STATUS_SELECTED = "selected"
STATUS_RESOLVED = "resolved"
STATUS_DISMISSED = "dismissed"

STATUS_CHOICES = (
    (STATUS_CANDIDATE, "Candidate"),
    (STATUS_SELECTED, "Selected"),
    (STATUS_RESOLVED, "Resolved"),
    (STATUS_DISMISSED, "Dismissed"),
)

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    STATUS_CANDIDATE: {STATUS_SELECTED, STATUS_DISMISSED},
    STATUS_SELECTED: {STATUS_RESOLVED, STATUS_DISMISSED},
    STATUS_RESOLVED: set(),
    STATUS_DISMISSED: set(),
}

RAW_DATA_NAMESPACES = frozenset({"report", "assessment", "references", "resolution"})
RAW_DATA_TOP_LEVEL_KEYS = RAW_DATA_NAMESPACES | {"schema_version"}


class WorkflowEpisodeContractError(ValueError):
    """A stable, machine-readable WorkflowEpisode contract violation."""

    def __init__(self, code: str, message: str, *, path: str | None = None):
        self.code = code
        self.path = path
        prefix = f"{path}: " if path else ""
        super().__init__(f"{code}: {prefix}{message}")


def validate_transition(current_status: str, new_status: str) -> None:
    """Raise unless ``current_status -> new_status`` is an allowed forward transition."""
    allowed = ALLOWED_TRANSITIONS.get(current_status)
    if allowed is None:
        raise WorkflowEpisodeContractError(
            "invalid_current_status", f"unknown status {current_status!r}", path="status"
        )
    if new_status not in allowed:
        raise WorkflowEpisodeContractError(
            "invalid_transition",
            f"cannot transition from {current_status!r} to {new_status!r}",
            path="status",
        )


def validate_raw_data_shape(raw_data: Any) -> None:
    """Validate only the closed top-level namespace set; sub-fields are free-form."""
    if not isinstance(raw_data, dict):
        raise WorkflowEpisodeContractError("invalid_raw_data_type", "raw_data must be a JSON object", path="raw_data")
    unknown_keys = set(raw_data) - RAW_DATA_TOP_LEVEL_KEYS
    if unknown_keys:
        raise WorkflowEpisodeContractError(
            "unknown_namespace",
            f"unknown top-level key(s): {sorted(unknown_keys)}",
            path="raw_data",
        )
    for namespace in RAW_DATA_NAMESPACES:
        if namespace in raw_data and not isinstance(raw_data[namespace], dict):
            raise WorkflowEpisodeContractError(
                "invalid_namespace_type", f"{namespace} must be a JSON object", path=f"raw_data.{namespace}"
            )
    if "schema_version" in raw_data and not isinstance(raw_data["schema_version"], int):
        raise WorkflowEpisodeContractError(
            "invalid_schema_version", "schema_version must be an integer", path="raw_data.schema_version"
        )
