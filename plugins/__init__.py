"""Plugins package — platform-specific product data extraction, routed via PluginRegistry."""
from plugins.base_plugin import PlatformPlugin, ProductData
from plugins.plugin_registry import PluginRegistry, get_plugin_registry

__all__ = ["PlatformPlugin", "ProductData", "PluginRegistry", "get_plugin_registry"]
