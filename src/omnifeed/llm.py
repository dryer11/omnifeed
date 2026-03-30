"""LLM-powered AI module — the brain of OmniFeed.

Capabilities:
  1. Smart query generation (creative, diverse, serendipitous)
  2. Batch categorization (accurate, multi-label)
  3. One-line summaries (compelling, concise)
  4. Recommendation reasons (personalized, natural language)

Uses Anthropic Messages API via httpx (no SDK dependency).
Graceful degradation: all functions fall back to rule-based on failure.
"""

from __future__ import annotations
import json
import time
import random
import os
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from rich.console import Console

from .models import FeedItem
from .config import Config

console = Console()

# ── Token tracking ──
_session_tokens = {"input": 0, "output": 0, "calls": 0}

QUERY_HISTORY_FILE = Path("~/.omnifeed/query_history.json").expanduser()
API_KEY_FILE = Path("~/.omnifeed/.api_key").expanduser()


def _read_key_file() -> str:
    """Read API key from file fallback."""
    if API_KEY_FILE.exists():
        return API_KEY_FILE.read_text().strip()
    return ""


class LLMClient:
    """Lightweight Anthropic Messages API client."""

    def __init__(self, config: Config):
        ai = config.ai_config if hasattr(config, 'ai_config') else {}
        self.base_url = (ai.get("base_url") or
                         os.environ.get("OMNIFEED_BASE_URL") or
                         "https://api.anthropic.com")
        self.api_key = (ai.get("api_key") or
                        os.environ.get("OMNIFEED_API_KEY") or
                        os.environ.get("ANTHROPIC_API_KEY") or
                        _read_key_file() or "")
        self.model_query = ai.get("models", {}).get("query_gen", "claude-sonnet-4-5")
        self.model_batch = ai.get("models", {}).get("batch", "claude-haiku-3-5")
        self.batch_size = ai.get("batch_size", 15)
        self.max_tokens_per_fetch = ai.get("max_tokens_per_fetch", 50000)
        self.features = set(ai.get("features", ["query_gen", "categorize", "summarize", "recommend_reason"]))

        # Strip trailing slash
        self.base_url = self.base_url.rstrip("/")

    def _call(self, model: str, system: str, user_msg: str,
              max_tokens: int = 2048, temperature: float = 0.7) -> Optional[str]:
        """Call Anthropic Messages API with retry."""
        if not self.api_key:
            return None

        # Budget check
        if _session_tokens["input"] + _session_tokens["output"] > self.max_tokens_per_fetch:
            console.print("[dim]  ⚠ Token budget exceeded, skipping LLM call[/dim]")
            return None

        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user_msg}],
        }

        for attempt in range(3):
            try:
                r = httpx.post(url, json=body, headers=headers, timeout=60)
                if r.status_code == 429:
                    wait = min(30, 2 ** attempt * 5)
                    console.print(f"[dim]  ⏳ Rate limited, waiting {wait}s...[/dim]")
                    time.sleep(wait)
                    continue
                if r.status_code != 200:
                    console.print(f"[dim]  ⚠ LLM API {r.status_code}: {r.text[:200]}[/dim]")
                    return None

                data = r.json()
                # Track tokens
                usage = data.get("usage", {})
                _session_tokens["input"] += usage.get("input_tokens", 0)
                _session_tokens["output"] += usage.get("output_tokens", 0)
                _session_tokens["calls"] += 1

                # Extract text
                content = data.get("content", [])
                if content and content[0].get("type") == "text":
                    return content[0]["text"]
                return None

            except httpx.TimeoutException:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                return None
            except Exception as e:
                console.print(f"[dim]  ⚠ LLM error: {e}[/dim]")
                return None

        return None

    def has_feature(self, feature: str) -> bool:
        return feature in self.features


# ═══════════════════════════════════════════════════════════════
# 1. SMART QUERY GENERATION — the soul of personalized discovery
# ═══════════════════════════════════════════════════════════════

