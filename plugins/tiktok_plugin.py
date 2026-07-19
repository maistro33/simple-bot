"""
TikTok platform plugin — handles cases where the user's raw input is a
TikTok video URL (e.g. a viral product video to repurpose). Uses
TikTok's public, key-less oEmbed endpoint for lightweight metadata.
"""
from __future__ import annotations

import re

from config.constants import PlatformName
from core.logger import get_logger
from plugins.base_plugin import PlatformPlugin, ProductData
from plugins.generic_scraper import domain_matches, fetch_html

logger = get_logger(__name__)

_DOMAIN_PATTERN = re.compile(r"(?:^|\.)tiktok\.com$", re.IGNORECASE)
_OEMBED_ENDPOINT = "https://www.tiktok.com/oembed?url={url}"


class TikTokPlugin(PlatformPlugin):
    """Handles TikTok video URLs via the public oEmbed metadata endpoint."""

    platform = PlatformName.TIKTOK

    def matches(self, url: str) -> bool:
        """Return True if the URL points at TikTok."""
        return domain_matches(url, _DOMAIN_PATTERN)

    def fetch_product_data(self, url: str) -> ProductData:
        """Fetch video title/author via oEmbed; description is left for the AI research stage to infer."""
        import json

        oembed_url = _OEMBED_ENDPOINT.format(url=url)
        try:
            raw = fetch_html(oembed_url)
            payload = json.loads(raw)
        except Exception as exc:
            logger.warning("TikTok oEmbed lookup failed for {}: {}", url, exc)
            return ProductData(title=None, description=f"Referenced TikTok video: {url}")

        return ProductData(
            title=payload.get("title"),
            description=f"Referenced TikTok video by {payload.get('author_name', 'unknown creator')}: {url}",
            image_urls=[payload["thumbnail_url"]] if payload.get("thumbnail_url") else [],
            raw_metadata={"author_name": payload.get("author_name"), "provider_name": payload.get("provider_name")},
        )
