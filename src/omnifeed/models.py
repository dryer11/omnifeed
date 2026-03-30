"""Core data models for OmniFeed."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
import time
import json
import hashlib


@dataclass
class Engagement:
    """Engagement metrics for a piece of content."""
    likes: int = 0
    comments: int = 0
    shares: int = 0
    views: int = 0

    @property
    def score(self) -> float:
        """Weighted engagement score."""
        return self.likes + self.comments * 3 + self.shares * 2 + self.views * 0.01


@dataclass
class FeedItem:
    """Universal content item from any platform."""

    # Identity
    id: str                          # "{platform}:{native_id}"
    platform: str                    # "twitter", "xhs", "bilibili", ...
    native_id: str = ""              # Platform-specific ID

    # Content
    title: str = ""
    content: str = ""                # Body text (truncated to ~500 chars)
    author: str = ""
    author_url: str = ""
    cover: str = ""                  # Cover image URL
    url: str = ""                    # Original link
    timestamp: int = 0               # Unix ms
    engagement: Engagement = field(default_factory=Engagement)
    media_type: str = "text"         # "text" | "image" | "video"
    tags: list[str] = field(default_factory=list)
    language: str = "zh"             # "zh" | "en"

    # Post-processing (filled by Processor / Ranker)
    category: str = ""               # "🔬 科研" | "🍜 美食" | ...
    summary: str = ""                # AI-generated one-liner
    relevance: float = 0.0           # 0-1 relevance to user interests
    cluster_id: str = ""             # Topic cluster ID
    recommend_reason: str = ""       # "因为你关注 AI Safety"
    topic_tags: list[str] = field(default_factory=list)  # LLM-generated topic tags
    query: str = ""                  # Which query produced this item
    source_type: str = "search"      # "search" | "trending" | "hop2"

    # Internal
    _raw: dict = field(default_factory=dict, repr=False)
    _score: float = 0.0             # Final ranking score

    @property
    def age_hours(self) -> float:
        """Hours since creation."""
        if not self.timestamp:
            return 999
        return (time.time() * 1000 - self.timestamp) / 3_600_000

    @property
    def content_hash(self) -> str:
        """Content fingerprint for dedup."""
        text = f"{self.title} {self.content[:200]}".lower().strip()
        return hashlib.md5(text.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        """Serialize for JSON output."""
        d = asdict(self)
        d.pop("_raw", None)
        d["engagement"] = asdict(self.engagement)
        return d


@dataclass
class TopicCluster:
    """A group of FeedItems discussing the same topic."""
    cluster_id: str
    topic: str                       # Inferred topic name
    items: list[FeedItem] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    total_engagement: float = 0.0

    def add(self, item: FeedItem):
        self.items.append(item)
        if item.platform not in self.platforms:
            self.platforms.append(item.platform)
        self.total_engagement += item.engagement.score


@dataclass
class QueryPlan:
    """A search plan for a single channel."""
    channel: str
    keywords: list[str] = field(default_factory=list)
    accounts: list[str] = field(default_factory=list)
    reason: str = ""
    limit: int = 20


@dataclass
class ChannelStatus:
    """Health check result for a channel."""
    name: str
    available: bool
    auth_required: bool
    auth_configured: bool
    error: str = ""
    latency_ms: int = 0


@dataclass
class FeedResult:
    """Complete result of a fetch+process+rank cycle."""
    generated_at: str = ""
    profile_name: str = ""
    stats: dict = field(default_factory=dict)
    items: list[FeedItem] = field(default_factory=list)
    clusters: list[TopicCluster] = field(default_factory=list)
    topic_tags: list[str] = field(default_factory=list)  # LLM-generated topic tags

    def to_json(self, **kwargs) -> str:
        return json.dumps({
            "generated_at": self.generated_at,
            "profile": self.profile_name,
            "stats": self.stats,
            "items": [it.to_dict() for it in self.items],
            "clusters": [
                {
                    "cluster_id": c.cluster_id,
                    "topic": c.topic,
                    "platforms": c.platforms,
                    "total_engagement": c.total_engagement,
                    "item_count": len(c.items),
                }
                for c in self.clusters
            ],
        }, ensure_ascii=False, **kwargs)
