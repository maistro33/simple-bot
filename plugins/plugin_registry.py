"""
Plugin Registry — routes an arbitrary input URL to the correct
:class:`PlatformPlugin` implementation, or reports that none matched
(in which case the Research Engine falls back to pure AI extraction
from raw text input).
"""
from __future__ import annotations

from core.logger import get_logger
from plugins.aliexpress_plugin import AliExpressPlugin
from plugins.amazon_plugin import AmazonPlugin
from plugins.base_plugin import PlatformPlugin, ProductData
from plugins.ebay_plugin import EbayPlugin
from plugins.shopify_plugin import ShopifyPlugin
from plugins.temu_plugin import TemuPlugin
from plugins.tiktok_plugin import TikTokPlugin
from plugins.youtube_plugin import YouTubePlugin

logger = get_logger(__name__)


class PluginRegistry:
    """
    Holds every registered :class:`PlatformPlugin` and resolves incoming
    URLs to the first plugin that claims to handle them. Registration
    order matters only where matchers could overlap (none currently do).
    """

    def __init__(self) -> None:
        self._plugins: list[PlatformPlugin] = [
            AmazonPlugin(),
            AliExpressPlugin(),
            TemuPlugin(),
            EbayPlugin(),
            ShopifyPlugin(),
            YouTubePlugin(),
            TikTokPlugin(),
        ]

    def register(self, plugin: PlatformPlugin) -> None:
        """Register an additional plugin at runtime (e.g. from a third-party extension)."""
        self._plugins.append(plugin)
        logger.info("Registered plugin: {}", plugin.__class__.__name__)

    def resolve(self, url: str) -> PlatformPlugin | None:
        """Return the first plugin whose ``matches`` accepts the given URL, or None."""
        for plugin in self._plugins:
            if plugin.matches(url):
                return plugin
        return None

    def fetch_product_data(self, url: str) -> ProductData | None:
        """Resolve the appropriate plugin for a URL and fetch normalised product data, or None if unmatched."""
        plugin = self.resolve(url)
        if plugin is None:
            logger.debug("No plugin matched URL: {}", url)
            return None
        logger.info("Using {} plugin for URL: {}", plugin.__class__.__name__, url)
        return plugin.fetch_product_data(url)


_plugin_registry: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    """Return the process-wide :class:`PluginRegistry` singleton."""
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry()
    return _plugin_registry
