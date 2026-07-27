"""Database models for the Nautobot Intent Catalog App."""

from __future__ import annotations

def _endpoint_is_usable_local(endpoint) -> bool:
    return endpoint_has_usable_ip(endpoint) or any(
        str(getattr(endpoint, field_name, "") or "").strip()
        for field_name in ("dns_name", "mdns_name")
    )


try:
    from django.core.exceptions import ValidationError
    from django.db import models
    from django.db.models.fields.json import KeyTextTransform
    from django.db.models.functions import Cast
    from django.urls import reverse
    from nautobot.apps.models import PrimaryModel, extras_features

    from .compute_contract import (
        CONFIG_SCHEMA_VERSION_V1,
        COMPUTE_PRIMARY_ENDPOINT_AMBIGUOUS,
        COMPUTE_PRIMARY_ENDPOINT_MISSING,
        ComputeContractError,
        INSTANCE_KIND_CONTAINER,
        INSTANCE_KIND_VIRTUAL_MACHINE,
        MEMORY_MB_MAX,
        MEMORY_MB_MIN,
        POWER_STATE_RUNNING,
        POWER_STATE_STOPPED,
        PROVIDER_TYPE_PROXMOX,
        ROOT_DISK_GB_MAX,
        ROOT_DISK_GB_MIN,
        VCPUS_MAX,
        VCPUS_MIN,
        effective_lifecycle,
        effective_value,
        endpoint_has_usable_ip,
        is_actionable_lifecycle,
        link_source_pairing_is_valid,
        normalize_mac_address,
        select_compute_primary_endpoint,
        validate_config_schema_version,
        validate_instance_config,
        validate_memory_mb,
        validate_platform_config,
        validate_provider_type,
        validate_root_disk_gb,
        validate_vcpus,
    )
except ImportError:  # pragma: no cover - Nautobot/Django are unavailable in local unit tests.
    PrimaryModel = object  # type: ignore[assignment]
