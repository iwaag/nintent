"""Runtime model and migration contracts for the current intent-catalog schema."""

from __future__ import annotations

try:
    from django.db import connection
    from django.db.migrations.loader import MigrationLoader
    from nautobot.core.testing import TestCase

    from nautobot_intent_catalog.models import DesiredNode, DesiredService
except ImportError:  # pragma: no cover - local Django-free discovery.
    pass
else:

    class ModelContractTests(TestCase):
        """Current ORM state and its historical migration path."""

        def test_desired_models_omit_reconciliation_cache_fields_and_constants(self):
            removed_fields = {"reconciliation_status", "reconciliation_checked_at"}
            removed_constants = {
                "RECONCILIATION_CONVERGED",
                "RECONCILIATION_DRIFTING",
                "RECONCILIATION_CONVERGING",
                "RECONCILIATION_UNKNOWN",
                "RECONCILIATION_STATUS_CHOICES",
            }
            for model in (DesiredNode, DesiredService):
                with self.subTest(model=model.__name__):
                    self.assertTrue(removed_fields.isdisjoint(field.name for field in model._meta.get_fields()))
                    self.assertTrue(removed_constants.isdisjoint(vars(model)))

        def test_migration_graph_retains_history_and_current_project_state_omits_cache_fields(self):
            loader = MigrationLoader(connection)
            app_label = "nautobot_intent_catalog"
            introduced = (app_label, "0009_reconciliation_status")
            removed = (app_label, "0016_remove_reconciliation_dashboard_surfaces")
            self.assertIn(introduced, loader.graph.nodes)
            self.assertIn(removed, loader.graph.nodes)
            self.assertIn(introduced, loader.graph.forwards_plan(removed))

            state = loader.project_state([removed])
            for model_name in ("desirednode", "desiredservice"):
                with self.subTest(model=model_name):
                    fields = state.models[(app_label, model_name)].fields
                    self.assertNotIn("reconciliation_status", fields)
                    self.assertNotIn("reconciliation_checked_at", fields)
