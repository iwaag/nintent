"""Nautobot-runtime tests for WorkflowEpisode: model, API, and (Step 3) GUI.

Guarded by the same ``try/except ImportError`` pattern as ``models.py`` so this module is
harmless to import during local Django-free test discovery; the real cases only execute
under Nautobot's own test runner (``nautobot-server test nautobot_intent_catalog.tests.test_workflow_episode``).
"""

from __future__ import annotations

try:
    from django.core.exceptions import ValidationError
    from django.urls import reverse
    from rest_framework import status

    from nautobot.core.testing import TestCase
    from nautobot.core.testing.api import APITestCase

    from nautobot_intent_catalog.models import WorkflowEpisode
except ImportError:  # pragma: no cover - Nautobot/Django are unavailable in local unit tests.
    pass
else:

    def _make_episode(**overrides):
        defaults = {"title": "Test Episode"}
        defaults.update(overrides)
        return WorkflowEpisode.objects.create(**defaults)

    class WorkflowEpisodeModelTests(TestCase):
        """Model-level field, transition, and raw_data validation coverage."""

        def test_status_defaults_to_candidate(self):
            episode = _make_episode()
            self.assertEqual(episode.status, WorkflowEpisode.STATUS_CANDIDATE)

        def test_raw_data_defaults_to_empty_dict(self):
            episode = _make_episode()
            self.assertEqual(episode.raw_data, {})

        def test_empty_or_whitespace_only_title_rejected(self):
            for title in ("", "   "):
                with self.subTest(title=repr(title)):
                    with self.assertRaises(ValidationError):
                        WorkflowEpisode(title=title).full_clean()

        def test_unknown_raw_data_namespace_rejected(self):
            episode = WorkflowEpisode(title="T", raw_data={"typo_namespace": {}})
            with self.assertRaises(ValidationError):
                episode.full_clean()

        def test_non_dict_namespace_value_rejected(self):
            episode = WorkflowEpisode(title="T", raw_data={"report": "not a dict"})
            with self.assertRaises(ValidationError):
                episode.full_clean()

        def test_valid_raw_data_accepted(self):
            episode = WorkflowEpisode(
                title="T",
                raw_data={"schema_version": 1, "report": {"summary": "..."}, "references": {"session_id": "s1"}},
            )
            episode.full_clean()  # must not raise

    class WorkflowEpisodeAPITests(APITestCase):
        """REST create/read, transition actions, and per-namespace write coverage."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                "nautobot_intent_catalog.view_workflowepisode",
                "nautobot_intent_catalog.add_workflowepisode",
                "nautobot_intent_catalog.change_workflowepisode",
                "nautobot_intent_catalog.delete_workflowepisode",
            )
            self.episodes_url = reverse("plugins-api:nautobot_intent_catalog-api:workflowepisode-list")

        def _detail_url(self, episode):
            return f"{self.episodes_url}{episode.pk}/"

        def _action_url(self, episode, action):
            return f"{self.episodes_url}{episode.pk}/{action}/"

        def test_create_and_read_while_generic_mutation_is_rejected(self):
            response = self.client.post(
                self.episodes_url,
                {"title": "Self-report", "raw_data": {"report": {"summary": "..."}, "references": {"session_id": "s1"}}},
                format="json",
                **self.header,
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(response.data["status"], WorkflowEpisode.STATUS_CANDIDATE)
            episode_id = response.data["id"]
            detail_url = f"{self.episodes_url}{episode_id}/"

            self.assertEqual(self.client.get(detail_url, **self.header).status_code, status.HTTP_200_OK)
            self.assertEqual(self.client.get(self.episodes_url, **self.header).status_code, status.HTTP_200_OK)

            for response in (
                self.client.patch(detail_url, {"title": "renamed"}, format="json", **self.header),
                self.client.put(detail_url, {"title": "renamed"}, format="json", **self.header),
                self.client.delete(detail_url, **self.header),
            ):
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        def test_create_with_client_supplied_status_is_rejected(self):
            # status is not a writable field (not in the mutation allow-list); this proves
            # a client cannot smuggle a starting status other than "candidate" past create.
            response = self.client.post(
                self.episodes_url,
                {"title": "T", "status": WorkflowEpisode.STATUS_RESOLVED},
                format="json",
                **self.header,
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(WorkflowEpisode.objects.filter(title="T").exists())

        def test_create_with_unknown_raw_data_namespace_fails(self):
            response = self.client.post(
                self.episodes_url, {"title": "T", "raw_data": {"bogus": {}}}, format="json", **self.header
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        def test_full_transition_round_trip(self):
            episode = _make_episode()

            select_response = self.client.post(self._action_url(episode, "select"), {}, format="json", **self.header)
            self.assertEqual(select_response.status_code, status.HTTP_200_OK)
            self.assertEqual(select_response.data["status"], WorkflowEpisode.STATUS_SELECTED)

            resolve_response = self.client.post(self._action_url(episode, "resolve"), {}, format="json", **self.header)
            self.assertEqual(resolve_response.status_code, status.HTTP_200_OK)
            self.assertEqual(resolve_response.data["status"], WorkflowEpisode.STATUS_RESOLVED)

            episode.refresh_from_db()
            self.assertEqual(episode.status, WorkflowEpisode.STATUS_RESOLVED)

        def test_candidate_to_dismissed_direct_transition(self):
            episode = _make_episode()
            response = self.client.post(self._action_url(episode, "dismiss"), {}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["status"], WorkflowEpisode.STATUS_DISMISSED)

        def test_second_select_on_already_selected_episode_rejected(self):
            episode = _make_episode()
            first = self.client.post(self._action_url(episode, "select"), {}, format="json", **self.header)
            self.assertEqual(first.status_code, status.HTTP_200_OK)

            second = self.client.post(self._action_url(episode, "select"), {}, format="json", **self.header)
            self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
            episode.refresh_from_db()
            self.assertEqual(episode.status, WorkflowEpisode.STATUS_SELECTED)

        def test_resolve_before_select_rejected(self):
            episode = _make_episode()
            response = self.client.post(self._action_url(episode, "resolve"), {}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            episode.refresh_from_db()
            self.assertEqual(episode.status, WorkflowEpisode.STATUS_CANDIDATE)

        def test_patch_status_through_standard_serializer_rejected(self):
            episode = _make_episode()
            response = self.client.patch(
                self._detail_url(episode), {"status": WorkflowEpisode.STATUS_SELECTED}, format="json", **self.header
            )
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
            episode.refresh_from_db()
            self.assertEqual(episode.status, WorkflowEpisode.STATUS_CANDIDATE)

        def test_namespace_write_updates_only_its_own_namespace(self):
            episode = _make_episode(
                raw_data={
                    "report": {"summary": "original report"},
                    "references": {"session_id": "s1"},
                }
            )

            response = self.client.post(
                self._action_url(episode, "assessment"), {"verdict": "promote"}, format="json", **self.header
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            episode.refresh_from_db()
            self.assertEqual(episode.raw_data["assessment"], {"verdict": "promote"})
            self.assertEqual(episode.raw_data["report"], {"summary": "original report"})
            self.assertEqual(episode.raw_data["references"], {"session_id": "s1"})

        def test_namespace_write_replaces_wholesale_not_merges(self):
            episode = _make_episode(raw_data={"report": {"summary": "v1", "extra": "keep?"}})

            response = self.client.post(
                self._action_url(episode, "report"), {"summary": "v2"}, format="json", **self.header
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            episode.refresh_from_db()
            self.assertEqual(episode.raw_data["report"], {"summary": "v2"})

        def test_namespace_write_rejects_non_object_body(self):
            episode = _make_episode()
            response = self.client.post(
                self._action_url(episode, "report"), ["not", "an", "object"], format="json", **self.header
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
