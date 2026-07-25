"""Reusable fixture factories for the eleven retained UI models (Interface Contract Phase 4 Step 1).

Guarded the same way as the models/views/tables it builds: importable during local Django-free
test discovery (the module-level names below simply won't exist), real factory functions only
defined when Nautobot/Django are present.

Every factory creates the minimal row that satisfies each model's own `clean()`/constraints, so
callers proving read-only route/table/permission behavior do not need to know
compute-topology/override validation details themselves. Compute-instance/platform/override
fixtures deliberately stay non-actionable (`lifecycle="planned"`) so they do not also need a
fully wired primary endpoint/realized-cluster/realized-VM chain just to pass `full_clean()`.
"""

from __future__ import annotations

import itertools

try:
    from nautobot_intent_catalog.models import (
        AlignmentReview,
        BrainDumpDocument,
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
except ImportError:  # pragma: no cover - Nautobot/Django are unavailable in local unit tests.
    pass
else:
    _counter = itertools.count(1)

    def _next(prefix: str) -> str:
        return f"{prefix}-{next(_counter)}"

    def make_intent_source(**overrides) -> IntentSource:
        slug = _next("src")
        defaults = {
            "name": slug,
            "slug": slug,
            "source_type": IntentSource.SOURCE_MANUAL,
            "enabled": True,
        }
        defaults.update(overrides)
        return IntentSource.objects.create(**defaults)

    def make_desired_node(**overrides) -> DesiredNode:
        slug = _next("node")
        defaults = {
            "name": slug,
            "slug": slug,
            "node_type": DesiredNode.NODE_TYPE_DEVICE,
            "lifecycle": DesiredNode.LIFECYCLE_ACTIVE,
        }
        defaults.update(overrides)
        node = DesiredNode(**defaults)
        node.full_clean()
        node.save()
        return node

    def make_desired_service(**overrides) -> DesiredService:
        slug = _next("svc")
        defaults = {
            "name": slug,
            "slug": slug,
            "display_name": slug,
            "service_type": DesiredService.SERVICE_TYPE_SERVICE,
            "lifecycle": DesiredService.LIFECYCLE_ACTIVE,
            "intent_source": overrides.pop("intent_source", None) or make_intent_source(),
            "catalog_metadata_name": slug,
        }
        defaults.update(overrides)
        service = DesiredService(**defaults)
        service.full_clean()
        service.save()
        return service

    def make_desired_dependency(**overrides) -> DesiredDependency:
        name = _next("dep")
        defaults = {
            "source_service": overrides.pop("source_service", None) or make_desired_service(),
            "dependency_kind": "service_ref",
            "namespace": "default",
            "name": name,
            "raw_ref": name,
            "dependency_type": "internal",
            "resolution_status": DesiredDependency.RESOLUTION_UNRESOLVED,
        }
        defaults.update(overrides)
        dependency = DesiredDependency(**defaults)
        dependency.full_clean()
        dependency.save()
        return dependency

    def make_desired_endpoint(**overrides) -> DesiredEndpoint:
        name = _next("ep")
        defaults = {
            "desired_node": overrides.pop("desired_node", None) or make_desired_node(),
            "name": name,
            "endpoint_type": DesiredEndpoint.ENDPOINT_TYPE_PRIMARY,
            "ip_policy": DesiredEndpoint.IP_POLICY_EXTERNAL,
        }
        defaults.update(overrides)
        endpoint = DesiredEndpoint(**defaults)
        endpoint.full_clean()
        endpoint.save()
        return endpoint

    def make_desired_compute_platform(**overrides) -> DesiredComputePlatform:
        slug = _next("platform")
        defaults = {
            "name": slug,
            "slug": slug,
            "provider_type": DesiredComputePlatform.PROVIDER_TYPE_PROXMOX,
            "lifecycle": DesiredComputePlatform.LIFECYCLE_PLANNED,
            "control_node": overrides.pop("control_node", None) or make_desired_node(),
            "config": {},
        }
        defaults.update(overrides)
        platform = DesiredComputePlatform(**defaults)
        platform.full_clean()
        platform.save()
        return platform

    def make_desired_compute_instance(**overrides) -> DesiredComputeInstance:
        defaults = {
            "desired_node": overrides.pop("desired_node", None) or make_desired_node(lifecycle="planned"),
            "platform": overrides.pop("platform", None) or make_desired_compute_platform(),
            "instance_kind": DesiredComputeInstance.INSTANCE_KIND_CONTAINER,
            "desired_power_state": DesiredComputeInstance.POWER_STATE_STOPPED,
            "vcpus": 1,
            "memory_mb": 512,
            "root_disk_gb": 8,
            "config": {"template": "local:vztmpl/example.tar.zst", "unprivileged": True},
        }
        defaults.update(overrides)
        instance = DesiredComputeInstance(**defaults)
        instance.full_clean()
        instance.save()
        return instance

    def make_desired_service_placement(**overrides) -> DesiredServicePlacement:
        name = _next("inst")
        defaults = {
            "desired_service": overrides.pop("desired_service", None) or make_desired_service(),
            "desired_node": overrides.pop("desired_node", None) or make_desired_node(),
            "instance_name": name,
            "desired_state": DesiredServicePlacement.STATE_ACTIVE,
            "deployment_profile": "default",
            "assignment_source": DesiredServicePlacement.SOURCE_MANUAL,
        }
        defaults.update(overrides)
        placement = DesiredServicePlacement(**defaults)
        placement.full_clean()
        placement.save()
        return placement

    def make_desired_node_operational_override(**overrides) -> DesiredNodeOperationalOverride:
        defaults = {
            "desired_node": overrides.pop("desired_node", None) or make_desired_node(),
            "is_laptop": True,
        }
        defaults.update(overrides)
        override = DesiredNodeOperationalOverride(**defaults)
        override.full_clean()
        override.save()
        return override

    def make_desired_ip_range(**overrides) -> DesiredIPRange:
        slug = _next("range")
        defaults = {
            "name": slug,
            "slug": slug,
            "start_address": "10.10.0.10",
            "end_address": "10.10.0.20",
            "range_policy": DesiredIPRange.RANGE_POLICY_STATIC_POOL,
            "lifecycle": DesiredIPRange.LIFECYCLE_ACTIVE,
        }
        defaults.update(overrides)
        ip_range = DesiredIPRange(**defaults)
        ip_range.full_clean()
        ip_range.save()
        return ip_range

    def make_braindump(**overrides) -> BrainDumpDocument:
        defaults = {
            "title": _next("Braindump"),
            "body": "Body text.",
            "authorship": BrainDumpDocument.AUTHORSHIP_USER_DIRECT,
        }
        defaults.update(overrides)
        return BrainDumpDocument.objects.create(**defaults)

    def make_alignment_review(**overrides) -> AlignmentReview:
        defaults = {
            "braindump": overrides.pop("braindump", None) or make_braindump(),
            "summary": "Reviewed.",
        }
        defaults.update(overrides)
        return AlignmentReview.objects.create(**defaults)
