"""V2EX channel — zero config, public API."""

from __future__ import annotations
import httpx
from typing import Optional

from .base import BaseChannel, ChannelRegistry
from ..models import FeedItem, Engagement, ChannelStatus
from ..config import ChannelConfig


@ChannelRegistry.register
class V2EXChannel(BaseChannel):
    name = "v2ex"
    display_name = "V2EX"
    icon = "💬"
    requires_auth = False
    rate_limit = 1.0  # V2EX rate limits aggressively

    HEADERS = {"User-Agent": "omnifeed/0.1"}

    def __init__(self, config: Optional[ChannelConfig] = None):
        super().__init__(config)
        self._client = httpx.Client(
            headers=self.HEADERS,
            timeout=15,
        )
        self._nodes = config.nodes if config else ["python", "ai"]

    def search(self, query: str, limit: int = 20) -> list[FeedItem]:
        """V2EX public API doesn't support search. Return hot topics instead."""
        return self.trending(limit)

    def trending(self, limit: int = 20) -> list[FeedItem]:
        """Get hot topics."""
        self._throttle()
        try:
            resp = self._client.get("https://www.v2ex.com/api/topics/hot.json")
            topics = resp.json()
            return [self._parse_topic(t) for t in topics[:limit]]
        except Exception:
            return []

    def node_topics(self, node: str, limit: int = 10) -> list[FeedItem]:
        """Get topics from a specific node."""
        self._throttle()
        try:
            resp = self._client.get(
                "https://www.v2ex.com/api/topics/show.json",
                params={"node_name": node, "page": 1},
            )
            topics = resp.json()
            return [self._parse_topic(t) for t in topics[:limit]]
        except Exception:
            return []

    def fetch_all(self, limit_per_node: int = 5) -> list[FeedItem]:
        """Fetch hot + configured nodes."""
        items = self.trending(10)
        for node in self._nodes:
            items.extend(self.node_topics(node, limit_per_node))
        # Dedup by ID
        seen = set()
        unique = []
        for it in items:
            if it.id not in seen:
                seen.add(it.id)
                unique.append(it)
        return unique

    def _parse_topic(self, t: dict) -> FeedItem:
        tid = str(t.get("id", ""))
        node = t.get("node", {})
        member = t.get("member", {})
        content = t.get("content", "")[:500]

        return FeedItem(
            id=self.make_id(tid),
            platform=self.name,
            native_id=tid,
            title=t.get("title", ""),
            content=content,
            author=member.get("username", ""),
            author_url=f"https://www.v2ex.com/member/{member.get('username', '')}",
            url=f"https://www.v2ex.com/t/{tid}",
            timestamp=t.get("created", 0) * 1000,
            engagement=Engagement(
                comments=t.get("replies", 0),
            ),
            media_type="text",
            tags=[node.get("title", ""), node.get("name", "")],
            language="zh",
        )

    def health_check(self) -> ChannelStatus:
        try:
            self._throttle()
            resp = self._client.get("https://www.v2ex.com/api/topics/hot.json")
            return ChannelStatus(
                name=self.name, available=resp.status_code == 200,
                auth_required=False, auth_configured=True,
                latency_ms=int(resp.elapsed.total_seconds() * 1000),
            )
        except Exception as e:
            return ChannelStatus(
                name=self.name, available=False,
                auth_required=False, auth_configured=True, error=str(e),
            )
