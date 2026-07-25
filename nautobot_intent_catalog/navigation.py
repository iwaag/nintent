"""Navigation items for the Nautobot Intent Catalog App."""

try:
    from django.conf import settings

    from nautobot.apps.ui import NavMenuGroup, NavMenuItem, NavMenuTab
except ImportError:  # pragma: no cover - allows loader-only tests without Nautobot.
    menu_items = ()
else:

    def _configured_dashboard_url():
        """Read the nctl dashboard link from PLUGINS_CONFIG (deployment config, not a model)."""

        plugins_config = getattr(settings, "PLUGINS_CONFIG", {}) or {}
        app_config = plugins_config.get("nautobot_intent_catalog", {}) or {}
        return app_config.get("dashboard_url")

    _dashboard_items = ()
    if _configured_dashboard_url():
        # NavMenuItem.link is always passed through reverse(), so it must be a URL
        # name, not the raw (possibly external) dashboard_url; dashboard_redirect is a
        # thin view that 302s to the configured URL.
        _dashboard_items = (
            NavMenuItem(
                link="plugins:nautobot_intent_catalog:dashboard_redirect",
                name="nctl Dashboard",
            ),
        )

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
                            link="plugins:nautobot_intent_catalog:desirednodeoperationaloverride_list",
                            name="Node Operational Overrides",
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
                NavMenuGroup(
                    name="Operational Tools",
                    weight=300,
                    items=(
                        NavMenuItem(
                            link="plugins:nautobot_intent_catalog:desiredhost_quick_add",
                            name="Quick Host Add",
                        ),
                    )
                    + _dashboard_items,
                ),
            ),
        ),
    )
