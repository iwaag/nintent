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
- Provides read-only human inspection surfaces for all domain models.
- Exposes desired state through Nautobot GraphQL for nctl reads and selected REST write surfaces.
- Keeps transactional Jobs for source import/analysis and desired IPAM reconciliation.
- Does not persist desired-vs-actual evaluations or compose consumer artifacts; nctl owns drift,
  dnsmasq rendering, and production inventory composition.

For the surviving model intent and storage boundaries, see [CONCEPT.md](CONCEPT.md). For current
operator commands, see [README_QUICK.md](README_QUICK.md).

## Intent Source YAML

The loader accepts exactly nine top-level roots, in this order: `intent_sources`,
`desired_nodes`, `desired_endpoints`, `desired_ip_ranges`, `desired_compute_platforms`,
`desired_compute_instances`, `desired_services`, `desired_service_placements`, and
`desired_node_operational_overrides`. Any other top-level key is a load error before any section
is normalized — including the two removed aliases `service_repositories` and
`desired_node_operational_configs`; ordinary OS, policy, path, and endpoint selection are derived
by nctl rather than imported. A missing known root is a no-op (an operator may supply a partial
document); an unknown root always fails.

`nauto/seed/intent_sources.yaml` is the one checked-in bulk desired-state document (moved from
`nauto/seed/home_cluster.yaml`, which now holds only native Nautobot prerequisites). The `Import
Intent Sources` Job reads this file: it defaults to a zero-write preview (`apply=false`) and
requires an explicit `apply=true` to commit. Omitting a row from the document never disables,
deletes, retires, or unlinks the corresponding existing row — it is silently preserved. An
existing `DesiredNode`'s `lifecycle` and every realized link/source field (`realized_device`,
`realized_ip_address`, `realized_cluster`, `realized_vm`, and their `_source` fields) are never
YAML-owned; an existing `DesiredService`'s `name`/`slug`/`display_name`/`requirements` and every
Analyze-owned catalog/source field are preserved on re-import, and a YAML value that disagrees
with a preserved field blocks the whole row as a conflict rather than overwriting it silently.

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
    # lifecycle omitted -> defaults to active; the node is in production scope
    # as soon as it's created (Better Usability Phase 3). Set an explicit
    # `lifecycle: planned` only for deliberate staging, and promote later
    # with `nctl lifecycle edge-router-1 active`.
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

desired_node_operational_overrides:
  - desired_node: edge-router-1
    ansible_port: 2222
    power_control: wol
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
    # lifecycle omitted -> defaults to active.

  - name: dnsmasq-main
    slug: dnsmasq-main
    node_type: service_host
    accepted_actual_types:
      - device
      - virtual_machine
      - container
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

For a compute-backed guest OS, set the node's `accepted_actual_types` to `device`:
`DesiredNode.realized_device` is the guest-OS/nodeutils realization. Its Proxmox
`virtual_machine` is independently linked through
`DesiredComputeInstance.realized_vm`; it is not an alternative realization type
for that DesiredNode. The two actual objects may both describe the same guest.

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

## Read-only UI Inspection & Ownership

The nintent UI provides read-only inspection for all domain objects. All model add/edit/delete forms, Quick Host Add,
and the Source YAML diagnostic page have been removed.

- **Bulk structural intent:** Owned by `nauto/seed/intent_sources.yaml` and loaded via nintent's `Import Intent Sources` Job.
- **Node lifecycle & linking:** Owned by `nctl lifecycle` and `nctl` node linking reconciler.
- **Braindump & Alignment Review writes:** Owned by `nctl` over the narrow REST API (`/api/plugins/intent-catalog/braindumps/` and `/api/plugins/intent-catalog/alignment-reviews/`).
- **IP Address linking:** Owned by nintent's `Reconcile Desired IPAM Intent` Job.
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

Canonical domain reads use Nautobot GraphQL (`query { desired_nodes ... }`).
Nautobot's REST API is retained only for narrow mutation workflows on five collections:

```text
GET, PATCH        /api/plugins/intent-catalog/nodes/<uuid>/
GET, PATCH        /api/plugins/intent-catalog/compute-platforms/<uuid>/
GET, PATCH        /api/plugins/intent-catalog/compute-instances/<uuid>/
GET, POST         /api/plugins/intent-catalog/braindumps/
GET               /api/plugins/intent-catalog/braindumps/<uuid>/
POST              /api/plugins/intent-catalog/braindumps/supersede/
GET, POST         /api/plugins/intent-catalog/alignment-reviews/
GET, PATCH, DELETE /api/plugins/intent-catalog/alignment-reviews/<uuid>/
```

- `nodes`: POST, PUT, DELETE, and bulk mutations return `405 Method Not Allowed`. Writable fields on detail PATCH are strictly limited to `lifecycle`, `realized_device`, and `realized_device_source`.
- `compute-platforms` can PATCH only `realized_cluster` and `realized_cluster_source`; `compute-instances` can PATCH only `realized_vm` and `realized_vm_source`. They are the narrow, ordered ledger-link writer used by `nctl`; all other compute fields remain GraphQL-read-only.
- `services` and `endpoints` REST collections are deleted (`404 Not Found`). Domain reads use GraphQL.
- Unallowed, system, or read-only mutation keys return `400 Bad Request`. Standard Nautobot REST conventions apply: authenticate with `Authorization: Token <api-token>`.

