"""Host-oriented use-case operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nautobot_intent_catalog.names import default_dns_name, default_mdns_name

try:
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError, transaction

    from nautobot_intent_catalog.models import DesiredEndpoint, DesiredNode
except ImportError:  # pragma: no cover - Nautobot/Django are unavailable in local unit tests.
    ValidationError = None  # type: ignore[assignment]
    IntegrityError = Exception  # type: ignore[assignment]
    transaction = None  # type: ignore[assignment]
    DesiredEndpoint = None  # type: ignore[assignment]
    DesiredNode = None  # type: ignore[assignment]


@dataclass(frozen=True)
class DesiredHostCreationResult:
    """Objects created by a quick host registration operation."""

    desired_node: Any
    desired_endpoint: Any


def create_desired_node_with_primary_endpoint(
    *,
    name: str,
    slug: str,
    node_type: str = "virtual_machine",
    accepted_actual_types: list[str] | None = None,
    lifecycle: str = "planned",
    role: str | None = None,
    description: str | None = None,
    intent_source: Any | None = None,
    intent_source_id: Any | None = None,
    ip_address: str | None = None,
    dns_name: str | None = None,
    mdns_name: str | None = None,
    vpn_dns_name: str | None = None,
    protocol: str | None = None,
    port: int | None = None,
    generate_dnsmasq: bool = True,
    ip_policy: str = "dhcp_reserved",
    dnsmasq_record_type: str = "host_record",
    endpoint_name: str = "primary",
    endpoint_type: str = "primary",
) -> DesiredHostCreationResult:
    """Create a desired node and its primary endpoint in one atomic operation.

    The operation intentionally raises Django ``ValidationError`` with a
    field-keyed error dictionary so forms and future API views can present the
    same validation result.
    """

    _require_django()
    if intent_source is not None and intent_source_id is not None:
        _raise_validation_error({"intent_source": ["Pass either intent_source or intent_source_id, not both."]})

    cleaned = {
        "name": _required_str(name, "name"),
        "slug": _required_str(slug, "slug"),
        "node_type": _required_str(node_type, "node_type"),
        "accepted_actual_types": _accepted_actual_types(accepted_actual_types, node_type),
        "lifecycle": _required_str(lifecycle, "lifecycle"),
        "role": _optional_str(role),
        "description": _optional_str(description),
        "ip_address": _optional_str(ip_address),
        "dns_name": _optional_str(dns_name),
        "mdns_name": _optional_str(mdns_name),
        "vpn_dns_name": _optional_str(vpn_dns_name),
        "protocol": _optional_str(protocol),
        "port": port,
        "ip_policy": _required_str(ip_policy, "ip_policy"),
        "dnsmasq_record_type": _required_str(dnsmasq_record_type, "dnsmasq_record_type"),
        "endpoint_name": _required_str(endpoint_name, "endpoint_name"),
        "endpoint_type": _required_str(endpoint_type, "endpoint_type"),
    }
    dns_name_was_explicit = cleaned["dns_name"] is not None
    mdns_name_was_explicit = cleaned["mdns_name"] is not None
    if cleaned["endpoint_name"] == "primary" and cleaned["endpoint_type"] == "primary":
        if cleaned["dns_name"] is None:
            cleaned["dns_name"] = default_dns_name(cleaned["name"])
        if cleaned["mdns_name"] is None:
            cleaned["mdns_name"] = default_mdns_name(cleaned["name"])

    _validate_node_identity(name=cleaned["name"], slug=cleaned["slug"])

    node_kwargs = {
        "name": cleaned["name"],
        "slug": cleaned["slug"],
        "node_type": cleaned["node_type"],
        "accepted_actual_types": cleaned["accepted_actual_types"],
        "lifecycle": cleaned["lifecycle"],
        "role": cleaned["role"],
        "description": cleaned["description"],
        "intent_source": intent_source,
    }
    if intent_source_id is not None:
        node_kwargs["intent_source_id"] = intent_source_id

    try:
        with transaction.atomic():
            desired_node = DesiredNode(**node_kwargs)
            desired_node.full_clean()
            desired_node.save()

            _validate_endpoint_identity(
                desired_node=desired_node,
                endpoint_name=cleaned["endpoint_name"],
                endpoint_type=cleaned["endpoint_type"],
            )
            desired_endpoint = DesiredEndpoint(
                desired_node=desired_node,
                name=cleaned["endpoint_name"],
                endpoint_type=cleaned["endpoint_type"],
                ip_address=cleaned["ip_address"],
                dns_name=cleaned["dns_name"],
                dns_name_source=("intent" if dns_name_was_explicit else "derived") if cleaned["dns_name"] else None,
                mdns_name=cleaned["mdns_name"],
                mdns_name_source=("intent" if mdns_name_was_explicit else "derived") if cleaned["mdns_name"] else None,
                vpn_dns_name=cleaned["vpn_dns_name"],
                protocol=cleaned["protocol"],
                port=cleaned["port"],
                generate_dnsmasq=generate_dnsmasq,
                ip_policy=cleaned["ip_policy"],
                dnsmasq_record_type=cleaned["dnsmasq_record_type"],
            )
            desired_endpoint.full_clean()
            desired_endpoint.save()
    except IntegrityError as exc:
        _raise_validation_error({"__all__": [f"Desired host could not be created because of a uniqueness conflict: {exc}"]})

    return DesiredHostCreationResult(desired_node=desired_node, desired_endpoint=desired_endpoint)


def _validate_node_identity(*, name: str, slug: str) -> None:
    errors: dict[str, list[str]] = {}
    if DesiredNode.objects.filter(slug=slug).exists():
        errors["slug"] = ["A desired node with this slug already exists."]
    if DesiredNode.objects.filter(name=name).exists():
        errors["name"] = ["A desired node with this name already exists."]
    if errors:
        _raise_validation_error(errors)


def _validate_endpoint_identity(*, desired_node: Any, endpoint_name: str, endpoint_type: str) -> None:
    if DesiredEndpoint.objects.filter(
        desired_node=desired_node,
        name=endpoint_name,
        endpoint_type=endpoint_type,
    ).exists():
        _raise_validation_error(
            {
                "endpoint_name": [
                    "A desired endpoint with this name and endpoint type already exists for the desired node."
                ]
            }
        )


def _required_str(value: Any, field_name: str) -> str:
    normalized = str(value).strip() if value is not None else ""
    if not normalized:
        _raise_validation_error({field_name: ["This field is required."]})
    return normalized


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _accepted_actual_types(value: list[str] | None, node_type: str) -> list[str]:
    if value is None:
        defaults = {
            "device": ["device"],
            "virtual_machine": ["virtual_machine"],
            "container": ["container"],
            "service_host": ["device", "virtual_machine", "container"],
        }
        return list(defaults.get(_required_str(node_type, "node_type"), ["device"]))

    if not isinstance(value, list):
        _raise_validation_error({"accepted_actual_types": ["Accepted actual types must be a list."]})

    allowed = {"device", "virtual_machine", "container"}
    actual_types = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            _raise_validation_error(
                {"accepted_actual_types": ["Accepted actual types must contain non-empty strings."]}
            )
        normalized = item.strip().lower().replace("-", "_")
        if normalized not in allowed:
            _raise_validation_error(
                {
                    "accepted_actual_types": [
                        "Accepted actual types must only contain device, virtual_machine, or container."
                    ]
                }
            )
        if normalized not in actual_types:
            actual_types.append(normalized)
    return actual_types


def _require_django() -> None:
    if ValidationError is None or transaction is None or DesiredNode is None or DesiredEndpoint is None:
        raise RuntimeError("Django and Nautobot are required to run host operations.")


def _raise_validation_error(errors: dict[str, list[str]]) -> None:
    if ValidationError is None:
        raise RuntimeError(errors)
    raise ValidationError(errors)
