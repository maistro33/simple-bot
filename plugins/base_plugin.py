"""
Base plugin interface for platform/affiliate integrations.

Every plugin (Amazon, AliExpress, Temu, eBay, Shopify, YouTube, TikTok)
implements this contract, letting the :class:`PluginRegistry` route an
arbitrary product URL to the correct handler without the Research
Engine needing any platform-specific knowledge (Open/Closed Principle:
adding a new platform means adding a new plugin file, not editing
existing code).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from config.constants import PlatformName


@dataclass(slots=True)
class ProductData:
    """Normalised product data returned by every plugin, regardless of source platform."""

    title: str | None = None
    description: str | None = None
    price: str | None = None
    currency: str | None = None
    image_urls: list[str] = field(default_factory=list)
    brand: str | None = None
    availability: str | None = None
    rating: float | None = None
    review_count: int | None = None
    raw_metadata: dict = field(default_factory=dict)


class PlatformPlugin(ABC):
    """Abstract base class every platform plugin must implement."""

    platform: PlatformName = PlatformName.GENERIC

    @abstractmethod
    def matches(self, url: str) -> bool:
        """Return True if this plugin knows how to handle the given URL."""
        raise NotImplementedError

    @abstractmethod
    def fetch_product_data(self, url: str) -> ProductData:
        """Fetch and normalise product data from the given URL."""
        raise NotImplementedError
