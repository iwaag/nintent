"""Database models for the Nautobot Intent Catalog App."""

from __future__ import annotations

import ipaddress

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
        DESIRED_PRESENCE_ABSENT,
        DESIRED_PRESENCE_PRESENT,
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
        desired_presence_requires_retired,
        endpoint_has_usable_ip,
        is_actionable_lifecycle,
        link_source_pairing_is_valid,
        normalize_mac_address,
        select_compute_primary_endpoint,
        validate_config_schema_version,
        validate_desired_presence,
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

    @extras_features("graphql")
    class DesiredService(PrimaryModel):
        """Desired service generated from source metadata."""

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
        slug = models.SlugField(max_length=255, unique=True)
        lifecycle = models.CharField(
            max_length=64,
            choices=LIFECYCLE_CHOICES,
            default=LIFECYCLE_PROPOSED,
        )
        class Meta:
            ordering = ("name",)
            verbose_name = "desired service"
            verbose_name_plural = "desired services"

        def __str__(self) -> str:
            return self.name

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:desiredservice", args=[self.pk])


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
        accepted_actual_types = models.JSONField(
            default=list,
            blank=True,
            help_text=(
                "Nautobot object types that may realize this desired node. "
                "Allowed values are device, virtual_machine, and container."
            ),
        )
        expected_spec = models.JSONField(default=dict, blank=True)
        realized_device = models.ForeignKey(
            "dcim.Device",
            on_delete=models.SET_NULL,
            blank=True,
            null=True,
            related_name="intent_catalog_desired_nodes",
        )

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
        gateway_address = models.CharField(max_length=128, blank=True, null=True)
        ip_policy = models.CharField(
            max_length=64,
            choices=IP_POLICY_CHOICES,
            default=IP_POLICY_EXTERNAL,
        )
        mac_address = models.CharField(max_length=17, blank=True, null=True)
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
            try:
                self.mac_address = normalize_mac_address(self.mac_address)
            except ComputeContractError as exc:
                errors["mac_address"] = str(exc)
            if self.gateway_address:
                try:
                    interface = ipaddress.ip_interface(self.ip_address or "")
                    gateway = ipaddress.ip_address(self.gateway_address)
                    if self.ip_policy != self.IP_POLICY_STATIC or interface.version != 4 or gateway.version != 4:
                        raise ValueError("gateway_address requires ip_policy static and an IPv4 CIDR ip_address.")
                    if gateway not in interface.network or gateway in {interface.network.network_address, interface.network.broadcast_address}:
                        raise ValueError("gateway_address must be a usable IPv4 address in the ip_address subnet.")
                except ValueError as exc:
                    errors["gateway_address"] = str(exc)
            if errors:
                raise ValidationError(errors)


    @extras_features("graphql")
    class DesiredComputePlatform(PrimaryModel):
        """A Proxmox scope capable of realizing desired compute instances."""

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
        config = models.JSONField(default=dict, blank=True)
        realized_cluster = models.ForeignKey(
            "virtualization.Cluster",
            on_delete=models.SET_NULL,
            blank=True,
            null=True,
            related_name="intent_catalog_desired_compute_platforms",
        )

        class Meta:
            ordering = ("name",)
            verbose_name = "desired compute platform"
            verbose_name_plural = "desired compute platforms"
            constraints = (
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
                self.config = validate_platform_config(self.config)
            except ComputeContractError as exc:
                errors["config"] = str(exc)

            if self.control_node_id and self.control_node.lifecycle == DesiredNode.LIFECYCLE_RETIRED:
                errors["control_node"] = "The control node must not be retired."

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
        if not desired_presence_requires_retired(instance.desired_presence, effective):
            raise ValidationError(
                {
                    "desired_presence": (
                        "desired_presence='absent' requires effective lifecycle 'retired'; "
                        f"the effective lifecycle is {effective!r}."
                    )
                }
            )
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

        DESIRED_PRESENCE_PRESENT = DESIRED_PRESENCE_PRESENT
        DESIRED_PRESENCE_ABSENT = DESIRED_PRESENCE_ABSENT
        DESIRED_PRESENCE_CHOICES = (
            (DESIRED_PRESENCE_PRESENT, "Present"),
            (DESIRED_PRESENCE_ABSENT, "Absent"),
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
        desired_presence = models.CharField(
            max_length=16,
            choices=DESIRED_PRESENCE_CHOICES,
            default=DESIRED_PRESENCE_PRESENT,
        )
        vcpus = models.PositiveIntegerField()
        memory_mb = models.PositiveIntegerField()
        root_disk_gb = models.PositiveIntegerField()
        config = models.JSONField(default=dict, blank=True)
        realized_vm = models.ForeignKey(
            "virtualization.VirtualMachine",
            on_delete=models.SET_NULL,
            blank=True,
            null=True,
            related_name="intent_catalog_desired_compute_instances",
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
                self.desired_presence = validate_desired_presence(self.desired_presence)
            except ComputeContractError as exc:
                errors["desired_presence"] = str(exc)
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
                self.config = validate_instance_config(self.config, instance_kind=self.instance_kind)
            except ComputeContractError as exc:
                errors["config"] = str(exc)

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
        deployment_profile = models.SlugField(max_length=255)
        config_schema_version = models.CharField(
            max_length=64,
            default="1",
        )
        config = models.JSONField(default=dict, blank=True)

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
    class DesiredServiceBinding(PrimaryModel):
        """A consumer placement's declared requirement on a provider service.

        Per idea-A section 3.1: identity only, no status/type/notes/lifecycle. Resolution
        (which provider placement/endpoint satisfies the binding) is computed, never stored.
        """

        consumer_placement = models.ForeignKey(
            DesiredServicePlacement,
            on_delete=models.PROTECT,
            related_name="service_bindings",
        )
        binding_name = models.SlugField(max_length=255)
        provider_service = models.ForeignKey(
            DesiredService,
            on_delete=models.PROTECT,
            related_name="inbound_bindings",
        )

        class Meta:
            ordering = ("consumer_placement__instance_name", "binding_name")
            verbose_name = "desired service binding"
            verbose_name_plural = "desired service bindings"
            constraints = (
                models.UniqueConstraint(
                    fields=("consumer_placement", "binding_name"),
                    name="nic_unique_binding_per_placement",
                ),
            )

        def __str__(self) -> str:
            return f"{self.consumer_placement}: {self.binding_name} -> {self.provider_service}"

        def get_absolute_url(self) -> str:
            return reverse("plugins:nautobot_intent_catalog:desiredservicebinding", args=[self.pk])


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

        STATUS_ACTIVE = "active"
        STATUS_SUPERSEDED = "superseded"
        STATUS_CHOICES = (
            (STATUS_ACTIVE, "Active"),
            (STATUS_SUPERSEDED, "Superseded"),
        )

        title = models.CharField(max_length=255)
        body = models.TextField()
        authorship = models.CharField(max_length=32, choices=AUTHORSHIP_CHOICES)
        status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

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
