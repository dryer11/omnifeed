"""Deep profile builder — mines OpenClaw context + multi-hop keyword expansion.

Layers:
  L0: Explicit interests (config.yaml, w=2-5)
  L1: Behavioral signals (GitHub Stars, interactions)
  L2: Contextual inference (USER.md, SOUL.md, memory, projects)
  L3: Multi-hop expansion (adjacent topics, cross-domain exploration)

The key insight: don't just search for what the user says they like.
Infer what they MIGHT like based on their identity, projects, and taste patterns.
A recommendation-systems researcher probably also cares about information retrieval,
A/B testing, causal inference, user modeling — none of which they explicitly stated.
"""

from __future__ import annotations
import json
import os
import re
import time
from pathlib import Path
from collections import Counter
from datetime import datetime, timedelta

import httpx

PROFILE_PATH = Path("~/.omnifeed/profile.json").expanduser()

# ── Multi-hop expansion graph ──
# For each seed topic, what adjacent topics should we explore?
# This is the "don't stay in the bubble" engine.
EXPANSION_GRAPH = {
    # Core AI
    "llm": ["prompt engineering", "tokenization", "context window", "inference optimization", "model serving"],
    "agent": ["tool use", "function calling", "planning", "multi-agent", "autonomous systems", "MCP"],
    "rl": ["reward modeling", "RLHF", "RLVR", "DPO", "PPO", "process reward", "outcome reward"],
    "reasoning": ["chain of thought", "tree of thought", "system 2 thinking", "math reasoning", "code reasoning"],
    "recommendation": ["collaborative filtering", "content-based filtering", "CTR prediction", "user modeling", "A/B testing", "cold start"],
    "rag": ["retrieval augmented generation", "vector database", "embedding", "chunking", "knowledge graph"],
    "safety": ["alignment", "red teaming", "jailbreak", "constitutional AI", "RLHF"],
    "diffusion": ["stable diffusion", "image generation", "video generation", "controlnet"],
    "transformer": ["attention mechanism", "positional encoding", "flash attention", "sparse attention"],

    # Broader tech
    "python": ["asyncio", "fastapi", "pydantic", "typing"],
    "open source": ["github trending", "new releases", "developer tools"],
    "quantization": ["GPTQ", "AWQ", "GGUF", "4-bit", "8-bit", "TurboQuant"],
    "fine-tune": ["LoRA", "QLoRA", "adapter", "instruction tuning", "SFT"],

    # Life / adjacent
    "合肥": ["合肥美食", "合肥探店", "合肥周末", "合肥咖啡", "科大周边"],
    "研究生": ["科研方法", "论文写作", "导师关系", "学术会议", "读博vs工作"],
    "ustc": ["中科大", "科大新闻", "合肥高新区"],

    # Cross-domain exploration (anti-bubble)
    "ai": ["AI ethics", "AI regulation", "AI startups", "AI art", "AI music"],
    "research": ["research methodology", "academic writing", "peer review", "reproducibility"],
    "deep-learning": ["neuroscience inspiration", "cognitive science", "brain-computer interface"],
}

# ── Identity-based inference ──
# Infer interests from who the user IS, not just what they stated
IDENTITY_INFERENCES = {
    "AI方向研究生": [
        ("论文阅读", 4), ("学术写作", 3), ("实验设计", 3),
        ("GPU集群", 2), ("数据标注", 2), ("benchmark", 3),
        ("顶会论文", 4), ("研究方法论", 3),
    ],
    "USTC": [
        ("中科大", 3), ("合肥", 3), ("科大新闻", 2),
    ],
    "25级研一": [
        ("新生指南", 2), ("课程选择", 3), ("研究方向选择", 3),
        ("开题准备", 2),
    ],
    "推荐系统": [
        ("信息检索", 4), ("用户画像", 3), ("点击率预测", 3),
        ("特征工程", 2), ("在线学习", 2), ("bandit算法", 3),
    ],
}


