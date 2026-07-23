from __future__ import annotations

from types import SimpleNamespace
import unittest

from nautobot_intent_catalog.operations.ipam import (
    IPAM_SUMMARY_SCHEMA_VERSION,
    build_ipam_reconcile_summary,
    ip_address_create_fields,
    plan_endpoint_ipam_reconcile,
)


def obj(**kwargs):
    return SimpleNamespace(**kwargs)


def node(**overrides):
    data = {"name": "edge-1", "slug": "edge-1"}
    data.update(overrides)
    return obj(**data)


def endpoint(**overrides):
    data = {
        "pk": "endpoint-1",
        "name": "primary",
        "desired_node": node(),
        "ip_address": "192.0.2.10",
        "ip_policy": "dhcp_reserved",
        "dns_name": "edge-1.example.test",
        "realized_ip_address": None,
    }
    data.update(overrides)
    return obj(**data)


def ip_address(**overrides):
    data = {
        "pk": "ip-1",
        "address": "192.0.2.10/32",
        "dns_name": "edge-1.example.test",
        "type": "dhcp",
    }
    data.update(overrides)
    return obj(**data)


class FakeField:
    def __init__(self, name, choices=()):
        self.name = name
        self.choices = choices


class FakeMeta:
    def __init__(self, fields):
        self.fields = fields

    def get_fields(self):
        return self.fields

    def get_field(self, name):
        for field in self.fields:
            if field.name == name:
                return field
        raise LookupError(name)


class FakeIPAddressModel:
    _meta = FakeMeta(
        [
            FakeField("host"),
            FakeField("mask_length"),
            FakeField("dns_name"),
            FakeField("type", choices=(("dhcp", "DHCP"), ("host", "Host"))),
            FakeField("status"),
        ]
    )


