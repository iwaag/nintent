"""IPAM reconciliation planning for desired endpoint intent."""

from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import ip_interface
from typing import Any, Iterable


DHCP_RESERVED_POLICY = "dhcp_reserved"
NON_DHCP_POLICIES = frozenset({"static", "external"})
KNOWN_IP_POLICIES = NON_DHCP_POLICIES | {DHCP_RESERVED_POLICY}
DHCP_TYPE_VALUES = frozenset({"dhcp", "dhcp_reserved"})
HOST_TYPE_VALUES = frozenset({"host"})
IPAM_SUMMARY_SCHEMA_VERSION = "nctl.ipam.reconcile.summary.v1"

# Eligibility bases returned by `_resolve_eligibility()`; only "eligible" produces
# a create/link/noop/conflict-over-existing-data plan. Every other basis is a
# fail-closed or manual-review skip.
_ELIGIBLE = "eligible"
_OBSERVATION_MISSING = "observation_missing"
_OBSERVATION_MISMATCH = "observation_mismatch"
_OBSERVATION_AMBIGUOUS = "observation_ambiguous"
_UNKNOWN_POLICY = "unknown_ip_policy"


@dataclass(frozen=True)
class IPAMReconcilePlan:
    """One planned IPAM reconcile action for a desired endpoint."""

    action: str
    desired_endpoint: dict[str, str]
    desired_ip_address: str
    dns_name: str
    ip_policy: str = ""
    reasons: list[str] = field(default_factory=list)
    existing_ip_address: dict[str, str] | None = None
    create_fields: dict[str, Any] = field(default_factory=dict)
    observed_ip_candidates: list[str] = field(default_factory=list)
    eligibility_basis: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "action": self.action,
            "desired_endpoint": self.desired_endpoint,
            "desired_ip_address": self.desired_ip_address,
            "dns_name": self.dns_name,
            "ip_policy": self.ip_policy,
            "reasons": list(self.reasons),
            "observed_ip_candidates": list(self.observed_ip_candidates),
            "eligibility_basis": self.eligibility_basis,
        }
        if self.existing_ip_address:
            payload["existing_ip_address"] = self.existing_ip_address
        if self.create_fields:
            payload["create_fields"] = dict(self.create_fields)
        return payload


