"""REST API serializers for the Nautobot Intent Catalog App."""

from nautobot.apps.api import NautobotModelSerializer
from rest_framework import serializers

from ..models import (
    AlignmentReview,
    BrainDumpDocument,
    DesiredComputeInstance,
    DesiredComputePlatform,
    DesiredNode,
)


def _check_allowed_mutation_keys(data: dict, allowed_keys: set[str], operation: str = "mutation") -> None:
    if not isinstance(data, dict):
        return
    unallowed = set(data.keys()) - allowed_keys
    if unallowed:
        errors = {key: f"Field '{key}' is not writable for {operation}." for key in sorted(unallowed)}
        raise serializers.ValidationError(errors)


class BrainDumpDocumentSerializer(NautobotModelSerializer):
    """Serializer for Braindump documents."""

    title = serializers.CharField(max_length=255, trim_whitespace=False)
    body = serializers.CharField(trim_whitespace=False)
    authorship = serializers.ChoiceField(choices=BrainDumpDocument.AUTHORSHIP_CHOICES)

    class Meta:
        model = BrainDumpDocument
        fields = ("id", "title", "body", "authorship", "status", "created", "last_updated")
        read_only_fields = ("id", "status", "created", "last_updated")

    def to_internal_value(self, data):
        allowed = {"title", "body", "authorship"}
        _check_allowed_mutation_keys(data, allowed, "BrainDumpDocument mutation")
        return super().to_internal_value(data)


class BrainDumpSupersedeSerializer(serializers.Serializer):
    """Request shape for the sole Braindump status transition."""

    old_ids = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=False, write_only=True
    )
    title = serializers.CharField(max_length=255, trim_whitespace=False)
    body = serializers.CharField(trim_whitespace=False)
    authorship = serializers.ChoiceField(choices=BrainDumpDocument.AUTHORSHIP_CHOICES)

    def validate_old_ids(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Each old Braindump ID must be supplied once.")
        return value

    def validate(self, attrs):
        for field_name in ("title", "body"):
            if not attrs[field_name].strip():
                raise serializers.ValidationError({field_name: "This field must not be blank."})
        return attrs


class AlignmentReviewSerializer(NautobotModelSerializer):
    """Serializer for one Braindump's current Alignment Review."""

    braindump = serializers.PrimaryKeyRelatedField(queryset=BrainDumpDocument.objects.all())
    summary = serializers.CharField(trim_whitespace=False)

    class Meta:
        model = AlignmentReview
        fields = ("id", "braindump", "summary", "created", "last_updated")
        read_only_fields = ("id", "created", "last_updated")

    def to_internal_value(self, data):
        if self.instance is None:
            allowed = {"braindump", "summary"}
        else:
            allowed = {"summary"}
        _check_allowed_mutation_keys(data, allowed, "AlignmentReview mutation")
        return super().to_internal_value(data)


class DesiredNodeSerializer(NautobotModelSerializer):
    """Serializer for desired node intent.
    
    Only lifecycle, realized_device, and realized_device_source are writable.
    All other fields are read-only.
    """

    realized_device_source = serializers.ChoiceField(
        choices=("derived", "override"), required=False, allow_null=True
    )

    class Meta:
        model = DesiredNode
        fields = (
            "id",
            "name",
            "slug",
            "node_type",
            "lifecycle",
            "role",
            "realized_device",
            "realized_device_source",
            "created",
            "last_updated",
        )
        read_only_fields = ("id", "name", "slug", "node_type", "role", "created", "last_updated")

    def to_internal_value(self, data):
        allowed = {"lifecycle", "realized_device", "realized_device_source"}
        _check_allowed_mutation_keys(data, allowed, "DesiredNode mutation")
        return super().to_internal_value(data)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        for relation_name in ("realized_device",):
            if relation_name in attrs:
                source_name = f"{relation_name}_source"
                if attrs[relation_name] is None:
                    attrs[source_name] = None
                elif source_name not in attrs:
                    attrs[source_name] = "override"
            relation = attrs.get(relation_name, getattr(self.instance, relation_name, None))
            source = attrs.get(
                f"{relation_name}_source",
                getattr(self.instance, f"{relation_name}_source", None),
            )
            if bool(relation) != bool(source):
                raise serializers.ValidationError(
                    {f"{relation_name}_source": f"Source must be set exactly when {relation_name} is set."}
                )
        return attrs


class _ComputeLinkSerializer(NautobotModelSerializer):
    """Narrow ledger-link surface shared by the two compute rows."""

    link_field = ""

    def to_internal_value(self, data):
        source_field = f"{self.link_field}_source"
        _check_allowed_mutation_keys(data, {self.link_field, source_field}, f"{self.Meta.model.__name__} mutation")
        return super().to_internal_value(data)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        source_field = f"{self.link_field}_source"
        if self.link_field in attrs:
            if attrs[self.link_field] is None:
                attrs[source_field] = None
            elif source_field not in attrs:
                attrs[source_field] = "override"
        relation = attrs.get(self.link_field, getattr(self.instance, self.link_field, None))
        source = attrs.get(source_field, getattr(self.instance, source_field, None))
        if bool(relation) != bool(source):
            raise serializers.ValidationError({source_field: f"Source must be set exactly when {self.link_field} is set."})
        return attrs


class DesiredComputePlatformSerializer(_ComputeLinkSerializer):
    link_field = "realized_cluster"
    realized_cluster_source = serializers.ChoiceField(choices=("derived", "override"), required=False, allow_null=True)

    class Meta:
        model = DesiredComputePlatform
        fields = ("id", "name", "slug", "provider_type", "lifecycle", "control_node", "config", "realized_cluster", "realized_cluster_source", "created", "last_updated")
        read_only_fields = ("id", "name", "slug", "provider_type", "lifecycle", "control_node", "config", "created", "last_updated")


class DesiredComputeInstanceSerializer(_ComputeLinkSerializer):
    link_field = "realized_vm"
    realized_vm_source = serializers.ChoiceField(choices=("derived", "override"), required=False, allow_null=True)

    class Meta:
        model = DesiredComputeInstance
        fields = ("id", "desired_node", "platform", "instance_kind", "desired_power_state", "vcpus", "memory_mb", "root_disk_gb", "config", "realized_vm", "realized_vm_source", "created", "last_updated")
        read_only_fields = ("id", "desired_node", "platform", "instance_kind", "desired_power_state", "vcpus", "memory_mb", "root_disk_gb", "config", "created", "last_updated")
