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
    desired_service_entry_locked_fields,
    desired_service_entry_update_fields,
    desired_service_identity,
    desired_service_placement_defaults,
    desired_service_placement_identity,
    desired_endpoint_defaults,
    desired_endpoint_identity,
    desired_ip_range_defaults,
    desired_ip_range_identity,
    desired_node_defaults,
    desired_node_identity,
    desired_node_update_fields,
    intent_source_defaults,
    plan_dependency_sync,
)
from .import_plan import CANONICAL_IMPORT_ROOTS, build_artifact, plan_upsert, unresolved_reference
from .loaders import IntentSourceEntry
from .loaders import load_default_intent_sources, load_intent_sources
from .intent_contract import require_unique_reference

IMPORT_SCHEMA_VERSION = "nintent.intent-import.v1"
IMPORT_ARTIFACT_FILENAME = "intent-import-result.json"

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

            source_info = _import_source_info(load_result)
            mode = "apply" if apply else "preview"

            if load_result.errors:
                artifact = build_artifact(
                    schema_version=IMPORT_SCHEMA_VERSION,
                    mode=mode,
                    source=source_info,
                    roots=CANONICAL_IMPORT_ROOTS,
                    counts_by_root=_import_counts_by_root(load_result),
                    objects=[],
                    errors=list(load_result.errors),
                    apply_requested=apply,
                    attempted=False,
                    committed=False,
                    transaction_status="blocked" if apply else "not_requested",
                    transaction_error=None,
                    confirmation_status="not_applicable",
                    confirmation_mismatches=[],
                )
                self._write_artifact(artifact)
                raise ValueError(
                    "Intent source catalog could not be loaded; see Job logs and the artifact for details."
                )

            planned_objects = _plan_import(load_result)
            blocked = any(obj.action == "conflict" for obj in planned_objects)

            attempted = False
            committed = False
            transaction_status = "not_requested"
            transaction_error: str | None = None
            confirmation_status = "not_applicable"
            confirmation_mismatches: list[dict] = []

            if apply:
                if blocked:
                    transaction_status = "blocked"
                else:
                    attempted = True
                    try:
                        with transaction.atomic():
                            _apply_import(load_result)
                    except Exception as exc:  # noqa: BLE001 - reported truthfully below, not swallowed
                        transaction_status = "rolled_back"
                        transaction_error = f"{exc.__class__.__name__}: {exc}"
                    else:
                        committed = True
                        transaction_status = "committed"
                        confirmation_mismatches = _confirm_import(load_result)
                        confirmation_status = "confirmed" if not confirmation_mismatches else "mismatched"

            artifact = build_artifact(
                schema_version=IMPORT_SCHEMA_VERSION,
                mode=mode,
                source=source_info,
                roots=CANONICAL_IMPORT_ROOTS,
                counts_by_root=_import_counts_by_root(load_result),
                objects=planned_objects,
                errors=[],
                apply_requested=apply,
                attempted=attempted,
                committed=committed,
                transaction_status=transaction_status,
                transaction_error=transaction_error,
                confirmation_status=confirmation_status,
                confirmation_mismatches=confirmation_mismatches,
            )
            self.logger.info("Intent source import %s summary: %s", mode, _json(artifact["totals"]))
            self._write_artifact(artifact)

        def _write_artifact(self, artifact: dict) -> None:
            self.create_file(
                IMPORT_ARTIFACT_FILENAME,
                json.dumps(artifact, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
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


def _import_source_info(load_result) -> dict:
    """Source identity block shared by preview and apply artifacts (plan Section 5.4)."""

    import hashlib
    import subprocess

    resolved_path = load_result.source_path
    sha256 = None
    try:
        sha256 = hashlib.sha256(resolved_path.read_bytes()).hexdigest()
    except OSError:
        pass

    repository_revision = None
    try:
        completed = subprocess.run(
            ["git", "-C", str(resolved_path.parent), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if completed.returncode == 0:
            repository_revision = completed.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass

    return {
        "configured_path": str(resolved_path),
        "resolved_path": str(resolved_path),
        "sha256": sha256,
        "repository_revision": repository_revision,
    }


def _import_counts_by_root(load_result) -> dict[str, int]:
    return {
        "intent_sources": len(load_result.intent_sources),
        "desired_nodes": len(load_result.desired_nodes),
        "desired_endpoints": len(load_result.desired_endpoints),
        "desired_ip_ranges": len(load_result.desired_ip_ranges),
        "desired_compute_platforms": len(load_result.desired_compute_platforms),
        "desired_compute_instances": len(load_result.desired_compute_instances),
        "desired_services": len(load_result.desired_services),
        "desired_service_placements": len(load_result.desired_service_placements),
        "desired_node_operational_overrides": len(load_result.desired_node_operational_overrides),
    }


def _project(row: dict | None, fields: dict) -> dict:
    """Project a `.values()` row (or `None`) onto exactly `fields`' keys, JSON-safe."""

    if row is None:
        return {}
    return {key: _json_safe(row.get(key)) for key in fields}


def _plan_import(load_result) -> list:
    """Build the complete read-only Import plan (plan Section 5.2).

    Never calls `save()`/`update()`/`delete()`/`bulk_create()` -- every existing row is read via
    `.values()` into a plain dict before `plan_upsert()` (itself pure, see `import_plan.py`)
    makes the create/update/unchanged/conflict decision. References are resolved against the
    union of already-existing rows and rows planned for creation in this same run; an
    unresolvable reference becomes a `conflict`, never a raised exception, so one bad row does
    not prevent the rest of the document from being planned and reported.
    """

    planned: list = []

    intent_source_rows = {
        row["slug"]: row
        for row in IntentSource.objects.values(
            "pk", "slug", "url", "name", "source_type", "enabled", "ref", "owner",
            "description", "source_config",
        )
    }
    intent_source_rows_by_url = {row["url"]: row for row in intent_source_rows.values() if row["url"]}
    planned_intent_source_slugs = {intent_source_defaults(s)["slug"] for s in load_result.intent_sources}

    for source in load_result.intent_sources:
        create_fields = intent_source_defaults(source)
        if source.source_type == "git_repository":
            identity = {"url": source.url}
            existing = [intent_source_rows_by_url[source.url]] if source.url in intent_source_rows_by_url else []
        else:
            identity = {"slug": create_fields["slug"]}
            existing = [intent_source_rows[create_fields["slug"]]] if create_fields["slug"] in intent_source_rows else []
        planned.append(
            plan_upsert(
                model="IntentSource",
                root="intent_sources",
                identity=identity,
                create_fields=_json_safe(create_fields),
                update_fields=_json_safe(create_fields),
                existing_matches=[_project(row, create_fields) for row in existing],
            )
        )

    def resolve_intent_source_pk(slug):
        if slug is None:
            return None, True
        row = intent_source_rows.get(slug)
        if row is not None:
            return row["pk"], True
        return (None, True) if slug in planned_intent_source_slugs else (None, False)

    node_rows = {
        row["slug"]: row
        for row in DesiredNode.objects.values(
            "pk", "slug", "name", "node_type", "accepted_actual_types", "lifecycle", "role",
            "description", "expected_spec", "notes", "intent_source_id",
        )
    }
    planned_node_slugs = {node.slug for node in load_result.desired_nodes}

    for node in load_result.desired_nodes:
        identity = desired_node_identity(node)
        intent_source_pk, resolved = resolve_intent_source_pk(node.intent_source)
        if not resolved:
            planned.append(
                unresolved_reference(
                    "DesiredNode", "desired_nodes", identity,
                    f"unknown intent_source slug: {node.intent_source}",
                )
            )
            continue
        create_fields = desired_node_defaults(node, intent_source_id=intent_source_pk)
        update_fields = desired_node_update_fields(node, intent_source_id=intent_source_pk)
        existing_row = node_rows.get(node.slug)
        planned.append(
            plan_upsert(
                model="DesiredNode",
                root="desired_nodes",
                identity=identity,
                create_fields=_json_safe(create_fields),
                update_fields=_json_safe(update_fields),
                existing_matches=[_project(existing_row, create_fields)] if existing_row else [],
            )
        )

    def resolve_node_pk(slug):
        row = node_rows.get(slug)
        if row is not None:
            return row["pk"], True
        return (None, True) if slug in planned_node_slugs else (None, False)

    ip_range_rows = {
        row["slug"]: row
        for row in DesiredIPRange.objects.values(
            "pk", "name", "start_address", "end_address", "range_policy", "lifecycle",
            "generate_dnsmasq", "dnsmasq_options", "description",
        )
    }
    for ip_range in load_result.desired_ip_ranges:
        identity = desired_ip_range_identity(ip_range)
        create_fields = desired_ip_range_defaults(ip_range)
        existing_row = ip_range_rows.get(ip_range.slug)
        planned.append(
            plan_upsert(
                model="DesiredIPRange",
                root="desired_ip_ranges",
                identity=identity,
                create_fields=_json_safe(create_fields),
                update_fields=_json_safe(create_fields),
                existing_matches=[_project(existing_row, create_fields)] if existing_row else [],
            )
        )

    endpoint_field_names = (
        "ip_address", "mac_address", "dns_name", "dns_name_source", "mdns_name",
        "mdns_name_source", "vpn_dns_name", "protocol", "port", "generate_dnsmasq", "ip_policy",
        "dnsmasq_record_type", "description",
    )
    endpoint_rows = {
        (row["desired_node__slug"], row["name"], row["endpoint_type"]): row
        for row in DesiredEndpoint.objects.values("pk", "desired_node__slug", "name", "endpoint_type", *endpoint_field_names)
    }
    planned_endpoint_keys = {
        (endpoint.desired_node, endpoint.name, endpoint.endpoint_type) for endpoint in load_result.desired_endpoints
    }

    for endpoint in load_result.desired_endpoints:
        node_pk, node_resolved = resolve_node_pk(endpoint.desired_node)
        identity = {"desired_node": endpoint.desired_node, "name": endpoint.name, "endpoint_type": endpoint.endpoint_type}
        if not node_resolved:
            planned.append(
                unresolved_reference(
                    "DesiredEndpoint", "desired_endpoints", identity,
                    f"unknown desired_node slug: {endpoint.desired_node}",
                )
            )
            continue
        create_fields = desired_endpoint_defaults(endpoint)
        existing_row = endpoint_rows.get((endpoint.desired_node, endpoint.name, endpoint.endpoint_type))
        planned.append(
            plan_upsert(
                model="DesiredEndpoint",
                root="desired_endpoints",
                identity=identity,
                create_fields=_json_safe(create_fields),
                update_fields=_json_safe(create_fields),
                existing_matches=[_project(existing_row, create_fields)] if existing_row else [],
            )
        )

    def resolve_endpoint_pk(node_slug, reference):
        if reference is None:
            return None, True
        key = (node_slug, reference["name"], reference["endpoint_type"])
        row = endpoint_rows.get(key)
        if row is not None:
            return row["pk"], True
        return (None, True) if key in planned_endpoint_keys else (None, False)

    platform_rows = {
        row["slug"]: row
        for row in DesiredComputePlatform.objects.values(
            "pk", "slug", "name", "provider_type", "lifecycle", "control_node_id",
            "config_schema_version", "config",
        )
    }
    planned_platform_slugs = {platform.slug for platform in load_result.desired_compute_platforms}

    for platform in load_result.desired_compute_platforms:
        control_node_pk, resolved = resolve_node_pk(platform.control_node)
        identity = desired_compute_platform_identity(platform)
        if not resolved:
            planned.append(
                unresolved_reference(
                    "DesiredComputePlatform", "desired_compute_platforms", identity,
                    f"unknown control_node slug: {platform.control_node}",
                )
            )
            continue
        create_fields = desired_compute_platform_defaults(platform, control_node_id=control_node_pk)
        existing_row = platform_rows.get(platform.slug)
        planned.append(
            plan_upsert(
                model="DesiredComputePlatform",
                root="desired_compute_platforms",
                identity=identity,
                create_fields=_json_safe(create_fields),
                update_fields=_json_safe(create_fields),
                existing_matches=[_project(existing_row, create_fields)] if existing_row else [],
            )
        )

    def resolve_platform_pk(slug):
        row = platform_rows.get(slug)
        if row is not None:
            return row["pk"], True
        return (None, True) if slug in planned_platform_slugs else (None, False)

    instance_rows = {
        row["desired_node_id"]: row
        for row in DesiredComputeInstance.objects.values(
            "pk", "desired_node_id", "platform_id", "instance_kind", "desired_power_state",
            "vcpus", "memory_mb", "root_disk_gb", "config_schema_version", "config",
        )
    }
    instance_rows_by_node_slug = {}
    for row in DesiredComputeInstance.objects.values(
        "pk", "desired_node__slug", "platform_id", "instance_kind", "desired_power_state",
        "vcpus", "memory_mb", "root_disk_gb", "config_schema_version", "config",
    ):
        instance_rows_by_node_slug[row["desired_node__slug"]] = row

    for instance in load_result.desired_compute_instances:
        node_pk, node_resolved = resolve_node_pk(instance.desired_node)
        platform_pk, platform_resolved = resolve_platform_pk(instance.platform)
        identity = {"desired_node": instance.desired_node}
        if not node_resolved:
            planned.append(
                unresolved_reference(
                    "DesiredComputeInstance", "desired_compute_instances", identity,
                    f"unknown desired_node slug: {instance.desired_node}",
                )
            )
            continue
        if not platform_resolved:
            planned.append(
                unresolved_reference(
                    "DesiredComputeInstance", "desired_compute_instances", identity,
                    f"unknown platform slug: {instance.platform}",
                )
            )
            continue
        create_fields = desired_compute_instance_defaults(instance, platform_id=platform_pk)
        existing_row = instance_rows_by_node_slug.get(instance.desired_node)
        planned.append(
            plan_upsert(
                model="DesiredComputeInstance",
                root="desired_compute_instances",
                identity=identity,
                create_fields=_json_safe(create_fields),
                update_fields=_json_safe(create_fields),
                existing_matches=[_project(existing_row, create_fields)] if existing_row else [],
            )
        )

    service_field_names = (
        "name", "slug", "display_name", "lifecycle", "source_ref", "source_catalog_path",
        "catalog_kind", "catalog_owner", "catalog_lifecycle", "prefers_gpu", "min_memory_gb",
        "requirements", "notes",
    )
    service_rows = {
        (row["intent_source__slug"], row["catalog_namespace"], row["catalog_metadata_name"], row["service_type"]): row
        for row in DesiredService.objects.values(
            "pk", "intent_source__slug", "catalog_namespace", "catalog_metadata_name",
            "service_type", *service_field_names,
        )
    }
    planned_service_keys = {
        (service.intent_source, service.catalog_namespace, service.catalog_metadata_name, service.service_type)
        for service in load_result.desired_services
    }

    for service in load_result.desired_services:
        identity = {
            "intent_source": service.intent_source,
            "catalog_namespace": service.catalog_namespace,
            "catalog_metadata_name": service.catalog_metadata_name,
            "service_type": service.service_type,
        }
        if service.intent_source not in intent_source_rows and service.intent_source not in planned_intent_source_slugs:
            planned.append(
                unresolved_reference(
                    "DesiredService", "desired_services", identity,
                    f"unknown intent_source slug: {service.intent_source}",
                )
            )
            continue
        create_fields = desired_service_entry_defaults(service)
        update_fields = desired_service_entry_update_fields(service)
        locked_fields = desired_service_entry_locked_fields(service)
        existing_row = service_rows.get(
            (service.intent_source, service.catalog_namespace, service.catalog_metadata_name, service.service_type)
        )
        planned.append(
            plan_upsert(
                model="DesiredService",
                root="desired_services",
                identity=identity,
                create_fields=_json_safe(create_fields),
                update_fields=_json_safe(update_fields),
                existing_matches=[_project(existing_row, create_fields)] if existing_row else [],
                locked_fields=_json_safe(locked_fields),
            )
        )

    def resolve_service_pk(reference):
        key = (reference["intent_source"], reference["catalog_namespace"], reference["catalog_metadata_name"], reference["service_type"])
        row = service_rows.get(key)
        if row is not None:
            return row["pk"], True
        return (None, True) if key in planned_service_keys else (None, False)

    placement_rows = {}
    for row in DesiredServicePlacement.objects.values(
        "pk", "desired_service__intent_source__slug", "desired_service__catalog_namespace",
        "desired_service__catalog_metadata_name", "desired_service__service_type", "instance_name",
        "desired_node_id", "desired_endpoint_id", "desired_state", "instance_role",
        "deployment_profile", "config_schema_version", "config", "assignment_source", "reason",
    ):
        key = (
            (
                row["desired_service__intent_source__slug"],
                row["desired_service__catalog_namespace"],
                row["desired_service__catalog_metadata_name"],
                row["desired_service__service_type"],
            ),
            row["instance_name"],
        )
        placement_rows[key] = row

    placement_field_names = (
        "desired_node_id", "desired_endpoint_id", "desired_state", "instance_role",
        "deployment_profile", "config_schema_version", "config", "assignment_source", "reason",
    )

    for placement in load_result.desired_service_placements:
        identity = {"desired_service": placement.desired_service, "instance_name": placement.instance_name}
        service_pk, service_resolved = resolve_service_pk(placement.desired_service)
        node_pk, node_resolved = resolve_node_pk(placement.desired_node)
        endpoint_pk, endpoint_resolved = resolve_endpoint_pk(placement.desired_node, placement.desired_endpoint)
        if not service_resolved:
            planned.append(unresolved_reference("DesiredServicePlacement", "desired_service_placements", identity, "unresolved desired_service reference"))
            continue
        if not node_resolved:
            planned.append(unresolved_reference("DesiredServicePlacement", "desired_service_placements", identity, f"unknown desired_node slug: {placement.desired_node}"))
            continue
        if not endpoint_resolved:
            planned.append(unresolved_reference("DesiredServicePlacement", "desired_service_placements", identity, "unresolved desired_endpoint reference"))
            continue
        create_fields = desired_service_placement_defaults(placement, desired_node_id=node_pk, desired_endpoint_id=endpoint_pk)
        service_key = (
            placement.desired_service["intent_source"], placement.desired_service["catalog_namespace"],
            placement.desired_service["catalog_metadata_name"], placement.desired_service["service_type"],
        )
        existing_row = placement_rows.get((service_key, placement.instance_name))
        planned.append(
            plan_upsert(
                model="DesiredServicePlacement",
                root="desired_service_placements",
                identity=identity,
                create_fields=_json_safe(create_fields),
                update_fields=_json_safe(create_fields),
                existing_matches=[_project(existing_row, dict.fromkeys(placement_field_names))] if existing_row else [],
            )
        )

    override_rows = {
        row["desired_node__slug"]: row
        for row in DesiredNodeOperationalOverride.objects.values(
            "pk", "desired_node__slug", "declared_host_os", "connection_path",
            "local_endpoint_id", "tailscale_endpoint_id", "ansible_port", "power_control", "is_laptop",
        )
    }
    override_field_names = (
        "declared_host_os", "connection_path", "local_endpoint_id", "tailscale_endpoint_id",
        "ansible_port", "power_control", "is_laptop",
    )

    for operational_override in load_result.desired_node_operational_overrides:
        identity = {"desired_node": operational_override.desired_node}
        node_pk, node_resolved = resolve_node_pk(operational_override.desired_node)
        local_pk, local_resolved = resolve_endpoint_pk(operational_override.desired_node, operational_override.local_endpoint)
        tailscale_pk, tailscale_resolved = resolve_endpoint_pk(operational_override.desired_node, operational_override.tailscale_endpoint)
        if not (node_resolved and local_resolved and tailscale_resolved):
            planned.append(
                unresolved_reference(
                    "DesiredNodeOperationalOverride", "desired_node_operational_overrides", identity,
                    f"unresolved reference on desired_node: {operational_override.desired_node}",
                )
            )
            continue
        create_fields = desired_node_operational_override_defaults(
            operational_override, local_endpoint_id=local_pk, tailscale_endpoint_id=tailscale_pk,
        )
        existing_row = override_rows.get(operational_override.desired_node)
        planned.append(
            plan_upsert(
                model="DesiredNodeOperationalOverride",
                root="desired_node_operational_overrides",
                identity=identity,
                create_fields=_json_safe(create_fields),
                update_fields=_json_safe(create_fields),
                existing_matches=[_project(existing_row, dict.fromkeys(override_field_names))] if existing_row else [],
            )
        )

    return planned


def _apply_import(load_result) -> None:
    """Apply an already-plan-validated document inside the caller's `transaction.atomic()`.

    Only called when `_plan_import()` reported zero conflicts, so every reference below is
    expected to resolve; a `require_unique_reference`/`DoesNotExist`/`full_clean()` failure here
    is a genuine precondition-changed-since-plan race, and propagates to abort and roll back the
    whole transaction (plan Section 5.2 items 6-7).
    """

    source_by_key = _intent_source_lookup()
    for source in load_result.intent_sources:
        create_fields = intent_source_defaults(source)
        if source.source_type == "git_repository":
            identity = {"url": source.url}
        else:
            identity = {"slug": create_fields["slug"]}
        _validated_upsert_split(IntentSource, identity, create_fields, create_fields)

    source_by_key = _intent_source_lookup()
    for node in load_result.desired_nodes:
        intent_source = source_by_key.get(node.intent_source) if node.intent_source else None
        identity = desired_node_identity(node)
        intent_source_id = getattr(intent_source, "pk", None)
        _validated_upsert_split(
            DesiredNode,
            identity,
            desired_node_defaults(node, intent_source_id=intent_source_id),
            desired_node_update_fields(node, intent_source_id=intent_source_id),
        )

    for ip_range in load_result.desired_ip_ranges:
        identity = desired_ip_range_identity(ip_range)
        create_fields = desired_ip_range_defaults(ip_range)
        _validated_upsert_split(DesiredIPRange, identity, create_fields, create_fields)

    for endpoint in load_result.desired_endpoints:
        desired_node = _resolve_desired_node(endpoint.desired_node)
        identity = desired_endpoint_identity(endpoint, desired_node_id=desired_node.pk)
        create_fields = desired_endpoint_defaults(endpoint)
        _validated_upsert_split(DesiredEndpoint, identity, create_fields, create_fields)

    for platform in load_result.desired_compute_platforms:
        control_node = _resolve_desired_node(platform.control_node)
        identity = desired_compute_platform_identity(platform)
        create_fields = desired_compute_platform_defaults(platform, control_node_id=control_node.pk)
        _validated_upsert_split(DesiredComputePlatform, identity, create_fields, create_fields)

    for instance in load_result.desired_compute_instances:
        desired_node = _resolve_desired_node(instance.desired_node)
        platform_obj = _resolve_desired_compute_platform(instance.platform)
        identity = desired_compute_instance_identity(desired_node.pk)
        create_fields = desired_compute_instance_defaults(instance, platform_id=platform_obj.pk)
        _validated_upsert_split(DesiredComputeInstance, identity, create_fields, create_fields)

    for service in load_result.desired_services:
        intent_source = source_by_key.get(service.intent_source)
        if intent_source is None:
            raise ValueError(
                f"desired_services entry references unknown intent_source slug: {service.intent_source}."
            )
        identity = desired_service_entry_identity(service, intent_source.pk)
        _validated_upsert_split(
            DesiredService,
            identity,
            desired_service_entry_defaults(service),
            desired_service_entry_update_fields(service),
            locked_fields=desired_service_entry_locked_fields(service),
        )

    for placement in load_result.desired_service_placements:
        desired_service = _resolve_desired_service(placement.desired_service)
        desired_node = _resolve_desired_node(placement.desired_node)
        desired_endpoint = _resolve_desired_endpoint(desired_node, placement.desired_endpoint, required=False)
        identity = desired_service_placement_identity(placement, desired_service.pk)
        create_fields = desired_service_placement_defaults(
            placement,
            desired_node_id=desired_node.pk,
            desired_endpoint_id=getattr(desired_endpoint, "pk", None),
        )
        _validated_upsert_split(DesiredServicePlacement, identity, create_fields, create_fields)

    for operational_override in load_result.desired_node_operational_overrides:
        desired_node = _resolve_desired_node(operational_override.desired_node)
        local_endpoint = _resolve_desired_endpoint(desired_node, operational_override.local_endpoint, required=False)
        tailscale_endpoint = _resolve_desired_endpoint(desired_node, operational_override.tailscale_endpoint, required=False)
        identity = desired_node_operational_override_identity(operational_override, desired_node.pk)
        create_fields = desired_node_operational_override_defaults(
            operational_override,
            local_endpoint_id=getattr(local_endpoint, "pk", None),
            tailscale_endpoint_id=getattr(tailscale_endpoint, "pk", None),
        )
        _validated_upsert_split(DesiredNodeOperationalOverride, identity, create_fields, create_fields)


def _confirm_import(load_result) -> list[dict]:
    """Refetch every planned identity post-commit and confirm the committed YAML-owned values
    (plan Section 5.2 item 9). Returns a list of mismatch dicts; empty means fully confirmed."""

    mismatches: list[dict] = []

    for node in load_result.desired_nodes:
        try:
            obj = DesiredNode.objects.get(slug=node.slug)
        except DesiredNode.DoesNotExist:
            mismatches.append({"model": "DesiredNode", "identity": {"slug": node.slug}, "reason": "not_found"})
            continue
        expected = desired_node_update_fields(node)
        for key, value in expected.items():
            if getattr(obj, key) != value:
                mismatches.append(
                    {
                        "model": "DesiredNode",
                        "identity": {"slug": node.slug},
                        "field": key,
                        "expected": _json_safe(value),
                        "actual": _json_safe(getattr(obj, key)),
                    }
                )

    for service in load_result.desired_services:
        intent_source = IntentSource.objects.filter(slug=service.intent_source).first()
        if intent_source is None:
            continue
        try:
            obj = DesiredService.objects.get(
                intent_source=intent_source,
                catalog_namespace=service.catalog_namespace,
                catalog_metadata_name=service.catalog_metadata_name,
                service_type=service.service_type,
            )
        except DesiredService.DoesNotExist:
            mismatches.append(
                {
                    "model": "DesiredService",
                    "identity": desired_service_entry_identity(service, intent_source.pk),
                    "reason": "not_found",
                }
            )
            continue
        expected = desired_service_entry_update_fields(service)
        for key, value in expected.items():
            if getattr(obj, key) != value:
                mismatches.append(
                    {
                        "model": "DesiredService",
                        "identity": desired_service_entry_identity(service, intent_source.pk),
                        "field": key,
                        "expected": _json_safe(value),
                        "actual": _json_safe(getattr(obj, key)),
                    }
                )

    return mismatches


def _validated_upsert_split(model, identity: dict, create_fields: dict, update_fields: dict, *, locked_fields: dict | None = None):
    """Create-or-update one row, writing only `update_fields` on an existing row.

    Raises if `locked_fields` disagrees with the stored value on an existing row -- this should
    never trigger because `_plan_import()` already reported that case as a `conflict` and the
    caller refuses to reach `_apply_import()` when any conflict exists; it exists as a
    defense-in-depth precondition-revalidation guard, not the primary safety mechanism.
    """

    queryset = model.objects.filter(**identity)
    match_count = queryset.count()
    if match_count > 1:
        require_unique_reference(model.__name__, match_count)
    if match_count == 0:
        obj = model(**identity)
        for key, value in create_fields.items():
            setattr(obj, key, value)
        obj.full_clean()
        obj.save()
        return obj

    obj = queryset.first()
    for key, value in (locked_fields or {}).items():
        if getattr(obj, key) != value:
            raise ValueError(f"{model.__name__}.{key} is not YAML-updatable on an existing row.")
    if all(getattr(obj, key) == value for key, value in update_fields.items()):
        return obj
    for key, value in update_fields.items():
        setattr(obj, key, value)
    obj.full_clean()
    obj.save()
    return obj


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