def plan_endpoint_ipam_reconcile(
    desired_endpoint: Any,
    *,
    ip_candidates: Iterable[Any] = (),
    ip_address_model: Any | None = None,
    default_status: Any | None = None,
    observed_ip_candidates: Iterable[Any] = (),
) -> IPAMReconcilePlan:
    """Return a side-effect-free IPAM reconcile plan for one DesiredEndpoint.

    `observed_ip_candidates` carries self-observation evidence (for example the
    linked realized Device/VM's `primary_ip_address`) used to decide whether a
    non-`dhcp_reserved` endpoint may be created/linked automatically. It has no
    effect on `dhcp_reserved` endpoints, which remain eligible without it.
    """

    endpoint_ref = _endpoint_ref(desired_endpoint)
    desired_ip = _normalized_interface(_text(getattr(desired_endpoint, "ip_address", None)))
    desired_host = _host_address(desired_ip)
    dns_name = _text(getattr(desired_endpoint, "dns_name", None))
    ip_policy = _text(getattr(desired_endpoint, "ip_policy", None))
    realized_ip = getattr(desired_endpoint, "realized_ip_address", None)
    observed_hosts = _normalized_observed_hosts(observed_ip_candidates)

    if not desired_ip:
        return IPAMReconcilePlan(
            action="skip",
            desired_endpoint=endpoint_ref,
            desired_ip_address="",
            dns_name=dns_name,
            ip_policy=ip_policy,
            reasons=["missing_ip_address"],
        )

    if ip_policy not in KNOWN_IP_POLICIES:
        return IPAMReconcilePlan(
            action="skip",
            desired_endpoint=endpoint_ref,
            desired_ip_address=desired_ip,
            dns_name=dns_name,
            ip_policy=ip_policy,
            reasons=[_UNKNOWN_POLICY],
        )

    eligibility_basis, used_observed_hosts = _resolve_eligibility(ip_policy, desired_host, observed_hosts)
    if eligibility_basis != _ELIGIBLE:
        return IPAMReconcilePlan(
            action="skip",
            desired_endpoint=endpoint_ref,
            desired_ip_address=desired_ip,
            dns_name=dns_name,
            ip_policy=ip_policy,
            reasons=[eligibility_basis],
            observed_ip_candidates=sorted(observed_hosts),
            eligibility_basis=eligibility_basis,
        )

    if realized_ip is not None:
        realized_host = _host_address(_ip_address_display(realized_ip))
        if realized_host and realized_host == desired_host:
            return IPAMReconcilePlan(
                action="noop",
                desired_endpoint=endpoint_ref,
                desired_ip_address=desired_ip,
                dns_name=dns_name,
                ip_policy=ip_policy,
                reasons=["already_linked"],
                existing_ip_address=_ip_ref(realized_ip),
                observed_ip_candidates=used_observed_hosts,
                eligibility_basis=eligibility_basis,
            )
        return IPAMReconcilePlan(
            action="conflict",
            desired_endpoint=endpoint_ref,
            desired_ip_address=desired_ip,
            dns_name=dns_name,
            ip_policy=ip_policy,
            reasons=["realized_ip_address_mismatch"],
            existing_ip_address=_ip_ref(realized_ip),
            observed_ip_candidates=used_observed_hosts,
            eligibility_basis=eligibility_basis,
        )

    matches = [candidate for candidate in ip_candidates if _host_address(_ip_address_display(candidate)) == desired_host]
    if len(matches) > 1:
        return IPAMReconcilePlan(
            action="conflict",
            desired_endpoint=endpoint_ref,
            desired_ip_address=desired_ip,
            dns_name=dns_name,
            ip_policy=ip_policy,
            reasons=["ambiguous_ip_address_candidates"],
            observed_ip_candidates=used_observed_hosts,
            eligibility_basis=eligibility_basis,
        )

    if len(matches) == 1:
        existing = matches[0]
        conflicts = _existing_ip_conflicts(existing, dns_name, ip_policy)
        if conflicts:
            return IPAMReconcilePlan(
                action="conflict",
                desired_endpoint=endpoint_ref,
                desired_ip_address=desired_ip,
                dns_name=dns_name,
                ip_policy=ip_policy,
                reasons=conflicts,
                existing_ip_address=_ip_ref(existing),
                observed_ip_candidates=used_observed_hosts,
                eligibility_basis=eligibility_basis,
            )
        return IPAMReconcilePlan(
            action="link_ip_address",
            desired_endpoint=endpoint_ref,
            desired_ip_address=desired_ip,
            dns_name=dns_name,
            ip_policy=ip_policy,
            reasons=["matching_ip_address_found"],
            existing_ip_address=_ip_ref(existing),
            observed_ip_candidates=used_observed_hosts,
            eligibility_basis=eligibility_basis,
        )

    create_fields = ip_address_create_fields(
        desired_ip,
        dns_name=dns_name,
        ip_address_model=ip_address_model,
        default_status=default_status,
        ip_policy=ip_policy,
    )
    model_field_names = _model_field_names(ip_address_model)
    if "type" in model_field_names and not create_fields.get("type"):
        return IPAMReconcilePlan(
            action="conflict",
            desired_endpoint=endpoint_ref,
            desired_ip_address=desired_ip,
            dns_name=dns_name,
            ip_policy=ip_policy,
            reasons=["ip_address_type_unresolvable"],
            observed_ip_candidates=used_observed_hosts,
            eligibility_basis=eligibility_basis,
        )

    return IPAMReconcilePlan(
        action="create_ip_address",
        desired_endpoint=endpoint_ref,
        desired_ip_address=desired_ip,
        dns_name=dns_name,
        ip_policy=ip_policy,
        reasons=["missing_actual_ip_address"],
        create_fields=create_fields,
        observed_ip_candidates=used_observed_hosts,
        eligibility_basis=eligibility_basis,
    )


def _resolve_eligibility(
    ip_policy: str, desired_host: str, observed_hosts: set[str]
) -> tuple[str, list[str]]:
    """Return `(basis, observed_hosts_used_as_evidence)` per the eligibility truth table."""

    if ip_policy == DHCP_RESERVED_POLICY:
        return _ELIGIBLE, []

    if not observed_hosts:
        return _OBSERVATION_MISSING, []
    if len(observed_hosts) > 1:
        return _OBSERVATION_AMBIGUOUS, sorted(observed_hosts)

    (only_host,) = observed_hosts
    if only_host == desired_host:
        return _ELIGIBLE, [only_host]
    return _OBSERVATION_MISMATCH, [only_host]


def _normalized_observed_hosts(observed_ip_candidates: Iterable[Any]) -> set[str]:
    hosts: set[str] = set()
    for candidate in observed_ip_candidates:
        raw_value = candidate
        if not isinstance(candidate, str):
            raw_value = getattr(candidate, "value", None)
            if raw_value is None and isinstance(candidate, dict):
                raw_value = candidate.get("value")
        host = _host_address(_normalized_interface(_text(raw_value)))
        if host:
            hosts.add(host)
    return hosts


def build_ipam_reconcile_summary(
    counts: dict[str, Any],
    plans: list[dict[str, Any]],
    *,
    requested_desired_node_slug: str | None,
    selected_desired_node_ids: Iterable[str] = (),
    selected_desired_node_slugs: Iterable[str] = (),
) -> dict[str, Any]:
    """Return the versioned `ipam-reconcile-summary.json` payload (nctl Phase 4 Step 6).

    `requested_desired_node_slug` is the Job's `desired_node` input verbatim
    (`None`/empty means cluster scope, unchanged from before this version).
    `selected_desired_node_ids`/`selected_desired_node_slugs` are the actual
    DesiredNode rows the processed endpoints belong to, letting a caller like
    nctl's host-scoped `reconcile_ipam` action verify the Job really stayed
    within the one node it asked for rather than trusting the request alone.
    """

    return {
        "schema_version": IPAM_SUMMARY_SCHEMA_VERSION,
        "scope": {
            "requested_desired_node_slug": requested_desired_node_slug or None,
            "selected_desired_node_ids": sorted(str(value) for value in selected_desired_node_ids),
            "selected_desired_node_slugs": sorted(str(value) for value in selected_desired_node_slugs),
        },
        "summary": counts,
        "plans": plans,
    }


