"""XiaoHongShu (小红书) channel — direct MCP HTTP protocol.

Connects to the local XHS MCP server (port 18060) via MCP Streamable HTTP.
Cookie stored in ~/.agent-reach/tools/xiaohongshu-mcp/cookies.json (valid ~1 year).
To refresh: run `bash scripts/xhs-refresh-login.sh` (QR scan, one-time).
"""

from __future__ import annotations
import json
import os
from typing import Optional

import httpx

from .base import BaseChannel, ChannelRegistry
from ..models import FeedItem, Engagement, ChannelStatus
from ..config import ChannelConfig

MCP_BASE = "http://127.0.0.1:18060"


class _XHSMCPSession:
    """Lightweight MCP session manager."""

    def __init__(self, timeout: int = 45):
        self._client = httpx.Client(timeout=timeout)
        self._session_id: str = ""
        self._initialized = False

    def _init_session(self):
        if self._initialized:
            return
        r = self._client.post(f"{MCP_BASE}/mcp", json={
            "jsonrpc": "2.0", "method": "initialize", "id": 1,
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "omnifeed", "version": "0.2"},
            },
        })
        if r.status_code != 200:
            raise ConnectionError(f"MCP init failed: {r.status_code}")
        self._session_id = r.headers.get("mcp-session-id", "")
        self._client.post(
            f"{MCP_BASE}/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=self._headers(),
        )
        self._initialized = True

    def _headers(self) -> dict:
        return {"Mcp-Session-Id": self._session_id} if self._session_id else {}

    def call_tool(self, name: str, arguments: dict, timeout: int = 45) -> dict:
        """Call an MCP tool and return parsed result."""
        self._init_session()
        r = self._client.post(
            f"{MCP_BASE}/mcp",
            json={
                "jsonrpc": "2.0", "method": "tools/call", "id": 2,
                "params": {"name": name, "arguments": arguments},
            },
            headers=self._headers(),
            timeout=timeout,
        )
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        content = data.get("result", {}).get("content", [])
        if content:
            return json.loads(content[0].get("text", "{}"))
        return {}

    def close(self):
        self._client.close()


@ChannelRegistry.register
class XHSChannel(BaseChannel):
    name = "xhs"
    display_name = "小红书"
    icon = "📕"
    requires_auth = True
    rate_limit = 2.0  # MCP calls are slow, space them out

    def __init__(self, config: Optional[ChannelConfig] = None):
        super().__init__(config)
        self._session: Optional[_XHSMCPSession] = None

    def _get_session(self) -> _XHSMCPSession:
        if not self._session:
            self._session = _XHSMCPSession(timeout=45)
        return self._session

    def search(self, query: str, limit: int = 20) -> list[FeedItem]:
        """Search XHS feeds by keyword. Falls back gracefully on timeout."""
        self._throttle()
        try:
            data = self._get_session().call_tool("search_feeds", {"keyword": query}, timeout=20)
            feeds = data.get("feeds", [])
            return [it for f in feeds[:limit] if (it := self._parse_feed(f, query))]
        except Exception:
            return []  # Timeout or error — skip silently

    def trending(self, limit: int = 40) -> list[FeedItem]:
        """Get homepage feed (fast, ~8s for 60+ items)."""
        self._throttle()
        try:
            data = self._get_session().call_tool("list_feeds", {}, timeout=20)
            feeds = data.get("feeds", [])
            return [it for f in feeds[:limit] if (it := self._parse_feed(f))]
        except Exception:
            return []

    def user_feed(self, user_id: str, limit: int = 20) -> list[FeedItem]:
        """Get a user's notes."""
        self._throttle()
        try:
            data = self._get_session().call_tool("user_profile", {
                "user_id": user_id,
                "xsec_token": "ABJznrg9jrnK6nOwgSbtCf2CXG9LjJElN0Cq88GPc3Ypk=",
            }, timeout=30)
            feeds = data.get("feeds", [])
            return [it for f in feeds[:limit] if (it := self._parse_feed(f))]
        except Exception:
            return []

    def _parse_feed(self, feed: dict, query: str = "") -> Optional[FeedItem]:
        try:
            note = feed.get("noteCard", {})
            user = note.get("user", {})
            interact = note.get("interactInfo", {})
            cover = note.get("cover", {})
            feed_id = feed.get("id", "")
            if not feed_id:
                return None

            title = note.get("displayTitle", "") or ""
            cover_url = cover.get("urlDefault", "") or cover.get("urlPre", "") or cover.get("url", "")
            # Fix http → https
            if cover_url.startswith("http://"):
                cover_url = "https://" + cover_url[7:]

            likes_raw = interact.get("likedCount", "0")
            try:
                s = str(likes_raw).replace("+", "")
                if "万" in s:
                    likes = int(float(s.replace("万", "")) * 10000)
                else:
                    likes = int(s)
            except (ValueError, TypeError):
                likes = 0

            return FeedItem(
                id=self.make_id(feed_id),
                platform=self.name,
                native_id=feed_id,
                title=title,
                content="",
                author=user.get("nickname", "") or user.get("nickName", ""),
                author_url=f"https://www.xiaohongshu.com/user/profile/{user.get('userId', '')}",
                cover=cover_url,
                url=f"https://www.xiaohongshu.com/explore/{feed_id}",
                engagement=Engagement(likes=likes),
                media_type="video" if note.get("type") == "video" else "image",
                language="zh",
                query=query,
            )
        except Exception:
            return None

    def health_check(self) -> ChannelStatus:
        try:
            session = _XHSMCPSession(timeout=10)
            session._init_session()
            session.close()
            return ChannelStatus(
                name=self.name, available=True,
                auth_required=True, auth_configured=True,
                latency_ms=0,
            )
        except Exception as e:
            return ChannelStatus(
                name=self.name, available=False,
                auth_required=True, auth_configured=False,
                error=f"MCP server unavailable: {e}. Start: ensure-xhs-mcp.sh",
            )
