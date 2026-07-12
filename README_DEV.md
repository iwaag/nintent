# Development Notes

## Current Boundary

`nautobot_intent_catalog` is the application layer for cluster intent. The code
currently analyzes Git-backed intent sources and persists desired service,
dependency, node, and endpoint records. Package, AppConfig, URL base, settings
key, Job names, and YAML loader names use Intent Catalog terminology.

The App should not depend on the physical checkout path of another repository.
When a YAML input file is needed during local development, provide it explicitly:

```python
PLUGINS_CONFIG = {
    "nautobot_intent_catalog": {
        "intent_sources_file": "/absolute/path/to/nauto/seed/intent_sources.yaml",
    },
}
```

For simple local testing, the equivalent environment variable is:

```bash
export NAUTOBOT_INTENT_SOURCES_FILE=/absolute/path/to/nauto/seed/intent_sources.yaml
```

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

Production inventory schema 1.0 and deployment-profile Job inputs are validated
by the Django-free `production_inventory_contract.py` module. Its scenario
fixtures cover supported platforms, actual-data freshness, reference failures,
profile validation, drift, power policy, and placement-variable conflicts.

### Quick Service Placement test boundary

The Quick Service Placement feature keeps its validation in Django-free layers so
the contract is testable without Nautobot:

- `tests/test_deployment_profiles.py` covers the read-only deployment_profiles
  projection accessor (`deployment_profiles.py`): export-contract ingestion
  (`project_deployment_profiles`, sharing `parse_profile_job_input` /
  `validate_deployment_profiles` with export), read-time revalidation, and the
  explicit "not synced" signal (`DeploymentProfilesUnavailable`).
- `tests/test_operations_placements.py` covers the placement operation
  (`operations/placements.py`): profile-derived `config_schema_version`, fixed
  `assignment_source="manual"`, slug-derived default `instance_name`, config
  validation via `map_placement_config`, endpoint ownership, instance uniqueness,
  and that derived fields are not operation inputs (so they cannot be hand-typed).

These require a Nautobot runtime and are therefore **not** covered by local unit
tests; verify them in a real Nautobot environment:

- `DeploymentProfileProjection` model persistence, the `SyncDeploymentProfiles`
  Job upsert/prune, and `load_deployment_profiles()` reading from the DB.
- The Quick Add form's dynamic `config` field generation from the selected
  profile schema, its "not synced" `clean()` error, and endpoint queryset
  filtering (`DesiredServicePlacementQuickAddForm`).
- The Quick Add view render/redirect and `desired_service` prefill, plus the
  "Place this service" link on the service detail page.
- That the regular CRUD `DesiredServicePlacementForm` and the Quick Add path stay
  consistent in omitting the derived `config_schema_version` / `assignment_source`
  inputs (the operation enforces the derived/fixed values; the model defaults back
  it; `tests/test_templates.py` guards the FormView templates against removal).

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

## Nautobot UI Compatibility

When adding object views for app models, either create the expected
`{app_label}/{model_name}.html` template or set `template_name` explicitly.
Generic `ObjectView` redirects can otherwise fail after a successful database
write because the default detail template is missing.

Keep `tests/test_templates.py` in sync with every default-template `ObjectView`;
it catches missing detail templates without a Nautobot runtime.

On Nautobot 3.1.x, `ButtonsColumn` includes a changelog action by default. If a
model does not provide a changelog URL/view, pass an explicit button set such as
`buttons=("edit", "delete")`. Also check related `tables.LinkColumn()` fields:
linked models need working `get_absolute_url()` targets and detail templates.

## Nautobot Model Compatibility

Do not assume display properties are ORM fields. For example, Nautobot 3.1.x
`IPAddress` uses concrete fields such as `host` and `mask_length`, so ORM calls
should order or filter on those fields instead of `address`.

Keep cross-version object conversion at the boundary where Nautobot models are
turned into app facts. Prefer small compatibility helpers there over scattering
direct assumptions such as `IPAddress.address` through evaluation logic.

## REST API

`DesiredNode` and `DesiredEndpoint` are the only two models with a REST API
today, deliberately scoped to the two models an agent needs to check
desired-vs-actual host/IP state. The implementation lives under
`nautobot_intent_catalog/api/`:

- `api/serializers.py`: `DesiredNodeSerializer` / `DesiredEndpointSerializer`,
  both plain `NautobotModelSerializer` subclasses with `fields = "__all__"`.
- `api/views.py`: `DesiredNodeViewSet` / `DesiredEndpointViewSet`, both plain
  `NautobotModelViewSet` subclasses reusing the existing `DesiredNodeFilterSet`
  / `DesiredEndpointFilterSet` from `filters.py`.
- `api/urls.py`: an `OrderedDefaultRouter` registering `nodes` and
  `endpoints`. Nautobot auto-discovers this via
  `import_string_optional(f"{app_module}.api.urls.urlpatterns")` in
  `nautobot.extras.plugins.__init__`, so no manual URL wiring in the main
  Nautobot install is required beyond the existing App installation.

Unlike `models.py`/`filters.py`, the `api/` package does not need the
`try/except ImportError` guard for Nautobot-less local unit tests: Nautobot
only imports `api/urls.py` when the App is loaded inside a real Nautobot
process, so a plain top-level `from nautobot.apps.api import ...` is fine.

To add another model to the API later, follow the same three-file pattern and
register it on the existing `router` in `api/urls.py`; there is no need for a
new router per model.

### Verifying the API in a running Nautobot

There is no local (Django-free) test coverage for the API layer since it only
exists inside a real Nautobot process. Verify it against a running instance:

```bash
curl -H "Authorization: Token <api-token>" http://localhost:8000/api/plugins/intent-catalog/nodes/
curl -H "Authorization: Token <api-token>" http://localhost:8000/api/plugins/intent-catalog/endpoints/
```

A 404 on `/api/plugins/intent-catalog/...` after installing this change
usually means the running container still has the old package (see the
GitHub-install/rebuild flow above) rather than a code problem.

## Rename Cleanup Checks

Before completing a rename-oriented step, run searches for old implementation
names. The concrete cleanup search patterns and manual removal targets are
documented in `README.md` under `Manual Cleanup During Rename`.

```bash
rg "old implementation name pattern"
```

Only migration history notes or explicit manual cleanup documentation should
refer to removed names.
