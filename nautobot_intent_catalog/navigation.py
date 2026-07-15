"""Navigation items for the Nautobot Intent Catalog App."""

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
                    name="Intent Catalog",
                    items=(
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:intentsource_list",
                            name="Sources",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desiredservice_list",
                            name="Desired Services",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desireddependency_list",
                            name="Dependencies",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desirednode_list",
                            name="Desired Nodes",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desiredhost_quick_add",
                            name="Quick Host Add",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desiredendpoint_list",
                            name="Desired Endpoints",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desiredserviceplacement_list",
                            name="Service Placements",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desirednodeoperationalconfig_list",
                            name="Node Operational Configs",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desirediprange_list",
                            name="Desired IP Ranges",
                        ),
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:source_yaml_list",
                            name="Source YAML",
                        ),
                    ),
                ),
            ),
        ),
    )
