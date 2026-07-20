"""Forms for Intent Catalog models."""

from __future__ import annotations

try:
    from django import forms
    from django.utils.text import slugify
    from nautobot.apps.forms import NautobotModelForm

    from .models import (
        DesiredDependency,
        DesiredEndpoint,
        DesiredIPRange,
        DesiredNode,
        DesiredNodeOperationalOverride,
        DesiredService,
        DesiredServicePlacement,
        IntentSource,
    )
except ImportError:  # pragma: no cover - Nautobot/Django are unavailable in local unit tests.
    pass
else:

    class DesiredHostQuickAddForm(forms.Form):
        """Quick-add form for one desired node and its primary endpoint."""

        name = forms.CharField(max_length=255)
        slug = forms.SlugField(max_length=255, required=False)
        node_type = forms.ChoiceField(
            choices=DesiredNode.NODE_TYPE_CHOICES,
            initial=DesiredNode.NODE_TYPE_VIRTUAL_MACHINE,
        )
        accepted_actual_types = forms.JSONField(required=False, widget=forms.HiddenInput)
        lifecycle = forms.ChoiceField(
            choices=DesiredNode.LIFECYCLE_CHOICES,
            initial=DesiredNode.LIFECYCLE_ACTIVE,
        )
        role = forms.CharField(max_length=255, required=False)
        description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
        intent_source = forms.ModelChoiceField(queryset=IntentSource.objects.all(), required=False)
        ip_address = forms.CharField(max_length=128, required=False)
        dns_name = forms.CharField(max_length=255, required=False)
        mdns_name = forms.CharField(max_length=255, required=False)
        vpn_dns_name = forms.CharField(max_length=255, required=False)
        protocol = forms.CharField(max_length=64, required=False)
        port = forms.IntegerField(required=False, min_value=1, max_value=65535)
        generate_dnsmasq = forms.BooleanField(required=False, initial=True)
        ip_policy = forms.ChoiceField(
            choices=DesiredEndpoint.IP_POLICY_CHOICES,
            initial=DesiredEndpoint.IP_POLICY_DHCP_RESERVED,
        )
        dnsmasq_record_type = forms.ChoiceField(
            choices=DesiredEndpoint.DNSMASQ_RECORD_TYPE_CHOICES,
            initial=DesiredEndpoint.DNSMASQ_HOST_RECORD,
        )
        endpoint_name = forms.CharField(
            max_length=255,
            initial=DesiredEndpoint.ENDPOINT_TYPE_PRIMARY,
            widget=forms.HiddenInput,
        )
        endpoint_type = forms.ChoiceField(
            choices=DesiredEndpoint.ENDPOINT_TYPE_CHOICES,
            initial=DesiredEndpoint.ENDPOINT_TYPE_PRIMARY,
            widget=forms.HiddenInput,
        )

        def clean_slug(self):
            """Generate a slug from name when omitted."""

            slug = self.cleaned_data.get("slug")
            if slug:
                return slug

            generated_slug = slugify(self.cleaned_data.get("name") or "")
            if not generated_slug:
                raise forms.ValidationError("Enter a slug or a name that can be converted to a slug.")
            return generated_slug

        def node_data(self):
            """Return cleaned values for DesiredNode creation."""

            return {
                "name": self.cleaned_data["name"],
                "slug": self.cleaned_data["slug"],
                "node_type": self.cleaned_data["node_type"],
                "accepted_actual_types": self.cleaned_data.get("accepted_actual_types"),
                "lifecycle": self.cleaned_data["lifecycle"],
                "role": self.cleaned_data.get("role"),
                "description": self.cleaned_data.get("description"),
                "intent_source": self.cleaned_data.get("intent_source"),
            }

        def endpoint_data(self):
            """Return cleaned values for DesiredEndpoint creation."""

            return {
                "ip_address": self.cleaned_data.get("ip_address"),
                "dns_name": self.cleaned_data.get("dns_name"),
                "mdns_name": self.cleaned_data.get("mdns_name"),
                "vpn_dns_name": self.cleaned_data.get("vpn_dns_name"),
                "protocol": self.cleaned_data.get("protocol"),
                "port": self.cleaned_data.get("port"),
                "generate_dnsmasq": self.cleaned_data.get("generate_dnsmasq"),
                "ip_policy": self.cleaned_data["ip_policy"],
                "dnsmasq_record_type": self.cleaned_data["dnsmasq_record_type"],
                "endpoint_name": self.cleaned_data["endpoint_name"],
                "endpoint_type": self.cleaned_data["endpoint_type"],
            }

        def operation_kwargs(self):
            """Return operation-ready keyword arguments."""

            return {**self.node_data(), **self.endpoint_data()}


    class IntentSourceForm(NautobotModelForm):
        """Create/edit form for intent sources."""

        class Meta:
            model = IntentSource
            fields = (
                "name",
                "slug",
                "source_type",
                "url",
                "ref",
                "enabled",
                "owner",
                "description",
                "source_config",
                "last_import_status",
                "last_import_summary",
            )


    class DesiredServiceForm(NautobotModelForm):
        """Edit form for desired services."""

        class Meta:
            model = DesiredService
            fields = (
                "name",
                "slug",
                "display_name",
                "service_type",
                "lifecycle",
                "intent_source",
                "source_ref",
                "source_catalog_path",
                "catalog_kind",
                "catalog_namespace",
                "catalog_metadata_name",
                "catalog_owner",
                "catalog_lifecycle",
                "prefers_gpu",
                "min_memory_gb",
                "requirements",
                "placement_policy",
                "notes",
            )


    class DesiredDependencyForm(NautobotModelForm):
        """Edit form for dependency metadata."""

        class Meta:
            model = DesiredDependency
            fields = (
                "source_service",
                "dependency_kind",
                "namespace",
                "name",
                "raw_ref",
                "dependency_type",
                "resolution_status",
                "resolved_service",
                "notes",
            )


    class DesiredNodeForm(NautobotModelForm):
        """Edit form for desired nodes."""

        class Meta:
            model = DesiredNode
            fields = (
                "name",
                "slug",
                "node_type",
                "lifecycle",
                "role",
                "description",
                "accepted_actual_types",
                "expected_spec",
                "intent_source",
                "realized_device",
                "realized_vm",
                "notes",
            )

        def save(self, commit=True):
            instance = super().save(commit=False)
            for relation_name in ("realized_device", "realized_vm"):
                if relation_name in self.changed_data:
                    relation_id = getattr(instance, f"{relation_name}_id")
                    setattr(instance, f"{relation_name}_source", "override" if relation_id else None)
            if commit:
                instance.save()
                self.save_m2m()
            return instance


    class DesiredEndpointForm(NautobotModelForm):
        """Edit form for desired endpoints."""

        class Meta:
            model = DesiredEndpoint
            fields = (
                "name",
                "desired_node",
                "endpoint_type",
                "ip_address",
                "ip_policy",
                "dns_name",
                "mdns_name",
                "vpn_dns_name",
                "protocol",
                "port",
                "generate_dnsmasq",
                "dnsmasq_record_type",
                "realized_ip_address",
                "description",
            )

        def save(self, commit=True):
            instance = super().save(commit=False)
            for name_field in ("dns_name", "mdns_name"):
                if name_field in self.changed_data:
                    setattr(instance, f"{name_field}_source", "intent" if getattr(instance, name_field) else None)
            if "realized_ip_address" in self.changed_data:
                instance.realized_ip_address_source = (
                    "override" if instance.realized_ip_address_id else None
                )
            if commit:
                instance.save()
                self.save_m2m()
            return instance


    class DesiredServicePlacementForm(NautobotModelForm):
        """Create or edit an explicit desired service placement.

        ``config_schema_version`` and ``assignment_source`` are intentionally not
        operator inputs: the contract only supports a single config schema version
        (the model default), and manual CRUD always means ``assignment_source``
        ``manual`` (the model default).  Keeping them off the form matches the
        Quick Add path, which derives/fixes the same two values in the operation.
        """

        class Meta:
            model = DesiredServicePlacement
            fields = (
                "desired_service",
                "instance_name",
                "desired_node",
                "desired_endpoint",
                "desired_state",
                "instance_role",
                "deployment_profile",
                "config",
                "reason",
            )


    class DesiredNodeOperationalOverrideForm(NautobotModelForm):
        """Create or edit optional desired-node operation exceptions."""

        class Meta:
            model = DesiredNodeOperationalOverride
            fields = (
                "desired_node",
                "declared_host_os",
                "connection_path",
                "local_endpoint",
                "tailscale_endpoint",
                "ansible_port",
                "power_control",
                "is_laptop",
            )


    class DesiredIPRangeForm(NautobotModelForm):
        """Edit form for desired IP ranges."""

        class Meta:
            model = DesiredIPRange
            fields = (
                "name",
                "slug",
                "start_address",
                "end_address",
                "range_policy",
                "lifecycle",
                "generate_dnsmasq",
                "dnsmasq_options",
                "description",
            )
