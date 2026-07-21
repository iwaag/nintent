"""REST API views for the Nautobot Intent Catalog App."""

from nautobot.apps.api import NautobotModelViewSet

from ..filters import (
    AlignmentReviewFilterSet,
    BrainDumpDocumentFilterSet,
    DesiredEndpointFilterSet,
    DesiredNodeFilterSet,
    DesiredServiceFilterSet,
)
from ..models import AlignmentReview, BrainDumpDocument, DesiredEndpoint, DesiredNode, DesiredService
from .serializers import (
    AlignmentReviewSerializer,
    BrainDumpDocumentSerializer,
    DesiredEndpointSerializer,
    DesiredNodeSerializer,
    DesiredServiceSerializer,
)


class BrainDumpDocumentViewSet(NautobotModelViewSet):
    """Read/write API endpoint for Braindump documents."""

    queryset = BrainDumpDocument.objects.select_related("alignment_review")
    serializer_class = BrainDumpDocumentSerializer
    filterset_class = BrainDumpDocumentFilterSet


class AlignmentReviewViewSet(NautobotModelViewSet):
    """Read/write API endpoint for Alignment Reviews."""

    queryset = AlignmentReview.objects.select_related("braindump")
    serializer_class = AlignmentReviewSerializer
    filterset_class = AlignmentReviewFilterSet


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
