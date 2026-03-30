"""GitHub Trending channel — uses gh CLI + web scraping."""

from __future__ import annotations
import subprocess
import json
import httpx
import re
from typing import Optional

from .base import BaseChannel, ChannelRegistry
from ..models import FeedItem, Engagement, ChannelStatus
from ..config import ChannelConfig


@ChannelRegistry.register
class GitHubChannel(BaseChannel):
    name = "github"
    display_name = "GitHub"
    icon = "🐙"
    requires_auth = False  # gh CLI handles auth
    rate_limit = 0.3

    def search(self, query: str, limit: int = 20) -> list[FeedItem]:
        """Search repos via gh CLI."""
        try:
            result = subprocess.run(
                ["gh", "search", "repos", query, "--sort=stars", "--limit", str(limit), "--json",
                 "fullName,description,url,stargazersCount,forksCount,updatedAt,language,isArchived"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                return []
            repos = json.loads(result.stdout)
            return [self._parse_repo(r, query) for r in repos if not r.get("isArchived")]
        except Exception:
            return []

    def trending(self, limit: int = 20) -> list[FeedItem]:
        """Scrape GitHub trending page."""
        try:
            resp = httpx.get(
                "https://github.com/trending",
                headers={"User-Agent": "omnifeed/0.1"},
                follow_redirects=True,
                timeout=15,
            )
            if resp.status_code != 200:
                return []
            return self._parse_trending_html(resp.text, limit)
        except Exception:
            return []

    def _parse_repo(self, r: dict, query: str = "") -> FeedItem:
        name = r.get("fullName", "")
        return FeedItem(
            id=self.make_id(name),
            platform=self.name,
            native_id=name,
            title=name,
            content=r.get("description", "") or "",
            author=name.split("/")[0] if "/" in name else "",
            author_url=f"https://github.com/{name.split('/')[0]}" if "/" in name else "",
            url=r.get("url", f"https://github.com/{name}"),
            engagement=Engagement(
                likes=r.get("stargazersCount", 0),
                shares=r.get("forksCount", 0),
            ),
            media_type="text",
            tags=[r.get("language", "")] if r.get("language") else [],
            language="en",
            query=query,
        )

    def _parse_trending_html(self, html: str, limit: int) -> list[FeedItem]:
        """Simple regex extraction from trending page."""
        items = []
        # Match repo entries: <h2 class="h3 lh-condensed">...<a href="/owner/repo">
        pattern = r'<h2[^>]*>\s*<a[^>]*href="(/[^"]+)"[^>]*>'
        matches = re.findall(pattern, html)

        for path in matches[:limit]:
            name = path.lstrip("/")
            if "/" not in name:
                continue
            items.append(FeedItem(
                id=self.make_id(name),
                platform=self.name,
                native_id=name,
                title=f"🔥 {name}",
                content="GitHub Trending",
                author=name.split("/")[0],
                url=f"https://github.com/{name}",
                media_type="text",
                tags=["trending"],
                language="en",
            ))
        return items

    def health_check(self) -> ChannelStatus:
        try:
            result = subprocess.run(
                ["gh", "auth", "status"], capture_output=True, text=True, timeout=5,
            )
            ok = result.returncode == 0
            return ChannelStatus(
                name=self.name, available=ok,
                auth_required=True, auth_configured=ok,
                error="" if ok else "gh CLI not authenticated",
            )
        except FileNotFoundError:
            return ChannelStatus(
                name=self.name, available=False,
                auth_required=True, auth_configured=False,
                error="gh CLI not found. Install: brew install gh",
            )
