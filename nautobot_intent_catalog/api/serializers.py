"""REST API serializers for the Nautobot Intent Catalog App."""

from nautobot.apps.api import NautobotModelSerializer
from rest_framework import serializers

from ..models import (
    AlignmentReview,
    BrainDumpDocument,
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
        fields = ("id", "title", "body", "authorship", "created", "last_updated")
        read_only_fields = ("id", "created", "last_updated")

    def to_internal_value(self, data):
        allowed = {"title", "body", "authorship"}
        _check_allowed_mutation_keys(data, allowed, "BrainDumpDocument mutation")
        return super().to_internal_value(data)


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