def generate_search_queries(client: LLMClient, config: Config) -> Optional[dict[str, list[str]]]:
    """Use LLM to generate creative, diverse search queries per channel.
    
    This is where OmniFeed's intelligence lives. The LLM doesn't just
    rephrase interests — it reasons about what would surprise and delight
    this specific user, today.
    """
    if not client.has_feature("query_gen"):
        return None

    context = _build_query_context(config)
    if not context:
        return None

    system = """You are OmniFeed's discovery engine — a creative content recommender that thinks like a curious human, not a search algorithm.

YOUR CORE MISSION: Generate search queries that create a DIVERSE, SURPRISING, RICH content diet. Not just what the user explicitly likes — what they'd LOVE but never thought to search for.

## THINKING STRATEGIES (use ALL of them):

### 1. 心理迁移 (Psychological Transfer)
Someone who likes AI reasoning → probably fascinated by philosophy of mind, cognitive biases, detective fiction, mathematical beauty
Someone who likes open source → might enjoy commons economics, Wikipedia culture, DIY maker movement
"What EMOTIONAL need does this interest serve? What else serves that same need?"

### 2. 兴趣多跳 (Multi-hop Interest Chaining)
推荐系统 → 信息茧房 → 注意力经济 → 多巴胺机制 → 数字极简主义
LLM reasoning → 形式逻辑 → 哥德尔不完备定理 → 数学哲学 → 科学史
"Chain 3-4 hops away from the stated interest. The magic is in hop 3+."

### 3. 画像想象 (Profile Imagination)  
A grad student in AI in a Chinese city → late nights in the lab, instant noodles, 考研压力, 
weekend city walks, catching up on films, thinking about career vs academia, 
wanting both intellectual depth and simple pleasures
"Imagine their DAILY LIFE, not just their resume. What do they need at 11pm? At Sunday noon?"

### 4. 场景联想 (Scenario Association)
It's spring → cherry blossoms, outdoor activities, new semester energy, graduation anxiety
It's Monday evening → winding down, seeking entertainment or inspiration
"What is this person likely DOING or FEELING right now?"

### 5. 反信息茧房 (Anti-Bubble Injection)
Every query set MUST include 2-3 queries that are WILDLY different from the user's stated interests.
A film they wouldn't normally watch. A hobby they've never tried. A perspective from a different field.
"What would blow their mind if they stumbled upon it?"

## RULES:
- Each query: 2-8 words, optimized for the target platform
- Chinese platforms (bilibili, xhs): Chinese queries. Reddit/GitHub: English
- NEVER repeat queries from previous runs
- Per channel: 3-4 precise queries + 3-4 exploratory + 2-3 serendipity shots
- Vary the EMOTIONAL TONE: some intellectual, some fun, some cozy, some provocative
- For 小红书: think LIFESTYLE, not just the user's research field

Output ONLY valid JSON, no markdown fences."""

    channels = config.enabled_channels()
    channel_desc = []
    for ch in channels:
        if ch == "bilibili":
            channel_desc.append("bilibili (B站): Chinese video platform. Tech tutorials, documentaries, vlogs, culture. Queries in Chinese.")
        elif ch == "reddit":
            subs = config.channels.get(ch)
            sub_list = subs.subreddits if subs else []
            channel_desc.append(f"reddit: English. Subreddits: {sub_list}. Tech, AI, programming discussions.")
        elif ch == "github":
            channel_desc.append("github: English. Code repos, tools, trending projects.")
        elif ch == "xhs":
            channel_desc.append("xhs (小红书): Chinese. Lifestyle, food, local, campus. Queries in Chinese.")
        elif ch == "v2ex":
            channel_desc.append("v2ex: Chinese tech forum. (Skip — uses node-based fetch, not search)")
        elif ch == "weibo":
            channel_desc.append("weibo: Chinese microblog. Hot topics, news. Queries in Chinese.")

    user_msg = f"""{context}

Enabled channels:
{chr(10).join('- ' + c for c in channel_desc)}

Generate search queries. Output JSON:
{{
  "bilibili": ["query1", "query2", ...],
  "reddit": ["query1", "query2", ...],
  "github": ["query1", "query2", ...],
  "xhs": ["query1", "query2", ...]
}}

Only include enabled channels (skip v2ex and rss). Make each query count."""

    result = client._call(
        model=client.model_query,
        system=system,
        user_msg=user_msg,
        max_tokens=1500,
        temperature=0.9,  # High creativity
    )

    if not result:
        return None

    try:
        # Parse JSON (handle markdown fences)
        cleaned = re.sub(r'^```(?:json)?\s*', '', result.strip())
        cleaned = re.sub(r'\s*```$', '', cleaned)
        queries = json.loads(cleaned)

        # Validate structure
        if not isinstance(queries, dict):
            return None

        # Filter to enabled channels and validate
        valid = {}
        for ch in channels:
            if ch in queries and isinstance(queries[ch], list):
                ch_queries = [q.strip() for q in queries[ch] if isinstance(q, str) and q.strip()]
                if ch_queries:
                    valid[ch] = ch_queries[:12]

        if valid:
            _save_query_history(valid)
            total_q = sum(len(v) for v in valid.values())
            console.print(f"  [magenta]🧠 LLM generated {total_q} queries across {len(valid)} channels[/magenta]")
            return valid

    except (json.JSONDecodeError, KeyError) as e:
        console.print(f"[dim]  ⚠ Failed to parse LLM query response: {e}[/dim]")

    return None


