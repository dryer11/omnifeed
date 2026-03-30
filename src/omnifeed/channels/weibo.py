"""Weibo channel — zero config, uses mobile API."""

from __future__ import annotations
import json
import httpx
from typing import Optional

from .base import BaseChannel, ChannelRegistry
from ..models import FeedItem, Engagement, ChannelStatus
from ..config import ChannelConfig


@ChannelRegistry.register
class WeiboChannel(BaseChannel):
    name = "weibo"
    display_name = "微博"
    icon = "🔴"
    requires_auth = False
    rate_limit = 0.5

    USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
    BASE = "https://m.weibo.cn/api"

    def __init__(self, config: Optional[ChannelConfig] = None):
        super().__init__(config)
        self._client = httpx.Client(
            headers={"User-Agent": self.USER_AGENT, "Referer": "https://m.weibo.cn/"},
            follow_redirects=True,
            timeout=15,
        )

    def search(self, query: str, limit: int = 20) -> list[FeedItem]:
        self._throttle()
        try:
            resp = self._client.get(
                f"{self.BASE}/container/getIndex",
                params={
                    "containerid": f"100103type=1&q={query}",
                    "page_type": "searchall",
                },
            )
            data = resp.json()
            cards = data.get("data", {}).get("cards", [])
            items = []
            for card in cards:
                for group in card.get("card_group", [card]):
                    mblog = group.get("mblog")
                    if not mblog:
                        continue
                    item = self._parse_mblog(mblog, query)
                    if item:
                        items.append(item)
                    if len(items) >= limit:
                        break
                if len(items) >= limit:
                    break
            return items
        except Exception as e:
            return []

    def trending(self, limit: int = 20) -> list[FeedItem]:
        """Get Weibo hot search topics."""
        self._throttle()
        try:
            resp = self._client.get(
                "https://m.weibo.cn/api/container/getIndex",
                params={"containerid": "106003type=25&t=3&disable_hot=1&filter_type=realtimehot"},
            )
            data = resp.json()
            cards = data.get("data", {}).get("cards", [])
            items = []
            for card in cards:
                for group in card.get("card_group", []):
                    desc = group.get("desc", "")
                    scheme = group.get("scheme", "")
                    if desc:
                        items.append(FeedItem(
                            id=self.make_id(f"hot:{desc}"),
                            platform=self.name,
                            title=desc,
                            url=scheme,
                            media_type="text",
                        ))
                    if len(items) >= limit:
                        break
            return items
        except Exception:
            return []

    def _parse_mblog(self, mblog: dict, query: str = "") -> Optional[FeedItem]:
        """Parse a Weibo mblog object into FeedItem."""
        try:
            mid = str(mblog.get("id", ""))
            user = mblog.get("user", {})
            text = mblog.get("text", "")
            # Strip HTML tags simply
            import re
            text_clean = re.sub(r"<[^>]+>", "", text)[:500]

            # Extract cover from pics
            pics = mblog.get("pics", [])
            cover = pics[0].get("url", "") if pics else ""

            created = mblog.get("created_at", "")

            return FeedItem(
                id=self.make_id(mid),
                platform=self.name,
                native_id=mid,
                title=text_clean[:80],
                content=text_clean,
                author=user.get("screen_name", ""),
                author_url=f"https://weibo.com/u/{user.get('id', '')}",
                cover=cover,
                url=f"https://m.weibo.cn/detail/{mid}",
                timestamp=0,  # created_at is relative ("x分钟前"), skip parsing
                engagement=Engagement(
                    likes=mblog.get("attitudes_count", 0),
                    comments=mblog.get("comments_count", 0),
                    shares=mblog.get("reposts_count", 0),
                ),
                media_type="image" if pics else "text",
                language="zh",
                query=query,
            )
        except Exception:
            return None

    def health_check(self) -> ChannelStatus:
        try:
            self._throttle()
            resp = self._client.get(
                f"{self.BASE}/container/getIndex",
                params={"containerid": "106003type=25&t=3&disable_hot=1&filter_type=realtimehot"},
            )
            ok = resp.status_code == 200
            return ChannelStatus(
                name=self.name, available=ok,
                auth_required=False, auth_configured=True,
                latency_ms=int(resp.elapsed.total_seconds() * 1000),
            )
        except Exception as e:
            return ChannelStatus(
                name=self.name, available=False,
                auth_required=False, auth_configured=True,
                error=str(e),
            )
