# Nautobot Intent Catalog

Nautobot App for importing and analyzing cluster intent. The current code
supports intent sources, desired services, desired dependencies, desired nodes,
desired endpoints, explicit service placements, typed node operational policy,
and transactional desired-state/IPAM operations.

## Install

Install the package into the same Python environment as Nautobot:

```bash
pip install -e /path/to/nintent
```

Enable the App in `nautobot_config.py`:

```python
PLUGINS = [
    "nautobot_intent_catalog",
]

PLUGINS_CONFIG = {
    "nautobot_intent_catalog": {
        "intent_sources_file": "/path/to/nauto/seed/intent_sources.yaml",
    },
}
```

If `intent_sources_file` is omitted, the App checks:

```bash
export NAUTOBOT_INTENT_SOURCES_FILE=/path/to/nauto/seed/intent_sources.yaml
```

If neither is set, the development fallback is:

```text
./nauto/seed/intent_sources.yaml
```

relative to Nautobot's current working directory.

After restarting Nautobot, open:

```text
/plugins/intent-catalog/sources/
```

Run migrations after installing or upgrading the App:

```bash
nautobot-server migrate nautobot_intent_catalog
```

## Current Scope

- Imports strict desired-state YAML into ledger models.
- Persists analyzed services and dependencies from configured source catalogs.
- Stores desired nodes, endpoints, IP ranges, service placements, and node operational policy.
- Provides normal Nautobot CRUD surfaces plus Quick Host Add.
- Exposes desired state through Nautobot GraphQL for nctl reads and selected REST write surfaces.
- Keeps transactional Jobs for source import/analysis and desired IPAM reconciliation.
- Does not persist desired-vs-actual evaluations or compose consumer artifacts; nctl owns drift,
  dnsmasq rendering, and production inventory composition.

For the surviving model intent and storage boundaries, see [CONCEPT.md](CONCEPT.md). For current
operator commands, see [README_QUICK.md](README_QUICK.md).

## Intent Source YAML

The loader accepts the current `intent_sources`, `desired_nodes`,
`desired_endpoints`, `desired_ip_ranges`, `desired_service_placements`, and
`desired_node_operational_configs` roots. It does not load renamed or legacy
placement and operational-policy shapes.

```yaml
intent_sources:
  - url: https://github.com/example/service
    enabled: true
    ref: main
    owner: platform
    service_hint: service
    catalog_paths:
      - catalog-info.yaml
    basic_file_paths:
      - README.md
    raw_url_template: https://raw.example.test/{ref}/{path}

desired_nodes:
  - name: Edge Router 1
    slug: edge-router-1
    node_type: virtual_machine
    accepted_actual_types:
      - virtual_machine
    lifecycle: approved
    role: edge
    intent_source: service
    expected_spec:
      cpu: 2
      memory_gb: 4

desired_endpoints:
  - name: mgmt
    desired_node: edge-router-1
    endpoint_type: management
    ip_address: 192.0.2.10/32
    ip_policy: dhcp_reserved
    dns_name: edge-router-1.example.test
    protocol: https
    port: 443
    generate_dnsmasq: true
    dnsmasq_record_type: host_record

desired_service_placements:
  - desired_service:
      intent_source: service
      catalog_namespace: default
      catalog_metadata_name: dnsmasq
      service_type: service
    instance_name: primary
    desired_node: edge-router-1
    desired_endpoint:
      name: mgmt
      endpoint_type: management
    desired_state: active
    instance_role: primary
    deployment_profile: dnsmasq
    config_schema_version: "1"
    assignment_source: yaml
    config:
      dhcp_authoritative: true

desired_node_operational_configs:
  - desired_node: edge-router-1
    actual_state_policy: required
    expected_host_os: linux
    connection_path: local
    local_endpoint:
      name: mgmt
      endpoint_type: management
    ansible_port: 22
    power_control: wol
    is_laptop: false
```

For the common one-host/one-primary-endpoint case, YAML may omit `dns_name` and
`mdns_name` on a primary endpoint. During import, missing or blank values are
filled from the resolved desired node name:

```yaml
desired_nodes:
  - name: pcmain
    slug: pcmain
    node_type: device
    accepted_actual_types:
      - device
    lifecycle: active

  - name: dnsmasq-main
    slug: dnsmasq-main
    node_type: service_host
    accepted_actual_types:
      - device
      - virtual_machine
      - container
    lifecycle: active
    role: dnsmasq

desired_endpoints:
  - name: primary
    desired_node: pcmain
    endpoint_type: primary
    ip_address: 192.168.10.25/24
    ip_policy: dhcp_reserved
    generate_dnsmasq: true
```

