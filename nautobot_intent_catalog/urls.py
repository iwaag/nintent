"""URL patterns for the Nautobot Intent Catalog App.

Contains read-only GET routes for inspection of nintent domain models.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("services/", views.DesiredServiceListView.as_view(), name="desiredservice_list"),
    path("services/<uuid:pk>/", views.DesiredServiceView.as_view(), name="desiredservice"),
    path("nodes/", views.DesiredNodeListView.as_view(), name="desirednode_list"),
    path("nodes/<uuid:pk>/", views.DesiredNodeView.as_view(), name="desirednode"),
    path("endpoints/", views.DesiredEndpointListView.as_view(), name="desiredendpoint_list"),
    path("endpoints/<uuid:pk>/", views.DesiredEndpointView.as_view(), name="desiredendpoint"),
    path(
        "compute-platforms/",
        views.DesiredComputePlatformListView.as_view(),
        name="desiredcomputeplatform_list",
    ),
    path(
        "compute-platforms/<uuid:pk>/",
        views.DesiredComputePlatformView.as_view(),
        name="desiredcomputeplatform",
    ),
    path(
        "compute-instances/",
        views.DesiredComputeInstanceListView.as_view(),
        name="desiredcomputeinstance_list",
    ),
    path(
        "compute-instances/<uuid:pk>/",
        views.DesiredComputeInstanceView.as_view(),
        name="desiredcomputeinstance",
    ),
    path(
        "placements/",
        views.DesiredServicePlacementListView.as_view(),
        name="desiredserviceplacement_list",
    ),
    path(
        "placements/<uuid:pk>/",
        views.DesiredServicePlacementView.as_view(),
        name="desiredserviceplacement",
    ),
    path(
        "operational-overrides/",
        views.DesiredNodeOperationalOverrideListView.as_view(),
        name="desirednodeoperationaloverride_list",
    ),
    path(
        "operational-overrides/<uuid:pk>/",
        views.DesiredNodeOperationalOverrideView.as_view(),
        name="desirednodeoperationaloverride",
    ),
    path("braindumps/", views.BrainDumpDocumentListView.as_view(), name="braindumpdocument_list"),
    path("braindumps/<uuid:pk>/", views.BrainDumpDocumentView.as_view(), name="braindumpdocument"),
    path("ip-ranges/", views.DesiredIPRangeListView.as_view(), name="desirediprange_list"),
    path("ip-ranges/<uuid:pk>/", views.DesiredIPRangeView.as_view(), name="desirediprange"),
    path(
        "service-bindings/",
        views.DesiredServiceBindingListView.as_view(),
        name="desiredservicebinding_list",
    ),
    path(
        "service-bindings/<uuid:pk>/",
        views.DesiredServiceBindingView.as_view(),
        name="desiredservicebinding",
    ),
]
