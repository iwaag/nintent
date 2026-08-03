from __future__ import annotations

import unittest

from nautobot_intent_catalog.workflow_episode_contract import (
    ALLOWED_TRANSITIONS,
    STATUS_CANDIDATE,
    STATUS_DISMISSED,
    STATUS_RESOLVED,
    STATUS_SELECTED,
    WorkflowEpisodeContractError,
    validate_raw_data_shape,
    validate_transition,
)


class ValidateTransitionTests(unittest.TestCase):
    def test_every_allowed_transition_succeeds(self):
        for current, allowed in ALLOWED_TRANSITIONS.items():
            for new_status in allowed:
                with self.subTest(current=current, new=new_status):
                    validate_transition(current, new_status)  # must not raise

    def test_selected_to_candidate_demotion_rejected(self):
        with self.assertRaises(WorkflowEpisodeContractError):
            validate_transition(STATUS_SELECTED, STATUS_CANDIDATE)

    def test_resolved_is_terminal(self):
        for new_status in (STATUS_CANDIDATE, STATUS_SELECTED, STATUS_DISMISSED, STATUS_RESOLVED):
            with self.subTest(new=new_status):
                with self.assertRaises(WorkflowEpisodeContractError):
                    validate_transition(STATUS_RESOLVED, new_status)

    def test_dismissed_is_terminal(self):
        for new_status in (STATUS_CANDIDATE, STATUS_SELECTED, STATUS_RESOLVED, STATUS_DISMISSED):
            with self.subTest(new=new_status):
                with self.assertRaises(WorkflowEpisodeContractError):
                    validate_transition(STATUS_DISMISSED, new_status)

    def test_self_transition_rejected(self):
        for status in ALLOWED_TRANSITIONS:
            with self.subTest(status=status):
                with self.assertRaises(WorkflowEpisodeContractError):
                    validate_transition(status, status)

    def test_unknown_current_status_rejected(self):
        with self.assertRaises(WorkflowEpisodeContractError):
            validate_transition("bogus", STATUS_SELECTED)


class ValidateRawDataShapeTests(unittest.TestCase):
    def test_full_valid_payload_accepted(self):
        validate_raw_data_shape(
            {
                "schema_version": 1,
                "report": {"summary": "..."},
                "assessment": {"verdict": "..."},
                "references": {"session_id": "..."},
                "resolution": {"outcome": "..."},
            }
        )  # must not raise

    def test_empty_dict_accepted(self):
        validate_raw_data_shape({})  # must not raise

    def test_non_dict_raw_data_rejected(self):
        with self.assertRaises(WorkflowEpisodeContractError):
            validate_raw_data_shape(["not", "a", "dict"])

    def test_unknown_top_level_key_rejected(self):
        with self.assertRaises(WorkflowEpisodeContractError):
            validate_raw_data_shape({"typo_namespace": {}})

    def test_non_dict_namespace_value_rejected(self):
        with self.assertRaises(WorkflowEpisodeContractError):
            validate_raw_data_shape({"report": "not a dict"})

    def test_non_int_schema_version_rejected(self):
        with self.assertRaises(WorkflowEpisodeContractError):
            validate_raw_data_shape({"schema_version": "1"})


if __name__ == "__main__":
    unittest.main()
