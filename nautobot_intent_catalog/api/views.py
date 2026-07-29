"""REST API views for the Nautobot Intent Catalog App."""

from django.db import transaction
from django.http import HttpResponseNotAllowed
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
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
    BrainDumpSupersedeSerializer,
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

    @action(detail=False, methods=["post"], url_path="supersede")
    def supersede(self, request, *args, **kwargs):
        """Atomically create one active replacement and supersede exact active rows."""
        serializer = BrainDumpSupersedeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        old_ids = values["old_ids"]

        with transaction.atomic():
            old_rows = list(
                BrainDumpDocument.objects.select_for_update().filter(pk__in=old_ids)
            )
            found_ids = {row.pk for row in old_rows}
            missing_ids = [str(old_id) for old_id in old_ids if old_id not in found_ids]
            if missing_ids:
                return Response(
                    {"old_ids": [f"Unknown Braindump IDs: {', '.join(missing_ids)}."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            inactive_ids = [str(row.pk) for row in old_rows if row.status != BrainDumpDocument.STATUS_ACTIVE]
            if inactive_ids:
                return Response(
                    {"old_ids": [f"Braindumps are not active: {', '.join(inactive_ids)}."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            replacement = BrainDumpDocument.objects.create(
                title=values["title"], body=values["body"], authorship=values["authorship"]
            )
            BrainDumpDocument.objects.filter(pk__in=old_ids).update(
                status=BrainDumpDocument.STATUS_SUPERSEDED
            )

        return Response(
            {
                "braindump": BrainDumpDocumentSerializer(replacement, context={"request": request}).data,
                "superseded_ids": [str(old_id) for old_id in old_ids],
            },
            status=status.HTTP_201_CREATED,
        )


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
