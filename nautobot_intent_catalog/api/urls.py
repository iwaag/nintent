"""URL patterns for the Nautobot Intent Catalog App REST API."""

from nautobot.apps.api import OrderedDefaultRouter

from . import views

router = OrderedDefaultRouter(view_name="Intent Catalog")
router.register("nodes", views.DesiredNodeViewSet)
router.register("compute-platforms", views.DesiredComputePlatformViewSet)
router.register("compute-instances", views.DesiredComputeInstanceViewSet)
router.register("braindumps", views.BrainDumpDocumentViewSet)
router.register("alignment-reviews", views.AlignmentReviewViewSet)

urlpatterns = router.urls
