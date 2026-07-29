"""REST API views for the Nautobot Intent Catalog App."""

import yaml

from django.db import transaction
from django.http import HttpResponseNotAllowed
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ParseError, PermissionDenied, ValidationError
from rest_framework.parsers import BaseParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from nautobot.apps.api import NautobotModelViewSet
from nautobot.core.api.serializers import BulkOperationSerializer

from .. import models
from ..batch import BatchValidationError, apply_batch, decode_batch, plan_batch
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


class _YAMLParser(BaseParser):
    """Parse one YAML media type into the same document shape as JSON."""

    def parse(self, stream, media_type=None, parser_context=None):
        try:
            document = yaml.safe_load(stream.read())
        except yaml.YAMLError as exc:
            raise ParseError(f"Malformed YAML: {exc}") from exc
        if not isinstance(document, dict):
            raise ParseError("YAML document must be an object")
        return document


class YAMLParser(_YAMLParser):
    media_type = "application/yaml"


class TextYAMLParser(_YAMLParser):
    media_type = "text/yaml"


class XYamlParser(_YAMLParser):
    media_type = "application/x-yaml"


_BATCH_MODELS = {
    "intent_source": models.IntentSource,
    "desired_node": models.DesiredNode,
    "desired_ip_range": models.DesiredIPRange,
    "desired_endpoint": models.DesiredEndpoint,
    "desired_compute_platform": models.DesiredComputePlatform,
    "desired_compute_instance": models.DesiredComputeInstance,
    "desired_service": models.DesiredService,
    "desired_dependency": models.DesiredDependency,
    "desired_service_placement": models.DesiredServicePlacement,
    "desired_node_operational_override": models.DesiredNodeOperationalOverride,
}


class DesiredStateBatchView(APIView):
    """Authenticated, non-persistent HTTP adapter for the batch service."""

    parser_classes = [JSONParser, YAMLParser, TextYAMLParser, XYamlParser]
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: None, 400: None, 403: None, 409: None})
    def post(self, request):
        try:
            document = request.data
            dry_run, operations = decode_batch(document)
        except BatchValidationError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        self._check_permissions(request, dry_run, operations)
        result = (plan_batch(document) if dry_run else apply_batch(document)).as_dict()
        response_status = (
            status.HTTP_409_CONFLICT
            if result["transaction"]["status"] in {"blocked", "rolled_back"}
            else status.HTTP_200_OK
        )
        return Response(result, status=response_status)

    @staticmethod
    def _check_permissions(request, dry_run, operations):
        if not dry_run and getattr(request.auth, "write_enabled", True) is False:
            raise PermissionDenied("This API token is not write-enabled.")

        permissions = set()
        for operation in operations:
            model = _BATCH_MODELS[operation.kind]
            actions = ("view",) if dry_run else (("delete",) if operation.op == "delete" else ("add", "change"))
            permissions.update(
                f"{model._meta.app_label}.{action}_{model._meta.model_name}" for action in actions
            )
        if not request.user.has_perms(permissions):
            raise PermissionDenied("Missing required desired-state model permission.")


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
