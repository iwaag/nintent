"""URL patterns for the Nautobot Intent Catalog App REST API."""

from nautobot.apps.api import OrderedDefaultRouter

from . import views

router = OrderedDefaultRouter(view_name="Intent Catalog")
router.register("nodes", views.DesiredNodeViewSet)
router.register("services", views.DesiredServiceViewSet)
router.register("endpoints", views.DesiredEndpointViewSet)

urlpatterns = router.urls
