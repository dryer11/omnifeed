"""Content processing: dedup, categorize, cluster, filter."""

from __future__ import annotations
import re
import time
from collections import defaultdict

from .models import FeedItem, TopicCluster
from .query_builder import is_spam

# ── Category rules (expanded, more precise) ──
CATEGORY_RULES: dict[str, list[str]] = {
    "Research": [
        "论文", "paper", "arxiv", "neurips", "iclr", "icml", "acl", "aaai",
        "cvpr", "emnlp", "naacl", "模型", "训练", "推理", "reasoning",
        "scaling", "alignment", "rl", "rlhf", "rlvr", "dpo", "ppo",
        "transformer", "llm", "大模型", "agent", "benchmark", "dataset",
        "研究", "实验", "research", "preprint", "开源模型", "sota",
        "quantization", "量化", "蒸馏", "distillation", "fine-tune",
        "微调", "inference", "attention", "diffusion", "reinforcement",
        # Expanded
        "机器学习", "深度学习", "machine learning", "deep learning",
        "neural network", "神经网络", "自然语言处理", "nlp", "计算机视觉",
        "computer vision", "生成式", "generative", "gpt", "claude", "gemini",
        "llama", "mistral", "qwen", "deepseek", "chatgpt", "openai",
        "anthropic", "google ai", "多模态", "multimodal", "mllm",
        "embedding", "向量", "retrieval", "rag", "知识图谱",
        "knowledge graph", "预训练", "pretrain", "语义", "semantic",
        "自监督", "self-supervised", "对比学习", "contrastive",
        "强化学习", "reward model", "grounding", "分割", "detection",
        "segmentation", "recognition", "classification", "generation",
        "image generation", "text generation", "video generation",
        "speech", "语音", "tts", "asr", "tokenizer", "vocab",
        "prompt", "提示词", "in-context", "few-shot", "zero-shot",
        "chain of thought", "cot", "思维链", "科研", "学术",
        "survey", "综述", "review paper", "实验结果", "消融实验",
        "ablation", "baseline", "metric", "evaluation", "评估",
        "robustness", "泛化", "generalization", "可解释",
        "explainability", "interpretability",
    ],
    "Tech": [
        "github", "开源", "tutorial", "教程", "代码", "code", "python",
        "javascript", "rust", "docker", "linux", "api", "框架", "工具",
        "deploy", "部署", "debug", "bug", "编程", "programming",
        "前端", "后端", "数据库", "cloud", "devops", "cli",
        "library", "package", "npm", "pip", "cargo",
        # Expanded
        "react", "vue", "angular", "typescript", "golang", "java",
        "swift", "kotlin", "c++", "cpp", "cmake", "makefile",
        "git", "vscode", "vim", "neovim", "emacs", "ide",
        "terminal", "shell", "bash", "zsh", "powershell",
        "kubernetes", "k8s", "nginx", "redis", "mongodb", "mysql",
        "postgresql", "sqlite", "elasticsearch", "kafka",
        "microservice", "微服务", "serverless", "aws", "gcp", "azure",
        "terraform", "ansible", "ci/cd", "jenkins", "github actions",
        "开发者", "developer", "程序员", "码农", "技术栈",
        "架构", "architecture", "设计模式", "design pattern",
        "算法", "algorithm", "数据结构", "data structure",
        "开发工具", "效率工具", "workflow", "自动化", "automation",
        "爬虫", "crawler", "scraper", "网络", "network", "http",
        "websocket", "grpc", "protobuf", "sdk", "插件", "plugin",
        "extension", "chrome extension", "browser",
        "cuda", "gpu", "显卡", "pytorch", "tensorflow", "jax",
        "numpy", "pandas", "jupyter", "notebook", "colab",
        "huggingface", "gradio", "streamlit", "fastapi", "flask",
        "django", "spring", "开发", "development", "software",
        "app", "应用", "小程序", "wasm", "webassembly",
    ],
    "Food": [
        "美食", "探店", "奶茶", "火锅", "餐厅", "咖啡", "甜品",
        "好吃", "food", "restaurant", "cafe", "烤肉",
        "外卖", "食堂", "brunch", "下午茶", "烘焙", "菜谱",
    ],
    "News": [
        "通知", "公告", "招聘", "讲座", "报告", "活动", "比赛",
        "deadline", "announcement", "event", "seminar", "workshop",
        "招生", "实习", "offer", "发布", "release", "launch",
        "更新", "update", "版本",
        # Expanded
        "新闻", "news", "breaking", "头条", "热搜", "热点",
        "政策", "policy", "regulation", "法规", "规定",
        "融资", "funding", "收购", "acquisition", "ipo",
        "产品发布", "product launch", "feature", "changelog",
    ],
    "Campus": [
        "校园", "大学", "学校", "宿舍", "食堂", "图书馆", "考试",
        "选课", "gpa", "毕业", "保研", "考研", "科大", "ustc",
        "campus", "university", "研究生",
    ],
    "Career": [
        "求职", "面试", "面经", "薪资", "跳槽", "职场",
        "career", "interview", "salary", "intern",
        "秋招", "春招", "裁员", "layoff",
        # Expanded
        "简历", "resume", "cv", "hr", "offer", "工作",
        "远程", "remote", "自由职业", "freelance",
    ],
    "Life": [
        "旅行", "拍照", "约会", "周末", "运动", "健身",
        "穿搭", "护肤", "租房", "搬家", "日常",
        "travel", "life", "合肥", "打卡",
        # Expanded
        "生活", "vlog", "日记", "分享", "经验", "攻略",
        "购物", "装修", "家居", "数码", "手机", "电脑",
        "耳机", "键盘", "显示器", "gadget", "评测", "测评",
        "开箱", "unboxing",
    ],
}

