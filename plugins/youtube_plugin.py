"""
YouTube platform plugin — handles cases where the user's raw input is a
YouTube video URL (e.g. a trending product-review video they want
analysed/repurposed) rather than a direct product page. Uses YouTube's
public, key-less oEmbed endpoint for lightweight metadata extraction.
"""
from __future__ import annotations

import re

from config.constants import PlatformName
from core.logger import get_logger
from plugins.base_plugin import PlatformPlugin, ProductData
from plugins.generic_scraper import domain_matches, fetch_html

logger = get_logger(__name__)

_DOMAIN_PATTERN = re.compile(r"(?:^|\.)(?:youtube\.com|youtu\.be)$", re.IGNORECASE)
_OEMBED_ENDPOINT = "https://www.youtube.com/oembed?url={url}&format=json"


class YouTubePlugin(PlatformPlugin):
    """Handles YouTube video URLs via the public oEmbed metadata endpoint."""

    platform = PlatformName.YOUTUBE

    def matches(self, url: str) -> bool:
        """Return True if the URL points at YouTube."""
        return domain_matches(url, _DOMAIN_PATTERN)

    def fetch_product_data(self, url: str) -> ProductData:
        """Fetch video title/author via oEmbed; description is left for the AI research stage to infer."""
        import json

        oembed_url = _OEMBED_ENDPOINT.format(url=url)
        try:
            raw = fetch_html(oembed_url)
            payload = json.loads(raw)
        except Exception as exc:
            logger.warning("YouTube oEmbed lookup failed for {}: {}", url, exc)
            return ProductData(title=None, description=f"Referenced YouTube video: {url}")

        return ProductData(
            title=payload.get("title"),
            description=f"Referenced YouTube video by {payload.get('author_name', 'unknown creator')}: {url}",
            image_urls=[payload["thumbnail_url"]] if payload.get("thumbnail_url") else [],
            raw_metadata={"author_name": payload.get("author_name"), "provider_name": payload.get("provider_name")},
        )