This imports the endpoint with `dns_name: pcmain.home.arpa` and
`mdns_name: pcmain.local`. Explicit YAML values are preserved. Non-primary
endpoints are not auto-filled.

Raw YAML desired node input separates the desired node classification from the
acceptable Nautobot object types that may realize it. Use `node_type` for the
intent catalog classification and `accepted_actual_types` for candidate matching
and explicit realized-object validation.

Desired endpoints and all new placement/operational records reference a desired
node only by its globally unique slug. References may target a node already in
the database or one declared earlier in the same atomic import. Missing and
ambiguous references abort the entire import. `DesiredEndpoint.ip_address` is stored as text so unrealized
intent can be captured before a Nautobot `IPAddress` exists; actual state is
linked separately through `realized_ip_address`.

Placement service references always include the IntentSource slug, catalog
namespace, catalog metadata name, and service type. Endpoint references are
always scoped to the selected node and contain both name and endpoint type.
Unknown placement/operational fields, incomplete references, invalid policy
combinations, list/scalar placement config, and non-boolean `is_laptop` values
are rejected rather than coerced.

## Quick Host Add

Use `Quick Host Add` for the common case where one host needs one primary DNS
name and one IP address. It is available from the `Intent Catalog` navigation
near `Desired Nodes`, and directly at:

```text
/plugins/intent-catalog/nodes/quick-add/
```

Quick Host Add does not create a separate host model. It writes the same
canonical records used everywhere else:

- one `DesiredNode`
- one primary `DesiredEndpoint`

If DNS or mDNS fields are left blank, Quick Host Add fills soft defaults from
the canonical node name. For a node named `pcmain`, the primary endpoint gets:

- `dns_name: pcmain.home.arpa`
- `mdns_name: pcmain.local`

Names such as `PCMAIN.local` and `pcmain.home.arpa` canonicalize to `pcmain`
for default generation. Explicit `dns_name` and `mdns_name` form values are
never overwritten.

Use the normal `DesiredNode` and `DesiredEndpoint` CRUD screens when a host
needs multiple endpoints, non-primary endpoint types, realized object links, or
fine-grained endpoint edits. Use YAML import when the desired state should be
managed from a source file or reviewed as a batch.

## Deployment profiles and service placements

Service placements remain ordinary `DesiredServicePlacement` ledger rows created through strict
YAML import or the regular Nautobot CRUD screen. The projection-dependent Quick Service Placement
form was removed in 0.6.0.

`deployment_profiles` are owned by Ansible at
`ansible_agdev/vars/deployment_profiles.yml`. Nautobot stores no copy or digest projection. nctl
reads and validates the file directly while composing the production inventory.

## dnsmasq and drift consumers

The dnsmasq renderer and reconciliation engine are owned by nctl. This App stores desired state and
exposes it through GraphQL; nctl joins it with Nautobot actual objects and nodeutils dumps.

`nctl render dnsmasq` computes actual-node/interface matches and DHCP MAC candidates fresh. No
Evaluate Job or persisted evaluation prerequisite exists. Missing/ambiguous actual nodes, IPs,
interfaces, or MACs appear in the JSON `skipped` details.

`nctl drift --json` is the single structured desired-vs-actual query surface for humans, AI, and
future automation. `nctl render production` reads the Ansible-owned deployment profiles directly
and writes the validated production inventory and companion report.

## REST API

`DesiredNode`, `DesiredEndpoint`, and `DesiredService` are exposed read/write through Nautobot's
REST API so both humans and agents can query desired state without going
through the UI or a Django shell:

```text
GET  /api/plugins/intent-catalog/nodes/
GET  /api/plugins/intent-catalog/nodes/<uuid>/
GET  /api/plugins/intent-catalog/endpoints/
GET  /api/plugins/intent-catalog/endpoints/<uuid>/
GET  /api/plugins/intent-catalog/services/
GET  /api/plugins/intent-catalog/services/<uuid>/
```

Standard Nautobot REST conventions apply: authenticate with
`Authorization: Token <api-token>`, use `POST`/`PATCH`/`DELETE` for writes, and
filter with the same fields exposed by `DesiredNodeFilterSet`,
`DesiredEndpointFilterSet`, and `DesiredServiceFilterSet` (for example
`?slug=agstudio` or `?desired_node=<uuid>`). This is also the write path `nctl dashboard` uses to
PATCH `reconciliation_status`/`reconciliation_checked_at` (see below). Other models such as
`DesiredServicePlacement` are not yet exposed through the REST API and remain
GraphQL-read/UI/ORM-managed for now.

