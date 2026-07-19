"""
Generic HTML scraping utilities shared by every platform plugin.

Rather than duplicating HTML-fetching and OpenGraph/meta-tag parsing
logic in every plugin, this module centralises it. Platform plugins
call :func:`fetch_html` and :func:`extract_open_graph_data`, then layer
platform-specific refinements (e.g. price regex patterns) on top.
"""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from config import get_settings
from core.exceptions import PluginError, TransientServiceError
from core.logger import get_logger
from plugins.base_plugin import ProductData

logger = get_logger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_PRICE_PATTERN = re.compile(r"[\$£€₺]\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?")


def domain_matches(url: str, domain_pattern: "re.Pattern[str]") -> bool:
    """
    Safely check whether a URL's hostname (not its full path/query string)
    matches the given compiled domain regex.

    This exists because naively running ``pattern.search(url)`` against
    the whole URL would incorrectly match spoofed hosts like
    ``notamazon.com`` (which contains the substring "amazon.com") or
    malicious paths like ``evil.com/amazon.com``. Restricting the match
    to ``urlparse(url).hostname`` closes that hole.
    """
    from urllib.parse import urlparse

    hostname = urlparse(url).hostname or ""
    return bool(domain_pattern.search(hostname))


def fetch_html(url: str, timeout: int | None = None) -> str:
    """
    Fetch raw HTML for a URL with a browser-like User-Agent.

    Raises:
        TransientServiceError: On timeouts/connection failures (retryable).
        PluginError: On any other HTTP failure (4xx/5xx).
    """
    settings = get_settings()
    try:
        response = requests.get(
            url, headers=_DEFAULT_HEADERS, timeout=timeout or settings.http_timeout_seconds
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.Timeout as exc:
        raise TransientServiceError(f"Timed out fetching {url}: {exc}") from exc
    except requests.exceptions.ConnectionError as exc:
        raise TransientServiceError(f"Connection error fetching {url}: {exc}") from exc
    except requests.exceptions.HTTPError as exc:
        raise PluginError(f"HTTP error fetching {url}: {exc}") from exc


def extract_open_graph_data(html: str) -> ProductData:
    """
    Extract normalised product data from a page's OpenGraph/meta tags.

    This works across virtually every modern e-commerce site since
    ``og:title``, ``og:description``, ``og:image`` and ``product:price:amount``
    are near-universal conventions for link-preview compatibility.
    """
    soup = BeautifulSoup(html, "lxml")
    data = ProductData()

    def meta_content(*names: str) -> str | None:
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return None

    data.title = meta_content("og:title", "twitter:title") or (soup.title.string.strip() if soup.title and soup.title.string else None)
    data.description = meta_content("og:description", "description", "twitter:description")
    data.brand = meta_content("product:brand", "og:brand")
    data.currency = meta_content("product:price:currency", "og:price:currency")

    price_content = meta_content("product:price:amount", "og:price:amount")
    if price_content:
        data.price = price_content
    else:
        text_sample = soup.get_text(" ", strip=True)[:5000]
        match = _PRICE_PATTERN.search(text_sample)
        if match:
            data.price = match.group(0)

    image_url = meta_content("og:image", "twitter:image")
    if image_url:
        data.image_urls.append(image_url)

    data.raw_metadata = {"page_title_tag": soup.title.string if soup.title else None}
    return data


def extract_product_via_ai_fallback(html: str, ai_generate_json) -> ProductData:
    """
    Last-resort extraction: when OpenGraph tags are sparse/absent, ask the
    configured AI model to read a truncated slice of the visible page text
    and extract structured product data. ``ai_generate_json`` is injected
    (rather than importing AIManager here) to avoid a circular dependency
    between plugins and services.
    """
    soup = BeautifulSoup(html, "lxml")
    visible_text = soup.get_text(" ", strip=True)[:6000]

    system_prompt = (
        "You are a product-page data extractor. Given raw visible text scraped from an "
        "e-commerce product page, extract the product's title, description, price and brand. "
        "Respond only with JSON: {\"title\": str|null, \"description\": str|null, "
        "\"price\": str|null, \"brand\": str|null}"
    )
    try:
        result = ai_generate_json(system_prompt, visible_text, temperature=0.2)
    except Exception as exc:
        raise PluginError(f"AI fallback extraction failed: {exc}") from exc

    return ProductData(
        title=result.get("title"),
        description=result.get("description"),
        price=result.get("price"),
        brand=result.get("brand"),
    )
