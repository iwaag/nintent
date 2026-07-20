# Intent Catalog Concepts

This document explains the design intent behind the core Intent Catalog models.
`README.md` focuses on installation and usage; this file explains what each
object is meant to represent.

## Big Picture

Intent Catalog separates desired state into a few layers:

- `IntentSource`: where desired state came from.
- `DesiredService`: a logical service or workload that should exist.
- `DesiredDependency`: another service or resource a desired service needs.
- `DesiredNode`: a desired node intent, classified separately from the actual
  Nautobot object types that may realize it.
- `DesiredEndpoint`: a desired IP/DNS/port-facing endpoint on a node.
- `DesiredServicePlacement`: one explicitly desired service instance bound to a
  desired node.
- `DesiredNodeOperationalOverride`: optional genuine exceptions to nctl's
  derived node operation values.
- `IntentEvaluation`: persisted desired-vs-actual review data.

The current implementation stores desired state and deterministic exports. It
does not yet automatically prove that every desired service is running or that
every dependency is satisfied.

## IntentSource

`IntentSource` describes the source of truth or input channel for intent.

The most important current source type is `git_repository`. It is intended to
mean:

> A source repository that declares a desired service for this environment.
> Catalog metadata in the repository is analyzed into `DesiredService` rows, and
> declared dependencies are imported as `DesiredDependency` rows that should be
> satisfied by another desired service, desired node, endpoint, or external
> system.

In practice, a GitHub or GitLab repository containing Backstage catalog metadata
can become the source for one or more desired services.

Other source types are available as classification hooks:

- `git_repository`: a source repository analyzed for service intent.
- `yaml_file`: a YAML file used to declare intent directly.
- `manual`: intent entered or maintained by a person in Nautobot.
- `api`: intent synchronized from another system.
- `generated`: intent produced by an agent or automation tool.

The non-Git source types are currently lightweight classifications. The thickest
implemented paths are Git-backed service analysis and YAML import.

## DesiredService

`DesiredService` represents a logical service or workload that should exist in
the managed environment. It is not a VM, IP address, DNS record, or physical
device.

Examples:

- `auth-api`
- `web-frontend`
- `metrics-worker`
- `postgresql`
- `redis`

`DesiredService` is intended to answer:

- What service should exist?
- What type of service is it?
- Who owns it?
- What lifecycle state is intended?
- What requirements or placement hints were detected?
- When was it last analyzed from its source?

The current Git analysis path primarily creates `DesiredService` rows from
Backstage `Component` catalog entries.

## DesiredDependency

`DesiredDependency` represents something a `DesiredService` needs in order to be
complete.

It is usually derived from Backstage `spec.dependsOn` metadata. For example:

```yaml
spec:
  dependsOn:
    - component:default/auth-api
    - resource:default/postgresql
```

This can become dependency rows such as:

```text
web-frontend -> component:default/auth-api
web-frontend -> resource:default/postgresql
```

`DesiredDependency` is intended to preserve dependency intent even before the
dependency is resolved. A dependency can be:

- `unresolved`: known desired dependency, but no matching internal target yet.
- `resolved`: linked to another `DesiredService`.
- `external`: satisfied outside this app or outside this environment.
- `ignored`: intentionally excluded from evaluation.

The current implementation stores and replaces dependency rows deterministically
during service analysis. It does not yet automatically evaluate whether every
dependency is satisfied.

## DesiredNode

`DesiredNode` represents a desired node-level intent. It describes what kind of
node the catalog wants, not just which Nautobot model should be linked to it.

Two fields carry that split:

- `node_type`: the desired node classification inside Intent Catalog.
- `accepted_actual_types`: the Nautobot object types that may realize the node.

Allowed `accepted_actual_types` values are currently `device`,
`virtual_machine`, and `container`. `container` can be expressed as intent now,
but actual candidate discovery is not added until the Nautobot-side container
model is chosen.

Examples:

- `proxmox-01`
- `vm-git-01`
- `vm-db-01`
- `nas-01`

For a simple DNS/DHCP inventory, this model can feel heavier than a single
`DesiredHost` table. The reason it exists separately is long-term flexibility:
one physical layer object may eventually host many logical nodes, and one node
may have several endpoints.

For example, a Proxmox host and its VMs can be represented as separate desired
nodes:

```yaml
desired_nodes:
  - name: proxmox-01
    slug: proxmox-01
    node_type: device
    accepted_actual_types:
      - device
    lifecycle: active
    role: hypervisor

  - name: vm-git-01
    slug: vm-git-01
    node_type: virtual_machine
    accepted_actual_types:
      - virtual_machine
    lifecycle: active
    role: git
    expected_spec:
      hypervisor: proxmox-01
      vcpu: 2
      memory_gb: 4
```

Node hierarchy is separate from service placement. Service membership must not
be stored in `expected_spec`; it is represented only by
`DesiredServicePlacement`.

A service host may intentionally allow several actual implementations. For
example, a `dnsmasq` node can be classified as a service host while accepting a
physical device, VM, or container as its realization:

```yaml
desired_nodes:
  - name: dnsmasq-main
    slug: dnsmasq-main
    node_type: service_host
    accepted_actual_types:
      - device
      - virtual_machine
      - container
    lifecycle: active
    role: dnsmasq
```

## DesiredEndpoint

`DesiredEndpoint` represents a desired network-facing endpoint on a
`DesiredNode`.

Examples:

