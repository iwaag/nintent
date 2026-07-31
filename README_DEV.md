# Development Notes

## Current Boundary

`nautobot_intent_catalog` is the application layer for cluster intent. The code
currently analyzes Git-backed intent sources and persists desired service,
dependency, node, and endpoint records. Package, AppConfig, URL base, settings
key, Job names, and YAML loader names use Intent Catalog terminology.

The App must not depend on another repository checkout or a desired-state file.
Submit the Phase 0 batch document to the authenticated desired-state batch endpoint.

No fallback to old plugin names, old setting keys, old import paths, or old URL
aliases should be added. If an implementation change leaves obsolete database
tables or configuration behind, document the manual cleanup in `README.md`
instead of adding automatic deletion code.

## Local Tests

This workspace does not include Nautobot or Django, so the fast checks focus on
loader, importer, and analysis code that can run without Nautobot:

```bash
python3 -m unittest discover -s nautobot_intent_catalog/tests
```

Desired-state request validation lives in the Django-free `batch.py`. Production composition,
profile validation, actual-fact policy, and drift comparators live and are tested in nctl; do not
reintroduce those processing rules here.

`compute_contract.py` is the semantic owner for the shared compute contract. Its Django-free
`compute_conformance.py` executes that owner over the ordered JSON-only case set and publishes the
deterministic fixture consumed by nctl. Change compute semantics here first, regenerate the
consumer fixture with `devtests/test_strategy/generate_compute_conformance.py` in the parent
repository, then run both the superproject freshness gate and nctl's replay test; nctl must not
import this module at runtime.

