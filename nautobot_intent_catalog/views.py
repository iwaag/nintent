"""Views for the Nautobot Intent Catalog App."""

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic.edit import FormView

from .loaders import load_default_intent_sources

try:
    from nautobot.apps.views import ObjectDeleteView, ObjectEditView, ObjectListView, ObjectView

    from .filters import (
        BrainDumpDocumentFilterSet,
        DesiredComputeInstanceFilterSet,
        DesiredComputePlatformFilterSet,
        DesiredDependencyFilterSet,
        DesiredEndpointFilterSet,
        DesiredIPRangeFilterSet,
        DesiredNodeFilterSet,
        DesiredNodeOperationalOverrideFilterSet,
        DesiredServiceFilterSet,
        DesiredServicePlacementFilterSet,
        IntentSourceFilterSet,
    )
    from .forms import (
        AlignmentReviewForm,
        BrainDumpDocumentForm,
        DesiredComputeInstanceForm,
        DesiredComputePlatformForm,
        DesiredDependencyForm,
        DesiredEndpointForm,
        DesiredHostQuickAddForm,
        DesiredIPRangeForm,
        DesiredNodeForm,
        DesiredNodeOperationalOverrideForm,
        DesiredServiceForm,
        DesiredServicePlacementForm,
        IntentSourceForm,
    )
    from .models import (
        AlignmentReview,
        BrainDumpDocument,
        DesiredComputeInstance,
        DesiredComputePlatform,
        DesiredDependency,
        DesiredEndpoint,
        DesiredIPRange,
        DesiredNode,
        DesiredNodeOperationalOverride,
        DesiredService,
        DesiredServicePlacement,
        IntentSource,
    )
    from .operations import (
        create_desired_node_with_primary_endpoint,
    )
    from .tables import (
        BrainDumpDocumentTable,
        DesiredComputeInstanceTable,
        DesiredComputePlatformTable,
        DesiredDependencyTable,
        DesiredEndpointTable,
        DesiredIPRangeTable,
        DesiredNodeTable,
        DesiredNodeOperationalOverrideTable,
        DesiredServiceTable,
        DesiredServicePlacementTable,
        IntentSourceTable,
    )
except ImportError:  # pragma: no cover - Nautobot is unavailable in local unit tests.
    pass
