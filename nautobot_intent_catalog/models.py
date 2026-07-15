"""Database models for the Nautobot Intent Catalog App."""

from __future__ import annotations

import ipaddress

def _endpoint_has_usable_ip(endpoint) -> bool:
    value = getattr(endpoint, "ip_address", None)
    if not value:
        return False
    try:
        ipaddress.ip_interface(str(value))
    except ValueError:
        return False
    return True


def _endpoint_is_usable_local(endpoint) -> bool:
    return _endpoint_has_usable_ip(endpoint) or any(
        str(getattr(endpoint, field_name, "") or "").strip()
        for field_name in ("dns_name", "mdns_name")
    )

try:
    from django.core.exceptions import ValidationError
    from django.db import models
    from django.urls import reverse
    from nautobot.apps.models import PrimaryModel, extras_features
except ImportError:  # pragma: no cover - Nautobot/Django are unavailable in local unit tests.
    PrimaryModel = object  # type: ignore[assignment]
else:

    @extras_features("graphql")
    class IntentSource(PrimaryModel):
        """Input source record used for intent import and analysis."""

        SOURCE_GIT_REPOSITORY = "git_repository"
        SOURCE_YAML_FILE = "yaml_file"
        SOURCE_MANUAL = "manual"
        SOURCE_API = "api"
        SOURCE_GENERATED = "generated"
        SOURCE_TYPE_CHOICES = (
            (SOURCE_GIT_REPOSITORY, "Git repository"),
            (SOURCE_YAML_FILE, "YAML file"),
            (SOURCE_MANUAL, "Manual"),
            (SOURCE_API, "API"),
            (SOURCE_GENERATED, "Generated"),
        )

        name = models.CharField(max_length=255)
        slug = models.SlugField(max_length=255, unique=True)
        source_type = models.CharField(
            max_length=64,
            choices=SOURCE_TYPE_CHOICES,
            default=SOURCE_GIT_REPOSITORY,
        )
        url = models.URLField(unique=True, blank=True, null=True)
        ref = models.CharField(max_length=255, blank=True, null=True)
        enabled = models.BooleanField(default=True)
        owner = models.CharField(max_length=255, blank=True, null=True)
        description = models.TextField(blank=True, null=True)
        source_config = models.JSONField(default=dict, blank=True)
        last_import_status = models.CharField(max_length=64, blank=True, null=True)
        last_imported_at = models.DateTimeField(blank=True, null=True)
        last_import_summary = models.JSONField(default=dict, blank=True)

        class Meta:
            ordering = ("name",)
            verbose_name = "intent source"
            verbose_name_plural = "intent sources"

        def __str__(self) -> str:
            return self.name

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:intentsource", args=[self.pk])


    @extras_features("graphql")
    class DesiredService(PrimaryModel):
        """Desired service generated from source metadata."""

        SERVICE_TYPE_SERVICE = "service"
        SERVICE_TYPE_WEBSITE = "website"
        SERVICE_TYPE_WORKER = "worker"
        SERVICE_TYPE_DATABASE = "database"
        SERVICE_TYPE_QUEUE = "queue"
        SERVICE_TYPE_STORAGE = "storage"
        SERVICE_TYPE_AGENT = "agent"
        SERVICE_TYPE_OTHER = "other"
        SERVICE_TYPE_CHOICES = (
            (SERVICE_TYPE_SERVICE, "Service"),
            (SERVICE_TYPE_WEBSITE, "Website"),
            (SERVICE_TYPE_WORKER, "Worker"),
            (SERVICE_TYPE_DATABASE, "Database"),
            (SERVICE_TYPE_QUEUE, "Queue"),
            (SERVICE_TYPE_STORAGE, "Storage"),
            (SERVICE_TYPE_AGENT, "Agent"),
            (SERVICE_TYPE_OTHER, "Other"),
        )

        LIFECYCLE_PROPOSED = "proposed"
        LIFECYCLE_PLANNED = "planned"
        LIFECYCLE_APPROVED = "approved"
        LIFECYCLE_ACTIVE = "active"
        LIFECYCLE_DEPRECATED = "deprecated"
        LIFECYCLE_RETIRED = "retired"
        LIFECYCLE_CHOICES = (
            (LIFECYCLE_PROPOSED, "Proposed"),
            (LIFECYCLE_PLANNED, "Planned"),
            (LIFECYCLE_APPROVED, "Approved"),
            (LIFECYCLE_ACTIVE, "Active"),
            (LIFECYCLE_DEPRECATED, "Deprecated"),
            (LIFECYCLE_RETIRED, "Retired"),
        )

        name = models.SlugField(max_length=255)
        slug = models.SlugField(max_length=255)
        display_name = models.CharField(max_length=255)
        service_type = models.CharField(
            max_length=64,
            choices=SERVICE_TYPE_CHOICES,
            default=SERVICE_TYPE_SERVICE,
        )
        lifecycle = models.CharField(
            max_length=64,
            choices=LIFECYCLE_CHOICES,
            default=LIFECYCLE_PROPOSED,
        )
        intent_source = models.ForeignKey(
            IntentSource,
            on_delete=models.CASCADE,
            related_name="desired_services",
        )
        source_ref = models.CharField(max_length=255, blank=True, null=True)
        source_catalog_path = models.CharField(max_length=512, blank=True, null=True)
        catalog_kind = models.CharField(max_length=64, blank=True, null=True)
        catalog_namespace = models.CharField(max_length=255, default="default")
        catalog_metadata_name = models.CharField(max_length=255)
        catalog_owner = models.CharField(max_length=255, blank=True, null=True)
        catalog_lifecycle = models.CharField(max_length=64, blank=True, null=True)
        prefers_gpu = models.BooleanField(default=False)
        min_memory_gb = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
        requirements = models.JSONField(default=dict, blank=True)
        placement_policy = models.JSONField(default=dict, blank=True)
        notes = models.TextField(blank=True, null=True)
        last_analyzed_at = models.DateTimeField(blank=True, null=True)

        class Meta:
            ordering = ("name",)
            verbose_name = "desired service"
            verbose_name_plural = "desired services"
            constraints = (
                models.UniqueConstraint(
                    fields=(
                        "intent_source",
                        "catalog_namespace",
                        "catalog_metadata_name",
                        "service_type",
                    ),
                    name="nic_unique_desired_service_entity",
                ),
            )

        def __str__(self) -> str:
            return self.display_name or self.name

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:desiredservice", args=[self.pk])


    @extras_features("graphql")
    class DesiredDependency(PrimaryModel):
        """Dependency metadata attached to a desired service."""

        RESOLUTION_UNRESOLVED = "unresolved"
        RESOLUTION_RESOLVED = "resolved"
        RESOLUTION_EXTERNAL = "external"
        RESOLUTION_IGNORED = "ignored"
        RESOLUTION_STATUS_CHOICES = (
            (RESOLUTION_UNRESOLVED, "Unresolved"),
            (RESOLUTION_RESOLVED, "Resolved"),
            (RESOLUTION_EXTERNAL, "External"),
            (RESOLUTION_IGNORED, "Ignored"),
        )

        source_service = models.ForeignKey(
            DesiredService,
            on_delete=models.CASCADE,
            related_name="dependencies",
        )
        dependency_kind = models.CharField(max_length=64)
        namespace = models.CharField(max_length=255, default="default")
        name = models.CharField(max_length=255)
        raw_ref = models.CharField(max_length=512)
        dependency_type = models.CharField(max_length=64)
        resolution_status = models.CharField(
            max_length=64,
            choices=RESOLUTION_STATUS_CHOICES,
            default=RESOLUTION_UNRESOLVED,
        )
        resolved_service = models.ForeignKey(
            DesiredService,
            on_delete=models.SET_NULL,
            blank=True,
            null=True,
            related_name="resolved_by_dependencies",
        )
        notes = models.TextField(blank=True, null=True)

        class Meta:
            ordering = ("source_service__name", "dependency_kind", "namespace", "name")
            verbose_name = "desired dependency"
            verbose_name_plural = "desired dependencies"
            constraints = (
                models.UniqueConstraint(
                    fields=("source_service", "dependency_kind", "namespace", "name"),
                    name="nic_unique_dependency_ref",
                ),
            )

        def __str__(self) -> str:
            return f"{self.dependency_kind}:{self.namespace}/{self.name}"

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:desireddependency", args=[self.pk])


    @extras_features("graphql")
    class DesiredNode(PrimaryModel):
        """Desired node intent that may be realized by one or more actual object types."""

        NODE_TYPE_DEVICE = "device"
        NODE_TYPE_VIRTUAL_MACHINE = "virtual_machine"
        NODE_TYPE_CONTAINER = "container"
        NODE_TYPE_SERVICE_HOST = "service_host"
        NODE_TYPE_CHOICES = (
            (NODE_TYPE_DEVICE, "Device"),
            (NODE_TYPE_VIRTUAL_MACHINE, "Virtual machine"),
            (NODE_TYPE_CONTAINER, "Container"),
            (NODE_TYPE_SERVICE_HOST, "Service host"),
        )

        ACTUAL_TYPE_DEVICE = "device"
        ACTUAL_TYPE_VIRTUAL_MACHINE = "virtual_machine"
        ACTUAL_TYPE_CONTAINER = "container"
        ACTUAL_TYPE_CHOICES = (
            (ACTUAL_TYPE_DEVICE, "Device"),
            (ACTUAL_TYPE_VIRTUAL_MACHINE, "Virtual machine"),
            (ACTUAL_TYPE_CONTAINER, "Container"),
        )

        LIFECYCLE_PLANNED = "planned"
        LIFECYCLE_APPROVED = "approved"
        LIFECYCLE_ACTIVE = "active"
        LIFECYCLE_DEPRECATED = "deprecated"
        LIFECYCLE_RETIRED = "retired"
        LIFECYCLE_CHOICES = (
            (LIFECYCLE_PLANNED, "Planned"),
            (LIFECYCLE_APPROVED, "Approved"),
            (LIFECYCLE_ACTIVE, "Active"),
            (LIFECYCLE_DEPRECATED, "Deprecated"),
            (LIFECYCLE_RETIRED, "Retired"),
        )

        name = models.CharField(max_length=255)
        slug = models.SlugField(max_length=255, unique=True)
        node_type = models.CharField(
            max_length=64,
            choices=NODE_TYPE_CHOICES,
            default=NODE_TYPE_DEVICE,
        )
        lifecycle = models.CharField(
            max_length=64,
            choices=LIFECYCLE_CHOICES,
            default=LIFECYCLE_PLANNED,
        )
        role = models.CharField(max_length=255, blank=True, null=True)
        description = models.TextField(blank=True, null=True)
        accepted_actual_types = models.JSONField(
            default=list,
            blank=True,
            help_text=(
                "Nautobot object types that may realize this desired node. "
                "Allowed values are device, virtual_machine, and container."
            ),
        )
        expected_spec = models.JSONField(default=dict, blank=True)
        intent_source = models.ForeignKey(
            IntentSource,
            on_delete=models.SET_NULL,
            blank=True,
            null=True,
            related_name="desired_nodes",
        )
        realized_device = models.ForeignKey(
            "dcim.Device",
            on_delete=models.SET_NULL,
            blank=True,
            null=True,
            related_name="intent_catalog_desired_nodes",
        )
        realized_vm = models.ForeignKey(
            "virtualization.VirtualMachine",
            on_delete=models.SET_NULL,
            blank=True,
            null=True,
            related_name="intent_catalog_desired_nodes",
        )
        notes = models.TextField(blank=True, null=True)

        class Meta:
            ordering = ("name",)
            verbose_name = "desired node"
            verbose_name_plural = "desired nodes"

        def __str__(self) -> str:
            return self.name

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:desirednode", args=[self.pk])

        def clean(self):
            """Validate desired node intent fields."""

            super().clean()
            accepted_actual_types = self.accepted_actual_types
            if accepted_actual_types is None:
                accepted_actual_types = []
                self.accepted_actual_types = accepted_actual_types

            if not isinstance(accepted_actual_types, list):
                raise ValidationError(
                    {"accepted_actual_types": "Accepted actual types must be a list."}
                )

            allowed_actual_types = {value for value, _label in self.ACTUAL_TYPE_CHOICES}
            invalid_actual_types = [
                value
                for value in accepted_actual_types
                if not isinstance(value, str) or value not in allowed_actual_types
            ]
            if invalid_actual_types:
                raise ValidationError(
                    {
                        "accepted_actual_types": (
                            "Accepted actual types must only contain device, virtual_machine, or container."
                        )
                    }
                )


    @extras_features("graphql")
    class DesiredEndpoint(PrimaryModel):
        """Desired endpoint attached to a desired node."""

        ENDPOINT_TYPE_PRIMARY = "primary"
        ENDPOINT_TYPE_MANAGEMENT = "management"
        ENDPOINT_TYPE_SERVICE = "service"
        ENDPOINT_TYPE_VPN = "vpn"
        ENDPOINT_TYPE_MDNS = "mdns"
        ENDPOINT_TYPE_OTHER = "other"
        ENDPOINT_TYPE_CHOICES = (
            (ENDPOINT_TYPE_PRIMARY, "Primary"),
            (ENDPOINT_TYPE_MANAGEMENT, "Management"),
            (ENDPOINT_TYPE_SERVICE, "Service"),
            (ENDPOINT_TYPE_VPN, "VPN"),
            (ENDPOINT_TYPE_MDNS, "mDNS"),
            (ENDPOINT_TYPE_OTHER, "Other"),
        )

        DNSMASQ_HOST_RECORD = "host_record"
        DNSMASQ_ADDRESS = "address"
        DNSMASQ_CNAME = "cname"
        DNSMASQ_RECORD_TYPE_CHOICES = (
            (DNSMASQ_HOST_RECORD, "host-record"),
            (DNSMASQ_ADDRESS, "address"),
            (DNSMASQ_CNAME, "cname"),
        )

        IP_POLICY_STATIC = "static"
        IP_POLICY_DHCP_RESERVED = "dhcp_reserved"
        IP_POLICY_EXTERNAL = "external"
        IP_POLICY_CHOICES = (
            (IP_POLICY_STATIC, "Static"),
            (IP_POLICY_DHCP_RESERVED, "DHCP reserved"),
            (IP_POLICY_EXTERNAL, "External"),
        )

        name = models.CharField(max_length=255)
        desired_node = models.ForeignKey(
            DesiredNode,
            on_delete=models.CASCADE,
            related_name="desired_endpoints",
        )
        endpoint_type = models.CharField(
            max_length=64,
            choices=ENDPOINT_TYPE_CHOICES,
            default=ENDPOINT_TYPE_PRIMARY,
        )
        ip_address = models.CharField(max_length=128, blank=True, null=True)
        ip_policy = models.CharField(
            max_length=64,
            choices=IP_POLICY_CHOICES,
            default=IP_POLICY_STATIC,
        )
        dns_name = models.CharField(max_length=255, blank=True, null=True)
        mdns_name = models.CharField(max_length=255, blank=True, null=True)
        vpn_dns_name = models.CharField(max_length=255, blank=True, null=True)
        protocol = models.CharField(max_length=64, blank=True, null=True)
        port = models.PositiveIntegerField(blank=True, null=True)
        generate_dnsmasq = models.BooleanField(default=False)
        dnsmasq_record_type = models.CharField(
            max_length=64,
            choices=DNSMASQ_RECORD_TYPE_CHOICES,
            default=DNSMASQ_HOST_RECORD,
        )
        realized_ip_address = models.ForeignKey(
            "ipam.IPAddress",
            on_delete=models.SET_NULL,
            blank=True,
            null=True,
            related_name="intent_catalog_desired_endpoints",
        )
        description = models.TextField(blank=True, null=True)

        class Meta:
            ordering = ("desired_node__name", "endpoint_type", "name")
            verbose_name = "desired endpoint"
            verbose_name_plural = "desired endpoints"
            constraints = (
                models.UniqueConstraint(
                    fields=("desired_node", "name", "endpoint_type"),
                    name="nic_unique_endpoint_per_node_type",
                ),
            )

        def __str__(self) -> str:
            return f"{self.desired_node}: {self.name}"

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:desiredendpoint", args=[self.pk])


    @extras_features("graphql")
    class DesiredServicePlacement(PrimaryModel):
        """Desired binding of one service instance to one desired node."""

        STATE_ACTIVE = "active"
        STATE_DISABLED = "disabled"
        DESIRED_STATE_CHOICES = (
            (STATE_ACTIVE, "Active"),
            (STATE_DISABLED, "Disabled"),
        )

        SOURCE_MANUAL = "manual"
        SOURCE_YAML = "yaml"
        SOURCE_POLICY = "policy"
        SOURCE_GENERATED = "generated"
        ASSIGNMENT_SOURCE_CHOICES = (
            (SOURCE_MANUAL, "Manual"),
            (SOURCE_YAML, "YAML"),
            (SOURCE_POLICY, "Policy"),
            (SOURCE_GENERATED, "Generated"),
        )

        desired_service = models.ForeignKey(
            DesiredService,
            on_delete=models.PROTECT,
            related_name="placements",
        )
        desired_node = models.ForeignKey(
            DesiredNode,
            on_delete=models.PROTECT,
            related_name="service_placements",
        )
        desired_endpoint = models.ForeignKey(
            DesiredEndpoint,
            on_delete=models.PROTECT,
            blank=True,
            null=True,
            related_name="service_placements",
        )
        instance_name = models.SlugField(max_length=255)
        desired_state = models.CharField(
            max_length=32,
            choices=DESIRED_STATE_CHOICES,
            default=STATE_ACTIVE,
        )
        instance_role = models.CharField(max_length=64, blank=True, null=True)
        deployment_profile = models.SlugField(max_length=255)
        config_schema_version = models.CharField(
            max_length=64,
            default="1",
        )
        config = models.JSONField(default=dict, blank=True)
        assignment_source = models.CharField(
            max_length=32,
            choices=ASSIGNMENT_SOURCE_CHOICES,
            default=SOURCE_MANUAL,
        )
        reason = models.TextField(blank=True, null=True)

        class Meta:
            ordering = ("desired_service__name", "instance_name")
            verbose_name = "desired service placement"
            verbose_name_plural = "desired service placements"
            constraints = (
                models.UniqueConstraint(
                    fields=("desired_service", "instance_name"),
                    name="nic_unique_service_instance",
                ),
                models.CheckConstraint(
                    check=~models.Q(deployment_profile=""),
                    name="nic_placement_profile_nonempty",
                ),
                models.CheckConstraint(
                    check=~models.Q(config_schema_version=""),
                    name="nic_placement_schema_nonempty",
                ),
                models.CheckConstraint(
                    check=models.expressions.RawSQL(
                        "jsonb_typeof(config) = 'object'",
                        (),
                        output_field=models.BooleanField(),
                    ),
                    name="nic_placement_config_object",
                ),
            )

        def __str__(self) -> str:
            return f"{self.desired_service}:{self.instance_name} on {self.desired_node}"

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:desiredserviceplacement", args=[self.pk])

        def clean(self):
            """Validate placement-owned values and endpoint ownership."""

            super().clean()
            errors = {}
            if not str(self.deployment_profile or "").strip():
                errors["deployment_profile"] = "Deployment profile must be non-empty."
            if not str(self.config_schema_version or "").strip():
                errors["config_schema_version"] = "Config schema version must be non-empty."
            if not isinstance(self.config, dict):
                errors["config"] = "Placement config must be a JSON object."
            if (
                self.desired_endpoint_id
                and self.desired_node_id
                and self.desired_endpoint.desired_node_id != self.desired_node_id
            ):
                errors["desired_endpoint"] = "Selected endpoint must belong to the placement node."
            if errors:
                raise ValidationError(errors)


    @extras_features("graphql")
    class DesiredNodeOperationalConfig(PrimaryModel):
        """Explicit non-service execution policy for one desired node."""

        ACTUAL_REQUIRED = "required"
        ACTUAL_DECLARED = "declared"
        ACTUAL_STATE_POLICY_CHOICES = (
            (ACTUAL_REQUIRED, "Required"),
            (ACTUAL_DECLARED, "Declared"),
        )

        HOST_OS_LINUX = "linux"
        HOST_OS_MACOS = "macos"
        EXPECTED_HOST_OS_CHOICES = (
            (HOST_OS_LINUX, "Linux"),
            (HOST_OS_MACOS, "macOS"),
        )

        HOST_OS_HAOS = "haos"
        DECLARED_HOST_OS_CHOICES = ((HOST_OS_HAOS, "Home Assistant OS"),)

        CONNECTION_LOCAL = "local"
        CONNECTION_TAILSCALE = "tailscale"
        CONNECTION_PATH_CHOICES = (
            (CONNECTION_LOCAL, "Local"),
            (CONNECTION_TAILSCALE, "Tailscale"),
        )

        POWER_NONE = "none"
        POWER_WOL = "wol"
        POWER_MACOS_SLEEP = "macos_sleep"
        POWER_CONTROL_CHOICES = (
            (POWER_NONE, "None"),
            (POWER_WOL, "Wake-on-LAN"),
            (POWER_MACOS_SLEEP, "macOS sleep"),
        )

        desired_node = models.OneToOneField(
            DesiredNode,
            on_delete=models.PROTECT,
            related_name="operational_config",
        )
        actual_state_policy = models.CharField(
            max_length=32,
            choices=ACTUAL_STATE_POLICY_CHOICES,
        )
        expected_host_os = models.CharField(
            max_length=32,
            choices=EXPECTED_HOST_OS_CHOICES,
            blank=True,
            null=True,
        )
        declared_host_os = models.CharField(
            max_length=32,
            choices=DECLARED_HOST_OS_CHOICES,
            blank=True,
            null=True,
        )
        connection_path = models.CharField(
            max_length=32,
            choices=CONNECTION_PATH_CHOICES,
        )
        local_endpoint = models.ForeignKey(
            DesiredEndpoint,
            on_delete=models.PROTECT,
            blank=True,
            null=True,
            related_name="local_operational_configs",
        )
        tailscale_endpoint = models.ForeignKey(
            DesiredEndpoint,
            on_delete=models.PROTECT,
            blank=True,
            null=True,
            related_name="tailscale_operational_configs",
        )
        ansible_port = models.PositiveIntegerField(blank=True, null=True)
        power_control = models.CharField(
            max_length=32,
            choices=POWER_CONTROL_CHOICES,
            default=POWER_NONE,
        )
        is_laptop = models.BooleanField(default=False)

        class Meta:
            ordering = ("desired_node__name",)
            verbose_name = "desired node operational config"
            verbose_name_plural = "desired node operational configs"
            constraints = (
                models.CheckConstraint(
                    check=(
                        models.Q(
                            actual_state_policy="required",
                            expected_host_os__in=("linux", "macos"),
                            declared_host_os__isnull=True,
                        )
                        | models.Q(
                            actual_state_policy="declared",
                            expected_host_os__isnull=True,
                            declared_host_os="haos",
                        )
                    ),
                    name="nic_operational_host_os_policy",
                ),
            )

        def __str__(self) -> str:
            return f"{self.desired_node} operational config"

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:desirednodeoperationalconfig", args=[self.pk])

        def clean(self):
            """Validate policy-dependent fields, endpoint ownership, and safe power policy."""

            super().clean()
            errors = {}
            if self.actual_state_policy == self.ACTUAL_REQUIRED:
                if self.expected_host_os not in {self.HOST_OS_LINUX, self.HOST_OS_MACOS}:
                    errors["expected_host_os"] = "Required actual state needs expected_host_os=linux or macos."
                if self.declared_host_os is not None:
                    errors["declared_host_os"] = "Required actual state forbids declared_host_os."
                platform = self.expected_host_os
            elif self.actual_state_policy == self.ACTUAL_DECLARED:
                if self.declared_host_os != self.HOST_OS_HAOS:
                    errors["declared_host_os"] = "Declared actual state supports only declared_host_os=haos."
                if self.expected_host_os is not None:
                    errors["expected_host_os"] = "Declared actual state forbids expected_host_os."
                platform = self.declared_host_os
            else:
                platform = None

            for field_name in ("local_endpoint", "tailscale_endpoint"):
                endpoint_id = getattr(self, f"{field_name}_id")
                if endpoint_id and self.desired_node_id:
                    endpoint = getattr(self, field_name)
                    if endpoint.desired_node_id != self.desired_node_id:
                        errors[field_name] = "Selected endpoint must belong to the configured node."

            if self.connection_path == self.CONNECTION_TAILSCALE:
                if not self.tailscale_endpoint_id or not _endpoint_has_usable_ip(self.tailscale_endpoint):
                    errors["tailscale_endpoint"] = "Tailscale connection requires an endpoint with a valid IP address."
            if self.actual_state_policy == self.ACTUAL_DECLARED and self.connection_path == self.CONNECTION_LOCAL:
                if not self.local_endpoint_id or not _endpoint_is_usable_local(self.local_endpoint):
                    errors["local_endpoint"] = "Declared local connection requires an endpoint with an IP, DNS, or mDNS address."

            allowed_power = {
                self.HOST_OS_LINUX: {self.POWER_NONE, self.POWER_WOL},
                self.HOST_OS_MACOS: {self.POWER_NONE, self.POWER_MACOS_SLEEP},
                self.HOST_OS_HAOS: {self.POWER_NONE},
            }
            if platform in allowed_power and self.power_control not in allowed_power[platform]:
                errors["power_control"] = f"Power control {self.power_control!r} is invalid for {platform}."

            if self.ansible_port is not None and not 1 <= self.ansible_port <= 65535:
                errors["ansible_port"] = "Ansible port must be between 1 and 65535."
            if errors:
                raise ValidationError(errors)


    @extras_features("graphql")
    class DesiredIPRange(PrimaryModel):
        """Desired address range intent managed by nintent."""

        RANGE_POLICY_STATIC_POOL = "static_pool"
        RANGE_POLICY_DHCP_RESERVABLE_POOL = "dhcp_reservable_pool"
        RANGE_POLICY_DHCP_DYNAMIC_POOL = "dhcp_dynamic_pool"
        RANGE_POLICY_EXCLUDED = "excluded"
        RANGE_POLICY_CHOICES = (
            (RANGE_POLICY_STATIC_POOL, "Static pool"),
            (RANGE_POLICY_DHCP_RESERVABLE_POOL, "DHCP reservable pool"),
            (RANGE_POLICY_DHCP_DYNAMIC_POOL, "DHCP dynamic pool"),
            (RANGE_POLICY_EXCLUDED, "Excluded"),
        )

        LIFECYCLE_PLANNED = "planned"
        LIFECYCLE_APPROVED = "approved"
        LIFECYCLE_ACTIVE = "active"
        LIFECYCLE_DEPRECATED = "deprecated"
        LIFECYCLE_RETIRED = "retired"
        LIFECYCLE_CHOICES = (
            (LIFECYCLE_PLANNED, "Planned"),
            (LIFECYCLE_APPROVED, "Approved"),
            (LIFECYCLE_ACTIVE, "Active"),
            (LIFECYCLE_DEPRECATED, "Deprecated"),
            (LIFECYCLE_RETIRED, "Retired"),
        )

        name = models.CharField(max_length=255)
        slug = models.SlugField(max_length=255, unique=True)
        start_address = models.CharField(max_length=128)
        end_address = models.CharField(max_length=128)
        range_policy = models.CharField(
            max_length=64,
            choices=RANGE_POLICY_CHOICES,
            default=RANGE_POLICY_STATIC_POOL,
        )
        lifecycle = models.CharField(
            max_length=64,
            choices=LIFECYCLE_CHOICES,
            default=LIFECYCLE_PLANNED,
        )
        generate_dnsmasq = models.BooleanField(default=False)
        dnsmasq_options = models.JSONField(default=dict, blank=True)
        description = models.TextField(blank=True, null=True)

        class Meta:
            ordering = ("start_address", "end_address", "name")
            verbose_name = "desired IP range"
            verbose_name_plural = "desired IP ranges"

        def __str__(self) -> str:
            return self.name

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:desirediprange", args=[self.pk])
