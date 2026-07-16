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
| YAML source diagnostic view | `/plugins/intent-catalog/sources/source-yaml/` |
| Quick Host Add | `/plugins/intent-catalog/nodes/quick-add/` |
| Desired service placements | `/plugins/intent-catalog/placements/` |

## Desired-state operations

Quick Host Add creates one `DesiredNode` and one primary `DesiredEndpoint`. Leave DNS/mDNS
blank for canonical defaults such as `pcmain.home.arpa` and `pcmain.local`.

Use normal CRUD screens or strict YAML import for services, placements, multiple endpoints,
operational configs, and IP ranges. `vars/deployment_profiles.yml` remains Ansible-owned and is
read directly by `nctl render production`; nintent has no profile projection or sync Job.

## Jobs retained in nintent

| Job | Purpose |
|---|---|
| `Preview Intent Source Analysis` | Analyze configured sources without writes. |
| `Import Intent Sources` | Import strict desired-state YAML into ledger models. |
| `Analyze Intent Sources` | Analyze source catalogs and persist services/dependencies. |
| `Reconcile Desired IPAM Intent` | Dry-run/apply `dhcp_reserved` endpoints into `IPAddress`. |

The old Evaluate Jobs, production inventory export Job, profile sync Job, `IntentEvaluation`, and
`DeploymentProfileProjection` were removed in 0.6.0.

## nctl workflows

```bash
nctl drift --json
nctl render dnsmasq --json
nctl render hosts-intent --out ansible_agdev/inventories/generated
nctl render production --out ansible_agdev/inventories/generated
nctl dashboard
```

`nctl drift` computes fresh state from nintent desired records, Nautobot actual records, and
nodeutils dumps. `render dnsmasq` computes MAC readiness fresh from the same source snapshot; no
evaluation Job prerequisite exists. Run `Reconcile Desired IPAM Intent` only when IPAddress
creation/linking is wanted. `nctl dashboard` runs drift, writes the static dashboard, and PATCHes
`reconciliation_status`/`reconciliation_checked_at` onto `DesiredNode`/`DesiredService` rows over
REST — a derived cache of the last run, read-only in nintent's UI. Set
`PLUGINS_CONFIG["nautobot_intent_catalog"]["dashboard_url"]` to wherever the dashboard is served
to get a nav-menu link and a "(view dashboard)" link on each node/service page.

## Local tests

```bash
python3 -m unittest discover -s nautobot_intent_catalog/tests
```
