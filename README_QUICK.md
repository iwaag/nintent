# Nautobot Intent Catalog — Quick Reference

Operator-facing steps only. For model intent and design rationale see
[CONCEPT.md](CONCEPT.md); for full behavior and field details see
[README.md](README.md).

## Install / upgrade

1. Install into Nautobot's Python environment:

   ```bash
   pip install -e /path/to/nintent
   ```

2. Enable the App in `nautobot_config.py`:

   ```python
   PLUGINS = ["nautobot_intent_catalog"]

   PLUGINS_CONFIG = {
       "nautobot_intent_catalog": {
           "intent_sources_file": "/path/to/nauto/seed/intent_sources.yaml",
       },
   }
   ```

   Alternatively set `NAUTOBOT_INTENT_SOURCES_FILE`; otherwise the dev fallback is
   `./nauto/seed/intent_sources.yaml`.

3. Run migrations after every install or upgrade:

   ```bash
   nautobot-server migrate nautobot_intent_catalog
   ```

4. Restart Nautobot, then open `/plugins/intent-catalog/sources/`.

## Key URLs

| Page | Path |
|------|------|
| Sources | `/plugins/intent-catalog/sources/` |
| YAML source diagnostic view | `/plugins/intent-catalog/sources/source-yaml/` |
| Quick Host Add | `/plugins/intent-catalog/nodes/quick-add/` |
| Quick Service Placement | `/plugins/intent-catalog/placements/quick-add/` |

## Quick Host Add

Create one desired node + one primary endpoint from one form.

1. Open Quick Host Add (navigation near `Desired Nodes`, or the URL above).
2. Fill the node name and IP. Leave `dns_name` / `mdns_name` blank to get
   defaults from the node name (e.g. `pcmain` → `pcmain.home.arpa`,
   `pcmain.local`). Explicit values are never overwritten.
3. Submit. It writes one `DesiredNode` and one primary `DesiredEndpoint`.

Use the normal `DesiredNode` / `DesiredEndpoint` CRUD screens for multiple or
non-primary endpoints, realized-object links, or fine-grained edits. Use YAML
import to manage state from a source file.

## Quick Service Placement

Place one service on one node from one form.

**Prerequisite:** sync deployment profiles first (see next section). Until then
the form shows an error instead of an empty profile picker.

1. Open a `DesiredService` detail page and click **Place this service**
   (the service is preselected), or open Quick Service Placement directly.
2. Choose the node (`desired_node`) and the deployment profile
   (`deployment_profile`). The profile dropdown comes from the synced projection.
3. Fill the `config` fields generated from the selected profile schema.
   - Optional: `instance_name` (defaults to the service slug), `desired_endpoint`
     (limited to endpoints on the chosen node), `desired_state`, `instance_role`,
     `reason`.
4. Submit. It writes one `DesiredServicePlacement`. `config_schema_version` and
   `assignment_source=manual` are set automatically (not typed in).

The regular `DesiredServicePlacement` CRUD screen and YAML import write the same
record; use them for batch or source-file management.

## Sync Deployment Profiles

Populate the read-only profile projection Quick Service Placement reads from.
`deployment_profiles` stay owned by Ansible (`ansible_agdev`
`vars/deployment_profiles.yml`); Nautobot only holds a projection.

1. Run the **Sync Deployment Profiles** Job.
2. Pass the **same** `deployment_profiles_json` + `deployment_profiles_digest`
   inputs you pass to `Export Production Inventory`.

Re-run whenever the Ansible-owned profiles change.

## dnsmasq export

Run jobs in this order when DHCP reservations depend on discovered facts:

1. `Evaluate Node Intent`
2. `Evaluate Endpoint Intent`
3. `Reconcile Desired IPAM Intent` — optional; dry-run by default, enable
   `commit_changes` to create/link `IPAddress` rows.
4. Run `nctl render dnsmasq` outside Nautobot.

`nctl render dnsmasq` produces dnsmasq configuration on stdout. Use `--out`
to write it to a file or `--json` to inspect records and skipped details.

The renderer lives in `nctl`; nintent only exposes its desired-state and
evaluation inputs through GraphQL.

## Evaluation jobs

| Job | Purpose |
|-----|---------|
| `Evaluate Service Intent` | Compare `DesiredService` with lifecycle, requirements, dependency state. |
| `Evaluate Node Intent` | Compare `DesiredNode` with actual `Device` / `VirtualMachine`. |
| `Evaluate Endpoint Intent` | Compare `DesiredEndpoint` with `IPAddress` and interface facts. |
| `Reconcile Desired IPAM Intent` | Dry-run/apply `dhcp_reserved` endpoints into `IPAddress`. |

Other jobs: `Preview Intent Source Analysis` (dry-run), `Import Intent Sources`,
`Analyze Intent Sources`, `Export Ansible Hosts Intent`,
`Export Production Inventory`.

## Local tests (no Nautobot required)

```bash
python3 -m unittest discover -s nautobot_intent_catalog/tests
```

## Manual cleanup notes

This App ships no backward-compatibility shims. Before applying schema changes in
an existing database, manually fix data the App no longer accepts (e.g. legacy
`DesiredNode.node_type` `network` / `other` → `device` / `virtual_machine` /
`container` / `service_host`, and set `accepted_actual_types`). When replacing an
older install, back up first, then remove obsolete `PLUGINS` / `PLUGINS_CONFIG`
entries, tables, migration rows, URLs, and packages. See
[README.md](README.md#manual-cleanup-during-rename) for the full list.
