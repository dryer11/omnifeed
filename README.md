<p align="center">
  <h1 align="center">OmniFeed</h1>
  <p align="center">
    <em>You check 7 apps every morning. OmniFeed checks them for you.</em>
  </p>
  <p align="center">
    <a href="#quick-start">Quick Start</a> •
    <a href="#features">Features</a> •
    <a href="#platforms">Platforms</a> •
    <a href="#how-it-works">How It Works</a> •
    <a href="#configuration">Configuration</a>
  </p>
</p>

---

OmniFeed is a **cross-platform personalized content aggregator** that fetches content from Bilibili, GitHub, Reddit, V2EX, 小红书 and more — then ranks everything in a single, beautiful feed page tailored to *you*.

Not another RSS reader. OmniFeed uses **LLM-powered query generation** to discover content you didn't know you wanted, **multi-hop retrieval** to chase topics across platforms, and a **cognitive expansion engine** to break you out of your information bubble.

<p align="center">
  <img src="docs/images/feed-preview.jpg" alt="OmniFeed Preview" width="600">
</p>

## Quick Start

```bash
# Install from GitHub
pip install git+https://github.com/dryer11/omnifeed.git

# Interactive setup (recommended)
omnifeed setup

# Or manual: init config, then fetch
omnifeed init
omnifeed fetch
omnifeed serve
```

`omnifeed setup` walks you through everything: profile, platform logins, AI configuration, and runs your first fetch automatically.

## Features

### 🧠 LLM-Powered Discovery

OmniFeed doesn't just search for what you tell it. It *reasons* about what you'd find fascinating.

```
Your interests: "LLM Reasoning, AI Safety"
OmniFeed searches: "RLVR reward verification reasoning", "合肥三月底樱花打卡攻略",
                    "chain of thought faithful reasoning debate"
```

The LLM considers your profile, time of day, recent interactions, and previous queries to generate diverse, creative search terms every run. Each fetch is different.

### 🔄 Multi-Hop Retrieval

**Hop 1:** Search your interests across all platforms + fetch trending content  
**Hop 2:** Analyze hop-1 results → extract emerging topics → chase them cross-platform

This catches trending discussions that haven't reached your usual feeds yet.

### 🎯 Deep Personalization

OmniFeed builds your interest profile from multiple signals:

- **Explicit interests** you set in config (weight 1-5)
- **GitHub Stars** — what repos you've starred reveals your tech taste
- **Bilibili favorites** — your collections reveal life interests (film, sports, cooking...)
- **Interaction history** — clicks and saves in the feed page refine future results
- **Cognitive expansion** — "if you like X, you'd probably also enjoy Y"

### 🏗️ Content Mix Control

Every feed maintains a balanced diet:

| Source | Target | Purpose |
|--------|--------|---------|
| Interest-aligned | ~40% | Direct matches to your profile |
| Trending | ~20% | What's hot right now |
| Multi-hop | ~20% | Cross-platform topic chasing |
| Exploratory | ~10% | Anti-bubble serendipity |
| Local/lifestyle | ~10% | Location-based discovery |

### 📱 Apple-Inspired UI

Clean masonry layout, glassmorphism header, platform-colored badges, topic clustering with fold/unfold. Save items, filter by platform or category. PWA-ready for mobile.

## Platforms

| Platform | Auth | Search | Trending | Profile Mining |
|----------|------|--------|----------|----------------|
| Bilibili (B站) | Optional | ✅ | ✅ | ⭐ Favorites analysis |
| GitHub | Optional | ✅ | ✅ | ⭐ Stars analysis |
| Reddit | None | ✅ | ✅ | — |
| V2EX | None | — | ✅ (nodes) | — |
| 小红书 (XHS) | Cookie/MCP | ✅ | ✅ | — |
| Weibo | None | ✅ | ✅ | — |
| RSS | None | — | — | Feed items |

**Login is recommended** — it dramatically improves content quality by mining your platform data for interest signals.

```bash
omnifeed login bilibili    # QR scan → auto-analyze favorites
omnifeed login github      # gh CLI or token → analyze stars
```

## How It Works

```
┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│  User Profile │ ──→ │  LLM Query    │ ──→ │  Multi-Hop   │
│  (interests,  │     │  Generation   │     │  Fetch       │
│   favorites,  │     │  (creative,   │     │  (Hop1→Hop2) │
│   stars)      │     │   diverse)    │     │              │
└──────────────┘     └───────────────┘     └──────┬───────┘
                                                   │
                     ┌───────────────┐     ┌──────▼───────┐
                     │  Render       │ ←── │  Process     │
                     │  (HTML/JSON/  │     │  (dedup,     │
                     │   Digest)     │     │   categorize,│
                     │              │     │   rank)      │
                     └───────────────┘     └──────────────┘
```

