from __future__ import annotations

import unittest

from nautobot_intent_catalog.operations import hosts


class FakeValidationError(Exception):
    def __init__(self, message_dict):
        super().__init__(message_dict)
        self.message_dict = message_dict


class FakeIntegrityError(Exception):
    pass


class FakeQuerySet:
    def __init__(self, rows):
        self.rows = rows

    def exists(self):
        return bool(self.rows)


class FakeManager:
    def __init__(self, force_exists: bool = False):
        self.rows = []
        self.force_exists = force_exists

    def filter(self, **criteria):
        if self.force_exists:
            return FakeQuerySet([object()])
        return FakeQuerySet(
            [
                row
                for row in self.rows
                if all(getattr(row, field_name, None) == expected for field_name, expected in criteria.items())
            ]
        )

    def add(self, row):
        row.pk = len(self.rows) + 1
        self.rows.append(row)


class FakeTransaction:
    def __init__(self, *managers):
        self.managers = managers

    def atomic(self):
        return FakeAtomic(self.managers)


class FakeAtomic:
    def __init__(self, managers):
        self.managers = managers
        self.snapshots = None

    def __enter__(self):
        self.snapshots = [list(manager.rows) for manager in self.managers]
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is not None:
            for manager, snapshot in zip(self.managers, self.snapshots, strict=True):
                manager.rows = snapshot
        return False


class FakeModel:
    objects = FakeManager()

    def __init__(self, **attrs):
        self.pk = None
        for key, value in attrs.items():
            setattr(self, key, value)

    def full_clean(self):
        return None

    def save(self):
        self.__class__.objects.add(self)


class FakeDesiredNode(FakeModel):
    objects = FakeManager()

    def __str__(self):
        return self.name


class FakeDesiredEndpoint(FakeModel):
    objects = FakeManager()


class HostOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.originals = {
            "ValidationError": hosts.ValidationError,
            "DesiredNode": hosts.DesiredNode,
            "DesiredEndpoint": hosts.DesiredEndpoint,
            "transaction": hosts.transaction,
            "IntegrityError": hosts.IntegrityError,
        }
        self.addCleanup(self.restore_hosts_module)
        FakeDesiredNode.objects = FakeManager()
        FakeDesiredEndpoint.objects = FakeManager()
        hosts.ValidationError = FakeValidationError
        hosts.DesiredNode = FakeDesiredNode
        hosts.DesiredEndpoint = FakeDesiredEndpoint
        hosts.transaction = FakeTransaction(FakeDesiredNode.objects, FakeDesiredEndpoint.objects)
        hosts.IntegrityError = FakeIntegrityError

    def restore_hosts_module(self) -> None:
        for name, value in self.originals.items():
            setattr(hosts, name, value)

    def test_create_desired_node_with_primary_endpoint_creates_both_objects_with_defaults(self) -> None:
        result = hosts.create_desired_node_with_primary_endpoint(
            name="App VM 1",
            slug="app-vm-1",
            ip_address="192.0.2.10/32",
            dns_name="app-vm-1.example.test",
            mdns_name="app-vm-1.local",
        )

        self.assertIs(result.desired_node, FakeDesiredNode.objects.rows[0])
        self.assertIs(result.desired_endpoint, FakeDesiredEndpoint.objects.rows[0])
        self.assertEqual(result.desired_node.name, "App VM 1")
        self.assertEqual(result.desired_node.slug, "app-vm-1")
        self.assertEqual(result.desired_node.node_type, "virtual_machine")
        self.assertEqual(result.desired_node.accepted_actual_types, ["virtual_machine"])
        self.assertEqual(result.desired_node.lifecycle, "active")
        self.assertEqual(result.desired_endpoint.desired_node, result.desired_node)
        self.assertEqual(result.desired_endpoint.name, "primary")
        self.assertEqual(result.desired_endpoint.endpoint_type, "primary")
        self.assertEqual(result.desired_endpoint.ip_address, "192.0.2.10/32")
        self.assertEqual(result.desired_endpoint.dns_name, "app-vm-1.example.test")
        self.assertEqual(result.desired_endpoint.mdns_name, "app-vm-1.local")
        self.assertTrue(result.desired_endpoint.generate_dnsmasq)
        self.assertEqual(result.desired_endpoint.ip_policy, "dhcp_reserved")
        self.assertEqual(result.desired_endpoint.dnsmasq_record_type, "host_record")

    def test_create_desired_node_with_primary_endpoint_derives_vm_actual_types(self) -> None:
        result = hosts.create_desired_node_with_primary_endpoint(
            name="App VM 1",
            slug="app-vm-1",
            node_type="virtual_machine",
        )

        self.assertEqual(result.desired_node.accepted_actual_types, ["virtual_machine"])

    def test_create_desired_node_with_primary_endpoint_accepts_explicit_actual_types(self) -> None:
        result = hosts.create_desired_node_with_primary_endpoint(
            name="DNS Host",
            slug="dns-host",
            node_type="service_host",
            accepted_actual_types=["device", "virtual-machine", "device"],
        )

        self.assertEqual(result.desired_node.accepted_actual_types, ["device", "virtual_machine"])

    def test_create_desired_node_with_primary_endpoint_preserves_explicit_planned_lifecycle(self) -> None:
        result = hosts.create_desired_node_with_primary_endpoint(
            name="Staged VM",
            slug="staged-vm",
            lifecycle="planned",
        )

        self.assertEqual(result.desired_node.lifecycle, "planned")

    def test_blank_primary_endpoint_dns_and_mdns_names_are_defaulted(self) -> None:
        result = hosts.create_desired_node_with_primary_endpoint(
            name="PC1.local",
            slug="pc1",
            dns_name=" ",
            mdns_name=None,
        )

        self.assertEqual(result.desired_endpoint.name, "primary")
        self.assertEqual(result.desired_endpoint.endpoint_type, "primary")
        self.assertEqual(result.desired_endpoint.dns_name, "pc1.home.arpa")
        self.assertEqual(result.desired_endpoint.mdns_name, "pc1.local")

    def test_explicit_primary_endpoint_dns_and_mdns_names_are_preserved(self) -> None:
        result = hosts.create_desired_node_with_primary_endpoint(
            name="PC1.local",
            slug="pc1",
            dns_name="custom.example.test",
            mdns_name="custom.local",
        )

        self.assertEqual(result.desired_endpoint.dns_name, "custom.example.test")
        self.assertEqual(result.desired_endpoint.mdns_name, "custom.local")

    def test_non_primary_endpoint_dns_and_mdns_names_are_not_defaulted(self) -> None:
        result = hosts.create_desired_node_with_primary_endpoint(
            name="PC1.local",
            slug="pc1",
            endpoint_name="mgmt",
            endpoint_type="management",
        )

        self.assertEqual(result.desired_endpoint.name, "mgmt")
        self.assertEqual(result.desired_endpoint.endpoint_type, "management")
        self.assertIsNone(result.desired_endpoint.dns_name)
        self.assertIsNone(result.desired_endpoint.mdns_name)

    def test_slug_duplicate_returns_field_validation_error_without_creating_objects(self) -> None:
        existing = FakeDesiredNode(name="Existing", slug="app-vm-1")
        existing.save()

        with self.assertRaises(FakeValidationError) as context:
            hosts.create_desired_node_with_primary_endpoint(name="App VM 1", slug="app-vm-1")

        self.assertEqual(
            context.exception.message_dict,
            {"slug": ["A desired node with this slug already exists."]},
        )
        self.assertEqual(FakeDesiredNode.objects.rows, [existing])
        self.assertEqual(FakeDesiredEndpoint.objects.rows, [])

    def test_endpoint_identity_error_rolls_back_created_node(self) -> None:
        FakeDesiredEndpoint.objects.force_exists = True

        with self.assertRaises(FakeValidationError) as context:
            hosts.create_desired_node_with_primary_endpoint(name="App VM 1", slug="app-vm-1")

        self.assertEqual(
            context.exception.message_dict,
            {
                "endpoint_name": [
                    "A desired endpoint with this name and endpoint type already exists for the desired node."
                ]
            },
        )
        self.assertEqual(FakeDesiredNode.objects.rows, [])
        self.assertEqual(FakeDesiredEndpoint.objects.rows, [])


if __name__ == "__main__":
    unittest.main()
