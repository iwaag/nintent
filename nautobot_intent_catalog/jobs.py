"""Nautobot Jobs for intent source analysis."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from .analysis import analyze_intent_sources
from .importers import (
    desired_compute_instance_defaults,
    desired_compute_instance_identity,
    desired_compute_platform_defaults,
    desired_compute_platform_identity,
    desired_node_operational_override_defaults,
    desired_node_operational_override_identity,
    desired_service_create_defaults,
    desired_service_update_fields,
    desired_service_entry_defaults,
    desired_service_entry_identity,
    desired_service_identity,
    desired_service_placement_defaults,
    desired_service_placement_identity,
    desired_endpoint_defaults,
    desired_endpoint_identity,
    desired_ip_range_defaults,
    desired_ip_range_identity,
    desired_node_defaults,
    desired_node_identity,
    intent_source_defaults,
    plan_dependency_sync,
)
from .loaders import IntentSourceEntry
from .loaders import load_default_intent_sources, load_intent_sources
from .intent_contract import require_unique_reference

try:
    from django.conf import settings
    from django.db import transaction
    from django.utils import timezone
    from nautobot.ipam.models import IPAddress
    from nautobot.apps.jobs import BooleanVar, IntegerVar, Job, StringVar, register_jobs

    from .models import (
        DesiredComputeInstance,
        DesiredComputePlatform,
        DesiredDependency,
        DesiredEndpoint,
        DesiredIPRange,
        DesiredNode,
        DesiredNodeOperationalOverride,
        DesiredService,
        DesiredServicePlacement,
        IntentSource,
    )
    from .operations import build_ipam_reconcile_summary, plan_endpoint_ipam_reconcile
except ImportError:  # pragma: no cover - Nautobot is not available in local unit tests.
    if importlib.util.find_spec("nautobot") is not None:
        raise
    jobs = ()
else:

    class PreviewIntentSourceAnalysis(Job):
        """Dry-run analyze configured intent sources."""

        source_file = StringVar(
            default="",
            description="Optional path to intent_sources.yaml. Empty uses App configuration.",
        )
        fetch_timeout = IntegerVar(
            default=10,
            description="HTTP timeout in seconds for each lightweight file request.",
        )
        include_service_preview = BooleanVar(
            default=True,
            description="Log generated desired services as JSON.",
        )

        class Meta:
            name = "Preview Intent Source Analysis"
            description = "Dry-run Backstage catalog detection for configured intent sources."
            has_sensitive_variables = False

        def run(self, source_file: str, fetch_timeout: int, include_service_preview: bool) -> None:
            if source_file:
                load_result = load_intent_sources(Path(source_file))
            else:
                load_result = load_default_intent_sources(_configured_source_file())

            for error in load_result.errors:
                self.logger.warning(error)

            if load_result.errors and not load_result.intent_sources:
                raise ValueError("Intent source catalog could not be loaded; see Job logs for details.")

            result = analyze_intent_sources(
                load_result.intent_sources,
                fetch_timeout=float(fetch_timeout),
            )
            summary = {
                "source_path": str(load_result.source_path),
                "intent_sources": len(load_result.intent_sources),
                "desired_nodes": len(load_result.desired_nodes),
                "desired_ip_ranges": len(load_result.desired_ip_ranges),
                "desired_endpoints": len(load_result.desired_endpoints),
                "source_analyses": len(result.source_analyses),
                "desired_services": len(result.desired_services),
                "analysis_errors": len(result.errors),
                "generated_at": result.generated_at,
            }

            self.logger.info("Intent source analysis summary: %s", _json(summary))
            self.logger.info("Intent source analysis detail: %s", _json(result.source_analyses))
            for error in result.errors:
                self.logger.warning(error)

            if include_service_preview:
                self.logger.info("Desired service preview: %s", _json(result.desired_services))


    class ImportIntentSources(Job):
        """Import intent source inputs from configured YAML into DB models."""

        source_file = StringVar(
            default="",
            description="Optional path to intent_sources.yaml. Empty uses App configuration.",
        )
        disable_missing = BooleanVar(
            default=False,
            description="Disable existing DB intent sources that are not present in the YAML input.",
        )
        preview = BooleanVar(
            default=False,
            description=(
                "Compute the exact per-object create/update/unchanged diff and always roll back. "
                "Makes zero committed writes regardless of disable_missing or a future commit "
                "default, independent of any UI checkbox state."
            ),
        )

        class Meta:
            name = "Import Intent Sources"
            description = "Import intent source YAML rows into IntentSource records."
            has_sensitive_variables = False

        def run(self, source_file: str, disable_missing: bool, preview: bool = False) -> None:
            if source_file:
                load_result = load_intent_sources(Path(source_file))
            else:
                load_result = load_default_intent_sources(_configured_source_file())

            for error in load_result.errors:
                self.logger.warning(error)
            if load_result.errors:
                raise ValueError("Intent source catalog could not be loaded; see Job logs for details.")

            with transaction.atomic():
                counts, diffs = _import_intent_rows(load_result, disable_missing=disable_missing)
                if preview:
                    # Force a rollback of every write this pass made -- including compute
                    # platform/instance rows a later row in the same YAML needed to resolve by
                    # slug -- while `counts`/`diffs` remain plain Python data already extracted
                    # from the (about to be discarded) DB state. This guarantees zero committed
                    # writes independent of `disable_missing` or any UI checkbox default
                    # (plan Section 5.8).
                    transaction.set_rollback(True)

            summary = {
                "source_path": str(load_result.source_path),
                "preview": bool(preview),
                "intent_sources": len(load_result.intent_sources),
                "desired_nodes": len(load_result.desired_nodes),
                "desired_ip_ranges": len(load_result.desired_ip_ranges),
                "desired_endpoints": len(load_result.desired_endpoints),
                "desired_compute_platforms": len(load_result.desired_compute_platforms),
                "desired_compute_instances": len(load_result.desired_compute_instances),
                "desired_services": len(load_result.desired_services),
                "desired_service_placements": len(load_result.desired_service_placements),
                "desired_node_operational_overrides": len(
                    load_result.desired_node_operational_overrides
                ),
                **counts,
            }
            self.logger.info(
                "Intent source import %s summary: %s",
                "preview" if preview else "apply",
                _json(summary),
            )
            self.create_file(
                "intent-import-preview.json" if preview else "intent-import-apply.json",
                json.dumps({"summary": summary, "diffs": diffs}, sort_keys=True, indent=2, ensure_ascii=True)
                + "\n",
            )


    class AnalyzeIntentSources(Job):
        """Analyze DB-backed intent sources and persist desired services plus dependencies."""

        fetch_timeout = IntegerVar(
            default=10,
            description="HTTP timeout in seconds for each lightweight file request.",
        )
        include_disabled = BooleanVar(
            default=False,
            description="Include disabled IntentSource rows in analysis.",
        )

        class Meta:
            name = "Analyze Intent Sources"
            description = "Analyze IntentSource records and persist desired services plus dependencies."
            has_sensitive_variables = False

        def run(self, fetch_timeout: int, include_disabled: bool) -> None:
            queryset = IntentSource.objects.all()
            if not include_disabled:
                queryset = queryset.filter(enabled=True)
            intent_sources = list(queryset.order_by("url"))
            entries = [_entry_from_intent_source(intent_source) for intent_source in intent_sources]
            source_by_url = {intent_source.url: intent_source for intent_source in intent_sources}

            result = analyze_intent_sources(entries, fetch_timeout=float(fetch_timeout))
            now = timezone.now()
            counts = {
                "intent_sources": len(intent_sources),
                "source_analyses": len(result.source_analyses),
                "services_created": 0,
                "services_updated": 0,
                "dependencies_created": 0,
                "dependencies_updated": 0,
                "dependencies_deleted": 0,
                "dependencies_unchanged": 0,
                "analysis_errors": len(result.errors),
            }

            for analysis in result.source_analyses:
                intent_source = source_by_url.get(analysis.get("url"))
                if intent_source is None:
                    continue
                intent_source.last_import_status = analysis.get("status")
                intent_source.last_imported_at = now
                intent_source.last_import_summary = analysis
                intent_source.save(
                    update_fields=("last_import_status", "last_imported_at", "last_import_summary")
                )

            for service in result.desired_services:
                source = service.get("intent_source") if isinstance(service.get("intent_source"), dict) else {}
                intent_source = source_by_url.get(source.get("url"))
                if intent_source is None:
                    self.logger.warning("Skipping desired service without matching intent source: %s", _json(service))
                    continue

                identity = desired_service_identity(service)

                # Reject duplicate normalized dependency keys before any write for this
                # service (p4/plan.md Step 4.3 item 4). Detecting duplicates only requires
                # the incoming analysis, so this check runs before the transaction opens and
                # before the service row itself is touched.
                try:
                    plan_dependency_sync(existing=[], service=service)
                except ValueError as exc:
                    self.logger.warning("Skipping desired service with malformed dependencies: %s (%s)", _json(service), exc)
                    continue

                with transaction.atomic():
                    try:
                        service_obj = DesiredService.objects.select_for_update().get(
                            intent_source=intent_source,
                            catalog_namespace=identity["catalog_namespace"],
                            catalog_metadata_name=identity["catalog_metadata_name"],
                            service_type=identity["service_type"],
                        )
                        created = False
                    except DesiredService.DoesNotExist:
                        service_obj = DesiredService(
                            intent_source=intent_source,
                            **desired_service_create_defaults(service),
                        )
                        created = True

                    if created:
                        service_obj.last_analyzed_at = now
                        service_obj.full_clean()
                        service_obj.save()
                        counts["services_created"] += 1
                    else:
                        update_fields = desired_service_update_fields(service)
                        for field_name, value in update_fields.items():
                            setattr(service_obj, field_name, value)
                        service_obj.last_analyzed_at = now
                        service_obj.save(update_fields=[*update_fields.keys(), "last_analyzed_at"])
                        counts["services_updated"] += 1

                    existing_rows = [
                        {
                            "dependency_kind": row.dependency_kind,
                            "namespace": row.namespace,
                            "name": row.name,
                            "raw_ref": row.raw_ref,
                            "dependency_type": row.dependency_type,
                        }
                        for row in service_obj.dependencies.all()
                    ]
                    # Duplicates were already rejected above; this second call only differs
                    # by `existing` (real DB rows), which cannot introduce new duplicates.
                    dependency_plan = plan_dependency_sync(existing=existing_rows, service=service)

                    if dependency_plan["create"]:
                        DesiredDependency.objects.bulk_create(
                            DesiredDependency(source_service=service_obj, **dependency)
                            for dependency in dependency_plan["create"]
                        )
                        counts["dependencies_created"] += len(dependency_plan["create"])

                    for change in dependency_plan["update"]:
                        kind, namespace, name = change["key"]
                        DesiredDependency.objects.filter(
                            source_service=service_obj,
                            dependency_kind=kind,
                            namespace=namespace,
                            name=name,
                        ).update(raw_ref=change["raw_ref"], dependency_type=change["dependency_type"])
                    counts["dependencies_updated"] += len(dependency_plan["update"])

                    if dependency_plan["delete_keys"]:
                        for kind, namespace, name in dependency_plan["delete_keys"]:
                            DesiredDependency.objects.filter(
                                source_service=service_obj,
                                dependency_kind=kind,
                                namespace=namespace,
                                name=name,
                            ).delete()
                        counts["dependencies_deleted"] += len(dependency_plan["delete_keys"])
                    counts["dependencies_unchanged"] += len(dependency_plan["unchanged_keys"])

            for error in result.errors:
                self.logger.warning(error)

            self.logger.info("Desired service import summary: %s", _json(counts))


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
        PreviewIntentSourceAnalysis,
        ImportIntentSources,
        AnalyzeIntentSources,
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
                desired_endpoint.realized_ip_address_source = "derived"
                desired_endpoint.full_clean()
                desired_endpoint.save(
                    update_fields=["realized_ip_address", "realized_ip_address_source"]
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
                desired_endpoint.realized_ip_address_source = "derived"
                desired_endpoint.full_clean()
                desired_endpoint.save(
                    update_fields=["realized_ip_address", "realized_ip_address_source"]
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


def _entry_from_intent_source(intent_source) -> IntentSourceEntry:
    source_config = intent_source.source_config or {}
    return IntentSourceEntry(
        url=intent_source.url,
        slug=intent_source.slug,
        name=intent_source.name,
        source_type=intent_source.source_type,
        enabled=intent_source.enabled,
        ref=intent_source.ref,
        owner=intent_source.owner,
        service_hint=source_config.get("service_hint") or intent_source.name,
        catalog_paths=list(source_config.get("catalog_paths") or []),
        basic_file_paths=list(source_config.get("basic_file_paths") or []),
        raw_url_template=source_config.get("raw_url_template"),
    )


def _import_intent_rows(load_result, *, disable_missing: bool) -> tuple[dict, list[dict]]:
    """Apply one strict YAML document atomically.

    Returns `(counts, diffs)`. `diffs` names the exact root, identity, and changed
    field old/new values for every row on every call -- not only in preview mode --
    so preview and apply always compute the diff through the identical code path
    (plan Section 5.8 preview/apply parity).
    """

    counts = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "disabled": 0,
        "nodes_created": 0,
        "nodes_updated": 0,
        "nodes_unchanged": 0,
        "ip_ranges_created": 0,
        "ip_ranges_updated": 0,
        "ip_ranges_unchanged": 0,
        "endpoints_created": 0,
        "endpoints_updated": 0,
        "endpoints_unchanged": 0,
        "compute_platforms_created": 0,
        "compute_platforms_updated": 0,
        "compute_platforms_unchanged": 0,
        "compute_instances_created": 0,
        "compute_instances_updated": 0,
        "compute_instances_unchanged": 0,
        "services_created": 0,
        "services_updated": 0,
        "services_unchanged": 0,
        "placements_created": 0,
        "placements_updated": 0,
        "placements_unchanged": 0,
        "operational_overrides_created": 0,
        "operational_overrides_updated": 0,
        "operational_overrides_unchanged": 0,
    }
    diffs: list[dict] = []

    def _record(root: str, identity: dict, status: str, changed: dict) -> None:
        diffs.append(
            {
                "root": root,
                "identity": _json_safe(identity),
                "status": status,
                "changed": changed,
            }
        )

    seen_urls = set()
    seen_slugs = set()
    for source in load_result.intent_sources:
        defaults = intent_source_defaults(source)
        seen_slugs.add(defaults["slug"])
        if source.source_type == "git_repository":
            identity = {"url": source.url}
            seen_urls.add(source.url)
        else:
            identity = {"slug": defaults["slug"]}
        status, _obj, changed = _validated_upsert_diff(IntentSource, identity, defaults)
        counts[status] += 1
        _record("intent_sources", identity, status, changed)

    if disable_missing:
        missing = (
            IntentSource.objects.filter(enabled=True)
            .exclude(url__in=seen_urls)
            .exclude(slug__in=seen_slugs)
        )
        disabled_slugs = list(missing.values_list("slug", flat=True))
        counts["disabled"] = missing.update(enabled=False)
        for slug in disabled_slugs:
            _record(
                "intent_sources",
                {"slug": slug},
                "disabled",
                {"enabled": {"old": True, "new": False}},
            )

    source_by_key = _intent_source_lookup()
    for node in load_result.desired_nodes:
        intent_source = source_by_key.get(node.intent_source) if node.intent_source else None
        identity = desired_node_identity(node)
        status, _obj, changed = _validated_upsert_diff(
            DesiredNode,
            identity,
            desired_node_defaults(node, intent_source_id=getattr(intent_source, "pk", None)),
        )
        counts[f"nodes_{status}"] += 1
        _record("desired_nodes", identity, status, changed)

    for ip_range in load_result.desired_ip_ranges:
        identity = desired_ip_range_identity(ip_range)
        status, _obj, changed = _validated_upsert_diff(
            DesiredIPRange,
            identity,
            desired_ip_range_defaults(ip_range),
        )
        counts[f"ip_ranges_{status}"] += 1
        _record("desired_ip_ranges", identity, status, changed)

    for endpoint in load_result.desired_endpoints:
        desired_node = _resolve_desired_node(endpoint.desired_node)
        identity = desired_endpoint_identity(endpoint, desired_node_id=desired_node.pk)
        status, _obj, changed = _validated_upsert_diff(
            DesiredEndpoint,
            identity,
            desired_endpoint_defaults(endpoint, desired_node=desired_node),
        )
        counts[f"endpoints_{status}"] += 1
        _record("desired_endpoints", identity, status, changed)

    for platform in load_result.desired_compute_platforms:
        control_node = _resolve_desired_node(platform.control_node)
        identity = desired_compute_platform_identity(platform)
        status, _obj, changed = _validated_upsert_diff(
            DesiredComputePlatform,
            identity,
            desired_compute_platform_defaults(platform, control_node_id=control_node.pk),
        )
        counts[f"compute_platforms_{status}"] += 1
        _record("desired_compute_platforms", identity, status, changed)

    for instance in load_result.desired_compute_instances:
        desired_node = _resolve_desired_node(instance.desired_node)
        platform_obj = _resolve_desired_compute_platform(instance.platform)
        identity = desired_compute_instance_identity(desired_node.pk)
        status, _obj, changed = _validated_upsert_diff(
            DesiredComputeInstance,
            identity,
            desired_compute_instance_defaults(instance, platform_id=platform_obj.pk),
        )
        counts[f"compute_instances_{status}"] += 1
        _record(
            "desired_compute_instances",
            {"desired_node": instance.desired_node, **identity},
            status,
            changed,
        )

    for service in load_result.desired_services:
        intent_source = source_by_key.get(service.intent_source)
        if intent_source is None:
            raise ValueError(
                f"desired_services entry references unknown intent_source slug: {service.intent_source}."
            )
        identity = desired_service_entry_identity(service, intent_source.pk)
        status, _obj, changed = _validated_upsert_diff(
            DesiredService,
            identity,
            desired_service_entry_defaults(service),
        )
        counts[f"services_{status}"] += 1
        _record("desired_services", identity, status, changed)

    for placement in load_result.desired_service_placements:
        desired_service = _resolve_desired_service(placement.desired_service)
        desired_node = _resolve_desired_node(placement.desired_node)
        desired_endpoint = _resolve_desired_endpoint(
            desired_node,
            placement.desired_endpoint,
            required=False,
        )
        identity = desired_service_placement_identity(placement, desired_service.pk)
        status, _obj, changed = _validated_upsert_diff(
            DesiredServicePlacement,
            identity,
            desired_service_placement_defaults(
                placement,
                desired_node_id=desired_node.pk,
                desired_endpoint_id=getattr(desired_endpoint, "pk", None),
            ),
        )
        counts[f"placements_{status}"] += 1
        _record("desired_service_placements", identity, status, changed)

    for operational_override in load_result.desired_node_operational_overrides:
        desired_node = _resolve_desired_node(operational_override.desired_node)
        local_endpoint = _resolve_desired_endpoint(
            desired_node,
            operational_override.local_endpoint,
            required=False,
        )
        tailscale_endpoint = _resolve_desired_endpoint(
            desired_node,
            operational_override.tailscale_endpoint,
            required=False,
        )
        identity = desired_node_operational_override_identity(operational_override, desired_node.pk)
        status, _obj, changed = _validated_upsert_diff(
            DesiredNodeOperationalOverride,
            identity,
            desired_node_operational_override_defaults(
                operational_override,
                local_endpoint_id=getattr(local_endpoint, "pk", None),
                tailscale_endpoint_id=getattr(tailscale_endpoint, "pk", None),
            ),
        )
        counts[f"operational_overrides_{status}"] += 1
        _record("desired_node_operational_overrides", identity, status, changed)

    return counts, diffs


def _validated_upsert(model, identity: dict, defaults: dict):
    queryset = model.objects.filter(**identity)
    match_count = queryset.count()
    if match_count > 1:
        require_unique_reference(model.__name__, match_count)
    obj = queryset.first() if match_count == 1 else model(**identity)
    created = match_count == 0
    if not created and _object_matches_defaults(obj, defaults):
        return "unchanged", obj
    for key, value in defaults.items():
        setattr(obj, key, value)
    obj.full_clean()
    obj.save()
    return ("created" if created else "updated"), obj


def _validated_upsert_diff(model, identity: dict, defaults: dict):
    """Same upsert as `_validated_upsert`, plus the exact changed-field old/new diff.

    Diffs the *persisted* values (after `full_clean()`/`save()`, i.e. after model-level
    normalization such as MAC canonicalization or config-key stripping) rather than the
    raw incoming `defaults`, so a preview and the eventual apply never disagree on what
    actually changed.
    """

    queryset = model.objects.filter(**identity)
    match_count = queryset.count()
    if match_count > 1:
        require_unique_reference(model.__name__, match_count)
    before = None
    if match_count == 1:
        existing = queryset.first()
        before = {key: getattr(existing, key) for key in defaults}

    status, obj = _validated_upsert(model, identity, defaults)

    changed = {}
    if status == "created":
        changed = {key: {"old": None, "new": _json_safe(getattr(obj, key))} for key in defaults}
    elif status == "updated":
        for key in defaults:
            old_value = before.get(key) if before else None
            new_value = getattr(obj, key)
            if old_value != new_value:
                changed[key] = {"old": _json_safe(old_value), "new": _json_safe(new_value)}
    return status, obj, changed


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _resolve_desired_node(slug: str):
    queryset = DesiredNode.objects.filter(slug=slug)
    require_unique_reference("DesiredNode", queryset.count())
    return queryset.get()


def _resolve_desired_compute_platform(slug: str):
    queryset = DesiredComputePlatform.objects.filter(slug=slug)
    require_unique_reference("DesiredComputePlatform", queryset.count())
    return queryset.get()


def _resolve_desired_service(reference: dict[str, str]):
    queryset = DesiredService.objects.filter(
        intent_source__slug=reference["intent_source"],
        catalog_namespace=reference["catalog_namespace"],
        catalog_metadata_name=reference["catalog_metadata_name"],
        service_type=reference["service_type"],
    )
    require_unique_reference("DesiredService", queryset.count())
    return queryset.get()


def _resolve_desired_endpoint(desired_node, reference, *, required: bool):
    if reference is None:
        if required:
            raise ValueError("DesiredEndpoint reference is required.")
        return None
    queryset = DesiredEndpoint.objects.filter(
        desired_node=desired_node,
        name=reference["name"],
        endpoint_type=reference["endpoint_type"],
    )
    require_unique_reference("DesiredEndpoint", queryset.count())
    return queryset.get()


def _intent_source_lookup() -> dict:
    lookup = {}
    for intent_source in IntentSource.objects.all():
        lookup[intent_source.slug] = intent_source
        lookup[intent_source.name] = intent_source
        if intent_source.url:
            lookup[intent_source.url] = intent_source
    return lookup


def _object_matches_defaults(obj, defaults: dict) -> bool:
    return all(getattr(obj, key) == value for key, value in defaults.items())
