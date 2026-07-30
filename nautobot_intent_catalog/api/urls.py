"""URL patterns for the Nautobot Intent Catalog App REST API."""

from django.urls import path
from nautobot.apps.api import OrderedDefaultRouter

from . import views

router = OrderedDefaultRouter(view_name="Intent Catalog")
router.register("braindumps", views.BrainDumpDocumentViewSet)
router.register("alignment-reviews", views.AlignmentReviewViewSet)

urlpatterns = [
    path("desired-state/batch/", views.DesiredStateBatchView.as_view(), name="desired-state-batch"),
    path("retirement-prune/actual/", views.RetirementActualPruneView.as_view(), name="retirement-prune-actual"),
] + router.urls