def build_deep_profile(github_user: str = "dryer11", force: bool = False) -> dict:
    """Build comprehensive multi-layer profile."""
    profile = {
        "initialized": True,
        "created_at": int(time.time()),
        "last_updated": int(time.time()),

        # L0: Explicit interests (high confidence)
        "explicit_interests": {},

        # L1: Behavioral (medium-high confidence)
        "behavioral_interests": {},

        # L2: Contextual inference (medium confidence)
        "inferred_interests": {},

        # L3: Expanded exploration (lower confidence, higher diversity)
        "exploration_topics": {},

        # Merged: all topics with final weights for ranker
        "topics": {},

        # Search keywords (粗+细)
        "keywords_precise": [],    # Precise: direct matches
        "keywords_broad": [],      # Broad: exploratory
        "keywords_trending": [],   # Trending: rotate each fetch

        # Metadata
        "languages": {},
        "sources_used": [],
    }

    # ── L0: Config interests ──
    config_path = Path("~/.omnifeed/config.yaml").expanduser()
    if config_path.exists():
        import yaml
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        for interest in cfg.get("profile", {}).get("interests", []):
            topic = interest.get("topic", "")
            weight = interest.get("weight", 3)
            if topic:
                profile["explicit_interests"][topic.lower()] = weight
        profile["sources_used"].append("config")

    # ── L1: GitHub Stars ──
    gh = _extract_github_stars(github_user)
    if gh:
        profile["behavioral_interests"] = gh["topics"]
        profile["languages"] = gh["languages"]
        profile["sources_used"].append("github_stars")

    # ── L1b: Bilibili Favorites ──
    bili_fav = _extract_bilibili_favorites()
    if bili_fav:
        for topic, weight in bili_fav.items():
            profile["behavioral_interests"][topic] = profile["behavioral_interests"].get(topic, 0) + weight
        profile["sources_used"].append("bilibili_favorites")

    # ── L2: OpenClaw deep context mining ──
    ctx = _mine_openclaw_deep()
    if ctx:
        profile["inferred_interests"] = ctx["inferred"]
        profile["sources_used"].append("openclaw_context")

    # ── L3: Multi-hop expansion ──
    seed_topics = set()
    for d in [profile["explicit_interests"], profile["behavioral_interests"], profile["inferred_interests"]]:
        seed_topics.update(d.keys())

    expanded = {}
    for seed in seed_topics:
        for base_topic, expansions in EXPANSION_GRAPH.items():
            if base_topic in seed.lower():
                for exp in expansions:
                    exp_lower = exp.lower()
                    if exp_lower not in seed_topics:
                        expanded[exp_lower] = expanded.get(exp_lower, 0) + 2
    profile["exploration_topics"] = expanded
    profile["sources_used"].append("multi_hop_expansion")

    # ── Merge all layers into final topics ──
    merged = {}
    # L0: Explicit — highest trust (multiply by 3.0)
    for t, w in profile["explicit_interests"].items():
        merged[t] = merged.get(t, 0) + w * 3.0
    # L1: Behavioral — high trust (multiply by 1.5, cap individual at 4)
    for t, w in profile["behavioral_interests"].items():
        merged[t] = merged.get(t, 0) + min(w, 4) * 1.5
    # L2: Inferred — medium trust (cap at 3)
    for t, w in profile["inferred_interests"].items():
        merged[t] = merged.get(t, 0) + min(w, 3) * 1.0
    # L3: Exploration — low trust, high diversity (flat weight)
    for t, w in profile["exploration_topics"].items():
        merged[t] = merged.get(t, 0) + 1.5

    # Normalize to 0-10
    max_w = max(merged.values()) if merged else 1
    for t in merged:
        merged[t] = round(min(10, merged[t] / max_w * 10), 1)

    profile["topics"] = merged

    # ── Generate keyword tiers ──
    sorted_topics = sorted(merged.items(), key=lambda x: x[1], reverse=True)

    # Precise: top weighted topics (direct interest match)
    profile["keywords_precise"] = [t for t, w in sorted_topics if w >= 5][:20]

    # Broad: medium topics + expanded (exploratory)
    profile["keywords_broad"] = [t for t, w in sorted_topics if 2 <= w < 5][:20]

    # Trending: curated current hot topics (rotated each fetch)
    profile["keywords_trending"] = _get_trending_keywords()

    # Save
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

    return profile


