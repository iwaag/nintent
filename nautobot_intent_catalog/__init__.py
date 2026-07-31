"""Nautobot Intent Catalog App."""

try:
    from nautobot.apps import NautobotAppConfig
except ImportError:  # pragma: no cover - supports loader-only local smoke tests.
    class NautobotAppConfig:  # type: ignore[no-redef]
        """Fallback base when Nautobot is not installed."""


class IntentCatalogConfig(NautobotAppConfig):
    """App configuration for the intent catalog."""

    name = "nautobot_intent_catalog"
    verbose_name = "Intent Catalog"
    description = "Manage and analyze cluster desired state and intent."
    version = "0.9.0"
    author = ""
    author_email = ""
    base_url = "intent-catalog"
    required_settings = []
    default_settings = {}
    home_view_name = "plugins:nautobot_intent_catalog:desiredservice_list"


config = IntentCatalogConfig
