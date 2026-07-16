"""REST API serializers for the Nautobot Intent Catalog App."""

from nautobot.apps.api import NautobotModelSerializer

from ..models import DesiredEndpoint, DesiredNode, DesiredService


class DesiredNodeSerializer(NautobotModelSerializer):
    """Serializer for desired node intent."""

    class Meta:
        model = DesiredNode
        fields = "__all__"


class DesiredServiceSerializer(NautobotModelSerializer):
    """Serializer for desired service intent."""

    class Meta:
        model = DesiredService
        fields = "__all__"


class DesiredEndpointSerializer(NautobotModelSerializer):
    """Serializer for desired endpoint intent."""

    class Meta:
        model = DesiredEndpoint
        fields = "__all__"
