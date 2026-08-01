"""REST API views for the Nautobot Intent Catalog App."""

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
from ..operations.retirement_prune import RetirementPruneError, delete as delete_retirement_actual, plan as plan_retirement_actual
from ..filters import (
    AlignmentReviewFilterSet,
    BrainDumpDocumentFilterSet,
)
from ..models import (
    AlignmentReview,
    BrainDumpDocument,
)
from .serializers import (
    AlignmentReviewSerializer,
    BrainDumpCompleteSerializer,
    BrainDumpDocumentSerializer,
    BrainDumpSupersedeSerializer,
)
from .yaml_input import YAMLDocumentError, load_yaml_document


class _YAMLParser(BaseParser):
    """Parse one YAML media type into the same document shape as JSON."""

    def parse(self, stream, media_type=None, parser_context=None):
        try:
            return load_yaml_document(stream.read())
        except YAMLDocumentError as exc:
            raise ParseError(str(exc)) from exc


class YAMLParser(_YAMLParser):
    media_type = "application/yaml"


class TextYAMLParser(_YAMLParser):
    media_type = "text/yaml"


class XYamlParser(_YAMLParser):
    media_type = "application/x-yaml"


_BATCH_MODELS = {
    "desired_node": models.DesiredNode,
    "desired_ip_range": models.DesiredIPRange,
    "desired_endpoint": models.DesiredEndpoint,
    "desired_compute_platform": models.DesiredComputePlatform,
    "desired_compute_instance": models.DesiredComputeInstance,
    "desired_service": models.DesiredService,
    "desired_service_placement": models.DesiredServicePlacement,
    "desired_service_binding": models.DesiredServiceBinding,
    "desired_node_operational_override": models.DesiredNodeOperationalOverride,
    "desired_workspace": models.DesiredWorkspace,
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


class RetirementActualPruneView(APIView):
    """Plan or delete only the Actual cascade rooted in a retired LXC's links."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.has_perms(("nautobot_intent_catalog.view_desirednode", "dcim.delete_device", "virtualization.delete_virtualmachine")):
            raise PermissionDenied("Missing required retirement-prune permission.")
        try:
            result = plan_retirement_actual(dict(request.data))
        except RetirementPruneError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(result)

    def delete(self, request):
        if not request.user.has_perms(("nautobot_intent_catalog.view_desirednode", "dcim.delete_device", "virtualization.delete_virtualmachine")):
            raise PermissionDenied("Missing required retirement-prune permission.")
        try:
            result = delete_retirement_actual(dict(request.data))
        except RetirementPruneError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(result)


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

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, *args, **kwargs):
        """Directly transition one active Braindump to completed, recording why."""
        serializer = BrainDumpCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data["reason"]

        with transaction.atomic():
            document = (
                BrainDumpDocument.objects.select_for_update()
                .filter(pk=self.kwargs["pk"])
                .first()
            )
            if document is None:
                return Response({"detail": "Braindump not found."}, status=status.HTTP_404_NOT_FOUND)
            if document.status != BrainDumpDocument.STATUS_ACTIVE:
                return Response(
                    {"detail": f"Braindump is not active (status={document.status})."},
                    status=status.HTTP_409_CONFLICT,
                )
            document.status = BrainDumpDocument.STATUS_COMPLETED
            document.completion_reason = reason
            document.validated_save()

        return Response(BrainDumpDocumentSerializer(document, context={"request": request}).data)


class BraindumpPurgeView(APIView):
    """Plan or immediately delete one exact superseded Braindump."""

    permission_classes = [IsAuthenticated]

    def post(self, request, braindump_id):
        return self._run(request, braindump_id, apply=False)

    def delete(self, request, braindump_id):
        return self._run(request, braindump_id, apply=True)

    @staticmethod
    def _run(request, braindump_id, *, apply):
        with transaction.atomic():
            document = (
                BrainDumpDocument.objects.select_for_update()
                .filter(pk=braindump_id)
                .first()
            )
            if document is None:
                return Response({"outcome": "already_purged", "braindump_id": str(braindump_id)})
            if document.status not in (BrainDumpDocument.STATUS_SUPERSEDED, BrainDumpDocument.STATUS_COMPLETED):
                return Response(
                    {
                        "outcome": "ineligible",
                        "braindump_id": str(document.pk),
                        "reason": "Braindump must have status=superseded or status=completed.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            result = {
                "outcome": "purged" if apply else "planned",
                "braindump": BrainDumpDocumentSerializer(document, context={"request": request}).data,
                "alignment_review_present": hasattr(document, "alignment_review"),
            }
            if apply:
                # The one-to-one review cascades with the document inside this transaction.
                document.delete()
            return Response(result)


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
