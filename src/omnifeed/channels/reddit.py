"""Reddit channel — zero config, public JSON API."""

from __future__ import annotations
import httpx
from typing import Optional

from .base import BaseChannel, ChannelRegistry
from ..models import FeedItem, Engagement, ChannelStatus
from ..config import ChannelConfig


@ChannelRegistry.register
class RedditChannel(BaseChannel):
    name = "reddit"
    display_name = "Reddit"
    icon = "🤖"
    requires_auth = False
    rate_limit = 1.0  # Reddit throttles aggressively

    HEADERS = {"User-Agent": "omnifeed/0.1 (content aggregator)"}

    def __init__(self, config: Optional[ChannelConfig] = None):
        super().__init__(config)
        self._client = httpx.Client(
            headers=self.HEADERS,
            follow_redirects=True,
            timeout=15,
        )
        self._subreddits = config.subreddits if config else ["MachineLearning", "LocalLLaMA"]

    def search(self, query: str, limit: int = 20) -> list[FeedItem]:
        self._throttle()
        try:
            resp = self._client.get(
                "https://www.reddit.com/search.json",
                params={"q": query, "limit": limit, "sort": "relevance", "t": "week"},
            )
            if resp.status_code != 200:
                return []
            posts = resp.json().get("data", {}).get("children", [])
            return [self._parse_post(p["data"], query) for p in posts if p.get("data")]
        except Exception:
            return []

    def trending(self, limit: int = 20) -> list[FeedItem]:
        """Get hot posts from configured subreddits."""
        items = []
        per_sub = max(5, limit // max(len(self._subreddits), 1))
        for sub in self._subreddits:
            items.extend(self._subreddit_hot(sub, per_sub))
        return items[:limit]

    def _subreddit_hot(self, subreddit: str, limit: int = 10) -> list[FeedItem]:
        self._throttle()
        try:
            resp = self._client.get(
                f"https://www.reddit.com/r/{subreddit}/hot.json",
                params={"limit": limit},
            )
            if resp.status_code != 200:
                return []
            posts = resp.json().get("data", {}).get("children", [])
            return [self._parse_post(p["data"]) for p in posts if p.get("data") and not p["data"].get("stickied")]
        except Exception:
            return []

    def _parse_post(self, d: dict, query: str = "") -> FeedItem:
        post_id = d.get("id", "")
        subreddit = d.get("subreddit", "")
        selftext = (d.get("selftext", "") or "")[:500]

        # Cover: thumbnail or preview image
        cover = ""
        if d.get("thumbnail", "").startswith("http"):
            cover = d["thumbnail"]
        preview = d.get("preview", {})
        if preview:
            images = preview.get("images", [])
            if images:
                cover = images[0].get("source", {}).get("url", "").replace("&amp;", "&")

        return FeedItem(
            id=self.make_id(post_id),
            platform=self.name,
            native_id=post_id,
            title=d.get("title", ""),
            content=selftext,
            author=d.get("author", ""),
            author_url=f"https://www.reddit.com/user/{d.get('author', '')}",
            cover=cover,
            url=f"https://www.reddit.com{d.get('permalink', '')}",
            timestamp=int(d.get("created_utc", 0) * 1000),
            engagement=Engagement(
                likes=d.get("ups", 0),
                comments=d.get("num_comments", 0),
            ),
            media_type="image" if d.get("post_hint") == "image" else "text",
            tags=[f"r/{subreddit}"],
            language="en",
            query=query,
        )

    def health_check(self) -> ChannelStatus:
        try:
            self._throttle()
            resp = self._client.get(
                "https://www.reddit.com/r/all/hot.json",
                params={"limit": 1},
            )
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
