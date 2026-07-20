"""Phase 4 Step 4.2, Decisions 5 and 6 (p4/plan.md).

Three independent changes batched into one deployable migration:

1. Add ``DesiredService.analysis_provenance`` (read-only, Job-owned) and move the four
   legacy analysis keys out of ``requirements`` into it, byte-for-byte, preserving every
   other operator-owned key untouched. Reversible: the reverse merges the four legacy keys
   back into ``requirements`` for rollback.
2. Remove ``DesiredService.placement_policy`` outright -- Step 4.1's live preflight
   (``p4/report4.1.md``) confirmed zero non-empty rows. The guard below re-checks this at
   migration time and aborts rather than silently dropping data if that has changed.
3. Change the generic ``DesiredEndpoint.ip_policy`` default from ``static`` to ``external``
   (future rows only; no existing row is rewritten), matching strict YAML's already-live
   no-address/no-policy result.
"""

from django.db import migrations, models

_LEGACY_ANALYSIS_KEYS = ("analysis_status", "analysis_confidence", "analysis_reasons", "analysis_warnings")
_PROVENANCE_KEYS = ("status", "confidence", "reasons", "warnings")
_LEGACY_TO_PROVENANCE = dict(zip(_LEGACY_ANALYSIS_KEYS, _PROVENANCE_KEYS))
_PROVENANCE_TO_LEGACY = dict(zip(_PROVENANCE_KEYS, _LEGACY_ANALYSIS_KEYS))


def split_legacy_analysis_keys(apps, schema_editor):
    DesiredService = apps.get_model("nautobot_intent_catalog", "DesiredService")
    database = schema_editor.connection.alias

    for service in DesiredService.objects.using(database).iterator():
        requirements = service.requirements
        if not isinstance(requirements, dict):
            continue
        present = {key for key in _LEGACY_ANALYSIS_KEYS if key in requirements}
        if not present:
            continue

        provenance = dict(service.analysis_provenance) if isinstance(service.analysis_provenance, dict) else {}
        cleaned_requirements = dict(requirements)
        for legacy_key in present:
            provenance[_LEGACY_TO_PROVENANCE[legacy_key]] = cleaned_requirements.pop(legacy_key)

        service.requirements = cleaned_requirements
        service.analysis_provenance = provenance
        service.save(using=database, update_fields=["requirements", "analysis_provenance"])


def merge_legacy_analysis_keys_back(apps, schema_editor):
    """Reverse of `split_legacy_analysis_keys`: for rollback only."""

    DesiredService = apps.get_model("nautobot_intent_catalog", "DesiredService")
    database = schema_editor.connection.alias

    for service in DesiredService.objects.using(database).iterator():
        provenance = service.analysis_provenance
        if not isinstance(provenance, dict):
            continue
        present = {key for key in _PROVENANCE_KEYS if key in provenance}
        if not present:
            continue

        requirements = dict(service.requirements) if isinstance(service.requirements, dict) else {}
        cleaned_provenance = dict(provenance)
        for provenance_key in present:
            requirements[_PROVENANCE_TO_LEGACY[provenance_key]] = cleaned_provenance.pop(provenance_key)

        service.requirements = requirements
        service.analysis_provenance = cleaned_provenance
        service.save(using=database, update_fields=["requirements", "analysis_provenance"])


def guard_placement_policy_is_empty(apps, schema_editor):
    """Abort rather than silently drop a non-empty placement_policy (p4/plan.md Step 4.2 item 2).

    Step 4.1's live preflight found zero non-empty rows; this guard protects against that
    having changed between planning and this migration actually running.
    """

    DesiredService = apps.get_model("nautobot_intent_catalog", "DesiredService")
    database = schema_editor.connection.alias

    non_empty = [
        service.pk
        for service in DesiredService.objects.using(database).iterator()
        if service.placement_policy not in (None, {})
    ]
    if non_empty:
        raise RuntimeError(
            "0013_analysis_provenance_and_generic_endpoint_policy: refusing to drop non-empty "
            f"placement_policy on DesiredService rows {non_empty!r}. Export the values and amend "
            "p4/plan.md Decision 6 with a real consumer or data mapping before re-running this "
            "migration."
        )


def noop_reverse(apps, schema_editor):
    """placement_policy is re-added empty by the paired AddField reverse; nothing else to do."""


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_intent_catalog", "0012_desired_node_lifecycle_default_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="desiredservice",
            name="analysis_provenance",
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
        migrations.RunPython(split_legacy_analysis_keys, merge_legacy_analysis_keys_back),
        migrations.RunPython(guard_placement_policy_is_empty, noop_reverse),
        migrations.RemoveField(
            model_name="desiredservice",
            name="placement_policy",
        ),
        migrations.AlterField(
            model_name="desiredendpoint",
            name="ip_policy",
            field=models.CharField(
                choices=[
                    ("static", "Static"),
                    ("dhcp_reserved", "DHCP reserved"),
                    ("external", "External"),
                ],
                default="external",
                max_length=64,
            ),
        ),
    ]
