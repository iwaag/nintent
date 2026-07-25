from __future__ import annotations

import unittest

from nautobot_intent_catalog.compute_contract import (
    ComputeContractError,
    effective_lifecycle,
    effective_single_source_value,
    effective_value,
    is_actionable_lifecycle,
    normalize_mac_address,
    validate_config_schema_version,
    validate_instance_config,
    validate_memory_mb,
    validate_platform_config,
    validate_provider_type,
    validate_root_disk_gb,
    validate_vcpus,
    validate_vmid,
)


class ProviderTypeTests(unittest.TestCase):
    def test_accepts_proxmox(self) -> None:
        self.assertEqual(validate_provider_type("proxmox"), "proxmox")

    def test_rejects_unknown_provider(self) -> None:
        with self.assertRaises(ComputeContractError) as ctx:
            validate_provider_type("aws")
        self.assertEqual(ctx.exception.code, "invalid_provider_type")

    def test_rejects_empty(self) -> None:
        with self.assertRaises(ComputeContractError):
            validate_provider_type("")


class ConfigSchemaVersionTests(unittest.TestCase):
    def test_omitted_defaults_to_v1(self) -> None:
        self.assertEqual(validate_config_schema_version(None), "v1")

    def test_explicit_v1_accepted(self) -> None:
        self.assertEqual(validate_config_schema_version("v1"), "v1")

    def test_explicit_other_value_rejected(self) -> None:
        with self.assertRaises(ComputeContractError) as ctx:
            validate_config_schema_version("v2")
        self.assertEqual(ctx.exception.code, "invalid_config_schema_version")

    def test_empty_string_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            validate_config_schema_version("")


class PlatformConfigTests(unittest.TestCase):
    def test_empty_object_is_valid(self) -> None:
        self.assertEqual(validate_platform_config({}), {})

    def test_partial_config_valid(self) -> None:
        self.assertEqual(
            validate_platform_config({"cluster_name": "aghub-proxmox"}),
            {"cluster_name": "aghub-proxmox"},
        )

    def test_full_config_valid_and_strips_whitespace(self) -> None:
        result = validate_platform_config(
            {
                "cluster_name": " aghub-proxmox ",
                "default_storage": "local-lvm",
                "default_bridge": "vmbr0",
            }
        )
        self.assertEqual(
            result,
            {
                "cluster_name": "aghub-proxmox",
                "default_storage": "local-lvm",
                "default_bridge": "vmbr0",
            },
        )

    def test_unknown_key_rejected(self) -> None:
        with self.assertRaises(ComputeContractError) as ctx:
            validate_platform_config({"api_url": "https://example"})
        self.assertEqual(ctx.exception.code, "unknown_config_key")

    def test_non_object_rejected(self) -> None:
        for bad in (None, [], "x", 1, True):
            with self.assertRaises(ComputeContractError) as ctx:
                validate_platform_config(bad)
            self.assertEqual(ctx.exception.code, "invalid_config_type")

    def test_wrong_scalar_type_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            validate_platform_config({"cluster_name": 123})

    def test_blank_identifier_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            validate_platform_config({"default_storage": "   "})

    def test_over_max_length_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            validate_platform_config({"default_bridge": "x" * 256})


