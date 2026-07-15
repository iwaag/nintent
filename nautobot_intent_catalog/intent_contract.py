"""Validation helpers for references in intent-source documents.

These rules belong to the ledger import boundary.  Production inventory and
deployment-profile processing live in nctl_core.
"""

from __future__ import annotations

import json
import re
from typing import Any

_ENDPOINT_TYPES = {"primary", "management", "service", "vpn", "mdns", "other"}
_SERVICE_TYPES = {"service", "website", "worker", "database", "queue", "storage", "agent", "other"}
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


class ContractError(ValueError):
    """A stable, machine-readable intent input violation."""

    def __init__(self, code: str, message: str, *, path: str | None = None):
        self.code = code
        self.path = path
        prefix = f"{path}: " if path else ""
        super().__init__(f"{code}: {prefix}{message}")


def canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for source hashes and comparisons."""

    _require_string_mapping_keys(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError("invalid_profile_json", str(exc)) from exc


def validate_desired_service_reference(value: Any) -> dict[str, str]:
    path = "desired_service"
    if not isinstance(value, dict):
        raise ContractError("invalid_service_reference", "reference must be an object", path=path)
    keys = {"intent_source", "catalog_namespace", "catalog_metadata_name", "service_type"}
    _require_exact_keys(value, keys, path)
    for key in keys:
        if not isinstance(value[key], str) or not value[key].strip():
            raise ContractError("incomplete_service_reference", "value must be a non-empty string", path=f"{path}.{key}")
    _require_slug(value["intent_source"], f"{path}.intent_source")
    if value["service_type"] not in _SERVICE_TYPES:
        raise ContractError("invalid_service_reference", "unsupported service_type", path=f"{path}.service_type")
    return {key: value[key].strip() for key in sorted(keys)}


def validate_endpoint_reference(value: Any) -> dict[str, str]:
    path = "desired_endpoint"
    if not isinstance(value, dict):
        raise ContractError("invalid_endpoint_reference", "reference must be an object", path=path)
    _require_exact_keys(value, {"name", "endpoint_type"}, path)
    if not isinstance(value["name"], str) or not value["name"].strip():
        raise ContractError("incomplete_endpoint_reference", "name must be non-empty", path=f"{path}.name")
    if value["endpoint_type"] not in _ENDPOINT_TYPES:
        raise ContractError("invalid_endpoint_reference", "unsupported endpoint_type", path=f"{path}.endpoint_type")
    return {"name": value["name"].strip(), "endpoint_type": value["endpoint_type"]}


def require_unique_reference(kind: str, match_count: int) -> None:
    if match_count == 0:
        raise ContractError("missing_reference", f"{kind} reference matched no rows")
    if match_count != 1:
        raise ContractError("ambiguous_reference", f"{kind} reference matched {match_count} rows")


def _require_exact_keys(value: dict, expected: set[str], path: str) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if not missing and not unknown:
        return
    details = []
    if missing:
        details.append(f"missing keys: {', '.join(sorted(missing))}")
    if unknown:
        details.append(f"unknown keys: {', '.join(sorted(unknown))}")
    raise ContractError("invalid_contract_keys", "; ".join(details), path=path)


def _require_slug(value: Any, path: str) -> None:
    if not isinstance(value, str) or not _SLUG_RE.fullmatch(value):
        raise ContractError("invalid_slug", "must be a lowercase slug", path=path)


def _require_string_mapping_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError("invalid_profile_json", "all mapping keys must be strings", path=path)
            _require_string_mapping_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _require_string_mapping_keys(item, f"{path}[{index}]")
