"""Multi-tier query builder — precise + broad + cognitive + trending.

5 tiers of queries per channel:
  30% precise   (high-confidence interest match)
  20% broad     (medium-confidence, wider net)
  20% cognitive (lateral/serendipity from cognitive expansion)
  15% trending  (hot topics, serendipity)
  15% collaborative (profile-based "people like you also search")
"""

from __future__ import annotations
import re
import random
from typing import Optional

from .config import Config
from .profile import get_profile
from .cognitive_expand import get_all_expanded_keywords, expand_keywords


# ── Ad/spam patterns ──
AD_PATTERNS = [
    r"加[微v]", r"免费领", r"限时\d", r"优惠券", r"点击购买",
    r"淘宝|拼多多|带货", r"9\.9元", r"薅羊毛", r"置顶.*广告",
    r"sponsored", r"promoted", r"\bad\b", r"affiliate link",
]
AD_RE = re.compile("|".join(AD_PATTERNS), re.IGNORECASE)

def is_spam(title: str, content: str = "") -> bool:
    return bool(AD_RE.search(f"{title} {content}"))


def build_smart_queries(config: Config) -> dict[str, list[str]]:
    """Build diverse, high-volume queries with cognitive expansion."""
    profile_data = get_profile()
    profile = config.profile

    # ── Tier 1: Profile keywords (precise + broad) ──
    precise = profile_data.get("keywords_precise", [])
    broad = profile_data.get("keywords_broad", [])
    trending = profile_data.get("keywords_trending", [])
    location = config.profile.location or ""

    # ── Tier 2: Cognitive expansion ──
    cog = expand_keywords(
        seed_interests=list(profile_data.get("explicit_interests", {}).keys()),
        identity_tags=["AI研究生", "USTC学生", "技术宅", "影迷", "足球迷",
                       "视频创作者", "公开课学习者"],
    )
    cog_precise = cog["precise"]      # Same-domain deep dive
    cog_lateral = cog["lateral"]      # Adjacent domain leaps
    cog_serendipity = cog["serendipity"]  # Anti-bubble surprises
    cog_collab = cog["collaborative"]     # Profile-based

    # Shuffle for variety each run
    random.shuffle(broad)
    random.shuffle(trending)
    random.shuffle(cog_lateral)
    random.shuffle(cog_serendipity)
    random.shuffle(cog_collab)

    queries: dict[str, list[str]] = {}

    for ch_name in config.enabled_channels():
        ch_q = []

        if ch_name in ("rss", "v2ex"):
            continue

        elif ch_name == "github":
            # GitHub: English tech terms + cognitive expansions
            en_precise = [t for t in precise if _is_en(t) and _is_tech(t)]
            en_broad = [t for t in broad if _is_en(t)]
            en_cog = [t for t in cog_precise + cog_lateral if _is_en(t)]
            ch_q = (en_precise[:3] + en_broad[:2] +
                    en_cog[:2] +
                    _pick(trending, 1, en_only=True))
            ch_q = ch_q[:8]

        elif ch_name == "reddit":
            # Reddit: English only, inject lateral/serendipity
            en_precise = [t for t in precise if _is_en(t)]
            en_cog_lat = [t for t in cog_lateral if _is_en(t)]
            en_cog_ser = [t for t in cog_serendipity if _is_en(t)]
            ch_q = (en_precise[:3] +
                    en_cog_lat[:2] +
                    en_cog_ser[:1] +
                    _pick(trending, 1, en_only=True) +
                    _pick(broad, 1, en_only=True))
            ch_q = ch_q[:8]

        elif ch_name == "bilibili":
            # Bilibili: Chinese cognitive expansions + life interests
            zh_precise = [t for t in precise if _has_zh(t)] or [t for t in precise[:3]]
            zh_cog = [t for t in cog_precise + cog_lateral if _has_zh(t)]
            zh_collab = [t for t in cog_collab if _has_zh(t)]
            zh_trending = [t for t in trending if _has_zh(t)]
            # Life interests from bilibili favorites (non-tech diversity)
            life_interests = _get_bilibili_life_queries(profile_data)
            ch_q = (zh_precise[:2] +
                    zh_cog[:2] +
                    life_interests[:2] +  # Film/doc/football etc.
                    zh_collab[:1] +
                    zh_trending[:1])
            # Ensure some core terms
            core_zh = ["大模型最新", "AI工具推荐"]
            for c in core_zh:
                if c not in ch_q and len(ch_q) < 12:
                    ch_q.append(c)
            ch_q = ch_q[:12]

        elif ch_name == "xhs":
            # XHS: lifestyle-heavy, cognitive serendipity + bilibili life interests
            ch_q = []
            if location:
                ch_q = [f"{location} 美食", f"{location} 探店"]
            # Cognitive: scenario-based life expansions
            zh_lat = [t for t in cog_lateral if _has_zh(t)]
            zh_ser = [t for t in cog_serendipity if _has_zh(t)]
            zh_collab = [t for t in cog_collab if _has_zh(t)]
            # Life interests from bilibili favorites
            life = _get_bilibili_life_queries(profile_data)
            xhs_life = [q for q in life if _has_zh(q)]
            ch_q.extend(zh_lat[:1])
            ch_q.extend(xhs_life[:1])
            ch_q.extend(zh_ser[:1])
            ch_q.extend(zh_collab[:1])
            ch_q = ch_q[:7]

        else:
            ch_q = (precise[:3] +
                    _pick(cog_lateral, 2) +
                    _pick(trending, 2) +
                    _pick(cog_serendipity, 1))

        # Deduplicate
        seen = set()
        deduped = []
        for q in ch_q:
            ql = q.lower().strip()
            if ql and ql not in seen:
                seen.add(ql)
                deduped.append(q)

        if deduped:
            queries[ch_name] = deduped

    return queries


