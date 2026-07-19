"""
Shopify platform plugin — extracts product data from any storefront
running on the Shopify platform (detected either via the domain
containing 'myshopify.com', or via the presence of Shopify's standard
``/products/<handle>.json`` endpoint convention).
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from config.constants import PlatformName
from core.exceptions import PluginError
from core.logger import get_logger
from plugins.base_plugin import PlatformPlugin, ProductData
from plugins.generic_scraper import domain_matches, extract_open_graph_data, fetch_html

logger = get_logger(__name__)

_MYSHOPIFY_PATTERN = re.compile(r"(?:^|\.)myshopify\.com$", re.IGNORECASE)
_PRODUCTS_PATH_PATTERN = re.compile(r"/products/[a-zA-Z0-9\-]+")


class ShopifyPlugin(PlatformPlugin):
    """Handles Shopify storefront product URLs, preferring the platform's JSON product endpoint."""

    platform = PlatformName.SHOPIFY

    def matches(self, url: str) -> bool:
        """Return True for known myshopify.com domains or URLs following the /products/<handle> convention."""
        return domain_matches(url, _MYSHOPIFY_PATTERN) or bool(_PRODUCTS_PATH_PATTERN.search(urlparse(url).path))

    def fetch_product_data(self, url: str) -> ProductData:
        """
        Fetch Shopify product data, preferring the store's public
        ``<product-url>.json`` endpoint (which every Shopify storefront
        exposes by convention) and falling back to OpenGraph tags.
        """
        json_data = self._try_json_endpoint(url)
        if json_data is not None:
            return json_data

        html = fetch_html(url)
        return extract_open_graph_data(html)

    def _try_json_endpoint(self, url: str) -> ProductData | None:
        """Attempt Shopify's ``.json`` product endpoint convention; return None on any failure."""
        match = _PRODUCTS_PATH_PATTERN.search(urlparse(url).path)
        if not match:
            return None

        json_url = urljoin(url, match.group(0) + ".json")
        try:
            html = fetch_html(json_url)
            payload = json.loads(html)
            product = payload.get("product", {})
            if not product:
                return None

            variant = (product.get("variants") or [{}])[0]
            images = [img.get("src") for img in product.get("images", []) if img.get("src")]

            return ProductData(
                title=product.get("title"),
                description=self._strip_html(product.get("body_html", "")),
                price=str(variant.get("price")) if variant.get("price") else None,
                brand=product.get("vendor"),
                image_urls=images,
                availability="in_stock" if variant.get("available") else "out_of_stock",
                raw_metadata={"shopify_product_type": product.get("product_type")},
            )
        except (PluginError, json.JSONDecodeError, KeyError, IndexError) as exc:
            logger.debug("Shopify JSON endpoint failed for {}: {}", json_url, exc)
            return None

    @staticmethod
    def _strip_html(html_fragment: str) -> str:
        """Strip HTML tags from Shopify's rich-text product body field."""
        from bs4 import BeautifulSoup

        return BeautifulSoup(html_fragment, "lxml").get_text(" ", strip=True)
