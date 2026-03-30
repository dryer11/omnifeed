"""Personalized ranking engine."""

from __future__ import annotations
import math
import re
from collections import Counter

from .models import FeedItem
from .config import UserProfile


def compute_relevance(item: FeedItem, profile: UserProfile, interaction_prefs: dict = None) -> float:
    """Compute relevance using ALL profile layers (0-1).
    
    Sources:
      1. Config interests (explicit, w=2-5) — highest trust
      2. Profile.json topics (GitHub Stars + inferred + expanded) — broad coverage
      3. Interaction history (clicks/favs) — short-term signals
    """
    from .profile import get_ranker_topics

    text = f"{item.title} {item.content[:300]} {' '.join(item.tags)}".lower()

    # ── Layer 1: Config explicit interests (40% of long-term) ──
    config_score = 0.0
    config_total = 0
    if profile.interests:
        for tag in profile.interests:
            config_total += tag.weight
            topic_lower = tag.topic.lower()
            if topic_lower in text:
                config_score += tag.weight
            else:
                words = topic_lower.split()
                matched = sum(1 for w in words if w in text)
                if words and matched > 0:
                    config_score += tag.weight * (matched / len(words)) * 0.5
    config_score = min(1.0, config_score / max(config_total, 1))

    # ── Layer 2: Profile.json deep topics (40% of long-term) ──
    profile_topics = get_ranker_topics()
    profile_score = 0.0
    if profile_topics:
        matched_weight = 0
        total_weight = sum(min(w, 10) for w in profile_topics.values())
        for topic, weight in profile_topics.items():
            if topic in text:
                matched_weight += min(weight, 10)
            else:
                # Partial word match for multi-word topics
                words = topic.split()
                if len(words) > 1:
                    wm = sum(1 for w in words if len(w) > 2 and w in text)
                    if wm > 0:
                        matched_weight += min(weight, 10) * (wm / len(words)) * 0.3
        profile_score = min(1.0, matched_weight / max(total_weight * 0.15, 1))

    # Location bonus
    if profile.location and profile.location.lower() in text:
        config_score = min(1.0, config_score + 0.15)

    # Blend config + profile
    long_term = 0.5 * config_score + 0.5 * profile_score

    # ── Layer 3: Interaction signals (30% blend when available) ──
    short_term = 0.0
    if interaction_prefs and interaction_prefs.get("total", 0) > 10:
        plat_prefs = interaction_prefs.get("platform_preference", {})
        total_clicks = sum(plat_prefs.values()) or 1
        plat_score = plat_prefs.get(item.platform, 0) / total_clicks

        cat_prefs = interaction_prefs.get("category_preference", {})
        total_cat = sum(cat_prefs.values()) or 1
        cat_score = cat_prefs.get(item.category, 0) / total_cat if item.category else 0

        tag_prefs = interaction_prefs.get("tag_affinity", {})
        tag_score = 0
        if item.tags and tag_prefs:
            matched = sum(tag_prefs.get(t.lower(), 0) for t in item.tags)
            max_tag = max(tag_prefs.values()) if tag_prefs else 1
            tag_score = min(1.0, matched / max(max_tag, 1))

        short_term = 0.4 * plat_score + 0.3 * cat_score + 0.3 * tag_score
        return 0.7 * long_term + 0.3 * short_term

    return long_term


def compute_freshness(item: FeedItem) -> float:
    """Freshness score: exponential decay over 48 hours (0-1)."""
    hours = item.age_hours
    if hours <= 0 or hours > 999:
        return 0.3  # Unknown age gets default
    return math.exp(-hours / 48)


# Platform-specific engagement caps for fair cross-platform comparison
PLATFORM_ENGAGEMENT_CAP = {
    "bilibili": 1_000_000,   # views dominate; 1M is already very popular
    "github": 5_000,         # 5k stars = very popular repo
    "reddit": 5_000,         # 5k upvotes = front-page level
    "v2ex": 200,             # V2EX is small; 200 is hot
    "xhs": 10_000,           # 10k likes = viral on XHS
    "twitter": 10_000,       # 10k likes = viral tweet
    "weibo": 50_000,         # Weibo has larger numbers
    "rss": 1_000,            # RSS has minimal engagement signals
}

# Clickbait penalty keywords — more matches = bigger penalty
CLICKBAIT_KEYWORDS = [
    "全套", "最全", "最细", "手把手", "零基础", "保姆级",
    "小白到大神", "七天学完", "包会", "一看就会", "从入门到精通",
    "全72集", "全集", "速成", "一学就会", "看完就会",
    "万字长文", "建议收藏", "赶紧收藏", "不看后悔", "必看",
    "吐血整理", "熬夜整理",
]


