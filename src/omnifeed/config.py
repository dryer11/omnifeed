"""Configuration loading and management."""

from __future__ import annotations
import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


DEFAULT_CONFIG_DIR = Path.home() / ".omnifeed"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"

# Example config template
EXAMPLE_CONFIG = """\
# OmniFeed Configuration
# See: https://github.com/dryer11/omnifeed

profile:
  name: "Your Name"
  location: "Your City"
  identity: "Student / Engineer / Researcher"

  # Interest tags (weight 1-5, higher = more relevant)
  interests:
    - topic: "AI"
      weight: 5
    - topic: "Technology"
      weight: 3

  # Accounts to follow
  follows: []
  #  - platform: twitter
  #    username: "karpathy"
  #  - platform: xhs
  #    user_id: "..."

  # RSS feeds
  feeds: []
  #  - url: "https://sspai.com/feed"
  #    name: "少数派"

# Platform toggles
channels:
  weibo:
    enabled: true
  v2ex:
    enabled: true
    nodes: ["python", "ai", "jobs"]
  github:
    enabled: true
  reddit:
    enabled: true
    subreddits: ["MachineLearning", "LocalLLaMA"]
  rss:
    enabled: true
  xhs:
    enabled: false
  twitter:
    enabled: false
  bilibili:
    enabled: false

# Output
output:
  html: true
  json: true
  daily_digest: false
  dir: "~/.omnifeed/output"
  deploy:
    github_pages:
      repo: ""
      branch: "gh-pages"

# AI features (optional)
ai:
  enabled: false
  # model: "anthropic/claude-sonnet-4-20250514"
  # features: [summarize, categorize, recommend_reason]
  # batch_size: 20

schedule:
  fetch_interval: "4h"
  digest_time: "08:00"
  timezone: "Asia/Shanghai"
"""


@dataclass
class InterestTag:
    topic: str
    weight: int = 3


@dataclass
class FollowAccount:
    platform: str
    user_id: str = ""
    username: str = ""
    name: str = ""


@dataclass
class RSSFeed:
    url: str
    name: str = ""


@dataclass
class UserProfile:
    name: str = ""
    location: str = ""
    identity: str = ""
    interests: list[InterestTag] = field(default_factory=list)
    follows: list[FollowAccount] = field(default_factory=list)
    feeds: list[RSSFeed] = field(default_factory=list)

    @property
    def interest_keywords(self) -> list[str]:
        """Flat list of interest keywords, weighted by repetition."""
        kws = []
        for tag in self.interests:
            kws.extend([tag.topic] * tag.weight)
        return kws

    @property
    def interest_set(self) -> set[str]:
        """Unique interest topics, lowercased."""
        return {t.topic.lower() for t in self.interests}


@dataclass
class ChannelConfig:
    enabled: bool = False
    nodes: list[str] = field(default_factory=list)       # V2EX
    subreddits: list[str] = field(default_factory=list)   # Reddit
    extra: dict = field(default_factory=dict)


@dataclass
class OutputConfig:
    html: bool = True
    json: bool = True
    daily_digest: bool = False
    dir: str = "~/.omnifeed/output"


@dataclass
class Config:
    profile: UserProfile = field(default_factory=UserProfile)
    channels: dict[str, ChannelConfig] = field(default_factory=dict)
    output: OutputConfig = field(default_factory=OutputConfig)
    ai_enabled: bool = False
    ai_model: str = ""
    ai_config: dict = field(default_factory=dict)  # Full AI config dict
    config_path: str = ""

    def enabled_channels(self) -> list[str]:
        return [name for name, cfg in self.channels.items() if cfg.enabled]


def load_config(path: Optional[str] = None) -> Config:
    """Load config from YAML file."""
    config_path = Path(path) if path else DEFAULT_CONFIG_FILE

    if not config_path.exists():
        return Config(config_path=str(config_path))

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    cfg = Config(config_path=str(config_path))

    # Profile
    p = raw.get("profile", {})
    cfg.profile = UserProfile(
        name=p.get("name", ""),
        location=p.get("location", ""),
        identity=p.get("identity", ""),
        interests=[
            InterestTag(topic=i["topic"], weight=i.get("weight", 3))
            for i in p.get("interests", [])
        ],
        follows=[
            FollowAccount(
                platform=f["platform"],
                user_id=f.get("user_id", ""),
                username=f.get("username", ""),
                name=f.get("name", ""),
            )
            for f in p.get("follows", [])
        ],
        feeds=[
            RSSFeed(url=f["url"], name=f.get("name", ""))
            for f in p.get("feeds", [])
        ],
    )

    # Channels
    for name, ch_raw in raw.get("channels", {}).items():
        if isinstance(ch_raw, dict):
            cfg.channels[name] = ChannelConfig(
                enabled=ch_raw.get("enabled", False),
                nodes=ch_raw.get("nodes", []),
                subreddits=ch_raw.get("subreddits", []),
                extra={k: v for k, v in ch_raw.items()
                       if k not in ("enabled", "nodes", "subreddits")},
            )

    # Output
    o = raw.get("output", {})
    cfg.output = OutputConfig(
        html=o.get("html", True),
        json=o.get("json", True),
        daily_digest=o.get("daily_digest", False),
        dir=o.get("dir", "~/.omnifeed/output"),
    )

    # AI
    ai = raw.get("ai", {})
    cfg.ai_enabled = ai.get("enabled", False)
    cfg.ai_model = ai.get("model", "")
    cfg.ai_config = {
        "base_url": ai.get("base_url", ""),
        "api_key": ai.get("api_key", ""),
        "models": ai.get("models", {}),
        "features": ai.get("features", ["query_gen", "categorize", "summarize", "recommend_reason"]),
        "batch_size": ai.get("batch_size", 15),
        "max_tokens_per_fetch": ai.get("max_tokens_per_fetch", 50000),
    }

    return cfg


def init_config(path: Optional[str] = None) -> Path:
    """Create default config file."""
    config_path = Path(path) if path else DEFAULT_CONFIG_FILE
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(EXAMPLE_CONFIG)
    return config_path
