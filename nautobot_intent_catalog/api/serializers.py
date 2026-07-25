"""REST API serializers for the Nautobot Intent Catalog App."""

from nautobot.apps.api import NautobotModelSerializer
from rest_framework import serializers

from ..models import AlignmentReview, BrainDumpDocument, DesiredEndpoint, DesiredNode, DesiredService, IntentSource


class BrainDumpDocumentSerializer(NautobotModelSerializer):
    """Serializer for Braindump documents.

    ``title``/``body`` disable DRF's default ``trim_whitespace`` so accepted prose is
    preserved byte-for-byte (the model's ``clean()``, run via ``ValidatedModelSerializer``,
    still rejects whitespace-only input). ``authorship`` has no serializer default, so it is
    required on create; a ``PATCH`` may still omit an unchanged value, per DRF's normal
    partial-update semantics.
    """

    title = serializers.CharField(max_length=255, trim_whitespace=False)
    body = serializers.CharField(trim_whitespace=False)
    authorship = serializers.ChoiceField(choices=BrainDumpDocument.AUTHORSHIP_CHOICES)

    class Meta:
        model = BrainDumpDocument
        fields = "__all__"


class AlignmentReviewSerializer(NautobotModelSerializer):
    """Serializer for one Braindump's current Alignment Review.

    ``braindump`` is a plain UUID primary-key relation, not a nested write.
    ``summary`` disables ``trim_whitespace`` for the same byte-for-byte reason as
    ``BrainDumpDocumentSerializer``. The one-review-per-Braindump uniqueness is enforced by
    the model's ``OneToOneField`` and surfaces as DRF's normal unique-together validation
    error on a duplicate create.
    """

    braindump = serializers.PrimaryKeyRelatedField(queryset=BrainDumpDocument.objects.all())
    summary = serializers.CharField(trim_whitespace=False)

    class Meta:
        model = AlignmentReview
        fields = "__all__"


class DesiredNodeSerializer(NautobotModelSerializer):
    """Serializer for desired node intent."""

    realized_device_source = serializers.ChoiceField(
        choices=("derived", "override"), required=False, allow_null=True
    )

    class Meta:
        model = DesiredNode
        fields = "__all__"

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


class DesiredServiceSerializer(NautobotModelSerializer):
    """Serializer for desired service intent.

    ``intent_source`` is declared as a plain ID-based related field rather than
    left to ``fields = "__all__"``'s default hyperlink, which tries to resolve
    a non-existent ``intentsource-detail`` route (no IntentSource viewset is
    registered -- see ``api/urls.py``) and breaks every GET/list/PATCH once a
    service has a non-null ``intent_source``. ``analysis_provenance`` and
    ``last_analyzed_at`` are Job-derived and read-only; ``reconciliation_status``
    and ``reconciliation_checked_at`` stay writable because nctl dashboard is
    their intentional sole writer.
    """

    intent_source = serializers.PrimaryKeyRelatedField(queryset=IntentSource.objects.all())

    class Meta:
        model = DesiredService
        fields = "__all__"
        read_only_fields = ("analysis_provenance", "last_analyzed_at")


class DesiredEndpointSerializer(NautobotModelSerializer):
    """Serializer for desired endpoint intent."""

    dns_name_source = serializers.ChoiceField(
        choices=("derived", "intent"), required=False, allow_null=True
    )
    mdns_name_source = serializers.ChoiceField(
        choices=("derived", "intent"), required=False, allow_null=True
    )
    realized_ip_address_source = serializers.ChoiceField(
        choices=("derived", "override"), required=False, allow_null=True
    )

    class Meta:
        model = DesiredEndpoint
        fields = "__all__"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        for value_name in ("dns_name", "mdns_name", "realized_ip_address"):
            source_name = f"{value_name}_source"
            if value_name in attrs:
                if attrs[value_name] is None or attrs[value_name] == "":
                    attrs[source_name] = None
                elif source_name not in attrs:
                    attrs[source_name] = "override" if value_name == "realized_ip_address" else "intent"
            value = attrs.get(value_name, getattr(self.instance, value_name, None))
            source = attrs.get(source_name, getattr(self.instance, source_name, None))
            if bool(value) != bool(source):
                raise serializers.ValidationError(
                    {source_name: f"Source must be set exactly when {value_name} is set."}
                )
        return attrs
