"""Nautobot Jobs for intent source analysis."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from .loaders import load_default_intent_sources, load_intent_sources
from .batch import apply_batch, document_from_load_result, plan_batch

IMPORT_SCHEMA_VERSION = "nintent.intent-import.v1"
IMPORT_ARTIFACT_FILENAME = "intent-import-result.json"


try:
    from django.conf import settings
    from django.db import transaction
    from nautobot.ipam.models import IPAddress
    from nautobot.apps.jobs import BooleanVar, IntegerVar, Job, StringVar, register_jobs

    from .models import (
        DesiredEndpoint,
        DesiredIPRange,
        DesiredNode,
        DesiredNodeOperationalOverride,
    )
    from .operations import build_ipam_reconcile_summary, plan_endpoint_ipam_reconcile
except ImportError:  # pragma: no cover - Nautobot is not available in local unit tests.
    if importlib.util.find_spec("nautobot") is not None:
        raise
    jobs = ()
else:

    class ImportIntentSources(Job):
        """Import intent source inputs from configured YAML into DB models.

        Defaults to a zero-write preview (plan Section 5). The read-only plan
        (`_plan_import`) and the atomic applier (`_apply_import`) are separate functions so
        `apply=false` structurally cannot invoke a mutation method.
        """

        source_file = StringVar(
            default="",
            description="Optional path to intent_sources.yaml. Empty uses App configuration.",
        )
        apply = BooleanVar(
            default=False,
            description=(
                "Commit the plan atomically. Preview (apply=false, the default) performs zero "
                "database writes and always emits the same versioned artifact shape."
            ),
        )

        class Meta:
            name = "Import Intent Sources"
            description = "Import intent source YAML rows into IntentSource records."
            has_sensitive_variables = False

        def run(self, source_file: str, apply: bool = False) -> None:
            if source_file:
                load_result = load_intent_sources(Path(source_file))
            else:
                load_result = load_default_intent_sources(_configured_source_file())

            for error in load_result.errors:
                self.logger.warning(error)

            mode = "apply" if apply else "preview"

            if load_result.errors:
                artifact = {"schema_version": "nintent.desired-state-batch.v1", "operations": [],
                            "errors": [{"message": error} for error in load_result.errors],
                            "totals": {name: 0 for name in ("create", "update", "delete", "unchanged", "conflict")},
                            "transaction": {"status": "blocked", "committed": False}}
                self._write_artifact(artifact)
                raise ValueError(
                    "Intent source catalog could not be loaded; see Job logs and the artifact for details."
                )

            document = document_from_load_result(load_result, dry_run=not apply)
            artifact = (plan_batch(document) if not apply else apply_batch(document)).as_dict()
            self.logger.info("Intent source import %s summary: %s", mode, _json(artifact["totals"]))
            self._write_artifact(artifact)
            if artifact["transaction"]["status"] in {"blocked", "rolled_back"}:
                raise ValueError("Intent source batch was not committed; see the result artifact.")
            return


        def _write_artifact(self, artifact: dict) -> None:
            self.create_file(
                IMPORT_ARTIFACT_FILENAME,
                json.dumps(artifact, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
            )


    class ReconcileDesiredIPAMIntent(Job):
        """Optionally create or link Nautobot IPAddress rows from explicit endpoint IP intent."""

        commit_changes = BooleanVar(
            default=False,
            description="Create/link Nautobot IPAddress rows. Leave disabled for dry-run.",
        )
        include_inactive = BooleanVar(
            default=False,
            description="Include endpoints attached to deprecated and retired DesiredNode rows.",
        )
        desired_node = StringVar(
            required=False,
            default="",
            description=(
                "Optional DesiredNode slug. Scopes reconciliation to that node's endpoints only "
                "(Phase 4 host-scoped reconcile); empty keeps the existing cluster-wide behavior."
            ),
        )

        class Meta:
            name = "Reconcile Desired IPAM Intent"
            description = (
                "Dry-run or apply explicit DesiredEndpoint IP intent to Nautobot IPAddress rows. "
                "dhcp_reserved endpoints are always eligible; static/external endpoints additionally "
                "require a matching self-observed primary IP address."
            )
            has_sensitive_variables = False

        def run(self, commit_changes: bool, include_inactive: bool, desired_node: str = "") -> None:
            requested_desired_node_slug = (desired_node or "").strip()
            endpoints = (
                DesiredEndpoint.objects.select_related(
                    "desired_node",
                    "desired_node__realized_device",
                    "realized_ip_address",
                )
                .exclude(ip_address__isnull=True)
                .exclude(ip_address="")
                .order_by("desired_node__slug", "endpoint_type", "name")
            )
            if not include_inactive:
                endpoints = endpoints.exclude(desired_node__lifecycle__in=("deprecated", "retired"))
            if requested_desired_node_slug:
                matching_nodes = list(DesiredNode.objects.filter(slug=requested_desired_node_slug))
                if len(matching_nodes) != 1:
                    raise ValueError(
                        f"expected exactly one DesiredNode with slug {requested_desired_node_slug!r}, "
                        f"found {len(matching_nodes)}"
                    )
                endpoints = endpoints.filter(desired_node__slug=requested_desired_node_slug)

            ip_candidates = list(IPAddress.objects.all().order_by("host", "mask_length"))
            default_status = _default_ip_address_status(IPAddress)
            counts = {
                "commit_changes": bool(commit_changes),
                "endpoints": 0,
                "eligible": 0,
                "planned_ip_address_creates": 0,
                "planned_ip_address_links": 0,
                "created_ip_addresses": 0,
                "linked_ip_addresses": 0,
                "noop": 0,
                "skipped": 0,
                "conflicts": 0,
            }
            plans = []
            selected_node_ids: set[str] = set()
            selected_node_slugs: set[str] = set()

            for desired_endpoint in endpoints:
                counts["endpoints"] += 1
                selected_node_ids.add(str(desired_endpoint.desired_node_id))
                selected_node_slugs.add(desired_endpoint.desired_node.slug)
                observed_ip_candidates = _observed_ip_candidates(desired_endpoint.desired_node)
                # Recheck eligibility against current Nautobot state immediately before
                # writing (defense in depth): the caller-fixed nctl decision that
                # triggered this run may be stale by the time this row executes.
                plan = plan_endpoint_ipam_reconcile(
                    desired_endpoint,
                    ip_candidates=ip_candidates,
                    ip_address_model=IPAddress,
                    default_status=default_status,
                    observed_ip_candidates=observed_ip_candidates,
                )
                if plan.eligibility_basis == "eligible":
                    counts["eligible"] += 1
                applied_plan = plan
                if commit_changes and plan.action in {"create_ip_address", "link_ip_address"}:
                    applied_plan = _apply_ipam_reconcile_plan(plan, desired_endpoint, IPAddress)
                    if applied_plan.action == "create_ip_address_applied":
                        ip_candidates = list(IPAddress.objects.all().order_by("host", "mask_length"))
                    elif applied_plan.action == "link_ip_address_applied":
                        desired_endpoint.refresh_from_db()

                plan_data = applied_plan.as_dict()
                plans.append(plan_data)
                self.logger.info("IPAM reconcile action: %s", _json(plan_data))
                _count_ipam_reconcile_action(counts, applied_plan.action)

            summary_payload = build_ipam_reconcile_summary(
                counts,
                plans,
                requested_desired_node_slug=requested_desired_node_slug,
                selected_desired_node_ids=selected_node_ids,
                selected_desired_node_slugs=selected_node_slugs,
            )
            self.create_file(
                "ipam-reconcile-summary.json",
                json.dumps(summary_payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
            )
            self.logger.info("Desired IPAM reconcile summary: %s", _json(counts))

    jobs = (
        ImportIntentSources,
        ReconcileDesiredIPAMIntent,
    )
    register_jobs(*jobs)


def _configured_source_file():
    plugins_config = getattr(settings, "PLUGINS_CONFIG", {}) or {}
    app_config = plugins_config.get("nautobot_intent_catalog", {}) or {}
    return app_config.get("intent_sources_file")


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _observed_ip_candidates(desired_node) -> list[dict[str, str]]:
    """Return self-observation evidence for a DesiredNode's linked realized objects.

    Reads only the `primary_ip_address`/`last_seen` custom fields the nauto
    `Ingest Nodeutils Inventory` Job already writes onto a realized Device (the
    same actual-state boundary nctl reads as `ActualFacts.local_ip`). Never
    reads the controller-local nodeutils cache directly. nauto ingestion only
    writes these guest-OS fields onto Devices; the compute-layer
    `DesiredComputeInstance.realized_vm` link is a separate resource-level
    realization and is never consulted for guest-OS IP evidence here.
    """

    candidates: list[dict[str, str]] = []
    for realized, source in (
        (getattr(desired_node, "realized_device", None), "realized_device"),
    ):
        if realized is None:
            continue
        custom_fields = dict(getattr(realized, "custom_field_data", {}) or {})
        value = _text(custom_fields.get("primary_ip_address"))
        if not value:
            continue
        candidates.append(
            {
                "value": value,
                "basis": f"{source}.primary_ip_address",
                "last_seen": _text(custom_fields.get("last_seen")),
            }
        )
    return candidates


def _default_ip_address_status(ip_address_model):
    """Return a Status row usable for a newly created IPAddress, if any is configured.

    IPAddress.status has no model-level default, so a plain endpoint create
    would otherwise always fail `full_clean()` with a required-field error.
    Prefer "Active", then "Reserved" before falling back to an arbitrary Status
    assigned to the IPAddress content type -- an alphabetical fallback could
    otherwise land on something like "Deprecated" for a freshly created
    address.
    """

    from nautobot.extras.models import Status

    statuses = Status.objects.get_for_model(ip_address_model)
    for name in ("Active", "Reserved"):
        found = statuses.filter(name=name).first()
        if found is not None:
            return found
    return statuses.order_by("name").first()


def _apply_ipam_reconcile_plan(plan, desired_endpoint, ip_address_model):
    try:
        with transaction.atomic():
            if plan.action == "create_ip_address":
                ip_address = ip_address_model(**plan.create_fields)
                ip_address.full_clean()
                ip_address.save()
                desired_endpoint.realized_ip_address = ip_address
                desired_endpoint.full_clean()
                desired_endpoint.save(
                    update_fields=["realized_ip_address"]
                )
                return plan.__class__(
                    action="create_ip_address_applied",
                    desired_endpoint=plan.desired_endpoint,
                    desired_ip_address=plan.desired_ip_address,
                    dns_name=plan.dns_name,
                    reasons=["created_and_linked_ip_address"],
                    existing_ip_address={
                        "id": str(getattr(ip_address, "pk", "")),
                        "address": plan.desired_ip_address,
                        "dns_name": plan.dns_name,
                        "type": str(plan.create_fields.get("type", "")),
                    },
                    create_fields=plan.create_fields,
                )

            if plan.action == "link_ip_address":
                ip_address_id = plan.existing_ip_address.get("id") if plan.existing_ip_address else ""
                ip_address = ip_address_model.objects.get(pk=ip_address_id)
                desired_endpoint.realized_ip_address = ip_address
                desired_endpoint.full_clean()
                desired_endpoint.save(
                    update_fields=["realized_ip_address"]
                )
                return plan.__class__(
                    action="link_ip_address_applied",
                    desired_endpoint=plan.desired_endpoint,
                    desired_ip_address=plan.desired_ip_address,
                    dns_name=plan.dns_name,
                    reasons=["linked_existing_ip_address"],
                    existing_ip_address=plan.existing_ip_address,
                )
    except Exception as exc:
        return plan.__class__(
            action="conflict",
            desired_endpoint=plan.desired_endpoint,
            desired_ip_address=plan.desired_ip_address,
            dns_name=plan.dns_name,
            reasons=[*plan.reasons, "apply_failed", f"{exc.__class__.__name__}: {exc}"],
            existing_ip_address=plan.existing_ip_address,
            create_fields=plan.create_fields,
        )
    return plan


def _count_ipam_reconcile_action(counts: dict, action: str) -> None:
    if action == "create_ip_address":
        counts["planned_ip_address_creates"] += 1
    elif action == "link_ip_address":
        counts["planned_ip_address_links"] += 1
    elif action == "create_ip_address_applied":
        counts["created_ip_addresses"] += 1
    elif action == "link_ip_address_applied":
        counts["linked_ip_addresses"] += 1
    elif action == "noop":
        counts["noop"] += 1
    elif action == "skip":
        counts["skipped"] += 1
    elif action == "conflict":
        counts["conflicts"] += 1
