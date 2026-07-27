"""Generated-fixture case set for the compute-contract semantic owner."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from . import compute_contract as contract

CONFORMANCE_SCHEMA = "compute-conformance/v1"

CONSTANTS = (
    "PROVIDER_TYPE_CHOICES", "CONFIG_SCHEMA_VERSION_V1", "INSTANCE_KIND_CHOICES",
    "POWER_STATE_CHOICES", "LIFECYCLE_CHOICES", "LINK_SOURCE_CHOICES", "VCPUS_MIN",
    "VCPUS_MAX", "MEMORY_MB_MIN", "MEMORY_MB_MAX", "ROOT_DISK_GB_MIN",
    "ROOT_DISK_GB_MAX", "VMID_MIN", "VMID_MAX", "PROVENANCE_INSTANCE_OVERRIDE",
    "PROVENANCE_PLATFORM_DEFAULT", "PROVENANCE_UNRESOLVED", "PROVENANCE_INTENT",
    "COMPUTE_PRIMARY_ENDPOINT_MISSING", "COMPUTE_PRIMARY_ENDPOINT_AMBIGUOUS",
)

PUBLIC_SYMBOLS = (
    "ComputeContractError", "validate_provider_type", "validate_compute_lifecycle",
    "validate_instance_kind", "validate_power_state", "validate_link_source",
    "link_source_pairing_is_valid", "validate_config_schema_version", "validate_platform_config",
    "validate_instance_config", "validate_vmid", "validate_vcpus", "validate_memory_mb",
    "validate_root_disk_gb", "normalize_mac_address", "endpoint_has_usable_ip",
    "endpoint_satisfies_compute_address_contract", "select_compute_primary_endpoint",
    "effective_lifecycle", "is_actionable_lifecycle", "effective_value",
    "effective_single_source_value",
)

_ENDPOINT = {
    "endpoint_type": "primary", "mac_address": "bc:24:11:23:dc:b7", "mdns_name": "node.local",
    "ip_policy": "static", "ip_address": "192.0.2.10/24", "dns_name": None,
    "generate_dnsmasq": False,
}

CASES: tuple[dict[str, Any], ...] = (
    {"id": "provider-ok", "rule": "validate_provider_type", "input": {"value": "proxmox"}},
    {"id": "provider-bad", "rule": "validate_provider_type", "input": {"value": "aws"}},
    {"id": "lifecycle-ok", "rule": "validate_compute_lifecycle", "input": {"value": "active"}},
    {"id": "lifecycle-bad", "rule": "validate_compute_lifecycle", "input": {"value": "enabled"}},
    {"id": "kind-ok", "rule": "validate_instance_kind", "input": {"value": "container"}},
    {"id": "kind-bad", "rule": "validate_instance_kind", "input": {"value": "bad"}},
    {"id": "power-ok", "rule": "validate_power_state", "input": {"value": "running"}},
    {"id": "power-bad", "rule": "validate_power_state", "input": {"value": "paused"}},
    {"id": "source-ok", "rule": "validate_link_source", "input": {"value": "derived"}},
    {"id": "source-bad", "rule": "validate_link_source", "input": {"value": "manual"}},
    {"id": "pair-ok", "rule": "link_source_pairing_is_valid", "input": {"link_present": True, "source": "derived"}},
    {"id": "pair-bad", "rule": "link_source_pairing_is_valid", "input": {"link_present": True, "source": None}},
    {"id": "schema-none", "rule": "validate_config_schema_version", "input": {"value": None}},
    {"id": "schema-bad", "rule": "validate_config_schema_version", "input": {"value": "v2"}},
    {"id": "platform-ok", "rule": "validate_platform_config", "input": {"value": {"cluster_name": " hub "}}},
    {"id": "platform-bad", "rule": "validate_platform_config", "input": {"value": {"bad": "x"}}},
    {"id": "instance-ok", "rule": "validate_instance_config", "input": {"value": {"template": "x"}, "instance_kind": "virtual_machine"}},
    {"id": "instance-bad", "rule": "validate_instance_config", "input": {"value": {"template": "x", "unprivileged": True}, "instance_kind": "virtual_machine"}},
    {"id": "mac-ok", "rule": "normalize_mac_address", "input": {"value": "BC-24-11-23-DC-B7"}},
    {"id": "mac-bad", "rule": "normalize_mac_address", "input": {"value": "bad"}},
    {"id": "ip-ok", "rule": "endpoint_has_usable_ip", "input": {"endpoint": _ENDPOINT}},
    {"id": "ip-bad", "rule": "endpoint_has_usable_ip", "input": {"endpoint": {**_ENDPOINT, "ip_address": "bad"}}},
    {"id": "address-ok", "rule": "endpoint_satisfies_compute_address_contract", "input": {"endpoint": _ENDPOINT}},
    {"id": "address-bad", "rule": "endpoint_satisfies_compute_address_contract", "input": {"endpoint": {**_ENDPOINT, "ip_policy": "external"}}},
    {"id": "endpoint-zero", "rule": "select_compute_primary_endpoint", "input": {"endpoints": []}},
    {"id": "endpoint-one", "rule": "select_compute_primary_endpoint", "input": {"endpoints": [_ENDPOINT]}},
    {"id": "endpoint-two", "rule": "select_compute_primary_endpoint", "input": {"endpoints": [_ENDPOINT, {**_ENDPOINT, "mdns_name": "two.local"}]}},
    {"id": "endpoint-no-mac", "rule": "select_compute_primary_endpoint", "input": {"endpoints": [{**_ENDPOINT, "mac_address": None}]}},
    {"id": "endpoint-no-mdns", "rule": "select_compute_primary_endpoint", "input": {"endpoints": [{**_ENDPOINT, "mdns_name": ""}]}},
    {"id": "endpoint-wrong-type", "rule": "select_compute_primary_endpoint", "input": {"endpoints": [{**_ENDPOINT, "endpoint_type": "secondary"}]}},
    {"id": "effective-value", "rule": "effective_value", "input": {"instance_value": None, "platform_value": "local"}},
    {"id": "single-source", "rule": "effective_single_source_value", "input": {"value": None}},
    {"id": "actionable", "rule": "is_actionable_lifecycle", "input": {"value": "approved"}},
) + tuple(
    {"id": f"vmid-{value}", "rule": "validate_vmid", "input": {"value": value}}
    for value in (100, 99, 999999999, 1000000000, None, "100", True, False)
) + tuple(
    {"id": f"{rule}-{value}", "rule": rule, "input": {"value": value}}
    for rule, minimum, maximum in (
        ("validate_vcpus", contract.VCPUS_MIN, contract.VCPUS_MAX),
        ("validate_memory_mb", contract.MEMORY_MB_MIN, contract.MEMORY_MB_MAX),
        ("validate_root_disk_gb", contract.ROOT_DISK_GB_MIN, contract.ROOT_DISK_GB_MAX),
    )
    for value in (minimum, minimum - 1, maximum, maximum + 1, None, "x", True, False)
) + tuple(
    {"id": f"effective-{node}-{platform}", "rule": "effective_lifecycle", "input": {"node": node, "platform": platform}}
    for node in contract.LIFECYCLE_CHOICES for platform in contract.LIFECYCLE_CHOICES
)


def _endpoint(attributes: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(**attributes)


def _run(case: dict[str, Any]) -> Any:
    data = case["input"]
    rule = case["rule"]
    if rule == "select_compute_primary_endpoint":
        selected, code = contract.select_compute_primary_endpoint([_endpoint(item) for item in data["endpoints"]])
        return {"selected": selected is not None, "code": code}
    if rule in {"endpoint_has_usable_ip", "endpoint_satisfies_compute_address_contract"}:
        return getattr(contract, rule)(_endpoint(data["endpoint"]))
    if rule == "validate_instance_config":
        return contract.validate_instance_config(data["value"], instance_kind=data["instance_kind"])
    if rule == "link_source_pairing_is_valid":
        return contract.link_source_pairing_is_valid(data["link_present"], data["source"])
    if rule == "validate_link_source":
        return contract.validate_link_source(data["value"], path="realized_vm_source")
    if rule == "effective_lifecycle":
        return contract.effective_lifecycle(data["node"], data["platform"])
    if rule == "effective_value":
        return contract.effective_value(**data)
    if rule == "effective_single_source_value":
        return contract.effective_single_source_value(**data)
    if rule == "is_actionable_lifecycle":
        return contract.is_actionable_lifecycle(data["value"])
    return getattr(contract, rule)(data["value"])


def build_fixture() -> dict[str, Any]:
    results = []
    for case in CASES:
        record = {"id": case["id"], "rule": case["rule"], "input": case["input"]}
        try:
            record["result"] = {"ok": _run(case)}
        except contract.ComputeContractError as exc:
            record["result"] = {"error": {"code": exc.code, "path": exc.path, "str": str(exc)}}
        results.append(record)
    return {"schema": CONFORMANCE_SCHEMA, "constants": {name: getattr(contract, name) for name in CONSTANTS}, "cases": results}


def dumps_fixture() -> str:
    return json.dumps(build_fixture(), ensure_ascii=False, indent=2) + "\n"
