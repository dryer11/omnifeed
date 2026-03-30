"""Bilibili channel — search + trending + user favorites.

Content mix strategy:
  - Search (interest-aligned): 60%
  - Trending (全站热门): 30%  
  - User favorites analysis: 10% (cold-start boost)

Cookie auto-acquired via anonymous homepage visit.
Login cookie optional for favorites access.
"""

from __future__ import annotations
import httpx
import re
import json
import os
from pathlib import Path
from typing import Optional

from .base import BaseChannel, ChannelRegistry
from ..models import FeedItem, Engagement, ChannelStatus
from ..config import ChannelConfig


def _fix_cover(url: str) -> str:
    if not url: return ""
    if url.startswith("//"): return "https:" + url
    if url.startswith("http://"): return "https://" + url[7:]
    return url


BILI_COOKIE_PATH = Path("~/.omnifeed/bilibili_cookies.json").expanduser()


@ChannelRegistry.register
class BilibiliChannel(BaseChannel):
    name = "bilibili"
    display_name = "B站"
    icon = "📺"
    requires_auth = False
    rate_limit = 0.3

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://search.bilibili.com/",
    }

    AD_SIGNALS = [
        "加微信", "加v", "联系方式", "私聊", "免费领", "限时",
        "优惠券", "点击购买", "淘宝", "拼多多", "带货",
    ]

    def __init__(self, config: Optional[ChannelConfig] = None):
        super().__init__(config)
        self._client = httpx.Client(headers=self.HEADERS, timeout=15, follow_redirects=True)
        self._cookie_init = False

    def _ensure_cookies(self):
        if self._cookie_init:
            return
        try:
            self._client.get("https://www.bilibili.com/")
        except Exception:
            pass
        self._cookie_init = True

    def search(self, query: str, limit: int = 20) -> list[FeedItem]:
        self._throttle()
        self._ensure_cookies()
        try:
            resp = self._client.get(
                "https://api.bilibili.com/x/web-interface/search/type",
                params={"search_type": "video", "keyword": query, "page": 1, "page_size": min(limit, 30)},
            )
            data = resp.json()
            results = data.get("data", {}).get("result", [])
            items = []
            for v in results:
                if not v: continue
                item = self._parse_video(v, query)
                if item and not self._is_ad(item):
                    items.append(item)
            return items[:limit]
        except Exception:
            return []

    def trending(self, limit: int = 25) -> list[FeedItem]:
        """Full-site trending — provides diversity and serendipity."""
        self._throttle()
        self._ensure_cookies()
        try:
            resp = self._client.get(
                "https://api.bilibili.com/x/web-interface/popular",
                params={"ps": min(limit, 30), "pn": 1},
            )
            data = resp.json()
            vlist = data.get("data", {}).get("list", [])
            items = []
            for v in vlist[:limit]:
                if not v: continue
                item = self._parse_popular(v)
                if item and not self._is_ad(item):
                    items.append(item)
            return items
        except Exception:
            return []

    def hot_search(self) -> list[str]:
        """Get bilibili hot search keywords — for query expansion."""
        try:
            resp = self._client.get(
                "https://api.bilibili.com/x/web-interface/wbi/search/square",
                params={"limit": 10},
            )
            data = resp.json()
            trending = data.get("data", {}).get("trending", {}).get("list", [])
            return [t.get("keyword", "") for t in trending if t.get("keyword")]
        except Exception:
            return []

    def _is_ad(self, item: FeedItem) -> bool:
        text = f"{item.title} {item.content}".lower()
        return any(sig in text for sig in self.AD_SIGNALS)

    def _parse_video(self, v: dict, query: str = "") -> FeedItem:
        bvid = v.get("bvid", "")
        title = re.sub(r"</?em[^>]*>", "", v.get("title", ""))
        cover = _fix_cover(v.get("pic", ""))
        return FeedItem(
            id=self.make_id(bvid), platform=self.name, native_id=bvid,
            title=title, content=v.get("description", "")[:500],
            author=v.get("author", ""),
            author_url=f"https://space.bilibili.com/{v.get('mid', '')}",
            cover=cover, url=f"https://www.bilibili.com/video/{bvid}",
            timestamp=v.get("pubdate", 0) * 1000,
            engagement=Engagement(likes=v.get("like", 0), views=v.get("play", 0), comments=v.get("review", 0)),
            media_type="video",
            tags=v.get("tag", "").split(",") if v.get("tag") else [],
            language="zh", query=query,
        )

    def _parse_popular(self, v: dict) -> FeedItem:
        bvid = v.get("bvid", "")
        stat = v.get("stat", {})
        owner = v.get("owner", {})
        cover = _fix_cover(v.get("pic", ""))
        return FeedItem(
            id=self.make_id(bvid), platform=self.name, native_id=bvid,
            title=v.get("title", ""), content=v.get("desc", "")[:500],
            author=owner.get("name", ""),
            author_url=f"https://space.bilibili.com/{owner.get('mid', '')}",
            cover=cover, url=f"https://www.bilibili.com/video/{bvid}",
            timestamp=v.get("pubdate", 0) * 1000,
            engagement=Engagement(likes=stat.get("like", 0), views=stat.get("view", 0),
                                  comments=stat.get("reply", 0), shares=stat.get("share", 0)),
            media_type="video", language="zh",
        )

    def health_check(self) -> ChannelStatus:
        try:
            self._ensure_cookies()
            self._throttle()
            resp = self._client.get(
                "https://api.bilibili.com/x/web-interface/popular",
                params={"ps": 1, "pn": 1},
            )
            ok = resp.status_code == 200 and resp.json().get("code") == 0
            return ChannelStatus(
                name=self.name, available=ok,
                auth_required=False, auth_configured=True,
                latency_ms=int(resp.elapsed.total_seconds() * 1000),
            )
        except Exception as e:
            return ChannelStatus(name=self.name, available=False,
                                 auth_required=False, auth_configured=True, error=str(e))