The local suite does not load Django/Nautobot. Model migrations, GraphQL registration, Job discovery,
and UI views must also be verified in the running Nautobot environment after deployment.
The repository [test strategy command matrix](../README_DEV.md#test-strategy-command-matrix) is the
authoritative list of runtime, clean-database, and conformance gates.

## Nautobot Verification

After installing into a real Nautobot environment, verify migrations there:

```bash
nautobot-server makemigrations nautobot_intent_catalog --check --dry-run
nautobot-server migrate nautobot_intent_catalog
```

If `makemigrations --check --dry-run` reports changes, regenerate the migration
inside that Nautobot environment and review only the App model differences.

For Job changes, verify discovery inside the same Nautobot environment:

```python
import nautobot_intent_catalog.jobs as j
print([job.__name__ for job in j.jobs])
```

If new Jobs are missing, check imports before UI permissions. Job modules should
use fully qualified Nautobot imports such as `nautobot.dcim.models`,
`nautobot.ipam.models`, and `nautobot.virtualization.models`; if Nautobot is
installed, broken imports should fail loudly instead of falling back to
`jobs = ()`. Register app Jobs with `register_jobs(*jobs)`, then run the normal
Nautobot upgrade/sync workflow and restart both web and worker processes.

### `Reconcile Desired IPAM Intent` (ipam_policy plan)

This Job's eligibility/type-resolution logic (`operations/ipam.py`) is Django-free and covered by
the local suite, but its queryset, real `IPAddress.type` choices, and custom-field reads on a real
Device row can only be proven against a live Nautobot instance:

- Confirm `nautobot-server makemigrations nautobot_intent_catalog --check --dry-run` reports no
  changes (this plan added no model fields).
- Confirm the Job's discovered `Meta.description` no longer says "DHCP-reserved" only.
- Dry-run (`commit_changes=False`) scoped to one `desired_node` whose primary endpoint has an
  explicit `static`/`external` IP and a linked realized Device reporting a matching
  `primary_ip_address` custom field. The summary must show `endpoints: 1`, the endpoint's id, and a
  Host-equivalent (not DHCP-equivalent) `create_fields.type`.
- Confirm a Device whose `primary_ip_address` custom field is absent or does not match produces a
  `skip` row with reason `observation_missing`/`observation_mismatch`, not a create/link attempt.
- Only after dry-run review, apply (`commit_changes=True`) and confirm the created/linked
  `IPAddress.type` is actually the Host-equivalent choice the model exposes (never invented), and
  that `DesiredEndpoint.realized_ip_address_source` is saved as `derived`.

## Nautobot UI Compatibility

When adding object views for app models, either create the expected
`{app_label}/{model_name}.html` template or set `template_name` explicitly.
Generic `ObjectView` redirects can otherwise fail after a successful database
write because the default detail template is missing.

Keep `tests/test_templates.py` in sync with every default-template `ObjectView`;
it catches missing detail templates without a Nautobot runtime.

Interface Contract Phase 3 deleted every nintent `ObjectEditView`, `ObjectDeleteView`, `FormView`,
`ButtonsColumn`, and `ToggleColumn`; `tables.py` defines only read-only list tables now (see
`tests/test_ui_contract.py::UIContractManifestTests.test_tables_have_no_action_or_toggle_columns`).
Do not reintroduce `ButtonsColumn`/`ToggleColumn`/`TABLE_ACTION_BUTTONS` or a mutation view for a
nintent model. `tables.LinkColumn()` fields still need working `get_absolute_url()` targets and
detail templates, since those remain read-only navigation, not mutation, affordances.

## Nautobot Model Compatibility

Do not assume display properties are ORM fields. For example, Nautobot 3.1.x
`IPAddress` uses concrete fields such as `host` and `mask_length`, so ORM calls
should order or filter on those fields instead of `address`.

Keep cross-version object conversion at the boundary where Nautobot models are
turned into app facts. Prefer small compatibility helpers there over scattering
direct assumptions such as `IPAddress.address` through evaluation logic.

## REST API

`DesiredNode`, `DesiredComputePlatform`, `DesiredComputeInstance`, `BrainDumpDocument`, and `AlignmentReview` are the five retained REST collections. The compute collections are the Phase 2 narrow writer for realization links only; `DesiredService` and `DesiredEndpoint` REST surfaces remain removed. The implementation lives under `nautobot_intent_catalog/api/`:

- `api/serializers.py`: all serializers use explicit fields (never `fields = "__all__"`). The compute serializers permit only the respective relation/source pair and enforce that the source exists exactly with the relation.
- `api/views.py`: compute link ViewSets allow only incidental `GET` and detail `PATCH`; `POST`, `PUT`, `DELETE`, list `PATCH`, and list `DELETE` return `405 Method Not Allowed`.
- `api/urls.py`: an `OrderedDefaultRouter` registering `nodes`, `compute-platforms`, `compute-instances`, `braindumps`, and `alignment-reviews`. Nautobot auto-discovers this via `import_string_optional(f"{app_module}.api.urls.urlpatterns")` in `nautobot.extras.plugins.__init__`.

Unlike `models.py`/`filters.py`, the `api/` package does not need the `try/except ImportError` guard for Nautobot-less local unit tests: Nautobot only imports `api/urls.py` when the App is loaded inside a real Nautobot process, so a plain top-level `from nautobot.apps.api import ...` is fine.

### Verifying the API in a running Nautobot

There is no local (Django-free) test coverage for the API layer since it only exists inside a real Nautobot process. Verify it against a running instance:

```bash
curl -H "Authorization: Token <api-token>" http://localhost:8000/api/plugins/intent-catalog/nodes/
curl -H "Authorization: Token <api-token>" http://localhost:8000/api/plugins/intent-catalog/compute-platforms/
curl -H "Authorization: Token <api-token>" http://localhost:8000/api/plugins/intent-catalog/compute-instances/
curl -H "Authorization: Token <api-token>" http://localhost:8000/api/plugins/intent-catalog/braindumps/
curl -H "Authorization: Token <api-token>" http://localhost:8000/api/plugins/intent-catalog/alignment-reviews/
```

Requests to removed collections (e.g. `/api/plugins/intent-catalog/services/` or `/api/plugins/intent-catalog/endpoints/`) return 404 Not Found.

## Rename Cleanup Checks

Before completing a rename-oriented step, run searches for old implementation
names. The concrete cleanup search patterns and manual removal targets are
documented in `README.md` under `Manual Cleanup During Rename`.

```bash
rg "old implementation name pattern"
```

Only migration history notes or explicit manual cleanup documentation should
refer to removed names.
