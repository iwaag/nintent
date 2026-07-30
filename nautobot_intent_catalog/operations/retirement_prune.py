"""Server-side, bounded collection of Actual records for retired-LXC pruning.

The client supplies the three immutable roots it observed.  This module resolves
them again through the Desired links before asking Django's deletion Collector
for the real cascade; it never searches by guest name, address, or VMID.
"""
from __future__ import annotations

from typing import Any

from django.db.models.deletion import Collector, ProtectedError, RestrictedError


class RetirementPruneError(ValueError):
    pass


def _roots(payload: dict[str, Any]):
    from nautobot.dcim.models import Device
    from nautobot.virtualization.models import Cluster, VirtualMachine
    from ..models import DesiredComputeInstance, DesiredNode

    required = ("desired_node_id", "device_id", "virtual_machine_id")
    if set(payload) != set(required) or not isinstance(payload["desired_node_id"], str) or not payload["desired_node_id"]:
        raise RetirementPruneError("payload must contain desired_node_id and optional device_id/virtual_machine_id roots")
    if any(payload[name] is not None and (not isinstance(payload[name], str) or not payload[name]) for name in ("device_id", "virtual_machine_id")):
        raise RetirementPruneError("Actual root ids must be non-empty strings or null")
    node = DesiredNode.objects.filter(pk=payload["desired_node_id"]).first()
    instances = list(DesiredComputeInstance.objects.filter(desired_node=node)) if node else []
    instance = instances[0] if len(instances) == 1 else None
    device = Device.objects.filter(pk=payload["device_id"]).first() if payload["device_id"] else None
    vm = VirtualMachine.objects.select_related("cluster").filter(pk=payload["virtual_machine_id"]).first() if payload["virtual_machine_id"] else None
    if not node or not instance:
        raise RetirementPruneError("selected Desired retirement records no longer exist")
    if node.lifecycle != "retired" or instance.desired_presence != "absent":
        raise RetirementPruneError("selected Desired records are not retired with desired_presence=absent")
    if device and str(node.realized_device_id) != str(device.pk):
        raise RetirementPruneError("selected Device no longer matches the Desired link")
    if vm and str(instance.realized_vm_id) != str(vm.pk):
        raise RetirementPruneError("selected VirtualMachine no longer matches the Desired link")
    if not device and node.realized_device_id and Device.objects.filter(pk=node.realized_device_id).exists():
        raise RetirementPruneError("linked Device exists but was omitted from the Actual cleanup plan")
    if not vm and instance.realized_vm_id and VirtualMachine.objects.filter(pk=instance.realized_vm_id).exists():
        raise RetirementPruneError("linked VirtualMachine exists but was omitted from the Actual cleanup plan")
    if not device and not vm:
        raise RetirementPruneError("no surviving Actual root is available for cleanup")
    vm_facts = vm._custom_field_data or {} if vm else {}
    cluster_facts = (vm.cluster._custom_field_data or {}) if vm and vm.cluster else {}
    if vm and (vm_facts.get("proxmox_presence") != "absent" or cluster_facts.get("proxmox_observation_state") != "complete"):
        raise RetirementPruneError("selected VM is not confirmed absent by a complete Proxmox observation")
    return node, instance, device, vm


def _collector(device, vm) -> Collector:
    from nautobot.dcim.models import Interface
    from nautobot.ipam.models import IPAddress
    from nautobot.virtualization.models import VMInterface

    root = device or vm
    collector = Collector(using=root._state.db)
    # ``Collector.collect()`` treats a list as a homogeneous model sequence;
    # Device and VirtualMachine must therefore be added as two roots.
    if device:
        collector.collect([device])
    if vm:
        collector.collect([vm])
    selected_interfaces = {str(item.pk) for item in collector.data.get(Interface, set())}
    selected_vm_interfaces = {str(item.pk) for item in collector.data.get(VMInterface, set())}
    candidates = IPAddress.objects.filter(
        vm_interfaces__pk__in=selected_vm_interfaces
    ) | IPAddress.objects.filter(interfaces__pk__in=selected_interfaces)
    for address in candidates.distinct():
        interface_ids = {str(pk) for pk in address.interfaces.values_list("pk", flat=True)}
        vm_interface_ids = {str(pk) for pk in address.vm_interfaces.values_list("pk", flat=True)}
        # Only delete an IP if every attachment belongs to this exact collector
        # set. Shared IPs stay outside the prune set.
        if interface_ids <= selected_interfaces and vm_interface_ids <= selected_vm_interfaces:
            collector.collect([address])
    return collector


def _summary(collector: Collector) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for model, instances in collector.data.items():
        label = f"{model._meta.app_label}.{model._meta.model_name}"
        records.extend({"model": label, "id": str(instance.pk)} for instance in instances)
    # Some relations are safe fast deletes and do not appear in ``data``.
    for queryset in collector.fast_deletes:
        model = queryset.model
        label = f"{model._meta.app_label}.{model._meta.model_name}"
        records.extend({"model": label, "id": str(pk)} for pk in queryset.values_list("pk", flat=True))
    return sorted(records, key=lambda item: (item["model"], item["id"]))


def plan(payload: dict[str, Any]) -> dict[str, Any]:
    node, instance, device, vm = _roots(payload)
    try:
        records = _summary(_collector(device, vm))
    except (ProtectedError, RestrictedError) as exc:
        raise RetirementPruneError(f"Actual deletion is blocked: {exc}") from exc
    return {
        "desired": {"node_id": str(node.pk), "compute_instance_id": str(instance.pk)},
        "actual_roots": {"device_id": str(device.pk) if device else None, "virtual_machine_id": str(vm.pk) if vm else None},
        "records": records,
    }


def delete(payload: dict[str, Any]) -> dict[str, Any]:
    expected = payload.get("records")
    roots_payload = {name: payload.get(name) for name in ("desired_node_id", "device_id", "virtual_machine_id")}
    if not isinstance(expected, list):
        raise RetirementPruneError("payload records must be the reviewed collector summary")
    node, instance, device, vm = _roots(roots_payload)
    try:
        collector = _collector(device, vm)
        current = _summary(collector)
    except (ProtectedError, RestrictedError) as exc:
        raise RetirementPruneError(f"Actual deletion is blocked: {exc}") from exc
    if current != expected:
        raise RetirementPruneError("Actual dependency set changed since the reviewed plan")
    deleted, per_model = collector.delete()
    return {"desired": {"node_id": str(node.pk), "compute_instance_id": str(instance.pk)}, "deleted_count": deleted,
            "deleted_by_model": {str(key): value for key, value in per_model.items()}, "records": current}
