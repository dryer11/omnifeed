"""RSS channel — reads any Atom/RSS feed."""

from __future__ import annotations
from typing import Optional
import time

from .base import BaseChannel, ChannelRegistry
from ..models import FeedItem, Engagement, ChannelStatus
from ..config import ChannelConfig


@ChannelRegistry.register
class RSSChannel(BaseChannel):
    name = "rss"
    display_name = "RSS"
    icon = "📡"
    requires_auth = False
    rate_limit = 0.2

    def search(self, query: str, limit: int = 20) -> list[FeedItem]:
        """RSS doesn't support search — return all entries."""
        return self.trending(limit)

    def trending(self, limit: int = 20) -> list[FeedItem]:
        """Not applicable for RSS."""
        return []

    def fetch_feed(self, url: str, name: str = "", limit: int = 20) -> list[FeedItem]:
        """Fetch a single RSS/Atom feed."""
        try:
            import feedparser
        except ImportError:
            return []

        self._throttle()
        feed = feedparser.parse(url)
        items = []

        for entry in feed.entries[:limit]:
            # Attempt to get timestamp
            ts = 0
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                ts = int(time.mktime(entry.published_parsed) * 1000)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                ts = int(time.mktime(entry.updated_parsed) * 1000)

            # Content
            content = ""
            if hasattr(entry, "summary"):
                content = entry.summary[:500]
            elif hasattr(entry, "content") and entry.content:
                content = entry.content[0].get("value", "")[:500]

            # Strip HTML simply
            import re
            content = re.sub(r"<[^>]+>", "", content).strip()

            items.append(FeedItem(
                id=self.make_id(entry.get("id", entry.get("link", ""))),
                platform=self.name,
                native_id=entry.get("id", ""),
                title=entry.get("title", ""),
                content=content,
                author=entry.get("author", name or feed.feed.get("title", "")),
                url=entry.get("link", ""),
                timestamp=ts,
                media_type="text",
                tags=[name] if name else [],
                language="zh" if any(
                    "\u4e00" <= c <= "\u9fff" for c in (entry.get("title", "") + content)[:50]
                ) else "en",
            ))

        return items

    def health_check(self) -> ChannelStatus:
        try:
            import feedparser
            return ChannelStatus(
                name=self.name, available=True,
                auth_required=False, auth_configured=True,
            )
        except ImportError:
            return ChannelStatus(
                name=self.name, available=False,
                auth_required=False, auth_configured=False,
                error="feedparser not installed. pip install feedparser",
            )