def _extract_github_stars(username: str) -> dict | None:
    try:
        all_repos = []
        for page in range(1, 4):
            r = httpx.get(f"https://api.github.com/users/{username}/starred",
                         params={"per_page": 30, "page": page},
                         headers={"User-Agent": "omnifeed"}, timeout=15)
            if r.status_code != 200: break
            repos = r.json()
            if not repos: break
            all_repos.extend(repos)
        if not all_repos: return None

        topics = Counter()
        languages = Counter()
        for repo in all_repos:
            for t in repo.get("topics", []):
                topics[t.lower()] += 1
            lang = repo.get("language", "")
            if lang: languages[lang] += 1
            desc = (repo.get("description") or "").lower()
            for kw in ["ai", "llm", "agent", "ml", "rl", "mcp", "recommendation",
                       "research", "rag", "reasoning", "safety"]:
                if kw in desc: topics[kw] += 1

        return {"topics": dict(topics.most_common(40)), "languages": dict(languages.most_common(10))}
    except Exception:
        return None


def _mine_openclaw_deep() -> dict | None:
    """Deep mine OpenClaw workspace for interest signals."""
    workspace = Path("~/.openclaw/workspace").expanduser()
    inferred = {}

    # USER.md — identity-based inference
    user_md = workspace / "USER.md"
    if user_md.exists():
        text = user_md.read_text()
        for trigger, inferences in IDENTITY_INFERENCES.items():
            if trigger.lower() in text.lower():
                for topic, weight in inferences:
                    inferred[topic.lower()] = max(inferred.get(topic.lower(), 0), weight)

    # Memory files — extract mentioned projects, tools, topics
    memory_dir = workspace / "memory"
    if memory_dir.exists():
        for days_ago in range(7):
            dt = datetime.now() - timedelta(days=days_ago)
            mem_file = memory_dir / f"{dt.strftime('%Y-%m-%d')}.md"
            if mem_file.exists():
                mem = mem_file.read_text()[:5000].lower()
                # Project names
                for match in re.findall(r'omnifeed|ustc.map|alpha.lab|alphalab', mem):
                    inferred[match] = inferred.get(match, 0) + 1
                # Tech terms
                for kw in ["mcp", "agent", "llm", "推荐", "检索", "爬虫", "前端", "canvas",
                           "github pages", "cron", "小红书", "bilibili"]:
                    if kw in mem:
                        inferred[kw] = inferred.get(kw, 0) + 2

    # SOUL.md — personality traits (what kind of content would they enjoy?)
    soul_md = workspace / "SOUL.md"
    if soul_md.exists():
        soul = soul_md.read_text().lower()
        if "resourceful" in soul or "figure it out" in soul:
            inferred["独立开发"] = 3
            inferred["工具推荐"] = 2
        if "opinions" in soul:
            inferred["科技评论"] = 2
            inferred["深度分析"] = 3

    return {"inferred": inferred} if inferred else None


