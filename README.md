# Nautobot Intent Catalog

`nintent` stores the normalized current desired state in Nautobot. The only
supported desired-state mutation surface is the authenticated batch endpoint:

```text
POST /api/plugins/intent-catalog/desired-state/batch/
```

The request is the Phase 0 `nintent.desired-state-batch.v1` document. Set
`dry_run: true` to plan without writes; set it to `false` to atomically apply
the complete operation list. A conflict response writes nothing. GraphQL and
the nintent UI are read-only desired-state consumers.

Use `nctl desired apply -f FILE` to preview an operator document and add
`--yes` to commit it. `nctl lifecycle` and reconciliation ledger links use the
same endpoint. nintent does not read a Git-held desired-state file, and no App
setting or environment variable points at one.

Nautobot prerequisites, nodeutils ingest policy, Braindumps, Alignment
Reviews, and the `Reconcile Desired IPAM Intent` Job remain separate domains.

## Service bindings

`DesiredServiceBinding` declares that a consumer placement needs a provider
*service* (`consumer_placement`, `binding_name`, `provider_service`):

```text
DesiredServicePlacement (consumer)
    -- DesiredServiceBinding -->
DesiredService (provider)
    -- resolution -->
DesiredServicePlacement (provider instance)
    -- endpoint -->
DesiredEndpoint
```

The binding targets the logical service, not a specific provider placement,
so a binding describes *what* the consumer needs while *which* placement
currently fulfills it is resolved separately. This keeps swapping the
provider instance behind a service from touching any consumer's binding row,
and makes provider-service deletion protection a simple "does this service
still have inbound bindings" check instead of a per-instance one. Resolution
(one active placement, one usable endpoint) is computed on every read, never
stored — zero or more-than-one active provider placements are reported as
unresolved/ambiguous, not guessed at.

## Install and test

Enable `nautobot_intent_catalog` in `PLUGINS`, run:

```bash
nautobot-server migrate nautobot_intent_catalog
python3 -m unittest discover -s nautobot_intent_catalog/tests
```

For the full local/runtime gate matrix, see the parent
[`README_DEV.md`](../README_DEV.md).
