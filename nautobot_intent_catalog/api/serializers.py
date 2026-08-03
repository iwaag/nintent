"""REST API serializers for the Nautobot Intent Catalog App."""

from nautobot.apps.api import NautobotModelSerializer
from rest_framework import serializers

from ..models import AlignmentReview, BrainDumpDocument, WorkflowEpisode
from ..workflow_episode_contract import WorkflowEpisodeContractError, validate_raw_data_shape


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
        fields = ("id", "title", "body", "authorship", "status", "completion_reason", "created", "last_updated")
        read_only_fields = ("id", "status", "completion_reason", "created", "last_updated")

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


class BrainDumpCompleteSerializer(serializers.Serializer):
    """Request shape for the direct active-to-completed status transition."""

    reason = serializers.CharField(trim_whitespace=False)

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("This field must not be blank.")
        return value


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


class WorkflowEpisodeSerializer(NautobotModelSerializer):
    """Serializer for workflow-improvement episodes. Status and raw_data namespaces are not
    writable here — status changes go through the transition actions, and each raw_data
    namespace is written through its own action (decision 5: never replace the whole raw_data).
    """

    title = serializers.CharField(max_length=255, trim_whitespace=False)

    class Meta:
        model = WorkflowEpisode
        fields = ("id", "title", "status", "raw_data", "created", "last_updated")
        read_only_fields = ("id", "status", "created", "last_updated")

    def to_internal_value(self, data):
        allowed = {"title", "raw_data"}
        _check_allowed_mutation_keys(data, allowed, "WorkflowEpisode mutation")
        return super().to_internal_value(data)

    def validate_raw_data(self, value):
        try:
            validate_raw_data_shape(value)
        except WorkflowEpisodeContractError as exc:
            raise serializers.ValidationError(str(exc))
        return value

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("This field must not be blank.")
        return value