# Emoji-to-English category mapping for legacy data
EMOJI_CATEGORY_MAP = {
    "📄 其他": "Other",
    "🔬 科研": "Research",
    "💻 技术": "Tech",
    "🍜 美食": "Food",
    "📰 资讯": "News",
    "🎓 校园": "Campus",
    "💼 职场": "Career",
    "🌿 生活": "Life",
    "📄 other": "Other",
    "🔬 research": "Research",
    "💻 tech": "Tech",
    "其他": "Other",
    "科研": "Research",
    "技术": "Tech",
    "美食": "Food",
    "资讯": "News",
    "校园": "Campus",
    "职场": "Career",
    "生活": "Life",
}

# Weight multipliers for category matching
CATEGORY_WEIGHTS = {
    "Research": 1.5,   # Boost research detection
    "Tech": 1.2,
    "Food": 1.0,
    "News": 1.0,
    "Campus": 1.0,
    "Career": 1.0,
    "Life": 0.8,
}


def categorize(item: FeedItem) -> str:
    """Rule-based categorization with weighted scoring."""
    text = f"{item.title} {item.content[:300]} {' '.join(item.tags)}".lower()
    scores: dict[str, float] = defaultdict(float)

    for category, keywords in CATEGORY_RULES.items():
        w = CATEGORY_WEIGHTS.get(category, 1.0)
        for kw in keywords:
            if kw.lower() in text:
                scores[category] += w

    if scores:
        best = max(scores, key=scores.get)
        if scores[best] >= 1.0:  # Minimum threshold
            return best
    return "Other"


def _normalize_category(cat: str) -> str:
    """Convert legacy emoji categories to English names."""
    if not cat:
        return ""
    # Direct mapping
    if cat in EMOJI_CATEGORY_MAP:
        return EMOJI_CATEGORY_MAP[cat]
    # Strip leading emoji and try again
    stripped = re.sub(r"^[\U0001F000-\U0001FFFF\u2600-\u27BF\uFE00-\uFE0F\u200D]+\s*", "", cat).strip()
    if stripped in EMOJI_CATEGORY_MAP:
        return EMOJI_CATEGORY_MAP[stripped]
    # Already a valid English category name
    valid_cats = set(CATEGORY_RULES.keys()) | {"Other"}
    if cat in valid_cats:
        return cat
    if stripped in valid_cats:
        return stripped
    return cat


def categorize_batch(items: list[FeedItem]) -> list[FeedItem]:
    for item in items:
        # First normalize any existing emoji category
        if item.category:
            item.category = _normalize_category(item.category)
        # Then categorize if empty or still "Other"
        if not item.category or item.category == "Other":
            new_cat = categorize(item)
            if new_cat != "Other" or not item.category:
                item.category = new_cat
    return items


def filter_items(items: list[FeedItem], max_age_hours: int = 168) -> list[FeedItem]:
    """Filter out spam/ads. Keep items up to 7 days old (168h).
    
    Lenient by design — diversity > purity. Only remove obvious spam.
    Items without timestamp are always kept.
    """
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - max_age_hours * 3600 * 1000
    result = []

    for item in items:
        # Skip obvious ads/spam only
        if is_spam(item.title, item.content):
            continue

        # Skip very old items (>7 days), but keep items with no timestamp
        if item.timestamp and 0 < item.timestamp < cutoff:
            continue

        result.append(item)

    return result


# ── Dedup ──

def dedup(items: list[FeedItem]) -> list[FeedItem]:
    seen_hashes: set[str] = set()
    seen_urls: set[str] = set()
    unique: list[FeedItem] = []

    for item in items:
        if item.url and item.url in seen_urls:
            continue
        h = item.content_hash
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        if item.url:
            seen_urls.add(item.url)
        unique.append(item)

    return unique


# ── Topic clustering ──

def _extract_keywords(text: str) -> set[str]:
    text = text.lower()
    text = re.sub(r"https?://\S+", "", text)
    tokens = re.findall(r"[\u4e00-\u9fff]+|[a-z]{3,}", text)
    stopwords = {"the", "and", "for", "with", "this", "that", "from", "are", "was",
                 "have", "has", "not", "but", "can", "will", "just", "about", "more",
                 "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
                 "一", "这", "上", "也", "到", "说", "会"}
    return {t for t in tokens if t not in stopwords and len(t) > 1}


def cluster_topics(items: list[FeedItem], threshold: float = 0.3) -> list[TopicCluster]:
    if not items:
        return []

    item_keywords = [(item, _extract_keywords(f"{item.title} {item.content[:200]}")) for item in items]
    clusters: list[TopicCluster] = []
    assigned: set[str] = set()

    for i, (item_a, kw_a) in enumerate(item_keywords):
        if item_a.id in assigned or not kw_a:
            continue
        cluster = TopicCluster(cluster_id=f"cluster_{i}", topic=item_a.title[:50])
        cluster.add(item_a)
        assigned.add(item_a.id)

        for j, (item_b, kw_b) in enumerate(item_keywords):
            if j <= i or item_b.id in assigned or not kw_b:
                continue
            overlap = len(kw_a & kw_b)
            union = len(kw_a | kw_b)
            if union > 0 and overlap / union >= threshold:
                cluster.add(item_b)
                assigned.add(item_b.id)

        if len(cluster.items) > 1:
            clusters.append(cluster)
            for it in cluster.items:
                it.cluster_id = cluster.cluster_id

    return clusters
