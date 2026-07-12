"""REST API views for the Nautobot Intent Catalog App."""

from nautobot.apps.api import NautobotModelViewSet

from ..filters import DesiredEndpointFilterSet, DesiredNodeFilterSet
from ..models import DesiredEndpoint, DesiredNode
from .serializers import DesiredEndpointSerializer, DesiredNodeSerializer


class DesiredNodeViewSet(NautobotModelViewSet):
    """Read/write API endpoint for desired nodes."""

    queryset = DesiredNode.objects.all()
    serializer_class = DesiredNodeSerializer
    filterset_class = DesiredNodeFilterSet


class DesiredEndpointViewSet(NautobotModelViewSet):
    """Read/write API endpoint for desired endpoints."""

    queryset = DesiredEndpoint.objects.all()
    serializer_class = DesiredEndpointSerializer
    filterset_class = DesiredEndpointFilterSet
