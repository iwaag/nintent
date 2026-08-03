"""URL patterns for the Nautobot Intent Catalog App REST API."""

from django.urls import path
from nautobot.apps.api import OrderedDefaultRouter

from . import views

router = OrderedDefaultRouter(view_name="Intent Catalog")
router.register("braindumps", views.BrainDumpDocumentViewSet)
router.register("alignment-reviews", views.AlignmentReviewViewSet)
router.register("workflow-episodes", views.WorkflowEpisodeViewSet)

urlpatterns = [
    path("desired-state/batch/", views.DesiredStateBatchView.as_view(), name="desired-state-batch"),
    path("retirement-prune/actual/", views.RetirementActualPruneView.as_view(), name="retirement-prune-actual"),
    path("braindumps/<uuid:braindump_id>/purge/", views.BraindumpPurgeView.as_view(), name="braindump-purge"),
] + router.urls
