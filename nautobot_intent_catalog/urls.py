"""URL patterns for the Nautobot Intent Catalog App."""

from django.urls import path

from . import views

urlpatterns = [
    path("sources/source-yaml/", views.source_yaml_intent_source_list, name="source_yaml_list"),
    path("dashboard/", views.dashboard_redirect, name="dashboard_redirect"),
]

if hasattr(views, "IntentSourceListView"):
    urlpatterns.extend(
        [
            path("sources/", views.IntentSourceListView.as_view(), name="intentsource_list"),
            path("sources/add/", views.IntentSourceEditView.as_view(), name="intentsource_add"),
            path("sources/<uuid:pk>/", views.IntentSourceView.as_view(), name="intentsource"),
            path("sources/<uuid:pk>/edit/", views.IntentSourceEditView.as_view(), name="intentsource_edit"),
            path(
                "sources/<uuid:pk>/delete/",
                views.IntentSourceDeleteView.as_view(),
                name="intentsource_delete",
            ),
            path("services/", views.DesiredServiceListView.as_view(), name="desiredservice_list"),
            path("services/add/", views.DesiredServiceEditView.as_view(), name="desiredservice_add"),
            path("services/<uuid:pk>/", views.DesiredServiceView.as_view(), name="desiredservice"),
            path("services/<uuid:pk>/edit/", views.DesiredServiceEditView.as_view(), name="desiredservice_edit"),
            path(
                "services/<uuid:pk>/delete/",
                views.DesiredServiceDeleteView.as_view(),
                name="desiredservice_delete",
            ),
            path("dependencies/", views.DesiredDependencyListView.as_view(), name="desireddependency_list"),
            path("dependencies/<uuid:pk>/", views.DesiredDependencyView.as_view(), name="desireddependency"),
            path(
                "dependencies/<uuid:pk>/edit/",
                views.DesiredDependencyEditView.as_view(),
                name="desireddependency_edit",
            ),
            path(
                "dependencies/<uuid:pk>/delete/",
                views.DesiredDependencyDeleteView.as_view(),
                name="desireddependency_delete",
            ),
            path("nodes/", views.DesiredNodeListView.as_view(), name="desirednode_list"),
            path("nodes/quick-add/", views.DesiredHostQuickAddView.as_view(), name="desiredhost_quick_add"),
            path("nodes/add/", views.DesiredNodeEditView.as_view(), name="desirednode_add"),
            path("nodes/<uuid:pk>/", views.DesiredNodeView.as_view(), name="desirednode"),
            path("nodes/<uuid:pk>/edit/", views.DesiredNodeEditView.as_view(), name="desirednode_edit"),
            path(
                "nodes/<uuid:pk>/delete/",
                views.DesiredNodeDeleteView.as_view(),
                name="desirednode_delete",
            ),
            path("endpoints/", views.DesiredEndpointListView.as_view(), name="desiredendpoint_list"),
            path("endpoints/add/", views.DesiredEndpointEditView.as_view(), name="desiredendpoint_add"),
            path("endpoints/<uuid:pk>/", views.DesiredEndpointView.as_view(), name="desiredendpoint"),
            path(
                "endpoints/<uuid:pk>/edit/",
                views.DesiredEndpointEditView.as_view(),
                name="desiredendpoint_edit",
            ),
            path(
                "endpoints/<uuid:pk>/delete/",
                views.DesiredEndpointDeleteView.as_view(),
                name="desiredendpoint_delete",
            ),
            path(
                "placements/",
                views.DesiredServicePlacementListView.as_view(),
                name="desiredserviceplacement_list",
            ),
            path(
                "placements/add/",
                views.DesiredServicePlacementEditView.as_view(),
                name="desiredserviceplacement_add",
            ),
            path(
                "placements/<uuid:pk>/",
                views.DesiredServicePlacementView.as_view(),
                name="desiredserviceplacement",
            ),
            path(
                "placements/<uuid:pk>/edit/",
                views.DesiredServicePlacementEditView.as_view(),
                name="desiredserviceplacement_edit",
            ),
            path(
                "placements/<uuid:pk>/delete/",
                views.DesiredServicePlacementDeleteView.as_view(),
                name="desiredserviceplacement_delete",
            ),
            path(
                "operational-configs/",
                views.DesiredNodeOperationalConfigListView.as_view(),
                name="desirednodeoperationalconfig_list",
            ),
            path(
                "operational-configs/add/",
                views.DesiredNodeOperationalConfigEditView.as_view(),
                name="desirednodeoperationalconfig_add",
            ),
            path(
                "operational-configs/<uuid:pk>/",
                views.DesiredNodeOperationalConfigView.as_view(),
                name="desirednodeoperationalconfig",
            ),
            path(
                "operational-configs/<uuid:pk>/edit/",
                views.DesiredNodeOperationalConfigEditView.as_view(),
                name="desirednodeoperationalconfig_edit",
            ),
            path(
                "operational-configs/<uuid:pk>/delete/",
                views.DesiredNodeOperationalConfigDeleteView.as_view(),
                name="desirednodeoperationalconfig_delete",
            ),
            path("ip-ranges/", views.DesiredIPRangeListView.as_view(), name="desirediprange_list"),
            path("ip-ranges/add/", views.DesiredIPRangeEditView.as_view(), name="desirediprange_add"),
            path("ip-ranges/<uuid:pk>/", views.DesiredIPRangeView.as_view(), name="desirediprange"),
            path(
                "ip-ranges/<uuid:pk>/edit/",
                views.DesiredIPRangeEditView.as_view(),
                name="desirediprange_edit",
            ),
            path(
                "ip-ranges/<uuid:pk>/delete/",
                views.DesiredIPRangeDeleteView.as_view(),
                name="desirediprange_delete",
            ),
        ]
    )
else:
    urlpatterns.append(path("sources/", views.source_yaml_intent_source_list, name="source_list"))