class InstanceConfigTests(unittest.TestCase):
    def test_container_valid(self) -> None:
        result = validate_instance_config(
            {"vmid": 108, "template": "local:vztmpl/x.tar.zst", "unprivileged": True},
            instance_kind="container",
        )
        self.assertEqual(
            result,
            {"vmid": 108, "template": "local:vztmpl/x.tar.zst", "unprivileged": True},
        )

    def test_virtual_machine_valid_without_unprivileged(self) -> None:
        result = validate_instance_config(
            {"template": "local:iso/debian.iso"}, instance_kind="virtual_machine"
        )
        self.assertEqual(result, {"template": "local:iso/debian.iso"})

    def test_unknown_key_rejected(self) -> None:
        with self.assertRaises(ComputeContractError) as ctx:
            validate_instance_config(
                {"template": "x", "unprivileged": True, "cores": 2}, instance_kind="container"
            )
        self.assertEqual(ctx.exception.code, "unknown_config_key")

    def test_missing_template_rejected(self) -> None:
        with self.assertRaises(ComputeContractError) as ctx:
            validate_instance_config({"unprivileged": True}, instance_kind="container")
        self.assertEqual(ctx.exception.code, "missing_config_value")

    def test_boolean_as_vmid_rejected(self) -> None:
        with self.assertRaises(ComputeContractError) as ctx:
            validate_instance_config(
                {"template": "x", "vmid": True, "unprivileged": True}, instance_kind="container"
            )
        self.assertEqual(ctx.exception.code, "invalid_vmid")

    def test_container_missing_unprivileged_rejected(self) -> None:
        with self.assertRaises(ComputeContractError) as ctx:
            validate_instance_config({"template": "x"}, instance_kind="container")
        self.assertEqual(ctx.exception.code, "missing_config_value")

    def test_container_non_bool_unprivileged_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            validate_instance_config(
                {"template": "x", "unprivileged": "yes"}, instance_kind="container"
            )

    def test_virtual_machine_forbids_unprivileged(self) -> None:
        with self.assertRaises(ComputeContractError) as ctx:
            validate_instance_config(
                {"template": "x", "unprivileged": True}, instance_kind="virtual_machine"
            )
        self.assertEqual(ctx.exception.code, "invalid_config_key")

    def test_invalid_instance_kind_rejected(self) -> None:
        with self.assertRaises(ComputeContractError) as ctx:
            validate_instance_config({"template": "x"}, instance_kind="hypervisor")
        self.assertEqual(ctx.exception.code, "invalid_instance_kind")

    def test_wrong_type_template_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            validate_instance_config(
                {"template": 5, "unprivileged": True}, instance_kind="container"
            )

    def test_optional_storage_bridge(self) -> None:
        result = validate_instance_config(
            {
                "template": "x",
                "unprivileged": False,
                "storage": "local-lvm",
                "bridge": "vmbr1",
            },
            instance_kind="container",
        )
        self.assertEqual(result["storage"], "local-lvm")
        self.assertEqual(result["bridge"], "vmbr1")


class NumericBoundsTests(unittest.TestCase):
    def test_vcpus_bounds(self) -> None:
        self.assertEqual(validate_vcpus(1), 1)
        self.assertEqual(validate_vcpus(8192), 8192)
        with self.assertRaises(ComputeContractError):
            validate_vcpus(0)
        with self.assertRaises(ComputeContractError):
            validate_vcpus(8193)
        with self.assertRaises(ComputeContractError):
            validate_vcpus(True)
        with self.assertRaises(ComputeContractError):
            validate_vcpus(1.5)

    def test_memory_mb_bounds(self) -> None:
        self.assertEqual(validate_memory_mb(16), 16)
        self.assertEqual(validate_memory_mb(2147483647), 2147483647)
        with self.assertRaises(ComputeContractError):
            validate_memory_mb(15)
        with self.assertRaises(ComputeContractError):
            validate_memory_mb(2147483648)

    def test_root_disk_gb_bounds(self) -> None:
        self.assertEqual(validate_root_disk_gb(1), 1)
        self.assertEqual(validate_root_disk_gb(2147483647), 2147483647)
        with self.assertRaises(ComputeContractError):
            validate_root_disk_gb(0)
        with self.assertRaises(ComputeContractError):
            validate_root_disk_gb(2147483648)

    def test_vmid_bounds(self) -> None:
        self.assertEqual(validate_vmid(100), 100)
        self.assertEqual(validate_vmid(999999999), 999999999)
        with self.assertRaises(ComputeContractError):
            validate_vmid(99)
        with self.assertRaises(ComputeContractError):
            validate_vmid(1000000000)
        with self.assertRaises(ComputeContractError):
            validate_vmid(True)
        with self.assertRaises(ComputeContractError):
            validate_vmid("108")