def _build_query_context(config: Config) -> str:
    """Build rich context for LLM query generation."""
    from .profile import get_profile

    profile = config.profile
    profile_data = get_profile()

    # Basic info
    parts = [
        f"User: {profile.name}",
        f"Identity: {profile.identity}",
        f"Location: {profile.location}",
    ]

    # Interests with weights
    if profile.interests:
        interest_str = ", ".join(f"{t.topic} (w={t.weight})" for t in profile.interests)
        parts.append(f"Explicit interests: {interest_str}")

    # Top profile topics (from GitHub stars, bilibili favorites, etc.)
    topics = profile_data.get("topics", {})
    if topics:
        sorted_t = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:20]
        topic_str = ", ".join(f"{t}({w:.0f})" for t, w in sorted_t)
        parts.append(f"Deep profile topics: {topic_str}")

    # Behavioral interests
    behavioral = profile_data.get("behavioral_interests", {})
    if behavioral:
        beh_str = ", ".join(f"{k}({v})" for k, v in sorted(behavioral.items(), key=lambda x: x[1], reverse=True)[:10])
        parts.append(f"Behavioral (from platform usage): {beh_str}")

    # Interaction preferences
    interaction_total = profile_data.get("interaction_total", 0)
    if interaction_total > 10:
        cat_pref = profile_data.get("category_affinity", {})
        if cat_pref:
            parts.append(f"Recently clicked categories: {cat_pref}")
        plat_pref = profile_data.get("platforms_affinity", {})
        if plat_pref:
            parts.append(f"Platform preference: {plat_pref}")

    # Current time context
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    parts.append(f"Current: {now.strftime('%A, %Y-%m-%d %H:%M')} (China Standard Time)")
    parts.append(f"Day of week context: {'weekday' if now.weekday() < 5 else 'weekend'}")

    # Previous queries (to avoid repetition)
    prev = _load_query_history()
    if prev:
        flat = []
        for run in prev[-2:]:  # Last 2 runs
            for ch, qs in run.items():
                flat.extend(qs)
        if flat:
            parts.append(f"Previous queries (AVOID repeating): {', '.join(flat[:30])}")

    # Random seed for variety
    parts.append(f"Randomization seed: {random.randint(1000, 9999)}")

    return "\n".join(parts)


