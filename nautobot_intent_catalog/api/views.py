"""REST API views for the Nautobot Intent Catalog App."""

from django.http import HttpResponseNotAllowed
from drf_spectacular.utils import extend_schema
from nautobot.apps.api import NautobotModelViewSet
from nautobot.core.api.serializers import BulkOperationSerializer

from ..filters import (
    AlignmentReviewFilterSet,
    BrainDumpDocumentFilterSet,
    DesiredNodeFilterSet,
    DesiredComputeInstanceFilterSet,
    DesiredComputePlatformFilterSet,
)
from ..models import (
    AlignmentReview,
    BrainDumpDocument,
    DesiredNode,
    DesiredComputeInstance,
    DesiredComputePlatform,
)
from .serializers import (
    AlignmentReviewSerializer,
    BrainDumpDocumentSerializer,
    DesiredNodeSerializer,
    DesiredComputeInstanceSerializer,
    DesiredComputePlatformSerializer,
)


class BrainDumpDocumentViewSet(NautobotModelViewSet):
    """Immutable Braindump API endpoint: read existing statements or create a new one."""

    queryset = BrainDumpDocument.objects.select_related("alignment_review")
    serializer_class = BrainDumpDocumentSerializer
    filterset_class = BrainDumpDocumentFilterSet
    http_method_names = ["get", "post", "head", "options"]


class AlignmentReviewViewSet(NautobotModelViewSet):
    """Read/write API endpoint for Alignment Reviews.

    Allowed methods: GET, POST, detail PATCH, detail DELETE.
    Disallowed: PUT, bulk PATCH, bulk DELETE.
    """

    queryset = AlignmentReview.objects.select_related("braindump")
    serializer_class = AlignmentReviewSerializer
    filterset_class = AlignmentReviewFilterSet
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def update(self, request, *args, **kwargs):
        if not kwargs.get("partial", False):
            return HttpResponseNotAllowed(["GET", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS"])
        return super().update(request, *args, **kwargs)

    def bulk_update(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS"])

    @extend_schema(request=BulkOperationSerializer(many=True))
    def bulk_destroy(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS"])


class DesiredNodeViewSet(NautobotModelViewSet):
    """API endpoint for desired nodes.

    Allowed methods: GET, detail PATCH.
    Disallowed: POST, PUT, DELETE, bulk PATCH, bulk DELETE.
    """

    queryset = DesiredNode.objects.all()
    serializer_class = DesiredNodeSerializer
    filterset_class = DesiredNodeFilterSet
    http_method_names = ["get", "patch", "head", "options"]

    def create(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "PATCH", "HEAD", "OPTIONS"])

    def update(self, request, *args, **kwargs):
        if not kwargs.get("partial", False):
            return HttpResponseNotAllowed(["GET", "PATCH", "HEAD", "OPTIONS"])
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "PATCH", "HEAD", "OPTIONS"])

    def bulk_update(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "PATCH", "HEAD", "OPTIONS"])

    @extend_schema(request=BulkOperationSerializer(many=True))
    def bulk_destroy(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "PATCH", "HEAD", "OPTIONS"])


class _ComputeLinkViewSet(NautobotModelViewSet):
    """GET/detail-PATCH only; compute creation is intentionally not a REST API."""

    http_method_names = ["get", "patch", "head", "options"]

    def create(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "PATCH", "HEAD", "OPTIONS"])

    def update(self, request, *args, **kwargs):
        if not kwargs.get("partial", False):
            return HttpResponseNotAllowed(["GET", "PATCH", "HEAD", "OPTIONS"])
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "PATCH", "HEAD", "OPTIONS"])

    def bulk_update(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "PATCH", "HEAD", "OPTIONS"])

    @extend_schema(request=BulkOperationSerializer(many=True))
    def bulk_destroy(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "PATCH", "HEAD", "OPTIONS"])


class DesiredComputePlatformViewSet(_ComputeLinkViewSet):
    queryset = DesiredComputePlatform.objects.all()
    serializer_class = DesiredComputePlatformSerializer
    filterset_class = DesiredComputePlatformFilterSet


class DesiredComputeInstanceViewSet(_ComputeLinkViewSet):
    queryset = DesiredComputeInstance.objects.select_related("platform", "realized_vm")
    serializer_class = DesiredComputeInstanceSerializer
    filterset_class = DesiredComputeInstanceFilterSet
