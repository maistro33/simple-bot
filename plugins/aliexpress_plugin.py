"""AliExpress platform plugin — extracts product data from aliexpress.com product pages."""
from __future__ import annotations

import re

from config.constants import PlatformName
from core.logger import get_logger
from plugins.base_plugin import PlatformPlugin, ProductData
from plugins.generic_scraper import domain_matches, extract_open_graph_data, extract_product_via_ai_fallback, fetch_html

logger = get_logger(__name__)

_DOMAIN_PATTERN = re.compile(r"(?:^|\.)aliexpress\.(?:com|us|ru)$", re.IGNORECASE)


class AliExpressPlugin(PlatformPlugin):
    """Handles AliExpress product URLs."""

    platform = PlatformName.ALIEXPRESS

    def matches(self, url: str) -> bool:
        """Return True if the URL points at AliExpress."""
        return domain_matches(url, _DOMAIN_PATTERN)

    def fetch_product_data(self, url: str) -> ProductData:
        """Fetch and normalise AliExpress product data via OpenGraph tags, with AI fallback."""
        html = fetch_html(url)
        data = extract_open_graph_data(html)

        if not data.title or not data.price:
            logger.debug("AliExpress OpenGraph extraction incomplete; using AI fallback for {}", url)
            from services.ai_manager import get_ai_manager

            fallback = extract_product_via_ai_fallback(html, get_ai_manager().generate_json)
            data.title = data.title or fallback.title
            data.description = data.description or fallback.description
            data.price = data.price or fallback.price
            data.brand = data.brand or fallback.brand

        return data