class IPAMReconcilePlanningTests(unittest.TestCase):
    def test_dhcp_reserved_endpoint_without_candidate_plans_create(self) -> None:
        plan = plan_endpoint_ipam_reconcile(
            endpoint(),
            ip_candidates=[],
            ip_address_model=FakeIPAddressModel,
        )

        self.assertEqual(plan.action, "create_ip_address")
        self.assertEqual(plan.desired_ip_address, "192.0.2.10/32")
        self.assertEqual(
            plan.create_fields,
            {
                "host": "192.0.2.10",
                "mask_length": 32,
                "dns_name": "edge-1.example.test",
                "type": "dhcp",
            },
        )

    def test_existing_matching_ip_plans_link_without_overwriting_fields(self) -> None:
        existing = ip_address(dns_name="")
        plan = plan_endpoint_ipam_reconcile(endpoint(), ip_candidates=[existing])

        self.assertEqual(plan.action, "link_ip_address")
        self.assertEqual(plan.existing_ip_address["id"], "ip-1")
        self.assertEqual(plan.create_fields, {})

    def test_existing_dns_name_conflict_is_not_overwritten(self) -> None:
        existing = ip_address(dns_name="other.example.test")
        plan = plan_endpoint_ipam_reconcile(endpoint(), ip_candidates=[existing])

        self.assertEqual(plan.action, "conflict")
        self.assertEqual(plan.reasons, ["dns_name_conflict"])

    def test_existing_type_conflict_is_not_overwritten(self) -> None:
        existing = ip_address(type="host")
        plan = plan_endpoint_ipam_reconcile(endpoint(), ip_candidates=[existing])

        self.assertEqual(plan.action, "conflict")
        self.assertEqual(plan.reasons, ["ip_address_type_conflict"])

    def test_multiple_matching_ips_are_conflict(self) -> None:
        plan = plan_endpoint_ipam_reconcile(
            endpoint(),
            ip_candidates=[ip_address(pk="ip-1"), ip_address(pk="ip-2")],
        )

        self.assertEqual(plan.action, "conflict")
        self.assertEqual(plan.reasons, ["ambiguous_ip_address_candidates"])

    def test_already_linked_matching_ip_is_noop(self) -> None:
        realized = ip_address()
        plan = plan_endpoint_ipam_reconcile(endpoint(realized_ip_address=realized), ip_candidates=[])

        self.assertEqual(plan.action, "noop")
        self.assertEqual(plan.reasons, ["already_linked"])

    def test_realized_ip_mismatch_is_conflict(self) -> None:
        realized = ip_address(address="192.0.2.11/32")
        plan = plan_endpoint_ipam_reconcile(endpoint(realized_ip_address=realized), ip_candidates=[])

        self.assertEqual(plan.action, "conflict")
        self.assertEqual(plan.reasons, ["realized_ip_address_mismatch"])

    def test_static_endpoint_without_observation_is_manual_review_skip(self) -> None:
        plan = plan_endpoint_ipam_reconcile(endpoint(ip_policy="static"), ip_candidates=[])

        self.assertEqual(plan.action, "skip")
        self.assertEqual(plan.reasons, ["observation_missing"])
        self.assertEqual(plan.eligibility_basis, "observation_missing")

    def test_static_endpoint_with_matching_observation_creates_host_type(self) -> None:
        plan = plan_endpoint_ipam_reconcile(
            endpoint(ip_policy="static"),
            ip_candidates=[],
            ip_address_model=FakeIPAddressModel,
            observed_ip_candidates=["192.0.2.10"],
        )

        self.assertEqual(plan.action, "create_ip_address")
        self.assertEqual(plan.create_fields["type"], "host")
        self.assertEqual(plan.eligibility_basis, "eligible")
        self.assertEqual(plan.observed_ip_candidates, ["192.0.2.10"])

    def test_external_endpoint_with_matching_observation_creates_host_type(self) -> None:
        plan = plan_endpoint_ipam_reconcile(
            endpoint(ip_policy="external"),
            ip_candidates=[],
            ip_address_model=FakeIPAddressModel,
            observed_ip_candidates=["192.0.2.10/24"],
        )

        self.assertEqual(plan.action, "create_ip_address")
        self.assertEqual(plan.create_fields["type"], "host")

    def test_observation_matches_by_host_portion_despite_different_prefix(self) -> None:
        plan = plan_endpoint_ipam_reconcile(
            endpoint(ip_policy="static", ip_address="192.0.2.10/24"),
            ip_candidates=[],
            ip_address_model=FakeIPAddressModel,
            observed_ip_candidates=["192.0.2.10/32"],
        )

        self.assertEqual(plan.action, "create_ip_address")

    def test_mismatching_observation_is_conflict(self) -> None:
        plan = plan_endpoint_ipam_reconcile(
            endpoint(ip_policy="static"),
            ip_candidates=[],
            observed_ip_candidates=["198.51.100.5"],
        )

        self.assertEqual(plan.action, "skip")
        self.assertEqual(plan.reasons, ["observation_mismatch"])
        self.assertEqual(plan.observed_ip_candidates, ["198.51.100.5"])

    def test_multiple_conflicting_observations_are_ambiguous(self) -> None:
        plan = plan_endpoint_ipam_reconcile(
            endpoint(ip_policy="static"),
            ip_candidates=[],
            observed_ip_candidates=["192.0.2.10", "198.51.100.5"],
        )

        self.assertEqual(plan.action, "skip")
        self.assertEqual(plan.reasons, ["observation_ambiguous"])
        self.assertEqual(plan.observed_ip_candidates, ["192.0.2.10", "198.51.100.5"])

    def test_dhcp_reserved_endpoint_does_not_require_observation(self) -> None:
        plan = plan_endpoint_ipam_reconcile(
            endpoint(ip_policy="dhcp_reserved"),
            ip_candidates=[],
            ip_address_model=FakeIPAddressModel,
        )

        self.assertEqual(plan.action, "create_ip_address")
        self.assertEqual(plan.eligibility_basis, "eligible")

    def test_unknown_policy_fails_closed(self) -> None:
        plan = plan_endpoint_ipam_reconcile(endpoint(ip_policy="bogus"), ip_candidates=[])

        self.assertEqual(plan.action, "skip")
        self.assertEqual(plan.reasons, ["unknown_ip_policy"])

    def test_existing_host_type_is_compatible_with_static(self) -> None:
        existing = ip_address(type="host")
        plan = plan_endpoint_ipam_reconcile(
            endpoint(ip_policy="static"),
            ip_candidates=[existing],
            observed_ip_candidates=["192.0.2.10"],
        )

        self.assertEqual(plan.action, "link_ip_address")

    def test_existing_dhcp_type_conflicts_with_static(self) -> None:
        existing = ip_address(type="dhcp")
        plan = plan_endpoint_ipam_reconcile(
            endpoint(ip_policy="static"),
            ip_candidates=[existing],
            observed_ip_candidates=["192.0.2.10"],
        )

        self.assertEqual(plan.action, "conflict")
        self.assertEqual(plan.reasons, ["ip_address_type_conflict"])

    def test_existing_host_type_conflicts_with_dhcp_reserved(self) -> None:
        existing = ip_address(type="host")
        plan = plan_endpoint_ipam_reconcile(endpoint(ip_policy="dhcp_reserved"), ip_candidates=[existing])

        self.assertEqual(plan.action, "conflict")
        self.assertEqual(plan.reasons, ["ip_address_type_conflict"])

    def test_create_does_not_proceed_without_required_type_choice(self) -> None:
        class ModelWithoutHostChoice:
            _meta = FakeMeta(
                [
                    FakeField("host"),
                    FakeField("mask_length"),
                    FakeField("dns_name"),
                    FakeField("type", choices=(("dhcp", "DHCP"),)),
                    FakeField("status"),
                ]
            )

        plan = plan_endpoint_ipam_reconcile(
            endpoint(ip_policy="static"),
            ip_candidates=[],
            ip_address_model=ModelWithoutHostChoice,
            observed_ip_candidates=["192.0.2.10"],
        )

        self.assertEqual(plan.action, "conflict")
        self.assertEqual(plan.reasons, ["ip_address_type_unresolvable"])

    def test_invalid_desired_ip_is_out_of_scope_regardless_of_policy(self) -> None:
        plan = plan_endpoint_ipam_reconcile(
            endpoint(ip_policy="static", ip_address="not an ip"),
            ip_candidates=[],
            observed_ip_candidates=["192.0.2.10"],
        )

        self.assertEqual(plan.action, "skip")
        self.assertEqual(plan.reasons, ["missing_ip_address"])

    def test_summary_includes_policy_observation_and_eligibility_evidence(self) -> None:
        plan = plan_endpoint_ipam_reconcile(
            endpoint(ip_policy="static"),
            ip_candidates=[],
            ip_address_model=FakeIPAddressModel,
            observed_ip_candidates=["192.0.2.10"],
        )
        payload = plan.as_dict()

        self.assertEqual(payload["ip_policy"], "static")
        self.assertEqual(payload["observed_ip_candidates"], ["192.0.2.10"])
        self.assertEqual(payload["eligibility_basis"], "eligible")

    def test_invalid_ip_is_skipped(self) -> None:
        plan = plan_endpoint_ipam_reconcile(endpoint(ip_address="not an ip"), ip_candidates=[])

        self.assertEqual(plan.action, "skip")
        self.assertEqual(plan.reasons, ["missing_ip_address"])

    def test_model_free_create_fields_use_address_value(self) -> None:
        fields = ip_address_create_fields("192.0.2.10", dns_name="edge-1.example.test")

        self.assertEqual(fields["address"], "192.0.2.10/32")
        self.assertEqual(fields["dns_name"], "edge-1.example.test")

    def test_default_status_is_included_when_model_supports_it(self) -> None:
        fields = ip_address_create_fields(
            "192.0.2.10",
            dns_name="edge-1.example.test",
            ip_address_model=FakeIPAddressModel,
            default_status="reserved-status-id",
        )

        self.assertEqual(fields["status"], "reserved-status-id")

    def test_default_status_object_is_stored_as_status_id(self) -> None:
        status = obj(pk="11111111-1111-1111-1111-111111111111", name="Reserved")

        fields = ip_address_create_fields(
            "192.0.2.10",
            ip_address_model=FakeIPAddressModel,
            default_status=status,
        )

        self.assertEqual(fields["status_id"], "11111111-1111-1111-1111-111111111111")
        self.assertNotIn("status", fields)

    def test_default_status_omitted_when_not_provided(self) -> None:
        fields = ip_address_create_fields(
            "192.0.2.10",
            ip_address_model=FakeIPAddressModel,
        )

        self.assertNotIn("status", fields)

    def test_create_ip_address_plan_threads_default_status(self) -> None:
        plan = plan_endpoint_ipam_reconcile(
            endpoint(),
            ip_candidates=[],
            ip_address_model=FakeIPAddressModel,
            default_status="reserved-status-id",
        )

        self.assertEqual(plan.action, "create_ip_address")
        self.assertEqual(plan.create_fields["status"], "reserved-status-id")


