"""Nautobot-runtime tests for the Braindump/Alignment Review exchange diary.

Guarded by the same ``try/except ImportError`` pattern as ``models.py`` so this module is
harmless to import during local Django-free test discovery; the real cases only execute
under Nautobot's own test runner (``nautobot-server test nautobot_intent_catalog.tests.test_braindump``),
which provisions and migrates its own disposable database.
"""

from __future__ import annotations

try:
    import uuid

    from django.core.exceptions import ValidationError
    from django.db import IntegrityError, transaction
    from django.urls import NoReverseMatch, reverse
    from rest_framework import status

    from nautobot.core.testing import TestCase
    from nautobot.core.testing.api import APITestCase

    from nautobot_intent_catalog.models import AlignmentReview, BrainDumpDocument
except ImportError:  # pragma: no cover - Nautobot/Django are unavailable in local unit tests.
    pass
else:

    def _make_braindump(**overrides):
        defaults = {
            "title": "Test Braindump",
            "body": "Body text.",
            "authorship": BrainDumpDocument.AUTHORSHIP_USER_DIRECT,
        }
        defaults.update(overrides)
        return BrainDumpDocument.objects.create(**defaults)

    class BrainDumpModelTests(TestCase):
        """Model-level field, validation, uniqueness, and cascade coverage."""

        def test_authorship_has_no_model_default(self):
            field = BrainDumpDocument._meta.get_field("authorship")
            self.assertFalse(field.has_default())

        def test_status_defaults_to_active(self):
            braindump = _make_braindump()
            self.assertEqual(braindump.status, BrainDumpDocument.STATUS_ACTIVE)

        def test_unicode_and_multiline_round_trip(self):
            body = "Line one\nライン2\n混在 mixed English\n😀 emoji"
            braindump = _make_braindump(title="日本語タイトル mixed", body=body)
            braindump.refresh_from_db()
            self.assertEqual(braindump.body, body)

        def test_accepted_surrounding_whitespace_is_not_rewritten(self):
            title = "  padded title  "
            body = "  padded body \n"
            braindump = BrainDumpDocument(
                title=title, body=body, authorship=BrainDumpDocument.AUTHORSHIP_USER_DIRECT
            )
            braindump.full_clean()
            self.assertEqual(braindump.title, title)
            self.assertEqual(braindump.body, body)

        def test_empty_and_whitespace_only_title_or_body_rejected(self):
            cases = [
                ("", "body"),
                ("   ", "body"),
                ("title", ""),
                ("title", "\n\t  "),
            ]
            for title, body in cases:
                with self.subTest(title=repr(title), body=repr(body)):
                    braindump = BrainDumpDocument(
                        title=title, body=body, authorship=BrainDumpDocument.AUTHORSHIP_USER_DIRECT
                    )
                    with self.assertRaises(ValidationError):
                        braindump.full_clean()

        def test_multiple_braindumps_may_share_a_title(self):
            _make_braindump(title="Shared title", body="one")
            _make_braindump(title="Shared title", body="two")
            self.assertEqual(BrainDumpDocument.objects.filter(title="Shared title").count(), 2)

        def test_review_summary_whitespace_only_rejected(self):
            braindump = _make_braindump()
            review = AlignmentReview(braindump=braindump, summary="   \n  ")
            with self.assertRaises(ValidationError):
                review.full_clean()

        def test_review_summary_surrounding_whitespace_not_rewritten(self):
            braindump = _make_braindump()
            summary = "  padded summary  "
            review = AlignmentReview(braindump=braindump, summary=summary)
            review.full_clean()
            self.assertEqual(review.summary, summary)

        def test_missing_review_means_unreviewed(self):
            braindump = _make_braindump()
            self.assertIsNone(getattr(braindump, "alignment_review", None))

        def test_one_review_per_braindump_enforced_at_database_level(self):
            braindump = _make_braindump()
            AlignmentReview.objects.create(braindump=braindump, summary="first")
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    AlignmentReview.objects.create(braindump=braindump, summary="second")
            self.assertEqual(AlignmentReview.objects.filter(braindump=braindump).count(), 1)

        def test_update_replaces_the_current_review_rather_than_appending(self):
            braindump = _make_braindump()
            review = AlignmentReview.objects.create(braindump=braindump, summary="v1")
            review.summary = "v2"
            review.save()
            self.assertEqual(AlignmentReview.objects.filter(braindump=braindump).count(), 1)
            review.refresh_from_db()
            self.assertEqual(review.summary, "v2")

        def test_review_only_deletion_preserves_its_braindump(self):
            braindump = _make_braindump()
            review = AlignmentReview.objects.create(braindump=braindump, summary="x")
            review.delete()
            self.assertTrue(BrainDumpDocument.objects.filter(pk=braindump.pk).exists())

        def test_braindump_deletion_cascades_to_its_review(self):
            braindump = _make_braindump()
            review = AlignmentReview.objects.create(braindump=braindump, summary="x")
            braindump.delete()
            self.assertFalse(AlignmentReview.objects.filter(pk=review.pk).exists())

        def test_neither_model_carries_reconciliation_fields(self):
            for model in (BrainDumpDocument, AlignmentReview):
                field_names = {f.name for f in model._meta.get_fields()}
                self.assertFalse(
                    any("reconciliation" in name for name in field_names),
                    f"{model.__name__} unexpectedly carries a reconciliation-status-like field",
                )


    class BrainDumpViewTests(TestCase):
        """Read-only UI route, panel-separation, escaping, and absence coverage.

        Interface Contract Phase 4 Step 1: the six cases below (`test_add_view_initial_authorship_
        is_user_direct`, `test_add_edit_delete_round_trip_and_agent_transcribed_selectable`,
        `test_review_add_binds_parent_and_returns_to_braindump`, `test_review_add_with_existing_
        review_redirects_to_edit_without_creating_a_second_row`, `test_review_edit_updates_summary_
        and_returns_to_braindump`, `test_review_delete_leaves_braindump_unreviewed_and_returns_to_it`)
        reversed and exercised deleted Braindump/Alignment Review add/edit/delete routes. Phase 3
        deleted those routes/views/forms; this class now proves their absence and that the retained
        read-only pages cannot mutate, instead of exercising mutation UI that no longer exists.
        REST immutability coverage for the same models lives in `BrainDumpAPITests` below.
        """

        user_permissions = (
            "nautobot_intent_catalog.view_braindumpdocument",
            "nautobot_intent_catalog.view_alignmentreview",
        )

        def test_list_view_shows_braindump(self):
            """Nautobot 3.1's ObjectListView renders table rows only for an htmx request;
            a plain page load intentionally serves an empty table shell first."""

            _make_braindump(title="Listed Braindump")
            response = self.client.get(
                reverse("plugins:nautobot_intent_catalog:braindumpdocument_list"), HTTP_HX_REQUEST="true"
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Listed Braindump")

        def test_detail_view_shows_unreviewed_and_both_panels(self):
            braindump = _make_braindump()
            response = self.client.get(braindump.get_absolute_url())
            self.assertContains(response, "User-originated Braindump")
            self.assertContains(response, "AI Alignment Review")
            self.assertContains(response, "Unreviewed")

        def test_detail_view_shows_reviewed_panel_content(self):
            braindump = _make_braindump()
            AlignmentReview.objects.create(braindump=braindump, summary="Looks aligned.")
            response = self.client.get(braindump.get_absolute_url())
            self.assertContains(response, "Looks aligned.")
            self.assertNotContains(response, "Unreviewed")

        def test_detail_view_escapes_script_and_html_looking_content(self):
            braindump = _make_braindump(
                title="<script>alert(1)</script>",
                body="<b>bold</b>\n$(rm -rf /)\n日本語のテスト",
            )
            AlignmentReview.objects.create(
                braindump=braindump, summary="<script>alert(2)</script> {{ template_injection }}"
            )
            response = self.client.get(braindump.get_absolute_url())
            content = response.content.decode()
            self.assertNotIn("<script>alert(1)</script>", content)
            self.assertNotIn("<script>alert(2)</script>", content)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", content)
            self.assertIn("&lt;script&gt;alert(2)&lt;/script&gt;", content)
            self.assertIn("{{ template_injection }}", content)  # inert literal text, not re-evaluated

        def test_detail_view_has_no_mutation_control(self):
            braindump = _make_braindump()
            AlignmentReview.objects.create(braindump=braindump, summary="x")
            response = self.client.get(braindump.get_absolute_url())
            content = response.content.decode()
            for needle in (
                'type="submit"',
                # The rendered CSRF hidden-input field name (Django's `{% csrf_token %}` tag
                # output). Not "csrf_token" alone: that substring also appears in the base
                # Nautobot page chrome's `nautobot_csrf_token` JS variable on every page,
                # mutation or not.
                "csrfmiddlewaretoken",
                "Add Alignment Review",
                "Edit",
                "Delete",
            ):
                self.assertNotIn(needle, content)

        def test_removed_braindump_and_review_routes_do_not_reverse(self):
            removed_names = [
                "braindumpdocument_add",
                "braindumpdocument_edit",
                "braindumpdocument_delete",
                "alignmentreview_add",
                "alignmentreview_edit",
                "alignmentreview_delete",
            ]
            dummy_pk = "00000000-0000-0000-0000-000000000000"
            for name in removed_names:
                with self.subTest(name=name):
                    with self.assertRaises(NoReverseMatch):
                        if name == "alignmentreview_add":
                            reverse(
                                f"plugins:nautobot_intent_catalog:{name}", kwargs={"braindump_pk": dummy_pk}
                            )
                        elif name.endswith(("_edit", "_delete")):
                            reverse(f"plugins:nautobot_intent_catalog:{name}", kwargs={"pk": dummy_pk})
                        else:
                            reverse(f"plugins:nautobot_intent_catalog:{name}")

        def test_former_literal_mutation_paths_return_404(self):
            braindump = _make_braindump()
            review = AlignmentReview.objects.create(braindump=braindump, summary="x")
            for path in (
                "/plugins/intent-catalog/braindumps/add/",
                f"/plugins/intent-catalog/braindumps/{braindump.pk}/edit/",
                f"/plugins/intent-catalog/braindumps/{braindump.pk}/delete/",
                f"/plugins/intent-catalog/braindumps/{braindump.pk}/reviews/add/",
                f"/plugins/intent-catalog/alignment-reviews/{review.pk}/edit/",
                f"/plugins/intent-catalog/alignment-reviews/{review.pk}/delete/",
            ):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path).status_code, 404)
                    self.assertEqual(self.client.post(path, {}).status_code, 404)

        def test_post_to_list_and_detail_pages_does_not_mutate(self):
            braindump = _make_braindump(title="Untouched", body="Untouched body")
            before_count = BrainDumpDocument.objects.count()
            list_url = reverse("plugins:nautobot_intent_catalog:braindumpdocument_list")
            detail_url = braindump.get_absolute_url()

            list_response = self.client.post(list_url, {"title": "mutation-attempt"})
            self.assertIn(list_response.status_code, (405, 200))
            detail_response = self.client.post(detail_url, {"title": "mutation-attempt"})
            self.assertIn(detail_response.status_code, (405, 200))

            braindump.refresh_from_db()
            self.assertEqual(braindump.title, "Untouched")
            self.assertEqual(braindump.body, "Untouched body")
            self.assertEqual(BrainDumpDocument.objects.count(), before_count)
            self.assertFalse(AlignmentReview.objects.filter(braindump=braindump).exists())


    class BrainDumpAPITests(APITestCase):
        """REST creation, reading, and immutability coverage."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                "nautobot_intent_catalog.view_braindumpdocument",
                "nautobot_intent_catalog.add_braindumpdocument",
                "nautobot_intent_catalog.change_braindumpdocument",
                "nautobot_intent_catalog.delete_braindumpdocument",
                "nautobot_intent_catalog.view_alignmentreview",
                "nautobot_intent_catalog.add_alignmentreview",
                "nautobot_intent_catalog.change_alignmentreview",
                "nautobot_intent_catalog.delete_alignmentreview",
            )
            self.braindumps_url = reverse("plugins-api:nautobot_intent_catalog-api:braindumpdocument-list")
            self.reviews_url = reverse("plugins-api:nautobot_intent_catalog-api:alignmentreview-list")
            self.supersede_url = f"{self.braindumps_url}supersede/"

        def test_supersede_creates_active_replacement_and_changes_exact_old_rows(self):
            first = _make_braindump(title="Old one")
            second = _make_braindump(title="Old two")
            untouched = _make_braindump(title="Untouched")
            response = self.client.post(
                self.supersede_url,
                {"old_ids": [str(first.pk), str(second.pk)], "title": "Replacement", "body": "new body", "authorship": "user_direct"},
                format="json", **self.header,
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            replacement = BrainDumpDocument.objects.get(pk=response.data["braindump"]["id"])
            self.assertEqual(replacement.status, BrainDumpDocument.STATUS_ACTIVE)
            self.assertEqual(response.data["superseded_ids"], [str(first.pk), str(second.pk)])
            first.refresh_from_db(); second.refresh_from_db(); untouched.refresh_from_db()
            self.assertEqual(first.status, BrainDumpDocument.STATUS_SUPERSEDED)
            self.assertEqual(second.status, BrainDumpDocument.STATUS_SUPERSEDED)
            self.assertEqual(untouched.status, BrainDumpDocument.STATUS_ACTIVE)

        def test_supersede_invalid_old_id_is_atomic(self):
            original = _make_braindump()
            before_count = BrainDumpDocument.objects.count()
            response = self.client.post(
                self.supersede_url,
                {"old_ids": [str(original.pk), str(uuid.uuid4())], "title": "Replacement", "body": "new body", "authorship": "user_direct"},
                format="json", **self.header,
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            original.refresh_from_db()
            self.assertEqual(original.status, BrainDumpDocument.STATUS_ACTIVE)
            self.assertEqual(BrainDumpDocument.objects.count(), before_count)

        def test_create_and_read_braindump_while_mutations_are_rejected(self):
            response = self.client.post(
                self.braindumps_url,
                {"title": "T", "body": "B", "authorship": "user_direct"},
                format="json",
                **self.header,
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            braindump_id = response.data["id"]
            detail_url = f"{self.braindumps_url}{braindump_id}/"

            self.assertEqual(self.client.get(detail_url, **self.header).status_code, status.HTTP_200_OK)
            self.assertEqual(self.client.get(self.braindumps_url, **self.header).status_code, status.HTTP_200_OK)

            for response in (
                self.client.patch(detail_url, {"body": "B2"}, format="json", **self.header),
                self.client.put(detail_url, {"title": "T", "body": "B", "authorship": "user_direct"}, format="json", **self.header),
                self.client.delete(detail_url, **self.header),
                self.client.patch(self.braindumps_url, [{}], format="json", **self.header),
                self.client.delete(self.braindumps_url, **self.header),
            ):
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
            braindump = BrainDumpDocument.objects.get(pk=braindump_id)
            self.assertEqual(braindump.body, "B")

        def test_create_without_authorship_fails(self):
            response = self.client.post(
                self.braindumps_url, {"title": "T", "body": "B"}, format="json", **self.header
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("authorship", response.data)

        def test_create_with_unknown_authorship_fails(self):
            response = self.client.post(
                self.braindumps_url,
                {"title": "T", "body": "B", "authorship": "not_a_real_choice"},
                format="json",
                **self.header,
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        def test_create_with_whitespace_only_body_fails(self):
            response = self.client.post(
                self.braindumps_url,
                {"title": "T", "body": "   ", "authorship": "user_direct"},
                format="json",
                **self.header,
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        def test_review_create_with_unknown_braindump_fails(self):
            response = self.client.post(
                self.reviews_url,
                {"braindump": str(uuid.uuid4()), "summary": "x"},
                format="json",
                **self.header,
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        def test_duplicate_review_creation_fails_without_changing_existing(self):
            braindump = _make_braindump()
            first = self.client.post(
                self.reviews_url,
                {"braindump": str(braindump.pk), "summary": "first"},
                format="json",
                **self.header,
            )
            self.assertEqual(first.status_code, status.HTTP_201_CREATED)

            second = self.client.post(
                self.reviews_url,
                {"braindump": str(braindump.pk), "summary": "second"},
                format="json",
                **self.header,
            )
            self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
            review = AlignmentReview.objects.get(braindump=braindump)
            self.assertEqual(review.summary, "first")

        def test_patch_replaces_the_current_review(self):
            braindump = _make_braindump()
            review = AlignmentReview.objects.create(braindump=braindump, summary="v1")
            detail_url = f"{self.reviews_url}{review.pk}/"
            response = self.client.patch(detail_url, {"summary": "v2"}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            review.refresh_from_db()
            self.assertEqual(review.summary, "v2")

        def test_patch_is_rejected_and_preserves_exact_text(self):
            body_text = "  padded body with a newline\nand Unicode 日本語  "
            braindump = _make_braindump(body=body_text)
            detail_url = f"{self.braindumps_url}{braindump.pk}/"
            response = self.client.patch(detail_url, {"title": "Renamed"}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
            braindump.refresh_from_db()
            self.assertEqual(braindump.title, "Test Braindump")
            self.assertEqual(braindump.body, body_text)

        def test_review_deletion_preserves_an_immutable_braindump(self):
            braindump = _make_braindump()
            review = AlignmentReview.objects.create(braindump=braindump, summary="x")

            review_detail = f"{self.reviews_url}{review.pk}/"
            self.assertEqual(self.client.delete(review_detail, **self.header).status_code, status.HTTP_204_NO_CONTENT)
            self.assertEqual(
                self.client.get(f"{self.braindumps_url}{braindump.pk}/", **self.header).status_code,
                status.HTTP_200_OK,
            )

            braindump_detail = f"{self.braindumps_url}{braindump.pk}/"
            self.assertEqual(
                self.client.delete(braindump_detail, **self.header).status_code, status.HTTP_405_METHOD_NOT_ALLOWED
            )
            self.assertEqual(self.client.get(braindump_detail, **self.header).status_code, status.HTTP_200_OK)


    class BrainDumpGraphQLTests(APITestCase):
        """GraphQL read coverage using the canonical Braindump query."""

        def setUp(self):
            super().setUp()
            self.add_permissions(
                "nautobot_intent_catalog.view_braindumpdocument",
                "nautobot_intent_catalog.view_alignmentreview",
            )
            self.api_url = reverse("graphql-api")

        def test_pinned_query_returns_multiple_documents_with_and_without_a_review(self):
            reviewed = _make_braindump(title="Reviewed Braindump", body="Body one 日本語")
            unreviewed = _make_braindump(title="Unreviewed Braindump", body="Body two")
            AlignmentReview.objects.create(braindump=reviewed, summary="Review one")

            query = """
            query {
              braindump_documents {
                id
                title
                body
                authorship
                status
                created
                last_updated
                alignment_review {
                  id
                  summary
                  created
                  last_updated
                }
              }
            }
            """
            response = self.client.post(self.api_url, {"query": query}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            documents = {doc["title"]: doc for doc in response.data["data"]["braindump_documents"]}

            self.assertEqual(documents["Reviewed Braindump"]["body"], "Body one 日本語")
            self.assertEqual(documents["Reviewed Braindump"]["status"], "ACTIVE")
            self.assertIsNotNone(documents["Reviewed Braindump"]["alignment_review"])
            self.assertEqual(documents["Reviewed Braindump"]["alignment_review"]["summary"], "Review one")

            # A missing review remains a normal, readable (null) condition -- not an error.
            self.assertIsNone(documents["Unreviewed Braindump"]["alignment_review"])

        def test_alignment_reviews_query_exposes_related_braindump_id(self):
            braindump = _make_braindump()
            review = AlignmentReview.objects.create(braindump=braindump, summary="x")
            query = """
            query {
              alignment_reviews {
                id
                summary
                created
                last_updated
                braindump {
                  id
                }
              }
            }
            """
            response = self.client.post(self.api_url, {"query": query}, format="json", **self.header)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            reviews = response.data["data"]["alignment_reviews"]
            self.assertEqual(len(reviews), 1)
            self.assertEqual(reviews[0]["id"], str(review.pk))
            self.assertEqual(reviews[0]["braindump"]["id"], str(braindump.pk))
