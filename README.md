# Nautobot Intent Catalog

Nautobot App for importing and analyzing cluster intent. The current code
supports intent sources, desired services, desired dependencies, desired nodes,
desired endpoints, explicit service placements, typed node operational policy,
deterministic desired-vs-actual evaluations, and dnsmasq DNS/DHCP export.

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

- Imports `intent_sources` YAML rows into `IntentSource`.
- Persists generated `DesiredService` records from source analysis.
- Persists normalized `DesiredDependency` rows from Backstage `spec.dependsOn`.
- Persists `DesiredNode` and `DesiredEndpoint` rows from YAML.
- Persists `DesiredServicePlacement` and `DesiredNodeOperationalConfig` rows
  from strict environment YAML or Nautobot CRUD screens.
- Provides `Quick Host Add` for creating one desired node and one primary endpoint from one Nautobot form.
- Provides `Quick Service Placement` for placing one service on one node from one
  Nautobot form, with profile-derived config schema and `manual` assignment.
- Projects the Ansible-owned `deployment_profiles` map into a read-only,
  digest-keyed snapshot via the `Sync Deployment Profiles` Job for UI choices and
  early validation.
- Persists `IntentEvaluation` rows for desired-vs-actual gap data.
- Evaluates desired services, desired nodes, and desired endpoints against
  deterministic state and Nautobot actual objects.
- Exports deterministic dnsmasq DNS records and DHCP reservations from eligible
  desired endpoints.
- Keeps a diagnostic YAML source view at `/plugins/intent-catalog/sources/source-yaml/`.
- Provides dry-run and import Nautobot Jobs for intent source analysis.
- Detects Backstage `Component` catalog entries for `service`, `website`, and `worker` desired services.
- Does not run remediation review yet.

For the model intent and design boundaries behind `IntentSource`,
`DesiredService`, `DesiredDependency`, `DesiredNode`, `DesiredEndpoint`,
`DesiredServicePlacement`, `DesiredNodeOperationalConfig`, and
`IntentEvaluation`, see [CONCEPT.md](CONCEPT.md).

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

## Quick Service Placement

Use `Quick Service Placement` for the common case of placing one service on one
node. It is available from the `Intent Catalog` navigation near `Service
Placements`, directly at:

```text
/plugins/intent-catalog/placements/quick-add/
```

and as the `Place this service` button on a `DesiredService` detail page, which
opens the form with that service preselected. Because `DesiredService` records
are collected from intent sources and cannot be hand-created, starting from the
service detail page removes the need to hunt for a service to reference.

Quick Service Placement does not create a separate model. It writes one
canonical `DesiredServicePlacement`, the same record used by YAML import and the
normal CRUD screen. The operator only chooses what they actually decide:

- the service (`desired_service`, preselected from the detail page)
- the node (`desired_node`)
- the deployment profile (`deployment_profile`)
- the profile's config values (`config`)

Other fields are derived or optional:

- `config_schema_version` is **not** an operator input. It is derived from the
  selected profile (the contract supports a single schema version).
- `assignment_source` is fixed to `manual` so manual placements stay
  distinguishable from future generated ones.
- `instance_name` defaults to the service slug when left blank.
- `desired_endpoint` is optional and limited to endpoints on the selected node.
- `deployment_profile` is a dropdown sourced from the synced deployment-profiles
  projection, and `config` fields are generated from that profile's `variables`
  schema and validated against it before saving.

