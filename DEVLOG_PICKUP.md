# Devlog Pickup

## IntentEvaluation detail template gap

Date: 2026-06-24

### Symptoms

Opening an `IntentEvaluation` detail page in Nautobot 3.1.3 failed with:

```text
django.template.exceptions.TemplateDoesNotExist: nautobot_intent_catalog/intentevaluation.html
```

The app was installed from GitHub into the container, so local workspace fixes
would not affect the running service until pushed or installed from a local
path and the image/container was rebuilt.

### Cause

`IntentEvaluationView` inherited from Nautobot's `ObjectView` without setting
`template_name`. Nautobot therefore derived the detail template path from the
app label and model name:

```text
nautobot_intent_catalog/intentevaluation.html
```

That template was not present. A horizontal check showed the same gap for other
model detail views that also relied on default template resolution:

```text
nautobot_intent_catalog/intentsource.html
nautobot_intent_catalog/desiredservice.html
```

`desirednode.html` and `desiredendpoint.html` already existed because an earlier
UI compatibility fix handled only the pages that had failed at that time.

### Fix applied here

- Added detail templates for `IntentSource`, `DesiredService`,
  and `IntentEvaluation`.
- Added a local unit test that checks all default `ObjectView` detail template
  files exist, so this class of omission is caught without requiring Django or
  Nautobot in the development workspace.

### Future checklist

When adding or renaming a Nautobot `ObjectView` for an app model, update the
template checklist/test at the same time as the URL and view. Do not stop after
fixing only the page that produced the first `TemplateDoesNotExist`; scan every
`ObjectView` using default template resolution.

## Nautobot 3.1.3 UI compatibility notes

Date: 2026-06-23

### Symptoms

After adding Quick Host Add, object creation succeeded in the database, but UI
pages failed while rendering node/endpoint views.

Observed errors:

- `TemplateDoesNotExist: nautobot_intent_catalog/desirednode.html`
- `NoReverseMatch: Reverse for 'desiredendpoint_changelog' not found`
- Desired Endpoints list showed: `Failed to load table content. The server responded with status: 500`

### Cause

Nautobot generic object views and tables assume more UI plumbing than this app
had implemented.

`ObjectView` resolves its template from the model app label and model name when
`template_name` is not set. For `DesiredNode`, that means:

```text
nautobot_intent_catalog/desirednode.html
```

If the template is missing, redirecting to the object detail page after create
will fail even though the database write succeeded.

Nautobot 3.1.3 `ButtonsColumn` also renders a changelog action by default. The
default button set is effectively:

```text
changelog, edit, delete
```

For app models that only define detail/edit/delete URLs, this causes reverse
lookups such as the following to fail during table rendering:

```text
plugins:nautobot_intent_catalog:desiredendpoint_changelog
```

This is especially easy to hit with older plugin-style code because list tables
may have worked before a Nautobot upgrade, then start failing once the default
action column expects changelog routes.

### Fix applied here

- Added `nautobot_intent_catalog/templates/nautobot_intent_catalog/desirednode.html`.
- Added `nautobot_intent_catalog/templates/nautobot_intent_catalog/desiredendpoint.html`.
- Changed all app `ButtonsColumn(...)` usages to explicitly use only:

```python
("edit", "delete")
```

### Future checklist

When adding a Nautobot `ObjectView` for an app model, do one of the following:

- create the expected `{app_label}/{model_name}.html` template, or
- set `template_name` explicitly on the view.

When using `ButtonsColumn` on Nautobot 3.1.x or later, either:

- define the expected changelog URL/view for the model, or
- pass an explicit button set such as `buttons=("edit", "delete")`.

Also check related table columns using `tables.LinkColumn()`. They rely on the
related object's `get_absolute_url()`, so the target detail route and template
must exist if users can click through.

## Nautobot 2.x/3.x Job registration notes

Date: 2026-06-23

### Symptoms

After adding `Export dnsmasq Records`, the Job class existed in
`nautobot_intent_catalog/jobs.py`, but the job did not appear in the Nautobot
Jobs list after reload/post-upgrade.

### Cause

Defining Job classes and a module-level `jobs = (...)` tuple is not sufficient
for current Nautobot job discovery. Nautobot 2.x/3.x apps should register jobs
from the jobs module with `register_jobs()`.

This can be confusing because older Job records may still be present in the
database and visible in the UI, while newly added Job classes do not get
created unless they are registered during module import.

### Fix applied here

Import `register_jobs` from `nautobot.apps.jobs` and call it after all Job
classes are defined:

```python
jobs = (PreviewIntentSourceAnalysis, ImportIntentSources, AnalyzeIntentSources, ExportDnsmasqRecords)
register_jobs(*jobs)
```

After changing job registration, run Nautobot's normal upgrade/sync workflow
and restart both web and worker processes.

## Nautobot 3.x Job import path notes

Date: 2026-06-24

### Symptoms

The `nautobot_intent_catalog` app was installed and loaded by Nautobot 3.1.3,
but none of its Jobs appeared in the Nautobot UI.