1. **Profile** → Build interest graph from config + platform data + memory
2. **Query** → LLM generates diverse search queries per platform (falls back to rules)
3. **Fetch** → Hop-1 searches + trending; Hop-2 chases emerging topics cross-platform
4. **Process** → Dedup → LLM categorize → LLM summarize → Filter spam
5. **Rank** → Relevance × Freshness × Engagement × Diversity, with clickbait penalty
6. **Render** → Static HTML (instant, deploy anywhere) + JSON + daily digest

## Configuration

```yaml
# ~/.omnifeed/config.yaml

profile:
  name: "Your Name"
  location: "Your City"
  identity: "AI researcher / student / developer"

  interests:
    - topic: "LLM Reasoning"
      weight: 5
    - topic: "Open Source"
      weight: 3
    - topic: "Local Food"
      weight: 2

channels:
  bilibili:
    enabled: true
  github:
    enabled: true
  reddit:
    enabled: true
    subreddits: ["MachineLearning", "LocalLLaMA"]
  v2ex:
    enabled: true
    nodes: ["python", "ai", "jobs"]

ai:
  enabled: true
  base_url: "https://api.anthropic.com"
  api_key: "sk-ant-..."          # or set OMNIFEED_API_KEY env var
  models:
    query_gen: "claude-sonnet-4-5"   # creative query generation
    batch: "claude-haiku-3-5"        # categorize/summarize (fast & cheap)
  features:
    - query_gen
    - categorize
    - summarize
    - recommend_reason
```

### AI is optional

Without AI, OmniFeed uses a rule-based cognitive expansion engine with manually curated keyword maps. It works, but LLM mode is significantly better at discovering interesting content.

## CLI Reference

```bash
omnifeed setup               # Interactive first-time setup
omnifeed fetch               # Fetch from all platforms
omnifeed fetch --channel bilibili  # Single platform
omnifeed fetch --dry-run     # Preview query plan
omnifeed serve               # Local preview (localhost:8080)
omnifeed doctor              # Check platform availability
omnifeed login bilibili      # Bilibili QR login
omnifeed login github        # GitHub auth
omnifeed profile             # Rebuild interest profile
omnifeed pool stats          # Content pool status
```

## Architecture

```
src/omnifeed/
├── cli.py              # CLI commands (click)
├── engine.py           # Core 2-hop fetch engine
├── llm.py              # LLM integration (query gen, categorize, summarize)
├── config.py           # YAML config loading
├── login.py            # Platform login flows
├── profile.py          # Deep profile builder (GitHub/Bilibili/context mining)
├── query_builder.py    # Rule-based query generation (LLM fallback)
├── cognitive_expand.py # Cognitive keyword expansion engine
├── processor.py        # Dedup, categorize, filter, cluster
├── ranker.py           # Personalized ranking with diversity control
├── renderer.py         # HTML/JSON/digest output
├── pool.py             # Content pool for instant refresh
├── interaction_sync.py # Browser interaction → profile feedback loop
├── models.py           # Data models (FeedItem, TopicCluster, etc.)
└── channels/
    ├── base.py         # BaseChannel + Registry
    ├── bilibili.py     # Bilibili search + trending
    ├── github.py       # GitHub trending + search
    ├── reddit.py       # Reddit search + hot
    ├── v2ex.py         # V2EX node-based fetch
    ├── xhs.py          # 小红书 (via MCP)
    ├── weibo.py        # Weibo search + trending
    └── rss.py          # RSS/Atom feeds
```

## Adding a Channel

OmniFeed uses a registry pattern. To add a new platform:

```python
from omnifeed.channels.base import BaseChannel, ChannelRegistry
from omnifeed.models import FeedItem

@ChannelRegistry.register
class MyChannel(BaseChannel):
    name = "myplatform"
    display_name = "My Platform"
    icon = "🌐"

    def search(self, query: str, limit: int = 20) -> list[FeedItem]:
        # Implement search
        ...

    def trending(self, limit: int = 20) -> list[FeedItem]:
        # Implement trending (optional)
        ...
```

## OpenClaw Integration

OmniFeed works standalone, but integrates with [OpenClaw](https://github.com/openclaw/openclaw) for enhanced personalization:

- Auto-generate profile from `USER.md` / `MEMORY.md`
- Schedule fetches via OpenClaw cron
- Push daily digests to chat (Telegram, Discord, etc.)
- "What's new today?" triggers instant fetch

See `integrations/openclaw/` for the OpenClaw skill.

## License

MIT

## Author

**Sun Yan** ([@dryer11](https://github.com/dryer11)) — USTC AI