## Reconciliation status fields and the dashboard link

`DesiredNode` and `DesiredService` each carry `reconciliation_status` (blank until first written;
otherwise one of `converged`/`drifting`/`converging`/`unknown`, matching `nctl.drift.v1`'s status
vocabulary exactly) and `reconciliation_checked_at` (null until first written). **Both fields are
a derived cache of the last `nctl dashboard` run** — nintent never computes them itself, and they
are read-only everywhere in the UI (a "Reconciliation" table column plus detail-page rows); the
single source of truth remains `nctl drift`. They are written by `nctl dashboard`'s status
write-back step via the REST routes above (`PATCH reconciliation_status` +
`reconciliation_checked_at`), which degrades to a warning per target rather than failing when
Nautobot is unreachable or a target has no matching row — a stale or blank value is expected
between `nctl dashboard` runs, and `reconciliation_checked_at` is what makes that staleness
visible.

The plugin setting `PLUGINS_CONFIG["nautobot_intent_catalog"]["dashboard_url"]` (default `None`)
points at wherever `nctl dashboard`'s output directory (`[dashboard].out_dir` in `nctl.toml`) is
served on the LAN. When set, it drives a "nctl Dashboard" navigation menu item and a
"(view dashboard)" link next to each node/service's reconciliation status row — both routed
through a resolvable Nautobot view (`dashboard_redirect`) that 302s to the configured URL, since
Nautobot's nav-menu link mechanism expects a Nautobot URL name, not an arbitrary external string.
It is deployment configuration, not a model field — per the roadmap, Nautobot stays the ledger
and visualization lives outside it.

## Reconciliation and IPAM boundary

nintent 0.6.0 removed `IntentEvaluation` and the Evaluate Node/Endpoint/Service Jobs. Deterministic
evaluation is computed fresh by nctl comparators instead of stored as a second, staleable source of
truth.

`Reconcile Desired IPAM Intent` remains because it is a transactional ledger write. It defaults to
dry-run and writes a versioned `ipam-reconcile-summary.json` (`nctl.ipam.reconcile.summary.v1`,
Phase 4 Step 6); with `commit_changes` it may create or link a non-conflicting `IPAddress`. It no
longer upserts evaluation rows as a side effect. An optional `desired_node` slug scopes it to one
node's endpoints instead of the whole cluster (`nctl reconcile [HOST]`'s host-scoped IPAM action);
the summary's `scope` records both the requested slug and the DesiredNode ids/slugs actually
touched, so a caller can verify the Job stayed in scope rather than trusting the request alone.
Cluster scope (no `desired_node`) is unchanged from before this version.

Stable integration boundaries are:

- desired state: nintent models read through Nautobot GraphQL;
- actual ledger state: Nautobot DCIM/IPAM GraphQL objects;
- observed state: nodeutils dumps read by nctl;
- reconciliation result: `nctl drift --json` (`nctl.drift.v1`);
- artifacts: `nctl render dnsmasq` and `nctl render production`;
- optional IPAM write: `Reconcile Desired IPAM Intent`.

For local checks that do not require Nautobot:

```bash
python3 -m unittest discover -s nautobot_intent_catalog/tests
```

## Manual Cleanup During Rename

This App is intentionally moving without backward compatibility artifacts. It
does not provide old plugin names, old URL aliases, old settings fallbacks, or
automatic cleanup migrations.

`DesiredNode.node_type` no longer accepts the ambiguous `network` or `other`
values. Before applying the schema change in an existing Nautobot database,
manually update affected rows to `device`, `virtual_machine`, `container`, or
`service_host`, and set `accepted_actual_types` to the Nautobot object types
that may realize each desired node. The App does not provide an automatic
compatibility migration for those old values.

When replacing an older installation, review your Nautobot environment and
manually remove obsolete data only after exporting anything you need to keep.
Typical cleanup items are:

- old plugin entries in `PLUGINS`, such as `nautobot_service_catalog`
- old plugin configuration keys in `PLUGINS_CONFIG`, such as
  `nautobot_service_catalog`
- old App database tables and migration history rows for the removed Service
  Catalog app
- old URL references to `/plugins/service-catalog/`
- old package installations such as `nautobot-service-catalog` from the Python
  environment

The exact SQL or operational commands depend on the Nautobot deployment and
database backend, so perform cleanup from an environment-specific maintenance
plan and backup first.