else:

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
        analysis_provenance = models.JSONField(default=dict, blank=True, editable=False)
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
            default=LIFECYCLE_ACTIVE,
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
        realized_device_source = models.CharField(
            max_length=16,
            choices=(("derived", "Derived"), ("override", "Override")),
            blank=True,
            null=True,
            editable=False,
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

            source_errors = {}
            for relation_name in ("realized_device",):
                relation_id = getattr(self, f"{relation_name}_id")
                source = getattr(self, f"{relation_name}_source")
                if bool(relation_id) != bool(source):
                    source_errors[f"{relation_name}_source"] = (
                        f"{relation_name}_source must be set exactly when {relation_name} is set."
                    )
            if source_errors:
                raise ValidationError(source_errors)

            if (
                self.pk
                and self.lifecycle == self.LIFECYCLE_RETIRED
                and self.controlled_compute_platforms.exists()
            ):
                raise ValidationError(
                    {
                        "lifecycle": (
                            "A DesiredNode that controls a DesiredComputePlatform cannot be retired."
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
            default=IP_POLICY_EXTERNAL,
        )
        mac_address = models.CharField(max_length=17, blank=True, null=True)
        dns_name = models.CharField(max_length=255, blank=True, null=True)
        dns_name_source = models.CharField(
            max_length=16,
            choices=(("derived", "Derived"), ("intent", "Intent")),
            blank=True,
            null=True,
            editable=False,
        )
        mdns_name = models.CharField(max_length=255, blank=True, null=True)
        mdns_name_source = models.CharField(
            max_length=16,
            choices=(("derived", "Derived"), ("intent", "Intent")),
            blank=True,
            null=True,
            editable=False,
        )
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
        realized_ip_address_source = models.CharField(
            max_length=16,
            choices=(("derived", "Derived"), ("override", "Override")),
            blank=True,
            null=True,
            editable=False,
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
                models.UniqueConstraint(
                    fields=("mac_address",),
                    condition=models.Q(mac_address__isnull=False),
                    name="nic_unique_desired_mac_address",
                ),
            )

        def __str__(self) -> str:
            return f"{self.desired_node}: {self.name}"

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:desiredendpoint", args=[self.pk])

        def clean(self):
            super().clean()
            errors = {}
            for value_name in ("dns_name", "mdns_name", "realized_ip_address"):
                value = (
                    getattr(self, "realized_ip_address_id")
                    if value_name == "realized_ip_address"
                    else getattr(self, value_name)
                )
                source = getattr(self, f"{value_name}_source")
                if bool(value) != bool(source):
                    errors[f"{value_name}_source"] = (
                        f"{value_name}_source must be set exactly when {value_name} is set."
                    )
            try:
                self.mac_address = normalize_mac_address(self.mac_address)
            except ComputeContractError as exc:
                errors["mac_address"] = str(exc)
            if errors:
                raise ValidationError(errors)


    @extras_features("graphql")
    class DesiredComputePlatform(PrimaryModel):
        """A Proxmox scope capable of realizing desired compute instances."""

        PROVIDER_TYPE_PROXMOX = PROVIDER_TYPE_PROXMOX
        PROVIDER_TYPE_CHOICES = ((PROVIDER_TYPE_PROXMOX, "Proxmox"),)

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
        provider_type = models.CharField(
            max_length=32,
            choices=PROVIDER_TYPE_CHOICES,
            default=PROVIDER_TYPE_PROXMOX,
        )
        lifecycle = models.CharField(
            max_length=64,
            choices=LIFECYCLE_CHOICES,
            default=LIFECYCLE_ACTIVE,
        )
        control_node = models.ForeignKey(
            DesiredNode,
            on_delete=models.PROTECT,
            related_name="controlled_compute_platforms",
        )
        config_schema_version = models.CharField(
            max_length=16,
            default=CONFIG_SCHEMA_VERSION_V1,
            editable=False,
        )
        config = models.JSONField(default=dict, blank=True)
        realized_cluster = models.ForeignKey(
            "virtualization.Cluster",
            on_delete=models.SET_NULL,
            blank=True,
            null=True,
            related_name="intent_catalog_desired_compute_platforms",
        )
        realized_cluster_source = models.CharField(
            max_length=16,
            choices=(("derived", "Derived"), ("override", "Override")),
            blank=True,
            null=True,
            editable=False,
        )

        class Meta:
            ordering = ("name",)
            verbose_name = "desired compute platform"
            verbose_name_plural = "desired compute platforms"
            constraints = (
                models.CheckConstraint(
                    check=models.Q(provider_type="proxmox"),
                    name="dcp_provider_type_proxmox",
                ),
                models.CheckConstraint(
                    check=models.Q(config_schema_version="v1"),
                    name="dcp_config_schema_v1",
                ),
                models.CheckConstraint(
                    check=models.expressions.RawSQL(
                        "jsonb_typeof(config) = 'object'",
                        (),
                        output_field=models.BooleanField(),
                    ),
                    name="dcp_config_object",
                ),
            )

        def __str__(self) -> str:
            return self.name

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:desiredcomputeplatform", args=[self.pk])

        def clean(self):
            super().clean()
            errors = {}
            try:
                validate_provider_type(self.provider_type)
            except ComputeContractError as exc:
                errors["provider_type"] = str(exc)

            try:
                self.config_schema_version = validate_config_schema_version(
                    self.config_schema_version or None
                )
            except ComputeContractError as exc:
                errors["config_schema_version"] = str(exc)

            try:
                self.config = validate_platform_config(self.config)
            except ComputeContractError as exc:
                errors["config"] = str(exc)

            if self.control_node_id and self.control_node.lifecycle == DesiredNode.LIFECYCLE_RETIRED:
                errors["control_node"] = "The control node must not be retired."

            if not link_source_pairing_is_valid(self.realized_cluster_id, self.realized_cluster_source):
                errors["realized_cluster_source"] = (
                    "realized_cluster_source must be set exactly when realized_cluster is set."
                )

            if errors:
                raise ValidationError(errors)


    def _resolve_compute_effective_value(instance, *, instance_key, platform_key):
        instance_config = instance.config or {}
        platform_config = instance.platform.config or {} if instance.platform_id else {}
        return effective_value(
            instance_value=instance_config.get(instance_key),
            platform_value=platform_config.get(platform_key),
        )


    def validate_compute_instance_topology(instance) -> str:
        """Shared service/model-boundary validator for one DesiredComputeInstance.

        Called from `DesiredComputeInstance.clean()` and from every other supported write path
        (forms, REST, YAML import) that can change node/platform/endpoint/instance state affecting
        compute topology, per plan Section 5.5. Returns the effective lifecycle. A
        planned/deprecated/retired instance is a non-actionable draft and is not further checked;
        an active/approved instance must resolve effective storage/bridge and exactly one
        NIC-bearing primary endpoint with a canonical desired MAC.
        """

        node = instance.desired_node
        platform = instance.platform
        effective = effective_lifecycle(node.lifecycle, platform.lifecycle)
        if not is_actionable_lifecycle(effective):
            return effective

        problems = []
        storage = _resolve_compute_effective_value(
            instance, instance_key="storage", platform_key="default_storage"
        )
        bridge = _resolve_compute_effective_value(
            instance, instance_key="bridge", platform_key="default_bridge"
        )
        if storage["provenance"] == "unresolved":
            problems.append("effective storage is unresolved")
        if bridge["provenance"] == "unresolved":
            problems.append("effective bridge is unresolved")

        _endpoint, endpoint_problem = select_compute_primary_endpoint(list(node.desired_endpoints.all()))
        if endpoint_problem == COMPUTE_PRIMARY_ENDPOINT_MISSING:
            problems.append(COMPUTE_PRIMARY_ENDPOINT_MISSING)
        elif endpoint_problem == COMPUTE_PRIMARY_ENDPOINT_AMBIGUOUS:
            problems.append(COMPUTE_PRIMARY_ENDPOINT_AMBIGUOUS)

        if problems:
            raise ValidationError({"__all__": problems})
        return effective


    @extras_features("graphql")
    class DesiredComputeInstance(PrimaryModel):
        """The compute realization required by exactly one DesiredNode."""

        INSTANCE_KIND_CONTAINER = INSTANCE_KIND_CONTAINER
        INSTANCE_KIND_VIRTUAL_MACHINE = INSTANCE_KIND_VIRTUAL_MACHINE
        INSTANCE_KIND_CHOICES = (
            (INSTANCE_KIND_CONTAINER, "Container"),
            (INSTANCE_KIND_VIRTUAL_MACHINE, "Virtual machine"),
        )

        POWER_STATE_RUNNING = POWER_STATE_RUNNING
        POWER_STATE_STOPPED = POWER_STATE_STOPPED
        POWER_STATE_CHOICES = (
            (POWER_STATE_RUNNING, "Running"),
            (POWER_STATE_STOPPED, "Stopped"),
        )

        desired_node = models.OneToOneField(
            DesiredNode,
            on_delete=models.CASCADE,
            related_name="desired_compute_instance",
        )
        platform = models.ForeignKey(
            DesiredComputePlatform,
            on_delete=models.PROTECT,
            related_name="desired_compute_instances",
        )
        instance_kind = models.CharField(max_length=32, choices=INSTANCE_KIND_CHOICES)
        desired_power_state = models.CharField(
            max_length=16,
            choices=POWER_STATE_CHOICES,
            default=POWER_STATE_RUNNING,
        )
        vcpus = models.PositiveIntegerField()
        memory_mb = models.PositiveIntegerField()
        root_disk_gb = models.PositiveIntegerField()
        config_schema_version = models.CharField(
            max_length=16,
            default=CONFIG_SCHEMA_VERSION_V1,
            editable=False,
        )
        config = models.JSONField(default=dict, blank=True)
        realized_vm = models.ForeignKey(
            "virtualization.VirtualMachine",
            on_delete=models.SET_NULL,
            blank=True,
            null=True,
            related_name="intent_catalog_desired_compute_instances",
        )
        realized_vm_source = models.CharField(
            max_length=16,
            choices=(("derived", "Derived"), ("override", "Override")),
            blank=True,
            null=True,
            editable=False,
        )

        class Meta:
            ordering = ("desired_node__name",)
            verbose_name = "desired compute instance"
            verbose_name_plural = "desired compute instances"
            constraints = (
                models.CheckConstraint(
                    check=models.Q(vcpus__gte=VCPUS_MIN) & models.Q(vcpus__lte=VCPUS_MAX),
                    name="dci_vcpus_bounds",
                ),
                models.CheckConstraint(
                    check=models.Q(memory_mb__gte=MEMORY_MB_MIN) & models.Q(memory_mb__lte=MEMORY_MB_MAX),
                    name="dci_memory_mb_bounds",
                ),
                models.CheckConstraint(
                    check=models.Q(root_disk_gb__gte=ROOT_DISK_GB_MIN)
                    & models.Q(root_disk_gb__lte=ROOT_DISK_GB_MAX),
                    name="dci_root_disk_gb_bounds",
                ),
                models.CheckConstraint(
                    check=models.Q(config_schema_version="v1"),
                    name="dci_config_schema_v1",
                ),
                models.CheckConstraint(
                    check=models.expressions.RawSQL(
                        "jsonb_typeof(config) = 'object'",
                        (),
                        output_field=models.BooleanField(),
                    ),
                    name="dci_config_object",
                ),
                models.UniqueConstraint(
                    "platform",
                    Cast(
                        KeyTextTransform("vmid", "config"),
                        output_field=models.BigIntegerField(),
                    ),
                    condition=models.Q(config__has_key="vmid"),
                    name="dci_unique_platform_vmid",
                ),
            )

        def __str__(self) -> str:
            return f"{self.desired_node}: {self.instance_kind}"

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:desiredcomputeinstance", args=[self.pk])

        def clean(self):
            super().clean()
            errors = {}
            try:
                self.vcpus = validate_vcpus(self.vcpus)
            except ComputeContractError as exc:
                errors["vcpus"] = str(exc)
            try:
                self.memory_mb = validate_memory_mb(self.memory_mb)
            except ComputeContractError as exc:
                errors["memory_mb"] = str(exc)
            try:
                self.root_disk_gb = validate_root_disk_gb(self.root_disk_gb)
            except ComputeContractError as exc:
                errors["root_disk_gb"] = str(exc)
            try:
                self.config_schema_version = validate_config_schema_version(
                    self.config_schema_version or None
                )
            except ComputeContractError as exc:
                errors["config_schema_version"] = str(exc)
            try:
                self.config = validate_instance_config(self.config, instance_kind=self.instance_kind)
            except ComputeContractError as exc:
                errors["config"] = str(exc)

            if not link_source_pairing_is_valid(self.realized_vm_id, self.realized_vm_source):
                errors["realized_vm_source"] = (
                    "realized_vm_source must be set exactly when realized_vm is set."
                )

            if not errors and self.realized_vm_id:
                platform = self.platform
                vm = self.realized_vm
                if not platform.realized_cluster_id or vm.cluster_id != platform.realized_cluster_id:
                    errors["realized_vm"] = (
                        "realized_vm must belong to the platform's realized_cluster."
                    )
                expected_guest_type = {
                    self.INSTANCE_KIND_CONTAINER: "lxc",
                    self.INSTANCE_KIND_VIRTUAL_MACHINE: "qemu",
                }[self.instance_kind]
                actual_guest_type = (vm.custom_field_data or {}).get("proxmox_guest_type")
                if actual_guest_type != expected_guest_type:
                    errors["realized_vm"] = (
                        f"realized_vm proxmox_guest_type must be {expected_guest_type!r}."
                    )
                requested_vmid = (self.config or {}).get("vmid")
                actual_vmid = (vm.custom_field_data or {}).get("proxmox_vmid")
                if requested_vmid is not None and requested_vmid != actual_vmid:
                    errors["realized_vm"] = "requested config.vmid must equal realized_vm proxmox_vmid."

            if errors:
                raise ValidationError(errors)

            if self.desired_node_id and self.platform_id:
                validate_compute_instance_topology(self)


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
    class DesiredNodeOperationalOverride(PrimaryModel):
        """Optional genuine exceptions to nctl's derived node operation values."""

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
            related_name="operational_override",
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
            blank=True,
            null=True,
        )
        local_endpoint = models.ForeignKey(
            DesiredEndpoint,
            on_delete=models.PROTECT,
            blank=True,
            null=True,
            related_name="local_operational_overrides",
        )
        tailscale_endpoint = models.ForeignKey(
            DesiredEndpoint,
            on_delete=models.PROTECT,
            blank=True,
            null=True,
            related_name="tailscale_operational_overrides",
        )
        ansible_port = models.PositiveIntegerField(blank=True, null=True)
        power_control = models.CharField(
            max_length=32,
            choices=POWER_CONTROL_CHOICES,
            blank=True,
            null=True,
        )
        is_laptop = models.BooleanField(blank=True, null=True)

        class Meta:
            ordering = ("desired_node__name",)
            verbose_name = "desired node operational override"
            verbose_name_plural = "desired node operational overrides"

        def __str__(self) -> str:
            return f"{self.desired_node} operational override"

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:desirednodeoperationaloverride", args=[self.pk])

        def clean(self):
            """Validate endpoint ownership and cross-field override consistency."""

            super().clean()
            errors = {}
            for field_name in ("local_endpoint", "tailscale_endpoint"):
                endpoint_id = getattr(self, f"{field_name}_id")
                if endpoint_id and self.desired_node_id:
                    endpoint = getattr(self, field_name)
                    if endpoint.desired_node_id != self.desired_node_id:
                        errors[field_name] = "Selected endpoint must belong to the configured node."

            if self.connection_path == self.CONNECTION_TAILSCALE:
                if not self.tailscale_endpoint_id or not endpoint_has_usable_ip(self.tailscale_endpoint):
                    errors["tailscale_endpoint"] = "Tailscale connection requires an endpoint with a valid IP address."
                if self.local_endpoint_id:
                    errors["local_endpoint"] = "Tailscale connection forbids a local endpoint override."
            elif self.tailscale_endpoint_id:
                errors["tailscale_endpoint"] = "A Tailscale endpoint requires connection_path=tailscale."

            if self.local_endpoint_id:
                if self.connection_path not in (None, self.CONNECTION_LOCAL):
                    errors["connection_path"] = "A local endpoint permits only connection_path=local."
                if not _endpoint_is_usable_local(self.local_endpoint):
                    errors["local_endpoint"] = "Local endpoint requires an IP, DNS, or mDNS address."

            if self.declared_host_os == self.HOST_OS_HAOS and self.power_control not in (None, self.POWER_NONE):
                errors["power_control"] = "HAOS permits only power_control=none."

            if self.ansible_port is not None and not 1 <= self.ansible_port <= 65535:
                errors["ansible_port"] = "Ansible port must be between 1 and 65535."
            meaningful = any(
                (
                    self.declared_host_os,
                    self.connection_path == self.CONNECTION_TAILSCALE,
                    self.local_endpoint_id,
                    self.tailscale_endpoint_id,
                    self.ansible_port,
                    self.power_control not in (None, self.POWER_NONE),
                    self.is_laptop is True,
                )
            )
            if not meaningful:
                errors["__all__"] = "At least one non-default operational override is required."
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


    @extras_features("graphql")
    class BrainDumpDocument(PrimaryModel):
        """User-originated free-form prose describing wishes, constraints, or preferences."""

        AUTHORSHIP_USER_DIRECT = "user_direct"
        AUTHORSHIP_AGENT_TRANSCRIBED = "agent_transcribed"
        AUTHORSHIP_CHOICES = (
            (AUTHORSHIP_USER_DIRECT, "User direct"),
            (AUTHORSHIP_AGENT_TRANSCRIBED, "Agent transcribed"),
        )

        title = models.CharField(max_length=255)
        body = models.TextField()
        authorship = models.CharField(max_length=32, choices=AUTHORSHIP_CHOICES)

        class Meta:
            ordering = ("-last_updated", "title")
            verbose_name = "Braindump document"
            verbose_name_plural = "Braindump documents"

        def __str__(self) -> str:
            return self.title

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:braindumpdocument", args=[self.pk])

        def clean(self):
            super().clean()
            errors = {}
            if not str(self.title or "").strip():
                errors["title"] = "Title must not be empty or whitespace-only."
            if not str(self.body or "").strip():
                errors["body"] = "Body must not be empty or whitespace-only."
            if errors:
                raise ValidationError(errors)


    @extras_features("graphql")
    class AlignmentReview(PrimaryModel):
        """The AI agent's latest natural-language reply to one Braindump."""

        braindump = models.OneToOneField(
            BrainDumpDocument,
            on_delete=models.CASCADE,
            related_name="alignment_review",
        )
        summary = models.TextField()

        class Meta:
            verbose_name = "Alignment review"
            verbose_name_plural = "Alignment reviews"

        def __str__(self) -> str:
            return f"Alignment review for {self.braindump}"

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:braindumpdocument", args=[self.braindump_id])

        def clean(self):
            super().clean()
            if not str(self.summary or "").strip():
                raise ValidationError({"summary": "Summary must not be empty or whitespace-only."})
