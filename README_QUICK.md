# Nautobot Intent Catalog — Quick Reference

Operator-facing ledger steps only. Desired-vs-actual drift and consumer rendering are owned by
`nctl`; see `nctl/README.md` in the parent repository.

## Install / upgrade

1. Install the App into Nautobot's Python environment and enable
   `nautobot_intent_catalog` in `PLUGINS`.
2. Run `nautobot-server migrate nautobot_intent_catalog`.
3. Restart Nautobot and open `/plugins/intent-catalog/services/`.

## Key URLs

| Page | Path |
|---|---|
| Desired Nodes | `/plugins/intent-catalog/nodes/` |
| Desired Services | `/plugins/intent-catalog/services/` |
| Desired service placements | `/plugins/intent-catalog/placements/` |
| Braindumps | `/plugins/intent-catalog/braindumps/` |

## Desired-state operations

The nintent UI is a read-only human inspection adapter. All add/edit/delete forms, Quick Host Add,
and the Source YAML diagnostic page have been removed.

All structural desired state, lifecycle transitions, and realization links are
written atomically through `POST /api/plugins/intent-catalog/desired-state/batch/`.
`nctl desired apply` is the supported operator client; GraphQL and the UI are readers.

## Jobs retained in nintent

| Job | Purpose |
|---|---|
| `Reconcile Desired IPAM Intent` | Dry-run/apply explicit-IP endpoints into `IPAddress` (`dhcp_reserved` always eligible; `static`/`external` need a matching self-observation). |

The old Evaluate Jobs, production inventory export Job, profile sync Job,
`IntentEvaluation`, and `DeploymentProfileProjection` were removed in 0.6.0.

## nctl workflows

```bash
nctl drift --json
nctl render dnsmasq --json
nctl render hosts-intent --out ansible_agdev/inventories/generated
nctl render production --out ansible_agdev/inventories/generated
nctl ops list
nctl ops show OPERATION_ID
```

`nctl drift` computes fresh state from nintent desired records, Nautobot actual records, and
nodeutils dumps — it is the current-status source, not a persisted dashboard. `render dnsmasq`
computes MAC readiness fresh from the same source snapshot; no evaluation Job prerequisite exists.
Run `Reconcile Desired IPAM Intent` only when IPAddress creation/linking is wanted. `nctl ops
list`/`nctl ops show` read the durable on-disk evidence a bounded `nctl reconcile` operation writes.
nintent has no reconciliation-status field and no dashboard setting/link — see
[devdocs/big/remove_unused_surfaces/roadmap.md](../devdocs/big/remove_unused_surfaces/roadmap.md).

## Local tests

```bash
python3 -m unittest discover -s nautobot_intent_catalog/tests
```