- primary DNS/IP for a VM
- management IP for a device
- VPN DNS name for a host
- service endpoint with protocol and port metadata

This separation allows one node to have multiple endpoints:

```yaml
desired_nodes:
  - name: vm-01
    slug: vm-01
    node_type: virtual_machine
    accepted_actual_types:
      - virtual_machine
    lifecycle: active

desired_endpoints:
  - name: primary
    desired_node: vm-01
    endpoint_type: primary
    ip_address: 192.168.10.21/24
    ip_policy: dhcp_reserved
    dns_name: vm-01.example.lan
    generate_dnsmasq: true

  - name: management
    desired_node: vm-01
    endpoint_type: management
    ip_address: 192.168.20.21/24
    ip_policy: dhcp_reserved
    dns_name: vm-01-mgmt.example.lan
    generate_dnsmasq: true
```

For basic host inventory, using one `primary` endpoint per node is enough. More
endpoints can be added later without changing the node identity.

In the simple primary endpoint path, the app can fill soft DNS and mDNS
defaults from the desired node name. A node named `pcmain` gets
`pcmain.home.arpa` as the DNS name and `pcmain.local` as mDNS metadata when
those fields are left blank. Explicit endpoint names remain authoritative, and
non-primary endpoints are not rewritten.

The dnsmasq export is generated from eligible `DesiredEndpoint` rows. mDNS names
are retained as metadata and are not exported as dnsmasq records.

## DesiredServicePlacement

`DesiredServicePlacement` is the operator-owned binding between one qualified
`DesiredService` identity and one globally unique `DesiredNode.slug`. Its
`deployment_profile` is a neutral key interpreted by the audited Ansible-side
profile map; the model contains no Ansible group field.

The stable identity is `(desired_service, instance_name)`. Repository analysis
may refresh service metadata and dependencies, but does not own or replace
placement rows. Optional endpoint references are resolved inside the selected
node by `(name, endpoint_type)`. Placement `config` must be a JSON object and is
validated against its deployment profile before production export; secrets do
not belong in it.

`config_schema_version` and `assignment_source` are not operator inputs in the
assisted paths. `config_schema_version` is derived from the selected profile (the
contract supports a single schema version), and manual placement always records
`assignment_source=manual`, keeping hand-made placements distinguishable from
future generated ones. The Quick Service Placement form and the regular CRUD form
both omit these as hand-typed fields; the placement operation derives/fixes them.
`config` is validated against the selected profile's `variables` schema at form
submission, not only at export time.

The `deployment_profile` profile map stays owned by Ansible. Nautobot keeps only
a read-only, digest-keyed projection synced through the same export-input
contract, used for profile choices and early `config` validation. The projection
is advisory: production inventory export still revalidates the map and records its
digest, so an authoritative copy never lives in Nautobot.

## DesiredNodeOperationalOverride

`DesiredNodeOperationalOverride` is an optional one-to-one exception record.
Without a row, nctl derives Linux/macOS from fresh nodeutils evidence and selects
the node's sole usable endpoint, or its unique primary endpoint. A row is used
only for declared HAOS, a forced local/Tailscale endpoint or path, a non-standard
Ansible port, power behavior, or laptop behavior. Empty/no-op rows are invalid.

Tailscale is never selected automatically and requires a VPN endpoint with a
usable IP. A forced local endpoint must belong to the node and have IP, DNS, or
mDNS. HAOS permits only `power_control=none`; observed Linux/macOS power safety
is validated by nctl after deriving the platform.

## IntentEvaluation

`IntentEvaluation` stores persisted desired-vs-actual review data. It is the
place where deterministic checks and optional AI review can be saved for UI,
API, or future agent workflows.

The initial upsert key is:

```text
target_type, target_id, source_hash
```

The model deliberately separates deterministic fields from AI review fields.
Deterministic fields include:

- `deterministic_summary`
- `actual_refs`
- `observed_facts`
- `expected_facts`
- `gap_summary`
- `recommended_actions`

AI-related fields include:

- `ai_review`
- `review_model`
- `reviewed_at`

An evaluation can be useful even when `ai_review` is empty.

Node evaluations compare desired nodes with actual Nautobot `Device` and
`VirtualMachine` rows. Name-like identity checks use conservative home-lab
normalization, so `pcmain` and `pcmain.local` can match, while unrelated FQDNs
are preserved. Endpoint evaluations can consume the latest stored node
evaluation facts to find interface and MAC candidates before dnsmasq export.

## Current Boundaries

These boundaries are intentional in the current implementation:

- `DesiredService` and `DesiredNode` are linked only through explicit
  `DesiredServicePlacement` instances; neither model embeds the other.
- `DesiredDependency` rows are stored, but dependency satisfaction is not yet
  automatically evaluated.
- `DesiredNode`, `DesiredEndpoint`, `DesiredServicePlacement`, and
  `DesiredNodeOperationalOverride` can be maintained through strict YAML import
  or Nautobot CRUD screens.
- `IntentEvaluation` has CRUD, schema support, and deterministic node,
  endpoint, and service evaluation jobs. Optional AI review is not implemented
  yet.
- The app does not preserve backward compatibility with the old package name,
  old URLs, old model names, old YAML root names, or old migrations.

This means the app is currently useful as an intent inventory, service/dependency
catalog, explicit placement and execution-policy inventory, endpoint source for
deterministic dnsmasq export, and storage surface for deterministic evaluations.