class MacAddressTests(unittest.TestCase):
    def test_none_and_empty_become_none(self) -> None:
        self.assertIsNone(normalize_mac_address(None))
        self.assertIsNone(normalize_mac_address(""))
        self.assertIsNone(normalize_mac_address("   "))

    def test_colon_separated_normalizes_lowercase(self) -> None:
        self.assertEqual(normalize_mac_address("BC:24:11:23:DC:B7"), "bc:24:11:23:dc:b7")

    def test_hyphen_separated_normalizes_to_colon(self) -> None:
        self.assertEqual(normalize_mac_address("bc-24-11-23-dc-b7"), "bc:24:11:23:dc:b7")

    def test_already_canonical_is_idempotent(self) -> None:
        self.assertEqual(normalize_mac_address("bc:24:11:23:dc:b7"), "bc:24:11:23:dc:b7")

    def test_dotted_form_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            normalize_mac_address("bc24.1123.dcb7")

    def test_short_form_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            normalize_mac_address("bc:24:11:23:dc")

    def test_overlong_form_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            normalize_mac_address("bc:24:11:23:dc:b7:00")

    def test_mixed_separator_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            normalize_mac_address("bc:24-11:23:dc:b7")

    def test_non_hex_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            normalize_mac_address("zz:24:11:23:dc:b7")

    def test_list_value_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            normalize_mac_address(["bc", "24", "11", "23", "dc", "b7"])

    def test_numeric_value_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            normalize_mac_address(123456789012)

    def test_boolean_value_rejected(self) -> None:
        with self.assertRaises(ComputeContractError):
            normalize_mac_address(True)


class EffectiveLifecycleTests(unittest.TestCase):
    def test_both_active_is_active(self) -> None:
        self.assertEqual(effective_lifecycle("active", "active"), "active")

    def test_node_active_platform_approved_is_approved(self) -> None:
        self.assertEqual(effective_lifecycle("active", "approved"), "approved")

    def test_either_planned_is_planned(self) -> None:
        self.assertEqual(effective_lifecycle("planned", "active"), "planned")
        self.assertEqual(effective_lifecycle("active", "planned"), "planned")

    def test_either_deprecated_is_deprecated(self) -> None:
        self.assertEqual(effective_lifecycle("deprecated", "active"), "deprecated")
        self.assertEqual(effective_lifecycle("active", "deprecated"), "deprecated")

    def test_either_retired_is_retired(self) -> None:
        self.assertEqual(effective_lifecycle("retired", "active"), "retired")
        self.assertEqual(effective_lifecycle("active", "retired"), "retired")

    def test_retired_wins_over_deprecated_and_planned(self) -> None:
        self.assertEqual(effective_lifecycle("retired", "deprecated"), "retired")
        self.assertEqual(effective_lifecycle("planned", "retired"), "retired")

    def test_deprecated_wins_over_planned(self) -> None:
        self.assertEqual(effective_lifecycle("deprecated", "planned"), "deprecated")

    def test_both_approved_is_approved(self) -> None:
        self.assertEqual(effective_lifecycle("approved", "approved"), "approved")

    def test_is_actionable(self) -> None:
        self.assertTrue(is_actionable_lifecycle("active"))
        self.assertTrue(is_actionable_lifecycle("approved"))
        self.assertFalse(is_actionable_lifecycle("planned"))
        self.assertFalse(is_actionable_lifecycle("deprecated"))
        self.assertFalse(is_actionable_lifecycle("retired"))


class EffectiveValueTests(unittest.TestCase):
    def test_instance_override_wins(self) -> None:
        self.assertEqual(
            effective_value(instance_value="local-lvm", platform_value="local"),
            {"value": "local-lvm", "provenance": "instance_override"},
        )

    def test_platform_default_used_when_no_override(self) -> None:
        self.assertEqual(
            effective_value(instance_value=None, platform_value="local"),
            {"value": "local", "provenance": "platform_default"},
        )

    def test_unresolved_when_neither_present(self) -> None:
        self.assertEqual(
            effective_value(instance_value=None, platform_value=None),
            {"value": None, "provenance": "unresolved"},
        )

    def test_single_source_present(self) -> None:
        self.assertEqual(
            effective_single_source_value("aghub-proxmox"),
            {"value": "aghub-proxmox", "provenance": "intent"},
        )

    def test_single_source_unresolved(self) -> None:
        self.assertEqual(
            effective_single_source_value(None),
            {"value": None, "provenance": "unresolved"},
        )


if __name__ == "__main__":
    unittest.main()
