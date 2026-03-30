"""Base channel adapter and registry."""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
import time

from ..models import FeedItem, ChannelStatus
from ..config import ChannelConfig, UserProfile


class BaseChannel(ABC):
    """Abstract base for all platform adapters."""

    name: str = ""
    display_name: str = ""
    icon: str = "📄"
    requires_auth: bool = False
    rate_limit: float = 0.5  # seconds between requests

    def __init__(self, config: Optional[ChannelConfig] = None):
        self.config = config or ChannelConfig()
        self._last_request = 0.0

    def _throttle(self):
        """Respect rate limits."""
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request = time.time()

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> list[FeedItem]:
        """Search content by keyword."""
        ...

    def trending(self, limit: int = 20) -> list[FeedItem]:
        """Get trending/hot content. Override if supported."""
        return []

    def user_feed(self, user_id: str, limit: int = 20) -> list[FeedItem]:
        """Get a specific user's content. Override if supported."""
        return []

    def health_check(self) -> ChannelStatus:
        """Check if this channel is operational."""
        return ChannelStatus(
            name=self.name,
            available=True,
            auth_required=self.requires_auth,
            auth_configured=True,
        )

    def make_id(self, native_id: str) -> str:
        """Create a global unique ID."""
        return f"{self.name}:{native_id}"


class ChannelRegistry:
    """Registry of available channel adapters."""

    _channels: dict[str, type[BaseChannel]] = {}

    @classmethod
    def register(cls, channel_class: type[BaseChannel]):
        cls._channels[channel_class.name] = channel_class
        return channel_class

    @classmethod
    def get(cls, name: str) -> Optional[type[BaseChannel]]:
        return cls._channels.get(name)

    @classmethod
    def all(cls) -> dict[str, type[BaseChannel]]:
        return dict(cls._channels)

    @classmethod
    def create(cls, name: str, config: Optional[ChannelConfig] = None) -> Optional[BaseChannel]:
        klass = cls.get(name)
        if klass:
            return klass(config)
        return None
