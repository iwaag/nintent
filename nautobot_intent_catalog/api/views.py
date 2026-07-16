"""REST API views for the Nautobot Intent Catalog App."""

from nautobot.apps.api import NautobotModelViewSet

from ..filters import DesiredEndpointFilterSet, DesiredNodeFilterSet, DesiredServiceFilterSet
from ..models import DesiredEndpoint, DesiredNode, DesiredService
from .serializers import DesiredEndpointSerializer, DesiredNodeSerializer, DesiredServiceSerializer


class DesiredNodeViewSet(NautobotModelViewSet):
    """Read/write API endpoint for desired nodes."""

    queryset = DesiredNode.objects.all()
    serializer_class = DesiredNodeSerializer
    filterset_class = DesiredNodeFilterSet


class DesiredServiceViewSet(NautobotModelViewSet):
    """Read/write API endpoint for desired services."""

    queryset = DesiredService.objects.all()
    serializer_class = DesiredServiceSerializer
    filterset_class = DesiredServiceFilterSet


class DesiredEndpointViewSet(NautobotModelViewSet):
    """Read/write API endpoint for desired endpoints."""

    queryset = DesiredEndpoint.objects.all()
    serializer_class = DesiredEndpointSerializer
    filterset_class = DesiredEndpointFilterSet