def _pick(pool: list[str], n: int, en_only: bool = False) -> list[str]:
    """Pick n random items from pool."""
    if en_only:
        pool = [t for t in pool if _is_en(t)]
    return pool[:n]


def _is_tech(kw: str) -> bool:
    signals = ["ai", "llm", "model", "agent", "code", "python", "rust", "ml",
               "deep", "machine", "推理", "模型", "开源", "rlvr", "safety",
               "reasoning", "rl", "reinforcement", "transformer", "diffusion",
               "neural", "大模型", "智能体", "mcp", "recommendation", "rlhf",
               "rag", "embedding", "quantization", "fine-tune", "lora",
               "benchmark", "dataset", "training", "inference",
               "alignment", "reward", "planning", "tool use"]
    return any(s in kw.lower() for s in signals)


def _is_en(text: str) -> bool:
    return not bool(re.search(r'[\u4e00-\u9fff]', text))


def _has_zh(text: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def _get_bilibili_life_queries(profile_data: dict) -> list[str]:
    """Extract life/culture search queries from bilibili favorites behavioral data.
    
    These are non-tech interests discovered from B站 favorites:
    film, documentary, football, short films, video editing, etc.
    """
    behavioral = profile_data.get("behavioral_interests", {})
    life_queries = []

    # Map behavioral topics to good search queries (rotated each run)
    LIFE_QUERY_MAP = {
        "电影": ["高分文艺片推荐", "导演深度解析", "经典电影混剪", "电影摄影 构图"],
        "纪录片": ["高分纪录片 2026", "人文纪录片 推荐", "BBC NHK 纪录片"],
        "足球": ["英超 精彩集锦", "足球 战术分析", "世界杯 经典"],
        "短片": ["获奖短片 推荐", "独立短片", "电影学院 短片"],
        "视频剪辑": ["剪辑 创意转场", "混剪 教程", "调色 思路"],
        "作者电影": ["作者电影 大师", "王家卫 侯孝贤", "电影手册 推荐"],
        "公开课": ["MIT 公开课", "Stanford CS", "3Blue1Brown"],
        "影评": ["深度影评", "电影解说", "视听语言分析"],
        "独立电影": ["独立电影 院线", "戛纳 获奖", "威尼斯 金狮"],
    }

    for topic, queries in LIFE_QUERY_MAP.items():
        if topic in behavioral and behavioral[topic] >= 3:
            life_queries.extend(random.sample(queries, min(len(queries), 1)))

    random.shuffle(life_queries)
    return life_queries