def _get_trending_keywords() -> list[str]:
    """Current trending AI/tech topics — manually curated + dynamic."""
    base = [
        # 2026 hot topics
        "Claude 4", "GPT-5", "Gemini 2.5", "Llama 4",
        "vibe coding", "AI coding agent", "cursor vs claude code",
        "local LLM deployment", "AI safety regulation",
        "multi-agent systems", "reasoning models",
        "AI video generation", "voice AI",
        # Chinese hot
        "大模型评测", "国产大模型", "AI编程工具",
        "智能体开发", "RAG实战", "向量数据库",
    ]

    # Try to get bilibili hot search dynamically
    try:
        r = httpx.get("https://api.bilibili.com/x/web-interface/wbi/search/square",
                      params={"limit": 10},
                      headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        data = r.json()
        trending = data.get("data", {}).get("trending", {}).get("list", [])
        for t in trending[:5]:
            kw = t.get("keyword", "")
            if kw: base.append(kw)
    except Exception:
        pass

    return base


def get_profile() -> dict:
    if PROFILE_PATH.exists():
        with open(PROFILE_PATH) as f:
            return json.load(f)
    return build_deep_profile()


def get_ranker_topics() -> dict[str, float]:
    """Get merged topic weights for ranker use. Returns {topic: weight_0_to_10}."""
    p = get_profile()
    return p.get("topics", {})


def _extract_bilibili_favorites() -> dict[str, int] | None:
    """Deep-mine Bilibili favorites for interest signals.
    
    Reads folder names (strong signal) + video titles (behavioral signal).
    Returns topic→weight dict for profile integration.
    """
    cookie_path = Path("~/.omnifeed/bilibili_cookies.json").expanduser()
    if not cookie_path.exists():
        return None

    try:
        with open(cookie_path) as f:
            login_data = json.load(f)
        cookies = login_data.get("cookies", {})
        mid = cookies.get("DedeUserID", "")
        if not mid:
            return None

        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {"User-Agent": "Mozilla/5.0", "Cookie": cookie_str, "Referer": "https://www.bilibili.com/"}

        # Get favorite folders
        r = httpx.get(
            "https://api.bilibili.com/x/v3/fav/folder/created/list-all",
            params={"up_mid": mid}, headers=headers, timeout=10,
        )
        data = r.json()
        if data.get("code") != 0:
            return None

        folders = data.get("data", {}).get("list", [])
        if not folders:
            return None

        topics = Counter()

        # ── Folder names are strong signals ──
        FOLDER_TOPIC_MAP = {
            "深度学习": [("深度学习", 5), ("神经网络", 3), ("PyTorch", 3)],
            "LDS": [("大模型", 4), ("LLM", 4), ("AI编程", 3)],
            "408": [("计算机基础", 4), ("操作系统", 3), ("数据结构", 3), ("CSAPP", 3)],
            "考研": [("数学", 3), ("概率论", 2), ("线性代数", 2)],
            "短片": [("短片", 4), ("电影创作", 3), ("独立电影", 3)],
            "纪录": [("纪录片", 5), ("人文纪实", 3)],
            "学习": [("公开课", 3), ("在线学习", 2)],
            "足球": [("足球", 5), ("英超", 2), ("体育", 2)],
            "电影评论": [("电影", 5), ("影评", 4), ("作者电影", 3), ("文艺片", 3)],
            "混剪": [("视频剪辑", 4), ("混剪", 3), ("影视美学", 3)],
            "p系列": [("PR剪辑", 3), ("视频制作", 3)],
            "R": [("R语言", 2), ("数据分析", 2)],
        }
        for folder in folders:
            fname = folder["title"]
            count = folder["media_count"]
            # Weight by collection size
            size_boost = min(3, count // 20)
            for pattern, topic_list in FOLDER_TOPIC_MAP.items():
                if pattern.lower() in fname.lower():
                    for topic, base_w in topic_list:
                        topics[topic] += base_w + size_boost

        # ── Mine video titles from top 5 folders ──
        sorted_folders = sorted(folders, key=lambda f: f["media_count"], reverse=True)
        for folder in sorted_folders[:5]:
            fid = folder.get("id", "")
            if not fid: continue
            try:
                r2 = httpx.get(
                    "https://api.bilibili.com/x/v3/fav/resource/list",
                    params={"media_id": fid, "pn": 1, "ps": 20, "platform": "web"},
                    headers=headers, timeout=10,
                )
                medias = r2.json().get("data", {}).get("medias", [])
                if not medias: continue
                for media in medias:
                    title = (media.get("title") or "").lower()
                    # Tech keywords
                    for kw in ["transformer", "llm", "agent", "rag", "pytorch", "深度学习",
                               "机器学习", "强化学习", "attention", "diffusion", "大模型",
                               "人工智能", "neural", "iclr", "neurips", "icml", "aaai",
                               "mit", "stanford", "cmu", "hinton", "公开课"]:
                        if kw in title: topics[kw] += 2
                    # Life/culture keywords
                    for kw in ["纪录片", "电影", "足球", "短片", "混剪", "city", "旅行",
                               "音乐", "摄影", "建筑", "美食", "设计", "哲学"]:
                        if kw in title: topics[kw] += 1
            except Exception:
                continue

        return dict(topics) if topics else None
    except Exception:
        return None
