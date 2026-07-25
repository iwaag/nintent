# Nautobot Intent Catalog — Quick Reference

Operator-facing ledger steps only. Desired-vs-actual drift and consumer rendering are owned by
`nctl`; see `nctl/README.md` in the parent repository.

## Install / upgrade

1. Install the App into Nautobot's Python environment and enable
   `nautobot_intent_catalog` in `PLUGINS`.
2. Configure `PLUGINS_CONFIG["nautobot_intent_catalog"]["intent_sources_file"]`, or set
   `NAUTOBOT_INTENT_SOURCES_FILE`.
3. Run `nautobot-server migrate nautobot_intent_catalog`.
4. Restart Nautobot and open `/plugins/intent-catalog/sources/`.

## Key URLs

| Page | Path |
|---|---|
| Sources | `/plugins/intent-catalog/sources/` |
| Desired Nodes | `/plugins/intent-catalog/nodes/` |
| Desired Services | `/plugins/intent-catalog/services/` |
| Desired service placements | `/plugins/intent-catalog/placements/` |
| Braindumps | `/plugins/intent-catalog/braindumps/` |

## Desired-state operations

The nintent UI is a read-only human inspection adapter. All add/edit/delete forms, Quick Host Add,
and the Source YAML diagnostic page have been removed.

Bulk structural intent is written via strict YAML import (`Import Intent Sources`). Lifecycle transitions and
node linking are owned by `nctl`. Braindump and Alignment Review writes are owned by `nctl` over the narrow REST API.

## Jobs retained in nintent

| Job | Purpose |
|---|---|
| `Import Intent Sources` | Preview (default) or apply the strict `intent_sources.yaml` document. `apply=false` (default) performs zero database writes and always writes `intent-import-result.json`; `apply=true` commits one atomic transaction and refetches every planned row to confirm it. |
| `Analyze Intent Sources` | Preview (default) or apply source-catalog analysis. `apply=false` (default) performs zero database writes and always writes `intent-analysis-result.json`; `apply=true` commits only analysis-owned fields (`IntentSource` status, `DesiredService` catalog fields, `DesiredDependency` rows) and preserves every operator-owned field. |
| `Reconcile Desired IPAM Intent` | Dry-run/apply explicit-IP endpoints into `IPAddress` (`dhcp_reserved` always eligible; `static`/`external` need a matching self-observation). |

Both Import and Analyze default to a safe, zero-write preview; pass `apply=true` explicitly to
commit. Neither Job ever infers a delete/retire/disable from a YAML omission. `Preview Intent
Source Analysis` was removed — Analyze's `apply=false` preview covers the same read-only
information. The old Evaluate Jobs, production inventory export Job, profile sync Job,
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