## Braindump and Alignment Review

nintent also stores a small exchange diary above desired state: a `BrainDumpDocument` holds a
user-originated free-form wish, constraint, or preference, and its zero-or-one current
`AlignmentReview` holds the AI agent's latest natural-language reply after reading that Braindump
together with current desired/actual state. See
[devdocs/big/braindump/roadmap.md](../devdocs/big/braindump/roadmap.md) in the parent repository for
the full design; this section documents only the nintent-side surface.

- **UI entry**: the `Braindumps` navigation item provides read-only list and detail views for
  `BrainDumpDocument` rows. Each Braindump's detail page shows the user's text and the current
  Alignment Review (or "Unreviewed") in two clearly separate panels, so AI-derived text is never
  mistaken for the user's own words.
- **REST**: Braindumps allow only `GET` and `POST`, except for the dedicated transactional
  `POST /braindumps/supersede/` transition; Alignment Reviews retain their ordinary CRUD
  surface at

  ```text
  /api/plugins/intent-catalog/braindumps/
  /api/plugins/intent-catalog/alignment-reviews/
  ```

  `authorship` (`user_direct` or `agent_transcribed`) has no default and must be supplied
  explicitly on every Braindump create. `AlignmentReview.braindump` is a UUID primary-key relation,
  not a nested write; creating a second review for the same Braindump fails with the framework's
  normal uniqueness validation response, and replacing a review is an ordinary `PATCH`/`PUT` of the
  existing row.
- **Correction workflow**: a Braindump is immutable once created. `status` is `active` by default;
  the dedicated supersede operation creates one active replacement and atomically changes exactly
  the selected active old documents to reference-only `superseded`. Generic PATCH remains unavailable.
- **GraphQL** (read-only, framework-generated via `@extras_features("graphql")`): the canonical
  top-level query fields are `braindump_document(id)` / `braindump_documents(...)` and
  `alignment_review(id)` / `alignment_reviews(...)`. The canonical Braindump GraphQL query:

  ```graphql
  query {
    braindump_documents {
      id
      title
      body
      authorship
      status
      created
      last_updated
      alignment_review {
        id
        summary
        created
        last_updated
      }
    }
  }
  ```

- **Writer ownership**: the user, or an agent transcribing confirmed user words, writes
  `BrainDumpDocument`; only the agent writes `AlignmentReview`. Neither model is written by nctl
  drift/reconcile, nintent Jobs, nodeutils, or Ansible.
- **Non-executable boundary**: `body` and `summary` are opaque, autoescaped text — never rendered
  as Markdown/HTML, never passed through `safe`, and never a path into desired state, drift,
  reconcile, Jobs, nodeutils, or host actuation. Turning a Braindump wish into a structured
  desired-state change remains a separate, explicit user-confirmed action through the normal
  nintent/nctl write paths.

## Current status and operation evidence

nintent stores confirmed desired intent; it does not cache reconciliation status. `DesiredNode` and
`DesiredService` carry no reconciliation-status field, and the plugin has no dashboard URL setting,
navigation link, or redirect view — the retired `nctl serve`/`nctl dashboard` family that used to
write and link to that cache was removed (see
[devdocs/big/remove_unused_surfaces/roadmap.md](../devdocs/big/remove_unused_surfaces/roadmap.md)).

Current cluster convergence is a fresh `nctl drift` computation (`--json` for structured agent/tool
consumption), not a persisted cache. A bounded `nctl reconcile` operation's outcome is its CLI
result plus the `plan.json`, round/final drift, action evidence, and `result.json` it persists to
disk. Past or running operations are read through `nctl ops list`/`nctl ops show OPERATION_ID` over
that durable evidence, not through a nintent-side field.

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

The Job handles explicit IP intent, not only DHCP-reserved intent (ipam_policy plan). It
enumerates every `DesiredEndpoint` with a nonblank `ip_address`, regardless of `ip_policy`, and
applies a policy-aware eligibility rule before creating or linking anything:

- `dhcp_reserved`: eligible without any self-observation, as before — a DHCP reservation may
  reserve ledger state before the host has ever been observed.
- `static` / `external`: eligible only when the endpoint's linked realized Device reports a
  `primary_ip_address` custom field whose host portion matches the desired IP. A missing,
  mismatched, or ambiguous (multiple distinct) observation is a manual-review skip, not an
  automatic write; it is re-evaluated immediately before writing (defense in depth) so a decision
  nctl made against an older snapshot cannot force a stale write.
- Every non-`dhcp_reserved` write also chooses Host-equivalent `IPAddress.type` instead of the
  DHCP-equivalent choice, resolved from live model metadata; an existing candidate whose type is
  empty, unknown, or incompatible with the endpoint's policy is a conflict, never silently
  overwritten.

Non-DHCP intent still requires a matching ingested self-observation before automation applies: IPAM
ledger reconciliation is not a host IP-configuration actuator, and a conflict, skip, or empty
Job-artifact coverage result is never reported as convergence.

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