def ip_address_create_fields(
    ip_address: str,
    *,
    dns_name: str = "",
    ip_address_model: Any | None = None,
    default_status: Any | None = None,
    ip_policy: str = DHCP_RESERVED_POLICY,
) -> dict[str, Any]:
    """Return IPAddress constructor fields supported by the target model."""

    normalized = _normalized_interface(ip_address)
    if not normalized:
        return {}

    interface = ip_interface(normalized)
    field_names = _model_field_names(ip_address_model)
    fields: dict[str, Any] = {}

    if not field_names or "address" in field_names:
        fields["address"] = normalized
    if "host" in field_names:
        fields["host"] = str(interface.ip)
    if "mask_length" in field_names:
        fields["mask_length"] = interface.network.prefixlen
    if dns_name and (not field_names or "dns_name" in field_names):
        fields["dns_name"] = dns_name

    type_value = _type_choice_for_policy(ip_address_model, ip_policy)
    if type_value and "type" in field_names:
        fields["type"] = type_value

    if default_status is not None and "status" in field_names:
        status_pk = getattr(default_status, "pk", None)
        if status_pk is not None:
            # Store the pk, not the model instance: create_fields is logged/serialized
            # as JSON (see jobs.py's _json helper) before being applied to the model.
            fields["status_id"] = str(status_pk)
        else:
            fields["status"] = default_status

    return fields


def _existing_ip_conflicts(existing_ip: Any, desired_dns_name: str, ip_policy: str) -> list[str]:
    conflicts: list[str] = []
    existing_dns_name = _text(getattr(existing_ip, "dns_name", None))
    if existing_dns_name and desired_dns_name and existing_dns_name != desired_dns_name:
        conflicts.append("dns_name_conflict")

    compatible_values = DHCP_TYPE_VALUES if ip_policy == DHCP_RESERVED_POLICY else HOST_TYPE_VALUES
    existing_type = _choice_value(getattr(existing_ip, "type", None)).lower()
    if existing_type not in compatible_values:
        conflicts.append("ip_address_type_conflict")
    return conflicts


def _type_choice_for_policy(ip_address_model: Any | None, ip_policy: str) -> Any | None:
    type_values, fallback_label = (
        (DHCP_TYPE_VALUES, "dhcp") if ip_policy == DHCP_RESERVED_POLICY else (HOST_TYPE_VALUES, "host")
    )
    return _resolve_type_choice(ip_address_model, type_values, fallback_label)


def _resolve_type_choice(ip_address_model: Any | None, type_values: frozenset[str], fallback_label: str) -> Any | None:
    if ip_address_model is None:
        return None
    try:
        field = ip_address_model._meta.get_field("type")
    except Exception:
        return None
    choices = getattr(field, "choices", None) or ()
    for value, label in choices:
        value_text = _text(value).lower()
        label_text = _text(label).lower()
        if value_text in type_values or label_text == fallback_label:
            return value
    return None


def _model_field_names(model: Any | None) -> set[str]:
    if model is None:
        return set()
    try:
        return {field.name for field in model._meta.get_fields()}
    except Exception:
        return set()


def _normalized_interface(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        return str(ip_interface(text))
    except ValueError:
        try:
            interface = ip_interface(f"{text}/32")
        except ValueError:
            return ""
        return str(interface)


def _host_address(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        return str(ip_interface(text).ip)
    except ValueError:
        return text.split("/", maxsplit=1)[0]


def _ip_address_display(actual_ip: Any) -> str:
    address = _text(getattr(actual_ip, "address", None))
    if address:
        return address

    host = _text(getattr(actual_ip, "host", None))
    mask_length = _text(getattr(actual_ip, "mask_length", None))
    if host and mask_length:
        return f"{host}/{mask_length}"
    return host


def _endpoint_ref(endpoint: Any) -> dict[str, str]:
    desired_node = getattr(endpoint, "desired_node", None)
    return {
        "id": _text(getattr(endpoint, "pk", None)),
        "name": _text(getattr(endpoint, "name", None)),
        "desired_node": _text(getattr(desired_node, "name", None)),
        "desired_node_slug": _text(getattr(desired_node, "slug", None)),
    }


def _ip_ref(ip_address: Any) -> dict[str, str]:
    return {
        "id": _text(getattr(ip_address, "pk", None)),
        "address": _ip_address_display(ip_address),
        "dns_name": _text(getattr(ip_address, "dns_name", None)),
        "type": _choice_value(getattr(ip_address, "type", None)),
    }


def _choice_value(value: Any) -> str:
    if value is None:
        return ""
    for attr in ("value", "slug", "name"):
        attr_value = getattr(value, attr, None)
        if attr_value:
            return str(attr_value)
    return str(value)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
