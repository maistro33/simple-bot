"""
YouTube Service — wraps the YouTube Data API v3 for two purposes:
competitor/keyword research (public, API-key auth) and optional direct
video upload (OAuth, only used if the user explicitly configures it).
"""
from __future__ import annotations

from typing import Any

import requests

from config import get_settings
from core.exceptions import AIServiceError, ConfigurationError, TransientServiceError
from core.logger import get_logger

logger = get_logger(__name__)

_YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeService:
    """
    Read-only YouTube Data API client used by the Research Engine to find
    competitor videos for a given product/niche, plus reach counts (views,
    likes) needed to gauge market saturation and content performance.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    def _require_api_key(self) -> str:
        """Return the configured YouTube API key or raise if missing."""
        if not self._settings.youtube_api_key:
            raise ConfigurationError(
                "YOUTUBE_API_KEY is not configured. Competitor research will fall back to AI estimation."
            )
        return self._settings.youtube_api_key

    def search_competitor_videos(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """
        Search YouTube for videos matching ``query`` (typically the product
        name or niche keyword) and return simplified competitor metadata.

        Raises:
            TransientServiceError: On network failures (retryable).
            AIServiceError: On any other API error response.
        """
        api_key = self._require_api_key()
        try:
            response = requests.get(
                f"{_YOUTUBE_API_BASE}/search",
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "maxResults": max_results,
                    "order": "relevance",
                    "key": api_key,
                },
                timeout=self._settings.http_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.Timeout as exc:
            raise TransientServiceError(f"YouTube search timed out: {exc}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise TransientServiceError(f"YouTube search connection error: {exc}") from exc
        except requests.exceptions.HTTPError as exc:
            raise AIServiceError(f"YouTube search API error: {exc}") from exc

        results = []
        for item in payload.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            if not video_id:
                continue
            results.append(
                {
                    "video_id": video_id,
                    "title": snippet.get("title"),
                    "channel_title": snippet.get("channelTitle"),
                    "published_at": snippet.get("publishedAt"),
                    "description": snippet.get("description"),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
            )
        return results

    def get_video_statistics(self, video_ids: list[str]) -> dict[str, dict[str, int]]:
        """
        Fetch view/like/comment counts for up to 50 video IDs at once.

        Returns:
            A mapping of ``video_id`` to a dict of ``{"views": int, "likes": int, "comments": int}``.
        """
        if not video_ids:
            return {}
        api_key = self._require_api_key()
        try:
            response = requests.get(
                f"{_YOUTUBE_API_BASE}/videos",
                params={"part": "statistics", "id": ",".join(video_ids[:50]), "key": api_key},
                timeout=self._settings.http_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.Timeout as exc:
            raise TransientServiceError(f"YouTube statistics request timed out: {exc}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise TransientServiceError(f"YouTube statistics connection error: {exc}") from exc
        except requests.exceptions.HTTPError as exc:
            raise AIServiceError(f"YouTube statistics API error: {exc}") from exc

        stats: dict[str, dict[str, int]] = {}
        for item in payload.get("items", []):
            video_id = item.get("id")
            statistics = item.get("statistics", {})
            stats[video_id] = {
                "views": int(statistics.get("viewCount", 0)),
                "likes": int(statistics.get("likeCount", 0)),
                "comments": int(statistics.get("commentCount", 0)),
            }
        return stats

    @property
    def is_configured(self) -> bool:
        """Whether a YouTube Data API key is available for research calls."""
        return bool(self._settings.youtube_api_key)