else:

    class IntentSourceListView(ObjectListView):
        """List DB-backed intent source records."""

        queryset = IntentSource.objects.all()
        filterset = IntentSourceFilterSet
        table = IntentSourceTable


    class IntentSourceView(ObjectView):
        """Show one intent source record."""

        queryset = IntentSource.objects.all()


    class IntentSourceEditView(ObjectEditView):
        """Create or edit an intent source record."""

        queryset = IntentSource.objects.all()
        model_form = IntentSourceForm


    class IntentSourceDeleteView(ObjectDeleteView):
        """Delete an intent source record."""

        queryset = IntentSource.objects.all()


    class DesiredServiceListView(ObjectListView):
        """List desired service records."""

        queryset = DesiredService.objects.select_related("intent_source")
        filterset = DesiredServiceFilterSet
        table = DesiredServiceTable


    class DesiredServiceView(ObjectView):
        """Show one desired service record."""

        queryset = DesiredService.objects.select_related("intent_source")

        def get_extra_context(self, request, instance):
            return {"dashboard_url": _configured_dashboard_url()}


    class DesiredServiceEditView(ObjectEditView):
        """Edit a desired service record."""

        queryset = DesiredService.objects.all()
        model_form = DesiredServiceForm


    class DesiredServiceDeleteView(ObjectDeleteView):
        """Delete a desired service record."""

        queryset = DesiredService.objects.all()


    class DesiredDependencyListView(ObjectListView):
        """List desired dependency records."""

        queryset = DesiredDependency.objects.select_related("source_service", "resolved_service")
        filterset = DesiredDependencyFilterSet
        table = DesiredDependencyTable


    class DesiredDependencyView(ObjectView):
        """Show one desired dependency record."""

        queryset = DesiredDependency.objects.select_related("source_service", "resolved_service")


    class DesiredDependencyEditView(ObjectEditView):
        """Edit a desired dependency record."""

        queryset = DesiredDependency.objects.all()
        model_form = DesiredDependencyForm


    class DesiredDependencyDeleteView(ObjectDeleteView):
        """Delete a desired dependency record."""

        queryset = DesiredDependency.objects.all()


    class DesiredNodeListView(ObjectListView):
        """List desired node records."""

        queryset = DesiredNode.objects.select_related("intent_source", "realized_device")
        filterset = DesiredNodeFilterSet
        table = DesiredNodeTable


    class DesiredNodeView(ObjectView):
        """Show one desired node record."""

        queryset = DesiredNode.objects.select_related(
            "intent_source", "realized_device"
        ).prefetch_related("controlled_compute_platforms", "desired_compute_instance")

        def get_extra_context(self, request, instance):
            return {"dashboard_url": _configured_dashboard_url()}


    class DesiredNodeEditView(ObjectEditView):
        """Edit a desired node record."""

        queryset = DesiredNode.objects.all()
        model_form = DesiredNodeForm


    class DesiredNodeDeleteView(ObjectDeleteView):
        """Delete a desired node record."""

        queryset = DesiredNode.objects.all()


    class DesiredHostQuickAddView(FormView):
        """Create one desired node and its primary desired endpoint."""

        form_class = DesiredHostQuickAddForm
        template_name = "nautobot_intent_catalog/desiredhost_quick_add.html"

        def form_valid(self, form):
            try:
                self.result = create_desired_node_with_primary_endpoint(**form.operation_kwargs())
            except ValidationError as exc:
                _add_validation_errors(form, exc)
                return self.form_invalid(form)

            endpoint = self.result.desired_endpoint
            endpoint_summary = _endpoint_summary(endpoint)
            node = self.result.desired_node
            accepted_types_source = "override" if form.cleaned_data.get("accepted_actual_types") else "derived"
            messages.success(
                self.request,
                f"Created desired node {node} with endpoint {endpoint.name}{endpoint_summary}. "
                f"Accepted actual types: {', '.join(node.accepted_actual_types)} ({accepted_types_source}).",
            )
            return super().form_valid(form)

        def get_success_url(self):
            return self.result.desired_node.get_absolute_url() if hasattr(self, "result") else super().get_success_url()


    class DesiredEndpointListView(ObjectListView):
        """List desired endpoint records."""

        queryset = DesiredEndpoint.objects.select_related("desired_node", "realized_ip_address")
        filterset = DesiredEndpointFilterSet
        table = DesiredEndpointTable


    class DesiredEndpointView(ObjectView):
        """Show one desired endpoint record."""

        queryset = DesiredEndpoint.objects.select_related("desired_node", "realized_ip_address")


    class DesiredEndpointEditView(ObjectEditView):
        """Edit a desired endpoint record."""

        queryset = DesiredEndpoint.objects.all()
        model_form = DesiredEndpointForm


    class DesiredEndpointDeleteView(ObjectDeleteView):
        """Delete a desired endpoint record."""

        queryset = DesiredEndpoint.objects.all()


    class DesiredComputePlatformListView(ObjectListView):
        """List desired compute platform records."""

        queryset = DesiredComputePlatform.objects.select_related("control_node", "realized_cluster")
        filterset = DesiredComputePlatformFilterSet
        table = DesiredComputePlatformTable


    class DesiredComputePlatformView(ObjectView):
        """Show one desired compute platform record."""

        queryset = DesiredComputePlatform.objects.select_related(
            "control_node", "realized_cluster"
        ).prefetch_related("desired_compute_instances")


    class DesiredComputePlatformEditView(ObjectEditView):
        """Create or edit a desired compute platform record."""

        queryset = DesiredComputePlatform.objects.all()
        model_form = DesiredComputePlatformForm


    class DesiredComputePlatformDeleteView(ObjectDeleteView):
        """Delete a desired compute platform record."""

        queryset = DesiredComputePlatform.objects.all()


    class DesiredComputeInstanceListView(ObjectListView):
        """List desired compute instance records."""

        queryset = DesiredComputeInstance.objects.select_related("desired_node", "platform", "realized_vm")
        filterset = DesiredComputeInstanceFilterSet
        table = DesiredComputeInstanceTable


    class DesiredComputeInstanceView(ObjectView):
        """Show one desired compute instance record."""

        queryset = DesiredComputeInstance.objects.select_related("desired_node", "platform", "realized_vm")

        def get_extra_context(self, request, instance):
            from .compute_contract import effective_lifecycle
            from .models import _resolve_compute_effective_value

            return {
                "effective_lifecycle": effective_lifecycle(
                    instance.desired_node.lifecycle, instance.platform.lifecycle
                ),
                "effective_storage": _resolve_compute_effective_value(
                    instance, instance_key="storage", platform_key="default_storage"
                ),
                "effective_bridge": _resolve_compute_effective_value(
                    instance, instance_key="bridge", platform_key="default_bridge"
                ),
            }


    class DesiredComputeInstanceEditView(ObjectEditView):
        """Create or edit a desired compute instance record."""

        queryset = DesiredComputeInstance.objects.all()
        model_form = DesiredComputeInstanceForm


    class DesiredComputeInstanceDeleteView(ObjectDeleteView):
        """Delete a desired compute instance record."""

        queryset = DesiredComputeInstance.objects.all()


    class DesiredServicePlacementListView(ObjectListView):
        """List explicit desired service placements."""

        queryset = DesiredServicePlacement.objects.select_related(
            "desired_service",
            "desired_node",
            "desired_endpoint",
        )
        filterset = DesiredServicePlacementFilterSet
        table = DesiredServicePlacementTable


    class DesiredServicePlacementView(ObjectView):
        """Show one explicit desired service placement."""

        queryset = DesiredServicePlacement.objects.select_related(
            "desired_service",
            "desired_node",
            "desired_endpoint",
        )


    class DesiredServicePlacementEditView(ObjectEditView):
        """Create or edit an explicit desired service placement."""

        queryset = DesiredServicePlacement.objects.all()
        model_form = DesiredServicePlacementForm


    class DesiredServicePlacementDeleteView(ObjectDeleteView):
        """Delete an explicit desired service placement."""

        queryset = DesiredServicePlacement.objects.all()


    class DesiredNodeOperationalOverrideListView(ObjectListView):
        """List desired node operational overrides."""

        queryset = DesiredNodeOperationalOverride.objects.select_related(
            "desired_node",
            "local_endpoint",
            "tailscale_endpoint",
        )
        filterset = DesiredNodeOperationalOverrideFilterSet
        table = DesiredNodeOperationalOverrideTable


    class DesiredNodeOperationalOverrideView(ObjectView):
        """Show one desired node operational override."""

        queryset = DesiredNodeOperationalOverride.objects.select_related(
            "desired_node",
            "local_endpoint",
            "tailscale_endpoint",
        )


    class DesiredNodeOperationalOverrideEditView(ObjectEditView):
        """Create or edit a desired node operational override."""

        queryset = DesiredNodeOperationalOverride.objects.all()
        model_form = DesiredNodeOperationalOverrideForm


    class DesiredNodeOperationalOverrideDeleteView(ObjectDeleteView):
        """Delete a desired node operational override."""

        queryset = DesiredNodeOperationalOverride.objects.all()


    class DesiredIPRangeListView(ObjectListView):
        """List desired IP range records."""

        queryset = DesiredIPRange.objects.all()
        filterset = DesiredIPRangeFilterSet
        table = DesiredIPRangeTable


    class DesiredIPRangeView(ObjectView):
        """Show one desired IP range record."""

        queryset = DesiredIPRange.objects.all()


    class DesiredIPRangeEditView(ObjectEditView):
        """Edit a desired IP range record."""

        queryset = DesiredIPRange.objects.all()
        model_form = DesiredIPRangeForm


    class DesiredIPRangeDeleteView(ObjectDeleteView):
        """Delete a desired IP range record."""

        queryset = DesiredIPRange.objects.all()


    class BrainDumpDocumentListView(ObjectListView):
        """List Braindump documents.

        ``select_related("alignment_review")`` avoids one query per row for the
        table's review-presence column.
        """

        queryset = BrainDumpDocument.objects.select_related("alignment_review")
        filterset = BrainDumpDocumentFilterSet
        table = BrainDumpDocumentTable


    class BrainDumpDocumentView(ObjectView):
        """Show one Braindump and its current Alignment Review, in separate panels."""

        queryset = BrainDumpDocument.objects.select_related("alignment_review")


    class BrainDumpDocumentEditView(ObjectEditView):
        """Create or edit a Braindump document."""

        queryset = BrainDumpDocument.objects.all()
        model_form = BrainDumpDocumentForm


    class BrainDumpDocumentDeleteView(ObjectDeleteView):
        """Delete a Braindump document (cascades to its Alignment Review, if any)."""

        queryset = BrainDumpDocument.objects.all()


    class AlignmentReviewAddView(ObjectEditView):
        """Create the current Alignment Review for one Braindump.

        Bound to the parent Braindump via the URL, not a form field, so a review can
        never be attached to the wrong document. If a review already exists, redirect
        to its edit route instead of creating a second, competing row.
        """

        queryset = AlignmentReview.objects.all()
        model_form = AlignmentReviewForm

        def dispatch(self, request, *args, **kwargs):
            braindump = get_object_or_404(BrainDumpDocument, pk=kwargs["braindump_pk"])
            existing_review = getattr(braindump, "alignment_review", None)
            if existing_review is not None:
                messages.info(
                    request,
                    "This Braindump already has a current review. Edit it instead of creating another.",
                )
                return redirect("plugins:nautobot_intent_catalog:alignmentreview_edit", pk=existing_review.pk)
            return super().dispatch(request, *args, **kwargs)

        def alter_obj(self, obj, request, url_args, url_kwargs):
            obj.braindump = get_object_or_404(BrainDumpDocument, pk=url_kwargs["braindump_pk"])
            return obj


    class AlignmentReviewEditView(ObjectEditView):
        """Edit the current Alignment Review's summary."""

        queryset = AlignmentReview.objects.all()
        model_form = AlignmentReviewForm


    class AlignmentReviewDeleteView(ObjectDeleteView):
        """Delete the current Alignment Review, leaving its Braindump unreviewed."""

        queryset = AlignmentReview.objects.all()

        def get_return_url(self, request, obj=None, default_return_url=None):
            braindump_id = getattr(obj, "braindump_id", None)
            if braindump_id:
                return obj.braindump.get_absolute_url()
            return super().get_return_url(request, obj, default_return_url)


    def _add_validation_errors(form, exc):
        if hasattr(exc, "message_dict"):
            for field_name, errors in exc.message_dict.items():
                form.add_error(None if field_name == "__all__" else field_name, errors)
            return
        form.add_error(None, exc)


    def _endpoint_summary(endpoint):
        details = [value for value in (endpoint.ip_address, endpoint.dns_name) if value]
        return f" ({', '.join(details)})" if details else ""