class BuildIpamReconcileSummaryTests(unittest.TestCase):
    """Phase 4 Step 6: the versioned summary nctl's `reconcile_ipam` action verifies."""

    def test_schema_version_is_stamped(self) -> None:
        payload = build_ipam_reconcile_summary({}, [], requested_desired_node_slug=None)

        self.assertEqual(payload["schema_version"], IPAM_SUMMARY_SCHEMA_VERSION)

    def test_cluster_scope_has_no_requested_slug(self) -> None:
        payload = build_ipam_reconcile_summary(
            {"endpoints": 2},
            [],
            requested_desired_node_slug="",
            selected_desired_node_ids=["n1", "n2"],
            selected_desired_node_slugs=["agdb", "agweb"],
        )

        self.assertIsNone(payload["scope"]["requested_desired_node_slug"])
        self.assertEqual(payload["scope"]["selected_desired_node_slugs"], ["agdb", "agweb"])

    def test_host_scope_records_the_requested_and_selected_node(self) -> None:
        payload = build_ipam_reconcile_summary(
            {"endpoints": 1},
            [{"action": "noop"}],
            requested_desired_node_slug="agweb",
            selected_desired_node_ids=["n1"],
            selected_desired_node_slugs=["agweb"],
        )

        self.assertEqual(payload["scope"]["requested_desired_node_slug"], "agweb")
        self.assertEqual(payload["scope"]["selected_desired_node_ids"], ["n1"])
        self.assertEqual(payload["scope"]["selected_desired_node_slugs"], ["agweb"])
        self.assertEqual(payload["summary"], {"endpoints": 1})
        self.assertEqual(payload["plans"], [{"action": "noop"}])

    def test_selected_node_fields_are_sorted_regardless_of_input_order(self) -> None:
        payload = build_ipam_reconcile_summary(
            {},
            [],
            requested_desired_node_slug=None,
            selected_desired_node_ids=["n2", "n1"],
            selected_desired_node_slugs=["agweb", "agdb"],
        )

        self.assertEqual(payload["scope"]["selected_desired_node_ids"], ["n1", "n2"])
        self.assertEqual(payload["scope"]["selected_desired_node_slugs"], ["agdb", "agweb"])


if __name__ == "__main__":
    unittest.main()
