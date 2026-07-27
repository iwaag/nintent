"""Django-free semantic owner for desired compute-platform/instance intent.

These helpers are shared by the model layer, forms, REST serializers, and the
strict YAML loader/importer so every write path converges on one validation,
normalization, effective-lifecycle, effective-default, NIC/address, and
realized-link/source implementation. ``compute_conformance`` publishes its
observed behavior for nctl's fixture-bound consumer test.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

PROVIDER_TYPE_PROXMOX = "proxmox"
PROVIDER_TYPE_CHOICES = (PROVIDER_TYPE_PROXMOX,)

CONFIG_SCHEMA_VERSION_V1 = "v1"

INSTANCE_KIND_CONTAINER = "container"
INSTANCE_KIND_VIRTUAL_MACHINE = "virtual_machine"
INSTANCE_KIND_CHOICES = (INSTANCE_KIND_CONTAINER, INSTANCE_KIND_VIRTUAL_MACHINE)

POWER_STATE_RUNNING = "running"
POWER_STATE_STOPPED = "stopped"
POWER_STATE_CHOICES = (POWER_STATE_RUNNING, POWER_STATE_STOPPED)

LIFECYCLE_PLANNED = "planned"
LIFECYCLE_APPROVED = "approved"
LIFECYCLE_ACTIVE = "active"
LIFECYCLE_DEPRECATED = "deprecated"
LIFECYCLE_RETIRED = "retired"
LIFECYCLE_CHOICES = (
    LIFECYCLE_PLANNED,
    LIFECYCLE_APPROVED,
    LIFECYCLE_ACTIVE,
    LIFECYCLE_DEPRECATED,
    LIFECYCLE_RETIRED,
)

LINK_SOURCE_DERIVED = "derived"
LINK_SOURCE_OVERRIDE = "override"
LINK_SOURCE_CHOICES = (LINK_SOURCE_DERIVED, LINK_SOURCE_OVERRIDE)

VCPUS_MIN = 1
VCPUS_MAX = 8192
MEMORY_MB_MIN = 16
MEMORY_MB_MAX = 2147483647
ROOT_DISK_GB_MIN = 1
ROOT_DISK_GB_MAX = 2147483647
VMID_MIN = 100
VMID_MAX = 999999999

PROVENANCE_INSTANCE_OVERRIDE = "instance_override"
PROVENANCE_PLATFORM_DEFAULT = "platform_default"
PROVENANCE_UNRESOLVED = "unresolved"
PROVENANCE_INTENT = "intent"

_PLATFORM_CONFIG_KEYS = {"cluster_name", "default_storage", "default_bridge"}
_INSTANCE_CONFIG_KEYS = {"vmid", "template", "storage", "bridge", "unprivileged"}

_MAC_COLON_RE = re.compile(r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")
_MAC_HYPHEN_RE = re.compile(r"^([0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2}$")


class ComputeContractError(ValueError):
    """A stable, machine-readable compute-intent contract violation."""

    def __init__(self, code: str, message: str, *, path: str | None = None):
        self.code = code
        self.path = path
        prefix = f"{path}: " if path else ""
        super().__init__(f"{code}: {prefix}{message}")


def validate_provider_type(value: Any, *, path: str = "provider_type") -> str:
    if value not in PROVIDER_TYPE_CHOICES:
        raise ComputeContractError(
            "invalid_provider_type",
            f"only {', '.join(PROVIDER_TYPE_CHOICES)!r} is accepted",
            path=path,
        )
    return value


def validate_compute_lifecycle(value: Any, *, path: str = "lifecycle") -> str:
    if value not in LIFECYCLE_CHOICES:
        raise ComputeContractError(
            "invalid_lifecycle", f"must be one of {', '.join(LIFECYCLE_CHOICES)}", path=path
        )
    return value


def validate_instance_kind(value: Any, *, path: str = "instance_kind") -> str:
    if value not in INSTANCE_KIND_CHOICES:
        raise ComputeContractError(
            "invalid_instance_kind", f"must be one of {', '.join(INSTANCE_KIND_CHOICES)}", path=path
        )
    return value


def validate_power_state(value: Any, *, path: str = "desired_power_state") -> str:
    if value not in POWER_STATE_CHOICES:
        raise ComputeContractError(
            "invalid_power_state", f"must be one of {', '.join(POWER_STATE_CHOICES)}", path=path
        )
    return value


def validate_link_source(value: Any, *, path: str) -> str:
    if value not in LINK_SOURCE_CHOICES:
        raise ComputeContractError(
            "invalid_source", f"must be one of {', '.join(LINK_SOURCE_CHOICES)}", path=path
        )
    return value


def link_source_pairing_is_valid(link_present: bool, source: str | None) -> bool:
    """Return whether a realized link and its source are either both set or both absent."""

    return bool(link_present) == bool(source)


def validate_config_schema_version(value: Any, *, path: str = "config_schema_version") -> str:
    """Normalize an omitted (``None``) schema version to ``v1``; reject any other explicit value."""

    if value is None:
        return CONFIG_SCHEMA_VERSION_V1
    if value != CONFIG_SCHEMA_VERSION_V1:
        raise ComputeContractError(
            "invalid_config_schema_version",
            f"only {CONFIG_SCHEMA_VERSION_V1!r} is accepted",
            path=path,
        )
    return value


def _require_json_object(value: Any, path: str) -> dict:
    if not isinstance(value, dict) or isinstance(value, bool):
        raise ComputeContractError("invalid_config_type", "config must be a JSON object", path=path)
    return value


def _require_non_empty_string(value: Any, path: str, *, max_length: int) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise ComputeContractError("invalid_config_value", "value must be a string", path=path)
    stripped = value.strip()
    if not stripped:
        raise ComputeContractError("invalid_config_value", "value must be non-empty", path=path)
    if len(stripped) > max_length:
        raise ComputeContractError(
            "invalid_config_value", f"value exceeds max length {max_length}", path=path
        )
    return stripped


def validate_platform_config(value: Any, *, path: str = "config") -> dict:
    """Validate and normalize a `DesiredComputePlatform` v1 config object.

    All three keys are optional. Unknown keys and wrong scalar types fail.
    """

    obj = _require_json_object(value, path)
    unknown = set(obj) - _PLATFORM_CONFIG_KEYS
    if unknown:
        raise ComputeContractError(
            "unknown_config_key", f"unknown keys: {', '.join(sorted(unknown))}", path=path
        )
    result: dict[str, str] = {}
    for key in ("cluster_name", "default_storage", "default_bridge"):
        if key in obj:
            result[key] = _require_non_empty_string(obj[key], f"{path}.{key}", max_length=255)
    return result


def validate_instance_config(value: Any, *, instance_kind: str, path: str = "config") -> dict:
    """Validate and normalize a `DesiredComputeInstance` v1 config object.

    `instance_kind` gates the `unprivileged` key: required boolean for
    `container`, forbidden for `virtual_machine`.
    """

    validate_instance_kind(instance_kind)

    obj = _require_json_object(value, path)
    unknown = set(obj) - _INSTANCE_CONFIG_KEYS
    if unknown:
        raise ComputeContractError(
            "unknown_config_key", f"unknown keys: {', '.join(sorted(unknown))}", path=path
        )

    result: dict[str, Any] = {}

    if "template" not in obj:
        raise ComputeContractError("missing_config_value", "template is required", path=f"{path}.template")
    result["template"] = _require_non_empty_string(obj["template"], f"{path}.template", max_length=512)

    if "vmid" in obj:
        result["vmid"] = validate_vmid(obj["vmid"], path=f"{path}.vmid")

    for key in ("storage", "bridge"):
        if key in obj:
            result[key] = _require_non_empty_string(obj[key], f"{path}.{key}", max_length=255)

    is_container = instance_kind == INSTANCE_KIND_CONTAINER
    if is_container:
        if "unprivileged" not in obj:
            raise ComputeContractError(
                "missing_config_value", "unprivileged is required for container", path=f"{path}.unprivileged"
            )
        if not isinstance(obj["unprivileged"], bool):
            raise ComputeContractError(
                "invalid_config_value", "unprivileged must be a boolean", path=f"{path}.unprivileged"
            )
        result["unprivileged"] = obj["unprivileged"]
    elif "unprivileged" in obj:
        raise ComputeContractError(
            "invalid_config_key",
            "unprivileged is forbidden for virtual_machine",
            path=f"{path}.unprivileged",
        )

    return result


def validate_vmid(value: Any, *, path: str = "vmid") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ComputeContractError("invalid_vmid", "vmid must be an integer", path=path)
    if not (VMID_MIN <= value <= VMID_MAX):
        raise ComputeContractError(
            "vmid_out_of_range", f"vmid must be within {VMID_MIN}..{VMID_MAX}", path=path
        )
    return value


def _validate_bounded_int(value: Any, *, minimum: int, maximum: int, path: str, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ComputeContractError(code, "must be an integer", path=path)
    if not (minimum <= value <= maximum):
        raise ComputeContractError(code, f"must be within {minimum}..{maximum}", path=path)
    return value


def validate_vcpus(value: Any, *, path: str = "vcpus") -> int:
    return _validate_bounded_int(
        value, minimum=VCPUS_MIN, maximum=VCPUS_MAX, path=path, code="vcpus_out_of_range"
    )


def validate_memory_mb(value: Any, *, path: str = "memory_mb") -> int:
    return _validate_bounded_int(
        value, minimum=MEMORY_MB_MIN, maximum=MEMORY_MB_MAX, path=path, code="memory_mb_out_of_range"
    )


def validate_root_disk_gb(value: Any, *, path: str = "root_disk_gb") -> int:
    return _validate_bounded_int(
        value, minimum=ROOT_DISK_GB_MIN, maximum=ROOT_DISK_GB_MAX, path=path, code="root_disk_gb_out_of_range"
    )


def normalize_mac_address(value: Any) -> str | None:
    """Return a canonical lower-case colon-separated MAC, or `None`.

    Six hexadecimal octets separated consistently by `:` or `-` are accepted.
    Dotted, short, overlong, mixed-separator, non-hex, list, numeric, and
    boolean values fail with `ComputeContractError`.
    """

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str):
        raise ComputeContractError("invalid_mac_address", "MAC address must be a string")
    stripped = value.strip()
    if not stripped:
        return None
    if _MAC_COLON_RE.fullmatch(stripped):
        octets = stripped.split(":")
    elif _MAC_HYPHEN_RE.fullmatch(stripped):
        octets = stripped.split("-")
    else:
        raise ComputeContractError(
            "invalid_mac_address",
            "must be six hex octets separated consistently by ':' or '-'",
        )
    return ":".join(octet.lower() for octet in octets)


def endpoint_has_usable_ip(endpoint: Any) -> bool:
    """Return whether an endpoint exposes a parseable desired IP interface."""

    value = getattr(endpoint, "ip_address", None)
    if not value:
        return False
    try:
        ipaddress.ip_interface(str(value))
    except ValueError:
        return False
    return True


def endpoint_satisfies_compute_address_contract(endpoint: Any) -> bool:
    """Return whether a primary endpoint satisfies the first Proxmox address contract."""

    if getattr(endpoint, "ip_policy", None) == "dhcp_reserved":
        return (
            endpoint_has_usable_ip(endpoint)
            and bool(str(getattr(endpoint, "dns_name", "") or "").strip())
            and bool(getattr(endpoint, "generate_dnsmasq", False))
        )
    if getattr(endpoint, "ip_policy", None) == "static":
        return endpoint_has_usable_ip(endpoint)
    return False


COMPUTE_PRIMARY_ENDPOINT_MISSING = "compute_primary_endpoint_missing"
COMPUTE_PRIMARY_ENDPOINT_AMBIGUOUS = "compute_primary_endpoint_ambiguous"


def select_compute_primary_endpoint(node_endpoints: list[Any]) -> tuple[Any | None, str | None]:
    """Select the sole primary endpoint that is ready for compute realization."""

    candidates = [
        endpoint
        for endpoint in node_endpoints
        if getattr(endpoint, "endpoint_type", None) == "primary"
        and getattr(endpoint, "mac_address", None)
        and str(getattr(endpoint, "mdns_name", "") or "").strip()
        and endpoint_satisfies_compute_address_contract(endpoint)
    ]
    if len(candidates) == 0:
        return None, COMPUTE_PRIMARY_ENDPOINT_MISSING
    if len(candidates) > 1:
        return None, COMPUTE_PRIMARY_ENDPOINT_AMBIGUOUS
    return candidates[0], None


def effective_lifecycle(node_lifecycle: str, platform_lifecycle: str) -> str:
    """Compute effective lifecycle from a DesiredNode and its DesiredComputePlatform.

    ```text
    if node or platform is retired: retired
    elif node or platform is deprecated: deprecated
    elif node or platform is planned: planned
    elif node and platform are both active: active
    else: approved
    ```
    """

    pair = (node_lifecycle, platform_lifecycle)
    if LIFECYCLE_RETIRED in pair:
        return LIFECYCLE_RETIRED
    if LIFECYCLE_DEPRECATED in pair:
        return LIFECYCLE_DEPRECATED
    if LIFECYCLE_PLANNED in pair:
        return LIFECYCLE_PLANNED
    if node_lifecycle == LIFECYCLE_ACTIVE and platform_lifecycle == LIFECYCLE_ACTIVE:
        return LIFECYCLE_ACTIVE
    return LIFECYCLE_APPROVED


def is_actionable_lifecycle(effective: str) -> bool:
    """`active`/`approved` require a complete static-create contract; the rest do not."""

    return effective in (LIFECYCLE_ACTIVE, LIFECYCLE_APPROVED)


def effective_value(*, instance_value: Any, platform_value: Any) -> dict:
    """Resolve one effective value with provenance from instance override then platform default.

    Used for `storage` and `bridge`. `cluster_name` and `vmid` use the
    single-source variant (`effective_single_source_value`).
    """

    if instance_value is not None:
        return {"value": instance_value, "provenance": PROVENANCE_INSTANCE_OVERRIDE}
    if platform_value is not None:
        return {"value": platform_value, "provenance": PROVENANCE_PLATFORM_DEFAULT}
    return {"value": None, "provenance": PROVENANCE_UNRESOLVED}


def effective_single_source_value(value: Any, *, provenance: str = PROVENANCE_INTENT) -> dict:
    """Resolve one effective value with no fallback source, e.g. `cluster_name` or `vmid`."""

    if value is None:
        return {"value": None, "provenance": PROVENANCE_UNRESOLVED}
    return {"value": value, "provenance": provenance}