def source_yaml_intent_source_list(request):
    """Render the configured intent source input list directly from YAML."""

    result = load_default_intent_sources(_configured_source_file())
    return render(
        request,
        "nautobot_intent_catalog/source_yaml_list.html",
        {
            "source_path": result.source_path,
            "intent_sources": result.intent_sources,
            "desired_nodes": result.desired_nodes,
            "desired_ip_ranges": result.desired_ip_ranges,
            "desired_endpoints": result.desired_endpoints,
            "desired_service_placements": result.desired_service_placements,
            "desired_node_operational_overrides": result.desired_node_operational_overrides,
            "errors": result.errors,
        },
    )


source_yaml_list = source_yaml_intent_source_list


def _configured_source_file():
    plugins_config = getattr(settings, "PLUGINS_CONFIG", {}) or {}
    app_config = plugins_config.get("nautobot_intent_catalog", {}) or {}
    return app_config.get("intent_sources_file")


def _configured_dashboard_url():
    """Return the nctl dashboard URL from PLUGINS_CONFIG, if set (deployment config, not a model)."""

    plugins_config = getattr(settings, "PLUGINS_CONFIG", {}) or {}
    app_config = plugins_config.get("nautobot_intent_catalog", {}) or {}
    return app_config.get("dashboard_url")


def dashboard_redirect(request):
    """Redirect to the configured nctl dashboard URL.

    Nautobot's NavMenuItem.link is always passed through reverse(), so an external
    dashboard_url can't be used as the nav link directly (it renders "ERROR: Invalid
    link!" while still keeping the right href). This resolvable view name is the nav
    link target instead; it 302s to the real, possibly-external, dashboard_url.
    """

    dashboard_url = _configured_dashboard_url()
    if not dashboard_url:
        raise Http404("dashboard_url is not configured in PLUGINS_CONFIG.")
    return HttpResponseRedirect(dashboard_url)
