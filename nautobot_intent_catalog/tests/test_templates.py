from __future__ import annotations

import unittest
from pathlib import Path


class ObjectViewTemplateTests(unittest.TestCase):
    def test_default_object_view_templates_exist(self) -> None:
        template_dir = (
            Path(__file__).resolve().parents[1]
            / "templates"
            / "nautobot_intent_catalog"
        )
        expected_templates = {
            "braindumpdocument.html",
            "desiredcomputeinstance.html",
            "desiredcomputeplatform.html",
            "desireddependency.html",
            "desiredendpoint.html",
            "desirediprange.html",
            "desirednode.html",
            "desirednodeoperationaloverride.html",
            "desiredservice.html",
            "desiredserviceplacement.html",
            "intentsource.html",
        }

        missing_templates = sorted(
            template_name
            for template_name in expected_templates
            if not (template_dir / template_name).is_file()
        )

        self.assertEqual(missing_templates, [])

    def test_form_view_templates_exist(self) -> None:
        template_dir = (
            Path(__file__).resolve().parents[1]
            / "templates"
            / "nautobot_intent_catalog"
        )
        # FormView templates are referenced by template_name, not by the generic
        # ObjectView lookup, so guard them explicitly against accidental removal.
        expected_templates = {
            "desiredhost_quick_add.html",
        }

        missing_templates = sorted(
            template_name
            for template_name in expected_templates
            if not (template_dir / template_name).is_file()
        )

        self.assertEqual(missing_templates, [])


if __name__ == "__main__":
    unittest.main()