def compute_engagement(item: FeedItem, max_engagement: float = 10000) -> float:
    """Normalized engagement score (0-1), using per-platform caps."""
    raw = item.engagement.score
    if raw <= 0:
        return 0.0
    # Use platform-specific cap instead of global max
    cap = PLATFORM_ENGAGEMENT_CAP.get(item.platform, max_engagement)
    return min(1.0, math.log1p(raw) / math.log1p(cap))


def compute_clickbait_penalty(item: FeedItem) -> float:
    """Returns a multiplier (0.5-1.0). More clickbait keywords = lower multiplier."""
    title = item.title.lower()
    matches = sum(1 for kw in CLICKBAIT_KEYWORDS if kw in title)
    if matches == 0:
        return 1.0
    elif matches == 1:
        return 0.75
    elif matches == 2:
        return 0.6
    else:
        return 0.5


def rank_items(
    items: list[FeedItem],
    profile: UserProfile,
    weights: dict[str, float] | None = None,
) -> list[FeedItem]:
    """
    Score and rank with source-aware mix control.
    
    Weights:
    - relevance: 0.30 (profile match)
    - freshness: 0.25 (recency)
    - engagement: 0.25 (popularity signal — important for trending)
    - diversity: 0.20 (platform/category spread)
    """
    if not items:
        return []

    w = weights or {
        "relevance": 0.30,
        "freshness": 0.25,
        "engagement": 0.25,
        "diversity": 0.20,
    }

    for item in items:
        item.relevance = compute_relevance(item, profile)

        # Source-aware scoring: trending items get engagement boost
        source = item.source_type
        eng_weight = w["engagement"]
        rel_weight = w["relevance"]

        if source == "trending":
            # Trending: still score by engagement, but cap the boost
            # so they don't dominate over interest-matched content
            eng_weight *= 1.0  # No extra boost
            rel_weight *= 0.5  # Lower relevance bar (they don't need to match interests)
        elif source == "hop2":
            rel_weight *= 1.2

        # Per-platform engagement normalization (no global max)
        eng_score = compute_engagement(item)

        raw_score = (
            rel_weight * item.relevance +
            w["freshness"] * compute_freshness(item) +
            eng_weight * eng_score
        )

        # Apply clickbait penalty
        item._score = raw_score * compute_clickbait_penalty(item)

    items.sort(key=lambda x: x._score, reverse=True)
    items = diversify(items)

    for item in items[:40]:
        item.recommend_reason = _make_reason(item, profile)

    return items


def diversify(items: list[FeedItem], max_consecutive: int = 2, platform_cap_pct: float = 0.40) -> list[FeedItem]:
    """
    Re-order for diversity on multiple axes:
    - No >2 consecutive same platform
    - No >2 consecutive same category
    - No >3 consecutive same source (search/trending/hop2)
    - Interleave trending with interest content
    - Platform cap: no platform exceeds 40% of top 50
    """
    if len(items) <= 3:
        return items

    result: list[FeedItem] = []
    remaining = list(items)
    recent_plat: list[str] = []
    recent_cat: list[str] = []
    recent_source: list[str] = []
    platform_counts: Counter = Counter()
    top_n = min(50, len(items))  # Apply platform cap within top 50
    max_per_platform = max(3, int(top_n * platform_cap_pct))

    while remaining:
        best = None
        best_idx = -1

        for idx, item in enumerate(remaining):
            plat = item.platform
            cat = item.category
            source = item.source_type

            # Hard constraints
            plat_count = sum(1 for p in recent_plat[-max_consecutive:] if p == plat)
            cat_count = sum(1 for c in recent_cat[-max_consecutive:] if c == cat)
            source_count = sum(1 for s in recent_source[-3:] if s == source)

            if plat_count >= max_consecutive:
                continue
            if cat_count >= max_consecutive:
                continue
            if source_count >= 3:
                continue

            # Platform quota: within top N, no platform exceeds cap
            if len(result) < top_n and platform_counts[plat] >= max_per_platform:
                continue

            best = item
            best_idx = idx
            break

        if best is None:
            best = remaining[0]
            best_idx = 0

        result.append(best)
        recent_plat.append(best.platform)
        recent_cat.append(best.category)
        recent_source.append(best.source_type)
        platform_counts[best.platform] += 1
        remaining.pop(best_idx)

    return result


def _make_reason(item: FeedItem, profile: UserProfile) -> str:
    reasons = []

    text = f"{item.title} {item.content[:100]} {' '.join(item.tags)}".lower()
    for tag in sorted(profile.interests, key=lambda t: t.weight, reverse=True):
        if tag.topic.lower() in text:
            reasons.append(f"Matches \"{tag.topic}\"")
            break

    if profile.location and profile.location.lower() in text:
        reasons.append(f"Near {profile.location}")

    source = item.source_type
    if source == "trending":
        reasons.append("Trending")
    elif source == "hop2":
        reasons.append("Related topic")

    if item.engagement.score > 5000:
        reasons.append("Popular")
    if item.age_hours < 6:
        reasons.append("Just posted")

    return " · ".join(reasons[:3]) if reasons else ""
