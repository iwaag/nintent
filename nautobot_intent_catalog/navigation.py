"""Navigation items for the Nautobot Intent Catalog App.

Only contains links to the ten retained read-only list pages.
"""

try:
    from nautobot.apps.ui import NavMenuGroup, NavMenuItem, NavMenuTab
except ImportError:  # pragma: no cover - allows loader-only tests without Nautobot.
    menu_items = ()
else:
    menu_items = (
        NavMenuTab(
            name="Intent Catalog",
            groups=(
                NavMenuGroup(
                    name="Braindump",
                    weight=100,
                    items=(
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:braindumpdocument_list",
                            name="Braindumps",
                        ),
                    ),
                ),
                NavMenuGroup(
                    name="Desired State",
                    weight=200,
                    items=(
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desiredservice_list",
                            name="Desired Services",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desirednode_list",
                            name="Desired Nodes",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desiredendpoint_list",
                            name="Desired Endpoints",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desiredcomputeplatform_list",
                            name="Desired Compute Platforms",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desiredcomputeinstance_list",
                            name="Desired Compute Instances",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desiredserviceplacement_list",
                            name="Service Placements",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desiredservicebinding_list",
                            name="Service Bindings",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desirednodeoperationaloverride_list",
                            name="Node Operational Overrides",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desirediprange_list",
                            name="Desired IP Ranges",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desiredworkspace_list",
                            name="Desired Workspaces",
                        ),
                    ),
                ),
            ),
        ),
    )
