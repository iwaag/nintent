"""Phase 3 real-HTTP proof for the DesiredNode ledger link.

This module is intentionally collected only by the Nautobot runtime command.
It uses Django's loopback live server, a test-only token, and test-database
rows; no persistent Nautobot service or credential participates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
try:
    from django.test import LiveServerTestCase

    from nautobot.core.testing.mixins import NautobotTestCaseMixin
    from nautobot.dcim.models import Device
    from nautobot.users.models import Token

    from nautobot_intent_catalog.models import DesiredNode
    from nctl_core.drift.context import DriftContext
    from nctl_core.drift.engine import compute_drift
    from nctl_core.artifacts import OperationArtifacts
    from nctl_core.config import Config
    from nctl_core.events import OperationLog
    from nctl_core.nautobot import NautobotClient
    from nctl_core.reconcile.executor import _execute_action, run_reconcile
    from nctl_core.reconcile.ledger import LedgerActionError, execute_link_actual_node
    from nctl_core.reconcile.model import PlanScope
    from nctl_core.reconcile.planner import build_plan
    from nctl_core.sources.actual import fetch_actual_snapshot
    from nctl_core.sources.desired import fetch_desired_snapshot
    from nctl_core.sources.snapshot import SourceSnapshot
except ImportError:  # pragma: no cover - local Django-free discovery
    HAS_RUNTIME = False
else:
    HAS_RUNTIME = True


if HAS_RUNTIME:

    class DesiredNodeLinkRealHttpTests(NautobotTestCaseMixin, LiveServerTestCase):
        """Use actual loopback GraphQL/PATCH/GraphQL traffic through Nautobot."""

        databases = ("default", "job_logs")

        def setUp(self) -> None:
            super().setUp()
            self.setUpNautobot(client=False, populate_status=True)
            self.add_permissions(
                "nautobot_intent_catalog.view_desirednode",
                "nautobot_intent_catalog.change_desirednode",
                "dcim.view_device",
                "virtualization.view_cluster",
                "virtualization.view_virtualmachine",
                "virtualization.view_vminterface",
                "ipam.view_ipaddress",
            )
            self.token = Token.objects.create(user=self.user)

            # The existing real-ORM fixture owns the metadata bootstrap. It creates
            # only test-database rows and lets the candidate be a genuine Device.
            from jobs.seed_home_cluster import SeedHomeCluster

            seed = SeedHomeCluster()
            seed.run("seed/home_cluster.yaml", dry_run=False, update_existing=True)
            from nautobot.dcim.models import DeviceType, Location
            from nautobot.extras.models import Role, Status

            self.node = DesiredNode.objects.create(
                name="p3-http-node",
                slug="p3-http-node",
                node_type="device",
                lifecycle="active",
                accepted_actual_types=["device"],
            )
            device_fields = {
                "device_type": DeviceType.objects.get(model="Ubuntu PC"),
                "role": Role.objects.get(name="workstation"),
                "location": Location.objects.get(name="Home"),
                "status": Status.objects.get(name="Active"),
            }
            self.device = Device.objects.create(
                name=self.node.name,
                **device_fields,
            )
            self.other_device = Device.objects.create(name="p3-http-other-device", **device_fields)

        def _client(
            self,
            traffic: list[tuple[str, str, int]] | None = None,
            after_patch=None,
        ) -> NautobotClient:
            client = NautobotClient(self.live_server_url, self.token.key)
            if traffic is not None:
                client._client.event_hooks["response"].append(
                    lambda response: traffic.append((response.request.method, response.request.url.path, response.status_code))
                )
            if after_patch is not None:
                real_rest_patch = client.rest_patch

                def rest_patch(path, payload):
                    response = real_rest_patch(path, payload)
                    after_patch()
                    return response

                client.rest_patch = rest_patch
            return client

        def _plan(self):
            with self._client() as client:
                # Do the two production GraphQL source reads directly. The
                # dump scanner is intentionally outside this ledger-only proof.
                snapshot = SourceSnapshot(
                    desired=fetch_desired_snapshot(client),
                    actual=fetch_actual_snapshot(client),
                    fetched_at=datetime.now(timezone.utc),
                )
            drift = compute_drift(snapshot, DriftContext(generated_at="2026-07-27T00:00:00+00:00"))
            plan = build_plan(
                snapshot=snapshot,
                diffs=[diff for target in drift.targets for diff in target.diffs],
                scope=PlanScope(kind="host", host_slug=self.node.slug),
                drift_generated_at="2026-07-27T00:00:00+00:00",
                profile_reconciliation={},
            )
            return snapshot, drift, plan

        def _link_action(self):
            _snapshot, drift, plan = self._plan()
            node_target = next(target for target in drift.targets if target.target.id == str(self.node.pk))
            self.assertIn("actual_node_not_linked", [diff.code for diff in node_target.diffs])
            [action] = [item for item in plan.actions if item.reconciler_id == "link_actual_node"]
            return action

        def test_real_graphql_patch_graphql_link_and_fresh_no_repeat(self) -> None:
            action = self._link_action()
            self.assertEqual(action.reconciler_id, "link_actual_node")
            self.assertEqual(action.targets[0].id, str(self.node.pk))
            self.assertEqual(action.parameters["candidate"]["id"], str(self.device.pk))

            traffic: list[tuple[str, str, int]] = []
            with self._client(traffic) as client:
                result = execute_link_actual_node(client, action)
            self.assertEqual(result.candidate_id, str(self.device.pk))
            self.assertEqual(
                traffic,
                [
                    ("POST", "/api/graphql/", 200),
                    ("PATCH", f"/api/plugins/intent-catalog/nodes/{self.node.pk}/", 200),
                    ("POST", "/api/graphql/", 200),
                ],
            )

            _fresh_snapshot, fresh_drift, fresh_plan = self._plan()
            fresh_target = next(target for target in fresh_drift.targets if target.target.id == str(self.node.pk))
            self.assertNotIn("actual_node_not_linked", [diff.code for diff in fresh_target.diffs])
            self.assertFalse([action for action in fresh_plan.actions if action.reconciler_id == "link_actual_node"])

        def test_reset_after_real_patch_fails_closed_and_fresh_plan_repeats_action(self) -> None:
            action = self._link_action()

            def reset():
                DesiredNode.objects.filter(pk=self.node.pk).update(
                    realized_device=None,
                    realized_device_source=None,
                )

            with self._client(after_patch=reset) as client:
                with self.assertRaises(LedgerActionError) as caught:
                    execute_link_actual_node(client, action)

            self.assertEqual(caught.exception.code, "node_link_not_confirmed")
            self.assertTrue(caught.exception.mutated)
            _snapshot, fresh_drift, fresh_plan = self._plan()
            fresh_target = next(target for target in fresh_drift.targets if target.target.id == str(self.node.pk))
            self.assertIn("actual_node_not_linked", [diff.code for diff in fresh_target.diffs])
            self.assertEqual([item.reconciler_id for item in fresh_plan.actions], ["link_actual_node"])

        def test_source_override_after_real_patch_preserves_mutation_evidence(self) -> None:
            action = self._link_action()

            def override():
                DesiredNode.objects.filter(pk=self.node.pk).update(realized_device_source="override")

            with self._client(after_patch=override) as client:
                with self.assertRaises(LedgerActionError) as caught:
                    execute_link_actual_node(client, action)

            self.assertEqual(caught.exception.code, "node_link_source_not_confirmed")
            self.assertTrue(caught.exception.mutated)

        def test_different_candidate_or_deleted_node_after_patch_fails_truthfully(self) -> None:
            for case_id, mutation, expected_code in (
                (
                    "different_candidate",
                    lambda: DesiredNode.objects.filter(pk=self.node.pk).update(
                        realized_device=self.other_device,
                        realized_device_source="derived",
                    ),
                    "node_link_not_confirmed",
                ),
                (
                    "node_disappears",
                    lambda: DesiredNode.objects.filter(pk=self.node.pk).delete(),
                    "node_fetch_failed",
                ),
            ):
                with self.subTest(case_id=case_id):
                    # Each branch owns a fresh isolated test row because the
                    # delete case intentionally removes its row.
                    if case_id != "different_candidate":
                        self.node = DesiredNode.objects.create(
                            name="p3-http-node-delete",
                            slug="p3-http-node-delete",
                            node_type="device",
                            lifecycle="active",
                            accepted_actual_types=["device"],
                        )
                        self.device.name = self.node.name
                        self.device.save()
                    action = self._link_action()
                    with self._client(after_patch=mutation) as client:
                        with self.assertRaises(LedgerActionError) as caught:
                            execute_link_actual_node(client, action)
                    self.assertEqual(caught.exception.code, expected_code)
                    self.assertTrue(caught.exception.mutated)

        def test_prelinked_or_partial_row_is_never_replaced(self) -> None:
            action = self._link_action()
            self.node.realized_device = self.device
            self.node.realized_device_source = "override"
            self.node.save()
            before = (self.node.realized_device_id, self.node.realized_device_source)

            with self._client() as client:
                with self.assertRaises(LedgerActionError) as caught:
                    execute_link_actual_node(client, action)
            self.assertEqual(caught.exception.code, "node_already_linked")
            self.assertFalse(caught.exception.mutated)
            self.node.refresh_from_db()
            self.assertEqual((self.node.realized_device_id, self.node.realized_device_source), before)

        def test_absent_or_denied_prepatch_request_has_no_mutation(self) -> None:
            action = self._link_action()
            absent = action.model_copy(
                update={"targets": [action.targets[0].model_copy(update={"id": "00000000-0000-0000-0000-000000000000"})]}
            )
            with self._client() as client:
                with self.assertRaises(LedgerActionError) as absent_error:
                    execute_link_actual_node(client, absent)
            self.assertEqual(absent_error.exception.code, "node_fetch_failed")
            self.assertFalse(absent_error.exception.mutated)

            with NautobotClient(self.live_server_url, None) as denied_client:
                with self.assertRaises(LedgerActionError) as denied_error:
                    execute_link_actual_node(denied_client, action)
            self.assertEqual(denied_error.exception.code, "node_fetch_failed")
            self.assertFalse(denied_error.exception.mutated)
            self.node.refresh_from_db()
            self.assertIsNone(self.node.realized_device_id)
            self.assertIsNone(self.node.realized_device_source)

        def test_malformed_graphql_pre_read_over_real_loopback_http_has_zero_patch(self) -> None:
            """The client crosses a real HTTP boundary; the fixture owns only its malformed reply."""
            action = self._link_action()
            calls: list[tuple[str, str]] = []

            class MalformedGraphQLHandler(BaseHTTPRequestHandler):
                def do_POST(self):  # noqa: N802 - stdlib handler API
                    calls.append((self.command, self.path))
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"data":{"desired_nodes":"not-a-list"}}')

                def log_message(self, *_args):
                    pass

            server = ThreadingHTTPServer(("127.0.0.1", 0), MalformedGraphQLHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with NautobotClient(f"http://127.0.0.1:{server.server_port}", "test-only") as client:
                    with self.assertRaises(LedgerActionError) as caught:
                        execute_link_actual_node(client, action)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(caught.exception.code, "node_fetch_failed")
            self.assertFalse(caught.exception.mutated)
            self.assertEqual(calls, [("POST", "/api/graphql/")])
            self.node.refresh_from_db()
            self.assertIsNone(self.node.realized_device_id)

        def test_real_http_post_patch_failure_is_retained_by_executor_evidence(self) -> None:
            snapshot, _drift, _plan = self._plan()
            action = self._link_action()
            with TemporaryDirectory(prefix="p3-node-link-events-") as directory:
                root = Path(directory)
                cfg = Config.model_validate(
                    {
                        "nautobot": {"url": self.live_server_url},
                        "inventory": {"dumps_dir": str(root / "dumps")},
                        "events": {"log_dir": str(root / "events")},
                        "ansible": {"playbook_dir": str(root), "inventory": str(root / "inventory.yaml")},
                        "source_path": root / "nctl.toml",
                    }
                )
                op = OperationLog.start("reconcile", root / "events")
                artifacts = OperationArtifacts.create(root / "events", op.operation_id)

                def reset():
                    DesiredNode.objects.filter(pk=self.node.pk).update(realized_device=None, realized_device_source=None)

                with self._client(after_patch=reset) as client:
                    executed = _execute_action(
                        cfg, op, artifacts, 0, action, snapshot, client,
                        lambda: datetime.now(timezone.utc), None, None, generated_at="2026-07-27T00:00:00+00:00",
                    )

                self.assertFalse(executed.result.success)
                self.assertTrue(executed.result.mutated)
                self.assertIn("node_link_not_confirmed", executed.result.error or "")
                events = [json.loads(line) for line in op.path.read_text().splitlines()]
                completed = [event for event in events if event["event"] == "action_completed"]
                self.assertEqual(len(completed), 1)
                self.assertFalse(completed[0]["data"]["success"])
                self.assertTrue(completed[0]["data"]["mutated"])

        def test_run_reconcile_retains_real_http_mutation_and_refreshes_final_drift(self) -> None:
            """A real PATCH/reset reaches the public reconcile loop and is never rewritten as no mutation.

            This is deliberately narrower than the focused executor matrix: its
            unique owner is the actual GraphQL/PATCH/GraphQL transport plus the
            public ``run_reconcile`` final-drift path.  The reset callback is
            test-owned and runs only after Nautobot accepted the real PATCH.
            """
            with TemporaryDirectory(prefix="p3-node-link-reconcile-") as directory:
                root = Path(directory)
                token_file = root / "test-token"
                token_file.write_text(self.token.key)
                playbook_dir = root / "ansible"
                (playbook_dir / "vars").mkdir(parents=True)
                (playbook_dir / "vars" / "deployment_profiles.yml").write_text(
                    "deployment_profiles: {}\ndeployment_profile_reconciliation: {}\n"
                )
                cfg = Config.model_validate(
                    {
                        "nautobot": {"url": self.live_server_url, "token_file": token_file},
                        "inventory": {"dumps_dir": root / "dumps"},
                        "events": {"log_dir": root / "events"},
                        "ansible": {
                            "playbook_dir": playbook_dir,
                            "inventory": "inventories/generated/hosts_intent.yml",
                        },
                        "reconcile": {"lock_path": root / "reconcile.lock"},
                        "ssh": {"known_hosts_file": root / "known_hosts", "lock_path": root / "ssh.lock"},
                        "source_path": root / "nctl.toml",
                    }
                )
                original_rest_patch = NautobotClient.rest_patch

                def reset_after_real_patch(client, path, payload):
                    response = original_rest_patch(client, path, payload)
                    if path == f"/api/plugins/intent-catalog/nodes/{self.node.pk}/":
                        DesiredNode.objects.filter(pk=self.node.pk).update(
                            realized_device=None,
                            realized_device_source=None,
                        )
                    return response

                with patch.object(NautobotClient, "rest_patch", reset_after_real_patch):
                    envelope = run_reconcile(cfg, host=self.node.slug, apply_changes=True, max_rounds=2)

                self.assertFalse(envelope.ok)
                self.assertEqual(envelope.data.state, "non_converged")
                self.assertTrue(any(error.code == "no_progress" for error in envelope.errors))
                self.assertEqual(len(envelope.data.rounds), 1)
                [result] = [
                    result
                    for result in envelope.data.rounds[0].actions
                    if result.reconciler_id == "link_actual_node"
                ]
                self.assertFalse(result.success)
                self.assertTrue(result.mutated)
                self.assertIn("node_link_not_confirmed", result.error or "")
                self.assertTrue(envelope.data.progress_made)
                self.assertTrue(envelope.data.final_drift_path)
                self.assertTrue(Path(envelope.data.final_drift_path).is_file())
                events = [json.loads(line) for line in Path(envelope.data.event_log_path).read_text().splitlines()]
                completed = [event for event in events if event["event"] == "action_completed"]
                self.assertEqual(len(completed), 1)
                self.assertFalse(completed[0]["data"]["success"])
                self.assertTrue(completed[0]["data"]["mutated"])

        def test_nodeutils_report_builder_ingest_and_actual_graphql_share_one_schema(self) -> None:
            """Step 6's one-way producer -> ORM ingest -> GraphQL reader conformance path."""
            import nodeutils_collect

            from jobs.ingest_nodeutils_inventory import IngestNodeutilsInventory
            from nctl_core.sources.actual import fetch_actual_snapshot
            from nautobot.ipam.models import Namespace

            collected_at = "2026-07-27T00:00:00+00:00"
            inventory = {
                "collected_at": collected_at,
                "system": "Linux",
                "hostname": "p3-schema-node",
                "fqdn": "p3-schema-node.example.test",
                "serial_number": "P3-SCHEMA-1",
                "os_name": "Ubuntu",
                "os_version": "24.04",
                "architecture": "arm64",
                "hardware": {"manufacturer": "Generic"},
                "cpu_model": "synthetic",
                "cpu_logical_cores": 2,
                "memory_gb": 4,
                "disk": {"root_total_gb": 20},
                "primary_interface": {"name": "eth0"},
                "primary_mac_address": "02:00:00:00:00:61",
                "services": {
                    "observed_services": {
                        "dnsmasq": {
                            "state": "active",
                            "managed_files": {
                                "records": {
                                    "path": "/etc/dnsmasq.d/nintent-records.conf",
                                    "sha256": "a" * 64,
                                    "size": 17,
                                    "status": "present",
                                    "checked_at": collected_at,
                                }
                            },
                        }
                    }
                },
                "proxmox": {
                    "schema_version": "nodeutils.proxmox.v1",
                    "enabled": True,
                    "detected": True,
                    "mode": "auto",
                    "inventory_source": "p3-schema",
                    "observed_at": collected_at,
                    "collection": {"state": "partial", "errors": [], "sections": {}},
                    "cluster": {
                        "name": "p3-schema-proxmox",
                        "name_source": "standalone_node_fallback",
                        "identity_value": "p3-schema-node",
                        "node_count": 1,
                        "observed_node_names": ["p3-schema-node"],
                    },
                    "qemu_vms": [],
                    "lxc_containers": [
                        {
                            "guest_type": "lxc", "vmid": 601, "node": "p3-schema-node",
                            "name": "p3-schema-valid", "proxmox_status": "running", "status": "Active",
                            "vcpus": 1, "memory_mb": 512, "disk_gb": 8,
                            "observation": {"state": "complete"},
                            "interfaces": {"config_interfaces": [], "agent_interfaces": [], "joined_interfaces": [], "unmatched": []},
                            "rootfs": {"storage": "local-lvm", "volume": "vm-601-disk-0", "size_gb": 8},
                        },
                        {
                            "guest_type": "lxc", "vmid": -1, "node": "p3-schema-node",
                            "name": "p3-schema-invalid", "proxmox_status": "running", "status": "Active",
                            "vcpus": 1, "memory_mb": 512, "disk_gb": 8,
                            "observation": {"state": "complete"},
                            "interfaces": {"config_interfaces": [], "agent_interfaces": [], "joined_interfaces": [], "unmatched": []},
                            "rootfs": {"storage": "local-lvm", "volume": "vm-invalid", "size_gb": 8},
                        },
                    ],
                    "storage_content": [],
                },
            }
            with patch.object(nodeutils_collect, "get_machine_id", return_value="p3-schema-machine"):
                report = nodeutils_collect.build_inventory_report({"purpose": "p3-schema"}, inventory)
            self.assertEqual(report["schema_version"], nodeutils_collect.SCHEMA_VERSION)

            job = IngestNodeutilsInventory()
            job.logger = logging.getLogger("p3.schema.ingest")
            artifacts: list[tuple[str, str]] = []
            job.create_file = lambda name, content: artifacts.append((name, content))
            Namespace.objects.get_or_create(name="Global")
            # The real ingestor intentionally defers Proxmox rows until its
            # observer Device has a persistent UUID. Establish that Device
            # with the same builder-produced report, then submit the exact
            # same report bytes plus its producer-owned Proxmox subtree.
            device_report = json.loads(json.dumps(report))
            del device_report["facts"]["proxmox"]
            job.run(
                report_batch=json.dumps({"reports": [{"source": "p3-schema", "text": json.dumps(device_report)}]}),
                policy_file="seed/nodeutils_ingest.yaml", dry_run=False, max_report_age_hours=72,
                max_report_bytes=1024 * 1024,
            )
            artifacts.clear()
            job.run(
                report_batch=json.dumps({"reports": [{"source": "p3-schema", "text": json.dumps(report)}]}),
                policy_file="seed/nodeutils_ingest.yaml", dry_run=False, max_report_age_hours=72,
                max_report_bytes=1024 * 1024,
            )
            summary = json.loads(artifacts[0][1])
            proxmox = summary["results"][0]["proxmox"]
            self.assertEqual(proxmox["observation_state"], "partial")
            self.assertEqual(proxmox["object_counts"]["vm"]["created"], 1)
            self.assertIn("invalid_vmid", {error["code"] for error in proxmox["guest_errors"]})

            with self._client() as client:
                actual = fetch_actual_snapshot(client)
            device = next(item for item in actual.devices if item.name == "p3-schema-node")
            facts = device.actual_facts()
            self.assertEqual(facts.collected_at, collected_at)
            self.assertEqual(facts.inventory_source, "nodeutils")
            self.assertEqual(facts.network_interface, "eth0")
            self.assertEqual(facts.observed_services["dnsmasq"]["managed_files"]["records"]["path"], "/etc/dnsmasq.d/nintent-records.conf")
            self.assertEqual(facts.observed_services["dnsmasq"]["managed_files"]["records"]["sha256"], "a" * 64)
            cluster = next(item for item in actual.clusters if item.name == "p3-schema-proxmox")
            self.assertEqual(cluster.proxmox.observation_state, "partial")
            vm = next(item for item in actual.virtual_machines if item.name == "p3-schema-valid")
            self.assertEqual((vm.proxmox.vmid, vm.proxmox.guest_type), (601, "lxc"))
            self.assertFalse(any(item.name == "p3-schema-invalid" for item in actual.virtual_machines))