The deployment-profiles projection must be synced first (see
[deployment_profiles ownership](#deployment_profiles-ownership-and-sync)). Until
then the form cannot offer profile choices or a config schema, so it shows a
clear error asking you to run the sync Job rather than presenting an empty
picker.

The regular `DesiredServicePlacement` CRUD screen follows the same rule: it does
not expose `config_schema_version` or `assignment_source` as hand-typed fields.
Use YAML import when placements should be managed from a source file or reviewed
as a batch.

## deployment_profiles ownership and sync

`deployment_profiles` are **owned by Ansible** (`ansible_agdev`
`vars/deployment_profiles.yml`). Nautobot holds only a read-only projection used
for UI choices and early validation; it never becomes an editable authoritative
copy, and production inventory export still revalidates the map at export time.

Run the `Sync Deployment Profiles` Job with the same canonical
`deployment_profiles_json` + `deployment_profiles_digest` inputs passed to
`Export Production Inventory`. The Job validates the input through the shared
export-input contract and stores a single digest-keyed projection. Quick Service
Placement reads this projection for profile choices and config schemas.

## dnsmasq rendering

The dnsmasq consumer-format renderer is owned by `nctl`; this app only stores
and exposes the desired endpoints, IP ranges, and intent evaluations that it
reads. Use `nctl render dnsmasq` instead of a Nautobot export Job.

`cname` records require `vpn_dns_name` as the alias target. `mdns_name` is kept
as endpoint metadata and is intentionally not exported as a dnsmasq record.

DHCP reservations use the same endpoint selection criteria plus deterministic
actual-state requirements from the latest `Evaluate Endpoint Intent` and
`Evaluate Node Intent` results:

- the related desired node has exactly one actual node match
- the endpoint evaluation has exactly one DHCP MAC candidate
- the MAC address is valid and normalized to lower-case colon format

When these conditions are met, `dnsmasq-records.conf` includes:

```text
dhcp-host=<mac>,<dns_name>,<ip>
```

`ip_address` values with CIDR suffixes are normalized to host addresses by the
`nctl` renderer. DNS records can still be rendered when DHCP is skipped;
missing actual nodes, missing MACs, ambiguous interfaces, invalid MACs, and
inactive lifecycles are reported by `nctl render dnsmasq --json`. MAC inference
and desired-vs-actual comparison remain inputs from Nautobot evaluation jobs.

Run the jobs in this order when DHCP reservations depend on discovered actual
node/interface facts:

1. `Evaluate Node Intent`
2. `Evaluate Endpoint Intent`
3. `Reconcile Desired IPAM Intent` when you want to dry-run or apply IPAM links
4. `nctl render dnsmasq` outside Nautobot

The endpoint evaluation consumes the latest stored node evaluation. This allows
an actual node discovered by normalized name matching, such as desired `pcmain`
to actual `pcmain.local`, to provide interface and MAC candidates for DHCP
reservation export.

## REST API

`DesiredNode` and `DesiredEndpoint` are exposed read/write through Nautobot's
REST API so both humans and agents can query desired state without going
through the UI or a Django shell:

```text
GET  /api/plugins/intent-catalog/nodes/
GET  /api/plugins/intent-catalog/nodes/<uuid>/
GET  /api/plugins/intent-catalog/endpoints/
GET  /api/plugins/intent-catalog/endpoints/<uuid>/
```

Standard Nautobot REST conventions apply: authenticate with
`Authorization: Token <api-token>`, use `POST`/`PATCH`/`DELETE` for writes, and
filter with the same fields exposed by `DesiredNodeFilterSet` and
`DesiredEndpointFilterSet` (for example `?slug=agstudio` or
`?desired_node=<uuid>`). Other models (`DesiredService`,
`DesiredServicePlacement`, `IntentEvaluation`, etc.) are not yet exposed
through the REST API and remain UI/ORM-only for now.

## Intent Evaluations

`IntentEvaluation` stores durable desired-vs-actual review data for UI, API,
and future agent workflows. It intentionally uses `target_type` and `target_id`
instead of a generic relation so external automation can address targets with a
small stable key.

The initial upsert key is:

```text
target_type, target_id, source_hash
```

Structured deterministic fields are kept separate from optional AI review:

- deterministic fields: `deterministic_summary`, `actual_refs`,
  `observed_facts`, `expected_facts`, `gap_summary`, `recommended_actions`
- AI fields: `ai_review`, `review_model`, `reviewed_at`

`ai_review` may be empty. Deterministic evaluations and recommended actions are
valid without any model-generated review.

Run `Evaluate Service Intent` to compare `DesiredService` rows with their
lifecycle, requirements, and `DesiredDependency` resolution state. Missing
nodeutils or monitoring facts are stored as `unknown` optional input instead of
failing the evaluation. The Job reserves an AI review interface in
`observed_facts.ai_review` but does not call a model; future review tasks should
consume the deterministic fields first and write generated review output only to
`ai_review` and `review_model`.

Run `Evaluate Node Intent` to compare `DesiredNode` rows with actual Nautobot
`Device` and `VirtualMachine` rows. Explicit `realized_device` or `realized_vm`
links are authoritative and are evaluated before candidate discovery, but a
link to an object type outside `accepted_actual_types` is a conflict. Unlinked
nodes are matched only against accepted actual types and then ranked
deterministically by hostname/name, serial or UUID, and platform or OS hints
from `expected_spec` and actual object fields/custom fields. Built-in home-lab
suffixes are normalized for name comparison, so `pcmain` and `pcmain.local` are
treated as the same node identity while unrelated FQDNs such as
`db01.prod.example.com` are not collapsed to `db01`. Ambiguous matches are not
adopted automatically; they are stored as `conflict` evaluations with
review-required actions.

Run `Evaluate Endpoint Intent` to compare `DesiredEndpoint` rows with
`IPAddress` rows and interface facts from the related realized node or the
latest stored node evaluation. It records IP address mismatches as `conflict`,
missing or unlinked IP addresses as `partial`, and DHCP MAC candidates in
`observed_facts`. Endpoints with no MAC or multiple MAC-bearing interfaces are
not considered DHCP-reservation-ready. `nctl render dnsmasq` consumes these
deterministic facts through GraphQL and emits `dhcp-host=` lines only when the
reservation is unambiguous.

Run `Reconcile Desired IPAM Intent` to optionally reflect
`DesiredEndpoint.ip_policy=dhcp_reserved` into Nautobot `IPAddress` rows. The
Job defaults to dry-run and writes an `ipam-reconcile-summary.json` JobResult
file. With `commit_changes` enabled, it can create a missing IPAddress or link
an existing non-conflicting IPAddress to `DesiredEndpoint.realized_ip_address`.
It does not overwrite existing IPAddress DNS names, assignment fields, or
non-DHCP types; conflicts are logged and stored in endpoint evaluation
`observed_facts.ipam_reconcile`.

Initial recommended action examples:

- `resolve_service_dependency`
- `review_service_lifecycle`
- `link_desired_node_to_actual`
- `create_or_link_ip_address`
- `select_dhcp_interface`

Recommended actions are JSON objects with a stable action name, a target, a
reason, and a review flag. Optional keys carry action-specific context such as
`dependency`, `actual_ref`, or `candidates`.

```json
{
  "action": "resolve_service_dependency",
  "target": {"id": "<desired-service-uuid>", "name": "api-service"},
  "dependency": {
    "dependency_kind": "component",
    "namespace": "default",
    "name": "database",
    "raw_ref": "component:default/database",
    "dependency_type": "component",
    "resolution_status": "unresolved"
  },
  "reason": "A desired service dependency is unresolved.",
  "requires_review": true
}
```

Agent and Ansible integrations should treat these surfaces as the stable query
boundary:

- desired state: `DesiredService`, `DesiredDependency`, `DesiredNode`,
  `DesiredEndpoint`
- actual state: Nautobot `Device`, `VirtualMachine`, `IPAddress`, and related
  interface facts referenced from evaluations
- evaluation state: `IntentEvaluation.target_type`, `target_id`, `status`,
  `deterministic_summary`, `actual_refs`, `observed_facts`, `expected_facts`,
  `gap_summary`, `recommended_actions`
- optional IPAM apply boundary: `Reconcile Desired IPAM Intent`
- dnsmasq deployment input: output from `nctl render dnsmasq`

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