def _load_query_history() -> list[dict]:
    if not QUERY_HISTORY_FILE.exists():
        return []
    try:
        with open(QUERY_HISTORY_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_query_history(queries: dict):
    history = _load_query_history()
    history.append(queries)
    # Keep last 5 runs
    history = history[-5:]
    QUERY_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUERY_HISTORY_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# 1b. LLM HOP-2 — intelligent cross-platform topic chasing
# ═══════════════════════════════════════════════════════════════

def generate_hop2_queries(client: LLMClient, hop1_items: list[FeedItem],
                          config: Config) -> dict[str, list[str]]:
    """Analyze Hop-1 results and generate Hop-2 chase queries.

    Instead of extracting high-frequency keywords (dumb), the LLM reasons
    about what emerging topics, debates, and events deserve cross-platform tracking.
    """
    if not client.has_feature("query_gen"):
        return {}

    # Summarize hop-1 findings for the LLM
    platform_summaries = {}
    for item in hop1_items[:80]:
        pl = item.platform
        if pl not in platform_summaries:
            platform_summaries[pl] = []
        if len(platform_summaries[pl]) < 15:
            platform_summaries[pl].append(f"[{pl}] {item.title[:60]}")

    summaries_text = "\n".join(
        f"\n{pl} ({len(items)} items):\n" + "\n".join(items)
        for pl, items in platform_summaries.items()
    )

    system = """You are analyzing Hop-1 search results to decide what to chase in Hop-2.

Your job: identify 3-5 EMERGING topics, debates, or events from these results that deserve CROSS-PLATFORM tracking.

Think about:
- What topic appeared on ONE platform but would have interesting discussions on OTHERS?
- Is there a breaking event/release/controversy that multiple communities would react to differently?
- What unexpected connection between items could lead to fascinating content?

For each topic, generate 1-2 search queries per platform (bilibili in Chinese, reddit/github in English).

Output JSON:
{
  "bilibili": ["query1", "query2", ...],
  "github": ["query1", ...],
  "reddit": ["query1", "query2", ...]
}

Max 3-4 queries per platform. Quality over quantity. ONLY JSON."""

    result = client._call(
        model=client.model_batch, system=system,
        user_msg=f"Hop-1 results:\n{summaries_text}",
        max_tokens=500, temperature=0.7,
    )

    if result:
        try:
            cleaned = re.sub(r'^```(?:json)?\s*', '', result.strip())
            cleaned = re.sub(r'\s*```$', '', cleaned)
            queries = json.loads(cleaned)
            if isinstance(queries, dict):
                valid = {}
                for ch, qs in queries.items():
                    if isinstance(qs, list):
                        valid[ch] = [q.strip() for q in qs if isinstance(q, str) and q.strip()][:5]
                if valid:
                    total = sum(len(v) for v in valid.values())
                    console.print(f"  [magenta]🧠 LLM Hop-2: {total} chase queries[/magenta]")
                    return valid
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


# ═══════════════════════════════════════════════════════════════
# 2. BATCH CATEGORIZATION
# ═══════════════════════════════════════════════════════════════

def categorize_items(client: LLMClient, items: list[FeedItem]) -> list[FeedItem]:
    """LLM-powered batch categorization. Falls back to rule-based."""
    if not client.has_feature("categorize"):
        return items

    # Only categorize items that are "Other" or uncategorized
    to_categorize = [it for it in items if not it.category or it.category == "Other"]
    if not to_categorize:
        return items

    system = """Categorize each content item into exactly ONE category.
Categories: Research, Tech, Food, News, Campus, Career, Life, Other

Output JSON array matching input order: ["Research", "Tech", ...]
ONLY the JSON array, nothing else."""

    batch_size = client.batch_size
    categorized = 0

    for i in range(0, len(to_categorize), batch_size):
        batch = to_categorize[i:i + batch_size]
        items_text = "\n".join(
            f"{j+1}. [{it.platform}] {it.title[:80]} | {it.content[:60]}"
            for j, it in enumerate(batch)
        )

        result = client._call(
            model=client.model_batch,
            system=system,
            user_msg=items_text,
            max_tokens=200,
            temperature=0.1,
        )

        if result:
            try:
                cleaned = re.sub(r'^```(?:json)?\s*', '', result.strip())
                cleaned = re.sub(r'\s*```$', '', cleaned)
                categories = json.loads(cleaned)
                if isinstance(categories, list):
                    for j, cat in enumerate(categories):
                        if j < len(batch) and isinstance(cat, str):
                            valid_cats = {"Research", "Tech", "Food", "News", "Campus", "Career", "Life", "Other"}
                            if cat in valid_cats:
                                batch[j].category = cat
                                categorized += 1
            except (json.JSONDecodeError, KeyError):
                pass

    if categorized:
        console.print(f"  [magenta]🧠 LLM categorized {categorized} items[/magenta]")

    return items


# ═══════════════════════════════════════════════════════════════
# 3. ONE-LINE SUMMARIES
# ═══════════════════════════════════════════════════════════════

def summarize_items(client: LLMClient, items: list[FeedItem]) -> list[FeedItem]:
    """Generate compelling one-line summaries for content-heavy items."""
    if not client.has_feature("summarize"):
        return items

    # Only summarize items with substantial content
    to_summarize = [it for it in items if len(it.content) > 100 and not it.summary]
    if not to_summarize:
        return items

    system = """Generate a compelling one-line summary (15-30 chars) for each item.
The summary should make someone want to click. Be specific, not generic.
Mix Chinese and English naturally based on the content language.

Output JSON array of strings matching input order: ["summary1", "summary2", ...]
ONLY the JSON array."""

    batch_size = client.batch_size
    summarized = 0

    for i in range(0, min(len(to_summarize), 60), batch_size):  # Cap at 60 items
        batch = to_summarize[i:i + batch_size]
        items_text = "\n".join(
            f"{j+1}. [{it.platform}] {it.title[:60]} — {it.content[:150]}"
            for j, it in enumerate(batch)
        )

        result = client._call(
            model=client.model_batch,
            system=system,
            user_msg=items_text,
            max_tokens=500,
            temperature=0.5,
        )

        if result:
            try:
                cleaned = re.sub(r'^```(?:json)?\s*', '', result.strip())
                cleaned = re.sub(r'\s*```$', '', cleaned)
                summaries = json.loads(cleaned)
                if isinstance(summaries, list):
                    for j, summary in enumerate(summaries):
                        if j < len(batch) and isinstance(summary, str):
                            batch[j].summary = summary.strip()
                            summarized += 1
            except (json.JSONDecodeError, KeyError):
                pass

    if summarized:
        console.print(f"  [magenta]🧠 LLM summarized {summarized} items[/magenta]")

    return items


# ═══════════════════════════════════════════════════════════════
# 4. RECOMMENDATION REASONS
# ═══════════════════════════════════════════════════════════════

def generate_reasons(client: LLMClient, items: list[FeedItem], config: Config) -> list[FeedItem]:
    """Generate personalized recommendation reasons for top items."""
    if not client.has_feature("recommend_reason"):
        return items

    # Only top 30 items
    to_reason = [it for it in items[:30] if not it.recommend_reason]
    if not to_reason:
        return items

    profile = config.profile
    interests_str = ", ".join(t.topic for t in profile.interests)

    system = f"""Generate a short, personalized recommendation reason for each content item.
The user is: {profile.name}, {profile.identity} at {profile.location}.
Their interests: {interests_str}.

Reasons should be specific and personal, like:
- "你关注的 RLVR 方向，DeepSeek 新工作"
- "合肥本地探店，离科大很近"
- "Trending on r/LocalLLaMA"
- "你star过类似项目"

Keep each reason under 30 chars. Mix zh/en naturally.
Output JSON array of strings: ["reason1", "reason2", ...]
ONLY the JSON array."""

    items_text = "\n".join(
        f"{j+1}. [{it.platform}] {it.title[:60]} | cat:{it.category} | tags:{','.join(it.tags[:3])}"
        for j, it in enumerate(to_reason)
    )

    result = client._call(
        model=client.model_batch,
        system=system,
        user_msg=items_text,
        max_tokens=800,
        temperature=0.6,
    )

    if result:
        try:
            cleaned = re.sub(r'^```(?:json)?\s*', '', result.strip())
            cleaned = re.sub(r'\s*```$', '', cleaned)
            reasons = json.loads(cleaned)
            if isinstance(reasons, list):
                applied = 0
                for j, reason in enumerate(reasons):
                    if j < len(to_reason) and isinstance(reason, str):
                        to_reason[j].recommend_reason = reason.strip()
                        applied += 1
                if applied:
                    console.print(f"  [magenta]🧠 LLM generated {applied} recommend reasons[/magenta]")
        except (json.JSONDecodeError, KeyError):
            pass

    return items


# ═══════════════════════════════════════════════════════════════
# USAGE REPORTING
# ═══════════════════════════════════════════════════════════════
# 5. DYNAMIC TOPIC TAGS — replace static category pills
# ═══════════════════════════════════════════════════════════════

def generate_topic_tags(client: LLMClient, items: list[FeedItem]) -> list[str]:
    """Generate 5-8 dynamic topic tags from current feed content.

    Instead of static categories (Research, Tech, Food...),
    analyze actual content and produce specific, timely topic labels.
    Examples: "RLVR突破", "开源工具", "求职面经", "本地探店"
    """
    if not client.has_feature("categorize"):
        return []

    # Send top 50 item titles to LLM
    sample = items[:50]
    titles = "\n".join(f"{i+1}. [{it.platform}] {it.title[:60]}" for i, it in enumerate(sample))

    system = """Analyze these content items and generate 5-8 topic tags that best describe the main themes.

Rules:
- Tags should be SPECIFIC and TIMELY, not generic categories
- Mix Chinese and English naturally based on content
- Each tag: 2-6 characters (concise)
- Good: "LLM推理", "开源工具", "求职秋招", "本地美食"
- Bad: "Technology", "Research", "Other" (too generic)

Output JSON array of strings: ["tag1", "tag2", ...]
ONLY the JSON array."""

    result = client._call(
        model=client.model_batch, system=system,
        user_msg=titles, max_tokens=200, temperature=0.5,
    )
    if result:
        try:
            cleaned = re.sub(r'^```(?:json)?\s*', '', result.strip())
            cleaned = re.sub(r'\s*```$', '', cleaned)
            tags = json.loads(cleaned)
            if isinstance(tags, list) and len(tags) >= 2:
                tags = [t.strip() for t in tags if isinstance(t, str) and t.strip()][:10]
                console.print(f"  [magenta]🧠 LLM generated {len(tags)} topic tags[/magenta]")
                return tags
        except (json.JSONDecodeError, KeyError):
            pass
    return []


def tag_items_with_topics(client: LLMClient, items: list[FeedItem], topics: list[str]) -> list[FeedItem]:
    """Assign 1-2 matching topic tags to each item from the generated list."""
    if not topics or not client.has_feature("categorize"):
        return items

    batch_size = client.batch_size
    tagged = 0

    for i in range(0, min(len(items), 100), batch_size):
        batch = items[i:i + batch_size]
        items_text = "\n".join(
            f"{j+1}. [{it.platform}] {it.title[:60]}"
            for j, it in enumerate(batch)
        )
        topic_list = ", ".join(f'"{t}"' for t in topics)

        system = f"""Assign 1-2 topic tags to each item from this list: [{topic_list}]

If no tag fits well, use empty array.
Output JSON array of arrays: [["tag1"], ["tag1", "tag2"], [], ...]
Match input order. ONLY the JSON array."""

        result = client._call(
            model=client.model_batch, system=system,
            user_msg=items_text, max_tokens=400, temperature=0.1,
        )
        if result:
            try:
                cleaned = re.sub(r'^```(?:json)?\s*', '', result.strip())
                cleaned = re.sub(r'\s*```$', '', cleaned)
                assignments = json.loads(cleaned)
                if isinstance(assignments, list):
                    for j, tags in enumerate(assignments):
                        if j < len(batch) and isinstance(tags, list):
                            batch[j].topic_tags = [t for t in tags if isinstance(t, str) and t in topics]
                            if batch[j].topic_tags:
                                tagged += 1
            except (json.JSONDecodeError, KeyError):
                pass

    if tagged:
        console.print(f"  [magenta]🧠 LLM tagged {tagged} items with topics[/magenta]")
    return items


# ═══════════════════════════════════════════════════════════════
# 6. LLM CLUSTERING — replace broken Jaccard similarity
# ═══════════════════════════════════════════════════════════════

def cluster_items_llm(client: LLMClient, items: list[FeedItem]) -> list:
    """Use LLM to identify topic clusters across items.

    Returns list of dicts: [{"topic": "...", "item_indices": [0, 3, 7]}, ...]
    """
    if not client.has_feature("categorize"):
        return []

    sample = items[:40]
    titles = "\n".join(f"{i+1}. [{it.platform}] {it.title[:60]}" for i, it in enumerate(sample))

    system = """Identify groups of items that discuss the SAME topic or event.
Only group items that are clearly about the same thing (not just same category).
Minimum 2 items per group. Return 0-5 groups.

Output JSON array: [{"topic": "short topic name", "items": [1, 3, 7]}, ...]
Item numbers are 1-indexed matching input. ONLY the JSON array."""

    result = client._call(
        model=client.model_batch, system=system,
        user_msg=titles, max_tokens=400, temperature=0.2,
    )
    if result:
        try:
            cleaned = re.sub(r'^```(?:json)?\s*', '', result.strip())
            cleaned = re.sub(r'\s*```$', '', cleaned)
            groups = json.loads(cleaned)
            if isinstance(groups, list):
                from .models import TopicCluster
                clusters = []
                for g in groups:
                    if not isinstance(g, dict):
                        continue
                    topic = g.get("topic", "")
                    indices = g.get("items", [])
                    if len(indices) < 2 or not topic:
                        continue
                    cluster = TopicCluster(cluster_id=f"llm_{len(clusters)}", topic=topic)
                    for idx in indices:
                        real_idx = int(idx) - 1
                        if 0 <= real_idx < len(sample):
                            cluster.add(sample[real_idx])
                    if len(cluster.items) >= 2:
                        for it in cluster.items:
                            it.cluster_id = cluster.cluster_id
                        clusters.append(cluster)
                if clusters:
                    console.print(f"  [magenta]🧠 LLM found {len(clusters)} topic clusters[/magenta]")
                return clusters
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    return []


# ═══════════════════════════════════════════════════════════════
# USAGE REPORTING
# ═══════════════════════════════════════════════════════════════

def report_usage():
    """Print token usage summary."""
    if _session_tokens["calls"] > 0:
        total = _session_tokens["input"] + _session_tokens["output"]
        console.print(
            f"  [dim]🧠 LLM: {_session_tokens['calls']} calls, "
            f"{_session_tokens['input']}in + {_session_tokens['output']}out = "
            f"{total} tokens[/dim]"
        )


def reset_usage():
    """Reset token counter for new fetch cycle."""
    _session_tokens["input"] = 0
    _session_tokens["output"] = 0
    _session_tokens["calls"] = 0
