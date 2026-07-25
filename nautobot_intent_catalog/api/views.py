"""REST API views for the Nautobot Intent Catalog App."""

from django.http import HttpResponseNotAllowed
from nautobot.apps.api import NautobotModelViewSet

from ..filters import (
    AlignmentReviewFilterSet,
    BrainDumpDocumentFilterSet,
    DesiredNodeFilterSet,
)
from ..models import (
    AlignmentReview,
    BrainDumpDocument,
    DesiredNode,
)
from .serializers import (
    AlignmentReviewSerializer,
    BrainDumpDocumentSerializer,
    DesiredNodeSerializer,
)


class BrainDumpDocumentViewSet(NautobotModelViewSet):
    """Read/write API endpoint for Braindump documents.

    Allowed methods: GET, POST, detail PATCH, detail DELETE.
    Disallowed: PUT, bulk PATCH, bulk DELETE.
    """

    queryset = BrainDumpDocument.objects.select_related("alignment_review")
    serializer_class = BrainDumpDocumentSerializer
    filterset_class = BrainDumpDocumentFilterSet
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def update(self, request, *args, **kwargs):
        if not kwargs.get("partial", False):
            return HttpResponseNotAllowed(["GET", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS"])
        return super().update(request, *args, **kwargs)

    def bulk_update(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS"])

    def bulk_destroy(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS"])


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

    def bulk_destroy(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "PATCH", "HEAD", "OPTIONS"])
