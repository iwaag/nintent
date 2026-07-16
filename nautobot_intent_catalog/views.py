"""Views for the Nautobot Intent Catalog App."""

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.views.generic.edit import FormView

from .loaders import load_default_intent_sources

try:
    from nautobot.apps.views import ObjectDeleteView, ObjectEditView, ObjectListView, ObjectView

    from .filters import (
        DesiredDependencyFilterSet,
        DesiredEndpointFilterSet,
        DesiredIPRangeFilterSet,
        DesiredNodeFilterSet,
        DesiredNodeOperationalConfigFilterSet,
        DesiredServiceFilterSet,
        DesiredServicePlacementFilterSet,
        IntentSourceFilterSet,
    )
    from .forms import (
        DesiredDependencyForm,
        DesiredEndpointForm,
        DesiredHostQuickAddForm,
        DesiredIPRangeForm,
        DesiredNodeForm,
        DesiredNodeOperationalConfigForm,
        DesiredServiceForm,
        DesiredServicePlacementForm,
        IntentSourceForm,
    )
    from .models import (
        DesiredDependency,
        DesiredEndpoint,
        DesiredIPRange,
        DesiredNode,
        DesiredNodeOperationalConfig,
        DesiredService,
        DesiredServicePlacement,
        IntentSource,
    )
    from .operations import (
        create_desired_node_with_primary_endpoint,
    )
    from .tables import (
        DesiredDependencyTable,
        DesiredEndpointTable,
        DesiredIPRangeTable,
        DesiredNodeTable,
        DesiredNodeOperationalConfigTable,
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

        queryset = DesiredNode.objects.select_related("intent_source", "realized_device", "realized_vm")
        filterset = DesiredNodeFilterSet
        table = DesiredNodeTable


    class DesiredNodeView(ObjectView):
        """Show one desired node record."""

        queryset = DesiredNode.objects.select_related("intent_source", "realized_device", "realized_vm")

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
            messages.success(
                self.request,
                f"Created desired node {self.result.desired_node} with endpoint {endpoint.name}{endpoint_summary}.",
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


    class DesiredNodeOperationalConfigListView(ObjectListView):
        """List desired node operational policies."""

        queryset = DesiredNodeOperationalConfig.objects.select_related(
            "desired_node",
            "local_endpoint",
            "tailscale_endpoint",
        )
        filterset = DesiredNodeOperationalConfigFilterSet
        table = DesiredNodeOperationalConfigTable


    class DesiredNodeOperationalConfigView(ObjectView):
        """Show one desired node operational policy."""

        queryset = DesiredNodeOperationalConfig.objects.select_related(
            "desired_node",
            "local_endpoint",
            "tailscale_endpoint",
        )


    class DesiredNodeOperationalConfigEditView(ObjectEditView):
        """Create or edit desired node operational policy."""

        queryset = DesiredNodeOperationalConfig.objects.all()
        model_form = DesiredNodeOperationalConfigForm


    class DesiredNodeOperationalConfigDeleteView(ObjectDeleteView):
        """Delete desired node operational policy."""

        queryset = DesiredNodeOperationalConfig.objects.all()


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
            "desired_node_operational_configs": result.desired_node_operational_configs,
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
