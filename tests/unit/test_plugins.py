"""Unit tests for platform plugins, using monkeypatched HTTP responses (no real network calls)."""
from __future__ import annotations


class _FakeResponse:
    """Minimal stand-in for requests.Response used across plugin tests."""

    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.exceptions.HTTPError(f"status {self.status_code}")


_SAMPLE_OG_HTML = """
<html>
<head>
  <meta property="og:title" content="Amazing Self-Stirring Mug" />
  <meta property="og:description" content="Stirs your coffee automatically." />
  <meta property="product:price:amount" content="24.99" />
  <meta property="product:price:currency" content="USD" />
  <meta property="og:image" content="https://example.com/mug.jpg" />
</head>
<body>Some page text with a price of $24.99 shown here.</body>
</html>
"""


def test_amazon_plugin_matches_domain():
    """AmazonPlugin.matches must accept amazon.com and amazon.co.uk URLs."""
    from plugins.amazon_plugin import AmazonPlugin

    plugin = AmazonPlugin()
    assert plugin.matches("https://www.amazon.com/dp/B0EXAMPLE") is True
    assert plugin.matches("https://www.amazon.co.uk/dp/B0EXAMPLE") is True
    assert plugin.matches("https://www.notamazon.com/product") is False


def test_amazon_plugin_extracts_open_graph_data(monkeypatch):
    """AmazonPlugin.fetch_product_data must parse title/price/description from OpenGraph tags."""
    import plugins.generic_scraper as scraper_module

    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(_SAMPLE_OG_HTML)

    monkeypatch.setattr(scraper_module.requests, "get", fake_get)

    from plugins.amazon_plugin import AmazonPlugin

    plugin = AmazonPlugin()
    data = plugin.fetch_product_data("https://www.amazon.com/dp/B0EXAMPLE")

    assert data.title == "Amazing Self-Stirring Mug"
    assert data.price == "24.99"
    assert data.currency == "USD"


def test_plugin_registry_resolves_correct_plugin():
    """PluginRegistry.resolve must route URLs to the correct platform plugin."""
    from plugins.aliexpress_plugin import AliExpressPlugin
    from plugins.amazon_plugin import AmazonPlugin
    from plugins.plugin_registry import PluginRegistry

    registry = PluginRegistry()

    amazon_plugin = registry.resolve("https://www.amazon.com/dp/B0EXAMPLE")
    assert isinstance(amazon_plugin, AmazonPlugin)

    aliexpress_plugin = registry.resolve("https://www.aliexpress.com/item/12345.html")
    assert isinstance(aliexpress_plugin, AliExpressPlugin)


def test_plugin_registry_returns_none_for_unknown_url():
    """PluginRegistry.resolve must return None for a URL matching no registered plugin."""
    from plugins.plugin_registry import PluginRegistry

    registry = PluginRegistry()
    assert registry.resolve("https://www.some-random-blog.example/post/1") is None


def test_shopify_plugin_matches_products_path():
    """ShopifyPlugin.matches must accept URLs following the /products/<handle> convention."""
    from plugins.shopify_plugin import ShopifyPlugin

    plugin = ShopifyPlugin()
    assert plugin.matches("https://mystore.com/products/cool-gadget") is True
    assert plugin.matches("https://mystore.myshopify.com/products/cool-gadget") is True
    assert plugin.matches("https://example.com/about") is False


def test_extract_open_graph_data_falls_back_to_title_tag(monkeypatch):
    """When og:title is absent, extraction should fall back to the <title> tag."""
    from plugins.generic_scraper import extract_open_graph_data

    html = "<html><head><title>Fallback Title</title></head><body>No price here.</body></html>"
    data = extract_open_graph_data(html)

    assert data.title == "Fallback Title"
