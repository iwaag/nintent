"""REST API serializers for the Nautobot Intent Catalog App."""

from nautobot.apps.api import NautobotModelSerializer
from rest_framework import serializers

from ..models import DesiredEndpoint, DesiredNode, DesiredService


class DesiredNodeSerializer(NautobotModelSerializer):
    """Serializer for desired node intent."""

    realized_device_source = serializers.ChoiceField(
        choices=("derived", "override"), required=False, allow_null=True
    )
    realized_vm_source = serializers.ChoiceField(
        choices=("derived", "override"), required=False, allow_null=True
    )

    class Meta:
        model = DesiredNode
        fields = "__all__"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        for relation_name in ("realized_device", "realized_vm"):
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
    """Serializer for desired service intent."""

    class Meta:
        model = DesiredService
        fields = "__all__"


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
