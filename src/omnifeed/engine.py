"""Core fetch engine — multi-hop retrieval with mix ratio control.

Content mix targets:
  ~40% Interest-aligned (profile search queries)
  ~20% Trending/popular (全站热门 per platform)
  ~20% Multi-hop (cross-platform topic chasing)
  ~10% Exploratory (serendipity, anti-bubble)
  ~10% XHS/lifestyle (location-based discovery)
"""

from __future__ import annotations
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import Counter

from rich.console import Console

from .models import FeedItem, FeedResult
from .config import Config
from .channels.base import ChannelRegistry
from .processor import dedup, categorize_batch, cluster_topics, filter_items
from .ranker import rank_items
from .query_builder import build_smart_queries

console = Console()

# Ensure all channels are imported / registered
from .channels import v2ex, github, reddit, rss  # noqa: F401
try:
    from .channels import bilibili  # noqa: F401
except Exception:
    pass
try:
    from .channels import xhs  # noqa: F401
except Exception:
    pass


def _extract_hop2_queries(items: list[FeedItem], existing: set[str], max_q: int = 8) -> list[str]:
    """Multi-hop query expansion from hop-1 results.
    
    Strategy:
      1. Term frequency extraction from top items (basic)
      2. Cross-platform gap detection (what platform X has that Y doesn't)
      3. Granularity variation (broad → specific, specific → broad)
      4. Style shift (tutorial → opinion, news → deep dive)
    """
    import re
    if not items:
        return []

    # Analyze top items
    top_items = sorted(items, key=lambda x: x._score, reverse=True)[:50]
    texts = [f"{it.title} {' '.join(it.tags)}" for it in top_items]
    combined = " ".join(texts).lower()

    stop = {"the","a","an","is","are","was","were","be","been","have","has","had",
            "do","does","did","will","would","could","should","may","might","can",
            "to","of","in","for","on","with","at","by","from","as","into","about",
            "and","or","but","not","this","that","it","its","my","your","his","her",
            "we","they","i","you","he","she","what","how","why","when","where",
            "new","best","top","how","get","use","using","make","just","like",
            "really","very","good","great","need","want","know","think","look",
            "的","了","是","在","我","有","和","就","不","人","都","一","这","上",
            "也","到","说","会","着","没有","你","他","她","们","个","里","些",
            "还","吧","吗","什么","怎么","可以","能","要","让","把","被","最",
            "从","很","最新","全套","教程","入门","实战","手把手","零基础",
            "最新版","干货","无废话","必看","全程","最全","最细","最详细",
            "保姆级","小白","学完","即就","弯路","全面","完整","系统",
            "收藏","一看就","轻松","带你","分钟","小时","天学",
            "整理","合集","汇总","盘点","推荐","总结","指南","攻略",
            "免费","付费","课程","视频","资料","笔记","思维导图",
            "黑马程序","一套全解","仁义礼智","全面解析","企业级",
            "全栈","一周学完","快速入门","包会","就够了","看这个",
            "不看后悔","建议收藏","强烈推荐","值得一看","必学"}

    # Quality filter: hop2 terms must look like real topics, not clickbait fragments
    def _is_quality_term(term: str) -> bool:
        """Reject clickbait fragments and require meaningful content."""
        # Too short Chinese terms are usually fragments
        if re.fullmatch(r'[\u4e00-\u9fff]{2}', term):
            # 2-char Chinese: only keep known meaningful ones
            meaningful_2char = {"推理","模型","安全","学习","训练","优化","搜索",
                               "检索","生成","编码","量化","微调","评测","部署",
                               "调优","蒸馏","剪枝","注意","融合","对齐","强化"}
            return term in meaningful_2char
        # Reject terms that are just numbers or punctuation noise
        if re.fullmatch(r'[\d\s./-]+', term): return False
        # Reject if it's a sentence fragment (has particle/conjunction feel)
        fragment_patterns = r'^(的|了|着|过|在|把|被|给|对|让|向|从|和|与|或|但|而|却|虽|因|为)'
        if re.match(fragment_patterns, term): return False
        return True

    # ── Strategy 1: Frequency-based term extraction ──
    en_words = re.findall(r'[a-z][a-z-]+', combined)
    en_words = [w for w in en_words if w not in stop and len(w) > 2]
    bigrams = [f"{en_words[i]} {en_words[i+1]}" for i in range(len(en_words)-1)]
    zh_terms = re.findall(r'[\u4e00-\u9fff]{2,6}', combined)
    zh_terms = [t for t in zh_terms if t not in stop]

    counter = Counter(bigrams + zh_terms + en_words)
    existing_lower = {q.lower() for q in existing}

    freq_candidates = []
    for term, count in counter.most_common(40):
        if count < 2: break
        if term in existing_lower or any(term in eq for eq in existing_lower): continue
        if len(term) < 3: continue
        if not _is_quality_term(term): continue
        freq_candidates.append(term)

    # ── Strategy 2: Cross-platform gap ──
    # Find topics in one platform but not others → search on missing platforms
    platform_topics: dict[str, set] = {}
    for item in top_items:
        keywords = set(re.findall(r'[a-z]{3,}|[\u4e00-\u9fff]{2,4}', item.title.lower()))
        keywords -= stop
        platform_topics.setdefault(item.platform, set()).update(keywords)

    gap_candidates = []
    all_platforms = list(platform_topics.keys())
    for plat_a in all_platforms:
        for plat_b in all_platforms:
            if plat_a == plat_b: continue
            unique_to_a = platform_topics[plat_a] - platform_topics[plat_b]
            for term in unique_to_a:
                if len(term) > 3 and term not in existing_lower:
                    gap_candidates.append(term)

    gap_counter = Counter(gap_candidates)

    # ── Strategy 3: Granularity shift ──
    # Smarter: match language, add domain-specific qualifiers
    granularity = []
    for term in freq_candidates[:5]:
        is_zh = bool(re.search(r'[\u4e00-\u9fff]', term))
        if len(term.split()) == 1 and not is_zh:
            # English single word → add tech qualifier
            granularity.append(f"{term} benchmark")
            granularity.append(f"{term} paper")
        elif is_zh and len(term) <= 6:
            # Chinese term → add research qualifier
            granularity.append(f"{term} 最新进展")
            granularity.append(f"{term} 论文解读")
        elif len(term.split()) >= 2:
            # Multi-word → extract most meaningful word
            words = term.split()
            longest = max(words, key=len)
            if len(longest) > 3:
                granularity.append(longest)

    # ── Combine all strategies ──
    all_candidates = []
    # 40% frequency-based
    all_candidates.extend(freq_candidates[:max_q * 2 // 5])
    # 30% cross-platform gaps
    gap_top = [t for t, _ in gap_counter.most_common(max_q)]
    all_candidates.extend(gap_top[:max_q * 3 // 10])
    # 30% granularity variations
    all_candidates.extend(granularity[:max_q * 3 // 10])

    # Deduplicate against existing
    seen = set(existing_lower)
    result = []
    for c in all_candidates:
        cl = c.lower().strip()
        if cl not in seen and len(cl) > 2:
            seen.add(cl)
            result.append(c)
    
    # ── Strategy 4: Cognitive expansion injection ──
    # Pull in lateral/serendipity terms from cognitive engine that weren't in hop1
    from .cognitive_expand import expand_keywords
    top_tags = []
    for item in top_items[:20]:
        top_tags.extend(item.tags[:3])
    if top_tags:
        tag_counter = Counter(top_tags)
        top_tag_seeds = [t for t, _ in tag_counter.most_common(5)]
        cog = expand_keywords(top_tag_seeds)
        cog_terms = cog["lateral"][:3] + cog["serendipity"][:1]
        for ct in cog_terms:
            ctl = ct.lower()
            if ctl not in seen:
                seen.add(ctl)
                result.append(ct)

    return result[:max_q]


def _fetch_channel(ch_name: str, channel, queries: list[str], config: Config) -> tuple[list[FeedItem], list[FeedItem]]:
    """Fetch items: returns (search_items, trending_items) separately for ratio control."""
    search_items: list[FeedItem] = []
    trending_items: list[FeedItem] = []

    # XHS: fast homepage feed only (search is too slow)
    if ch_name == "xhs":
        trending_items = channel.trending(limit=40) if hasattr(channel, "trending") else []
        return search_items, trending_items

    # V2EX: node-based fetch — more nodes
    if ch_name == "v2ex" and hasattr(channel, "fetch_all"):
        search_items = channel.fetch_all(limit_per_node=8)
        return search_items, trending_items

    # Search queries (interest-aligned) — higher volume
    for kw in queries:
        results = channel.search(kw, limit=20)
        for item in results:
            item.query = kw
        search_items.extend(results)

    # Trending (popular/hot — diversity source) — higher volume
    if hasattr(channel, "trending"):
        trending_items = channel.trending(limit=25)

    # RSS feeds
    if ch_name == "rss" and config.profile.feeds:
        for feed_cfg in config.profile.feeds:
            search_items.extend(channel.fetch_feed(feed_cfg.url, feed_cfg.name, limit=10))

    return search_items, trending_items


def fetch(config: Config, channels: Optional[list[str]] = None, dry_run: bool = False, hops: int = 2) -> FeedResult:
    """
    Multi-hop fetch with mix ratio control.

    Hop 1: Profile queries + trending per platform
    Hop 2: Cross-platform topic chasing from hop-1 results
    Final: merge all → dedup → filter → categorize → rank (with diversity)
    """
    from pathlib import Path
    profile_path = Path("~/.omnifeed/profile.json").expanduser()
    if not profile_path.exists() and not dry_run:
        console.print("  [dim]First run — building your interest profile...[/dim]")
        try:
            from .profile import build_deep_profile
            build_deep_profile()
        except Exception:
            pass

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)

    enabled = channels or config.enabled_channels()

    # ── LLM-powered query generation ──
    llm_client = None
    llm_queries = None
    if config.ai_enabled:
        from .llm import LLMClient, generate_search_queries, reset_usage
        reset_usage()
        llm_client = LLMClient(config)
        console.print("  [dim]🧠 LLM query generation...[/dim]")
        llm_queries = generate_search_queries(llm_client, config)

    # Use LLM queries if available, fall back to rule-based
    if llm_queries:
        queries = llm_queries
    else:
        queries = build_smart_queries(config)

    if dry_run:
        console.print("\nQuery Plan (dry run)\n")
        for ch, kws in queries.items():
            if ch in enabled:
                console.print(f"  [cyan]{ch}[/cyan]: {', '.join(kws)}")
        return FeedResult(generated_at=now.isoformat())

    # ── Pre-fetch: sync interaction history ──
    from .interaction_sync import sync_interactions_from_file
    sync_interactions_from_file()

    console.print(f"\nOmniFeed — {len(enabled)} channels, {hops}-hop\n")

    # Separate buckets for ratio control
    search_all: list[FeedItem] = []      # Interest-aligned
    trending_all: list[FeedItem] = []    # Popular/hot
    hop2_all: list[FeedItem] = []        # Multi-hop
    stats: dict[str, int] = {}
    channel_instances: dict[str, object] = {}
    all_queried: set[str] = set()

    # ── Hop 1 ──
    console.print("  [dim]Hop 1[/dim]")
    for ch_name in enabled:
        ch_config = config.channels.get(ch_name)
        channel = ChannelRegistry.create(ch_name, ch_config)
        if not channel:
            continue
        channel_instances[ch_name] = channel

        console.print(f"    {channel.icon} {channel.display_name} ", end="")
        try:
            ch_queries = queries.get(ch_name, [])
            all_queried.update(ch_queries)
            s_items, t_items = _fetch_channel(ch_name, channel, ch_queries, config)
            search_all.extend(s_items)
            trending_all.extend(t_items)
            total = len(s_items) + len(t_items)
            stats[ch_name] = total
            detail = f"({len(s_items)}s+{len(t_items)}t)" if t_items else f"{len(s_items)}"
            console.print(f"[green]{detail}[/green]")
        except Exception as e:
            stats[ch_name] = 0
            console.print(f"[red]{e}[/red]")

    console.print(f"  [dim]  → {len(search_all)} search + {len(trending_all)} trending[/dim]")

    # ── Quick rank for hop-2 topic extraction ──
    hop1_merged = dedup(search_all + trending_all)
    hop1_merged = categorize_batch(hop1_merged)
    hop1_merged = rank_items(hop1_merged, config.profile)

    # ── Hop 2: Cross-platform refinement ──
    if hops >= 2 and len(hop1_merged) > 10:
        hop2_queries = _extract_hop2_queries(hop1_merged, all_queried, max_q=8)
        if hop2_queries:
            console.print(f"  [dim]Hop 2: {hop2_queries}[/dim]")
            for ch_name, channel in channel_instances.items():
                if ch_name in ("v2ex", "rss", "xhs"):
                    continue
                console.print(f"    {channel.icon} {channel.display_name} ", end="")
                try:
                    h2_items = []
                    for kw in hop2_queries[:4]:  # 4 queries per channel
                        results = channel.search(kw, limit=10)
                        for item in results:
                            item.query = f"hop2:{kw}"
                        h2_items.extend(results)
                    hop2_all.extend(h2_items)
                    stats[ch_name] = stats.get(ch_name, 0) + len(h2_items)
                    console.print(f"[green]+{len(h2_items)}[/green]")
                except Exception:
                    console.print("[dim]skip[/dim]")

    # ── Merge with source tagging ──
    for item in search_all:
        item.source_type = "search"
    for item in trending_all:
        item.source_type = "trending"
    for item in hop2_all:
        item.source_type = "hop2"

    all_items = search_all + trending_all + hop2_all

    # ── Final processing ──
    all_items = dedup(all_items)
    all_items = filter_items(all_items, max_age_hours=168)

    # LLM-powered processing (falls back to rule-based)
    if llm_client and config.ai_enabled:
        from .llm import categorize_items, summarize_items, generate_reasons, report_usage
        console.print("  [dim]🧠 LLM processing...[/dim]")
        all_items = categorize_items(llm_client, all_items)
        all_items = summarize_items(llm_client, all_items)

    # Rule-based categorization for anything LLM missed
    all_items = categorize_batch(all_items)
    all_items = rank_items(all_items, config.profile)

    # LLM recommendation reasons (after ranking, for top items)
    if llm_client and config.ai_enabled:
        all_items = generate_reasons(llm_client, all_items, config)
        report_usage()

    clusters = cluster_topics(all_items[:50])

    # ── Pool ──
    from .pool import pool_add, prerender_pages
    added = pool_add(all_items)
    output_dir = config.output.dir if hasattr(config, 'output') else "~/.omnifeed/output"
    n_pages = prerender_pages(all_items, output_dir, page_size=50)

    # ── Stats ──
    source_counts = Counter(it.source_type for it in all_items)
    result = FeedResult(
        generated_at=now.isoformat(),
        profile_name=config.profile.name,
        stats={
            "platforms": len([v for v in stats.values() if v > 0]),
            "raw_items": sum(stats.values()),
            "final_items": len(all_items),
            "clusters": len(clusters),
            "per_channel": stats,
            "hops": hops,
            "mix": dict(source_counts),
            "pool_added": added,
        },
        items=all_items,
        clusters=clusters,
    )

    console.print(f"\n  Pool: +{added} new, {n_pages} pages")
    console.print(f"  Mix: {dict(source_counts)}")
    console.print(f"  [bold green]Done: {len(all_items)} items[/bold green]\n")
    return result


def doctor(config: Config) -> None:
    from rich.table import Table
    console.print("\nOmniFeed Doctor\n")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Channel"); table.add_column("Status"); table.add_column("Auth")
    table.add_column("Latency"); table.add_column("Note")

    for name, klass in ChannelRegistry.all().items():
        ch_config = config.channels.get(name)
        channel = klass(ch_config)
        status = channel.health_check()
        enabled = config.channels.get(name, None)
        enabled_str = "+" if (enabled and enabled.enabled) else "-"
        table.add_row(
            f"{channel.icon} {channel.display_name} {enabled_str}",
            "[green]OK[/green]" if status.available else "[red]FAIL[/red]",
            "key" if status.auth_required else "free",
            f"{status.latency_ms}ms" if status.latency_ms else "-",
            status.error or "",
        )
    console.print(table)