The app itself was clearly present:

- `PLUGINS = ["nautobot_intent_catalog"]` was configured.
- migration output included `nautobot_intent_catalog`.
- Nautobot logs emitted serializer warnings for `nautobot_intent_catalog`
  models.

However, importing the jobs module inside the running Nautobot container showed
an empty module-level `jobs` tuple:

```python
import nautobot_intent_catalog.jobs as j
print([job.__name__ for job in j.jobs])
# []
```

This means Nautobot had no app Jobs to refresh/register, even though
`nautobot_intent_catalog/jobs.py` existed in site-packages.

### Cause

`jobs.py` used old short Nautobot model import paths:

```python
from dcim.models import Device
from ipam.models import IPAddress
from virtualization.models import VirtualMachine
```

In the observed Nautobot 3.1.3 container these modules were not importable:

```text
ModuleNotFoundError: No module named 'dcim'
ModuleNotFoundError: No module named 'ipam'
ModuleNotFoundError: No module named 'virtualization'
```

The correct import paths in that environment are fully qualified under the
`nautobot` package:

```python
from nautobot.dcim.models import Device
from nautobot.ipam.models import IPAddress
from nautobot.virtualization.models import VirtualMachine
```

The failure was hard to see because `jobs.py` wrapped all Nautobot imports in a
single `try` block and handled any `ImportError` with:

```python
jobs = ()
```

That fallback is useful for local unit tests where Nautobot is not installed,
but in a real Nautobot process it silently converts an import failure into "no
Jobs exist".

### Fix applied here

- Updated `jobs.py` to use fully qualified Nautobot 3-compatible model imports:

```python
from nautobot.dcim.models import Device
from nautobot.ipam.models import IPAddress
from nautobot.virtualization.models import VirtualMachine
```

- Kept the local no-Nautobot fallback, but changed it so that if the `nautobot`
  package is installed, `ImportError` is re-raised instead of being swallowed.

The practical effect is:

- local tests without Nautobot can still import loader/helper modules;
- real Nautobot deployments fail loudly on broken app imports;
- `jobs.py` can reach the Job class definitions and call `register_jobs(*jobs)`.

### Future checklist

When adding Job code that imports Nautobot models, prefer fully qualified
Nautobot imports:

```python
from nautobot.dcim.models import Device
from nautobot.ipam.models import IPAddress
from nautobot.virtualization.models import VirtualMachine
```

Avoid broad `except ImportError: jobs = ()` behavior in production-facing Job
modules. If a fallback is needed for local tests, only use it when Nautobot is
not installed; otherwise re-raise the exception so startup logs show the real
problem.

For missing Jobs in Nautobot, check in this order:

1. Import `nautobot_intent_catalog.jobs` inside the Nautobot container.
2. Print `[job.__name__ for job in nautobot_intent_catalog.jobs.jobs]`.
3. If the list is empty, investigate import failures before looking at UI
   permissions or Job enablement.
4. After fixing registration/imports, run the normal Nautobot upgrade/sync
   workflow and restart web and worker processes.

## Nautobot 3.x IPAddress field compatibility notes

Date: 2026-06-24

### Symptoms

`Evaluate Endpoint Intent` appeared in Nautobot and started, but failed in the
Job console with:

```text
django.core.exceptions.FieldError: Cannot resolve keyword 'address' into field.
Choices are: ... dns_name, host, ... mask_length, ...
```

### Cause

The endpoint evaluation Job queried Nautobot IP addresses with:

```python
IPAddress.objects.all().order_by("address")
```

In the observed Nautobot 3.1.3 environment, `IPAddress` does not expose
`address` as an ORM field. The model stores the address parts as fields such as
`host` and `mask_length`. Code may still need to support older test doubles or
older Nautobot-style objects that expose an `address` attribute, but ORM queries
must use concrete model fields for the deployed Nautobot version.

The same assumption also existed in deterministic endpoint evaluation helpers:
they read `actual_ip.address` when building observed facts and matching desired
endpoint IPs to actual `IPAddress` candidates. That path did not always crash
because it used `getattr()`, but it could silently fail to match Nautobot 3 IP
objects that only expose `host` and `mask_length`.

### Fix applied here

- Changed the Job candidate query to sort by concrete Nautobot 3 fields:

```python
IPAddress.objects.all().order_by("host", "mask_length")
```

- Added an IP display helper that prefers `actual_ip.address` when present and
  otherwise derives `host/mask_length`.
- Updated endpoint matching, observed facts, and actual refs to use the helper.
- Added tests for Nautobot 3-style `IPAddress` objects with `host` and
  `mask_length`.

### Future checklist

When using Nautobot model fields in ORM calls such as `filter()`, `exclude()`,
or `order_by()`, verify the exact field names in the target Nautobot version.
Properties and display helpers are not valid ORM field names.

For cross-version plugin code, keep compatibility helpers at the boundary where
model objects are converted into app facts. Avoid scattering direct assumptions
like `IPAddress.address` through evaluation logic.
