"""Cognitive Keyword Expansion Engine — 认知级关键词推理.

NOT synonym expansion. This is about:
  "If someone likes X, what would they ALSO find fascinating, even if they
   don't know it yet?"

Three expansion strategies:
  1. Cognitive Transfer  — 心理迁移 (风景→河边吹风, AI→科幻电影)
  2. Scenario Expansion  — 场景联想 (合肥→周末去哪, 研究生→深夜实验室)
  3. Collaborative Profile — 画像协同 (像你这样的人还喜欢什么)

Each seed interest spawns:
  - 2-3 precise expansions (same domain, finer granularity)
  - 2-3 lateral expansions (adjacent domain, cognitive leap)
  - 1-2 serendipity shots (surprise, anti-bubble)
"""

from __future__ import annotations
import random

# ── Cognitive Transfer Map ──
# Key: seed interest pattern
# Value: list of (expansion_keyword, type) where type is:
#   P = precise (same domain), L = lateral (adjacent), S = serendipity
COGNITIVE_MAP: dict[str, list[tuple[str, str]]] = {
    # ── AI / ML Research ──
    "llm": [
        # Precise
        ("大模型架构设计", "P"), ("LLM benchmark 排行", "P"), ("大模型推理加速", "P"),
        # Lateral
        ("语言学与AI", "L"), ("认知科学 语言理解", "L"), ("AI产品设计", "L"),
        # Serendipity
        ("科幻小说 人工智能", "S"), ("图灵测试 哲学", "S"),
    ],
    "agent": [
        ("AI agent 开发框架", "P"), ("multi-agent 协作", "P"), ("agent benchmark", "P"),
        ("自动化工作流", "L"), ("RPA 机器人流程自动化", "L"), ("游戏AI NPC", "L"),
        ("科幻 人工智能助手", "S"), ("管家 效率工具", "S"),
    ],
    "reasoning": [
        ("数学推理 LLM", "P"), ("代码推理", "P"), ("思维链 prompt", "P"),
        ("逻辑谜题", "L"), ("批判性思维", "L"), ("认知偏差", "L"),
        ("侦探推理 小说", "S"), ("数学之美", "S"),
    ],
    "rag": [
        ("RAG 优化技巧", "P"), ("向量检索", "P"), ("知识库搭建", "P"),
        ("搜索引擎原理", "L"), ("图书馆学 信息组织", "L"), ("知识管理 PKM", "L"),
        ("第二大脑", "S"), ("记忆宫殿", "S"),
    ],
    "recommendation": [
        ("推荐算法 最新论文", "P"), ("冷启动 推荐", "P"), ("多目标推荐", "P"),
        ("信息茧房 研究", "L"), ("注意力经济", "L"), ("用户行为分析", "L"),
        ("Netflix 推荐故事", "S"), ("算法伦理", "S"),
    ],
    "safety": [
        ("AI alignment 最新", "P"), ("red teaming 技术", "P"), ("大模型安全评测", "P"),
        ("AI 伦理法规", "L"), ("隐私计算", "L"), ("可解释AI", "L"),
        ("三体 黑暗森林", "S"), ("技术失控 电影", "S"),
    ],
    "rlvr": [
        ("RLHF 实战", "P"), ("reward model 训练", "P"), ("PPO vs DPO", "P"),
        ("博弈论 AI", "L"), ("行为经济学", "L"), ("激励机制设计", "L"),
        ("游戏理论", "S"),
    ],
    "diffusion": [
        ("Stable Diffusion 最新", "P"), ("ComfyUI 工作流", "P"), ("AI视频生成", "P"),
        ("数字艺术 创作", "L"), ("摄影构图", "L"), ("电影视觉特效", "L"),
        ("赛博朋克 美学", "S"), ("梵高 星空", "S"),
    ],
    "transformer": [
        ("attention 优化", "P"), ("flash attention", "P"), ("位置编码 进展", "P"),
        ("信号处理", "L"), ("脑科学 注意力", "L"), ("信息论", "L"),
        ("混沌理论", "S"),
    ],
    "quantization": [
        ("模型量化 最新", "P"), ("4bit 推理", "P"), ("本地部署 大模型", "P"),
        ("边缘计算", "L"), ("树莓派 AI", "L"), ("嵌入式 机器学习", "L"),
        ("极简主义 less is more", "S"),
    ],

    # ── Programming / Tools ──
    "python": [
        ("Python 高级技巧", "P"), ("asyncio 实战", "P"), ("Python 性能优化", "P"),
        ("Rust 入门", "L"), ("命令行工具 开发", "L"), ("开发者效率", "L"),
        ("编程之美", "S"), ("黑客与画家", "S"),
    ],
    "开源": [
        ("GitHub 热门项目", "P"), ("开源社区 贡献", "P"), ("独立开发者", "P"),
        ("创业 技术选型", "L"), ("远程工作", "L"), ("side project", "L"),
        ("车库创业 故事", "S"),
    ],
    "mcp": [
        ("MCP protocol 教程", "P"), ("MCP server 开发", "P"), ("tool use 最新", "P"),
        ("API 设计", "L"), ("微服务架构", "L"), ("开发者工具链", "L"),
        ("瑞士军刀 工具", "S"),
    ],

    # ── Campus Life ──
    "合肥": [
        ("合肥 隐藏美食", "P"), ("合肥 周末好去处", "P"), ("科大 周边探店", "P"),
        ("安徽 自驾游", "L"), ("南京 杭州 周末", "L"), ("黄山 旅行攻略", "L"),
        ("城市漫步 citywalk", "S"), ("深夜食堂", "S"),
    ],
    "研究生": [
        ("研究生 时间管理", "P"), ("科研 论文写作", "P"), ("开题报告 模板", "P"),
        ("读博 还是 工作", "L"), ("学术焦虑 应对", "L"), ("科研人 日常", "L"),
        ("费曼学习法", "S"), ("深度工作 专注力", "S"), ("冥想 减压", "S"),
    ],
    "ustc": [
        ("中科大 最新通知", "P"), ("科大 课程推荐", "P"), ("合肥高新区", "P"),
        ("C9 高校 动态", "L"), ("中科院 科研", "L"),
        ("少年班 传奇", "S"),
    ],

    # ── Life / Aesthetics / Serendipity ──
    "美食": [
        ("家常菜 教程", "P"), ("一人食 简单做法", "P"),
        ("咖啡 手冲入门", "L"), ("烘焙 甜点", "L"), ("调酒 入门", "L"),
        ("纪录片 舌尖上的中国", "S"), ("世界各地 street food", "S"),
    ],
    "效率": [
        ("GTD 时间管理", "P"), ("Notion 模板", "P"),
        ("极简生活", "L"), ("数字花园", "L"), ("冥想 正念", "L"),
        ("原子习惯", "S"), ("心流 体验", "S"),
    ],
    "工具": [
        ("AI工具合集 2026", "P"), ("Mac 效率工具", "P"), ("开发者工具", "P"),
        ("自动化 workflow", "L"), ("Raycast 快捷键", "L"),
        ("瑞士军刀 设计哲学", "S"),
    ],

    # ── From Bilibili favorites deep mining ──
    "电影": [
        ("豆瓣高分电影", "P"), ("文艺片 推荐", "P"), ("作者电影 大师", "P"),
        ("电影摄影 构图", "L"), ("电影配乐 原声", "L"), ("电影哲学", "L"),
        ("王家卫 美学", "S"), ("塔可夫斯基 时间", "S"), ("侯孝贤 长镜头", "S"),
    ],
    "纪录片": [
        ("高分纪录片 2026", "P"), ("人文纪录片", "P"), ("自然纪录片", "P"),
        ("城市漫游 纪实", "L"), ("独立纪录片 导演", "L"), ("摄影 纪实", "L"),
        ("BBC 地球脉动", "S"), ("NHK 纪录片", "S"),
    ],
    "足球": [
        ("英超 集锦", "P"), ("足球 技术分析", "P"),
        ("体育数据分析", "L"), ("运动科学", "L"), ("NBA 篮球", "L"),
        ("足球哲学 全攻全守", "S"), ("马拉多纳 纪录片", "S"),
    ],
    "短片": [
        ("获奖短片", "P"), ("学生短片 作品", "P"),
        ("视频剪辑 技巧", "L"), ("分镜 故事板", "L"), ("影像叙事", "L"),
        ("皮克斯 幕后", "S"), ("一镜到底", "S"),
    ],
    "公开课": [
        ("MIT OCW 推荐", "P"), ("Stanford CS 课程", "P"), ("CMU 公开课", "P"),
        ("Coursera 好课", "L"), ("学术讲座 AI", "L"),
        ("费曼 物理学讲义", "S"), ("3Blue1Brown 数学", "S"),
    ],
    "视频制作": [
        ("PR 剪辑技巧", "P"), ("调色 教程", "P"), ("达芬奇 调色", "P"),
        ("UP主 运营", "L"), ("摄影 入门", "L"), ("灯光 布光", "L"),
        ("电影感 调色", "S"), ("VLOG 设备", "S"),
    ],
    "csapp": [
        ("计算机体系结构", "P"), ("操作系统 理解", "P"),
        ("编译原理", "L"), ("计算机网络", "L"),
        ("The Art of Computer Programming", "S"),
    ],
    "城市": [
        ("citywalk 路线", "P"), ("城市探索", "P"),
        ("建筑 欣赏", "L"), ("城市规划", "L"), ("街头摄影", "L"),
        ("孤独星球", "S"), ("城市天际线", "S"),
    ],
}

# ── Collaborative Profile Templates ──
# "People like you also like..."
COLLABORATIVE_PROFILES: dict[str, list[str]] = {
    "AI研究生": [
        "arxiv daily", "机器之心", "量子位", "新智元",
        "AI 创业公司", "技术博客 推荐",
        "程序员 摸鱼", "科研 meme", "PhD comics",
        "TED 演讲 技术", "播客 AI相关",
    ],
    "USTC学生": [
        "科大瀚海星云", "合肥 生活指南", "考研 经验",
        "实习 内推 AI", "秋招 春招 经验",
        "校园 摄影", "图书馆 自习",
    ],
    "技术宅": [
        "Homelab 折腾", "NAS 搭建", "树莓派 项目",
        "mechanical keyboard", "显示器 推荐",
        "独立游戏", "像素艺术",
    ],
    "内容消费者": [
        "信息素养", "批判性阅读", "媒体素养",
        "长文 深度报道", "非虚构写作",
        "纪录片 推荐", "播客 推荐",
    ],
    "影迷": [
        "文艺片 推荐", "导演 访谈", "电影节 获奖片单",
        "criterion collection", "影史经典", "独立电影 院线",
        "王家卫 配乐", "是枝裕和", "滨口�的介",
        "电影手册 cahiers", "视听语言",
    ],
    "足球迷": [
        "英超 战术分析", "欧冠 集锦", "足球 数据",
        "FIFA 游戏", "FM 足球经理", "球星 故事",
    ],
    "视频创作者": [
        "剪辑 思路", "转场 技巧", "达芬奇 调色教程",
        "拍摄 运镜", "UP主 经验分享", "创意广告",
    ],
    "公开课学习者": [
        "MIT missing semester", "CS自学指南", "TEACH YOURSELF CS",
        "计算机科学 路线图", "名校 公开课推荐",
    ],
}


def expand_keywords(
    seed_interests: list[str],
    identity_tags: list[str] | None = None,
    max_per_seed: int = 6,
    serendipity_ratio: float = 0.2,
) -> dict[str, list[str]]:
    """Generate cognitively-expanded keywords from seed interests.

    Returns:
        {
            "precise": [...],     # Same-domain, finer grain
            "lateral": [...],     # Adjacent domain, cognitive leap
            "serendipity": [...], # Surprise / anti-bubble
            "collaborative": [...], # Profile-based "also likes"
        }
    """
    precise, lateral, serendipity = [], [], []

    for seed in seed_interests:
        seed_lower = seed.lower()
        matched = False

        for pattern, expansions in COGNITIVE_MAP.items():
            if pattern in seed_lower or seed_lower in pattern:
                matched = True
                p = [kw for kw, t in expansions if t == "P"]
                l = [kw for kw, t in expansions if t == "L"]
                s = [kw for kw, t in expansions if t == "S"]

                # Take proportionally
                precise.extend(random.sample(p, min(len(p), 2)))
                lateral.extend(random.sample(l, min(len(l), 2)))
                serendipity.extend(random.sample(s, min(len(s), 1)))

        if not matched:
            # For unmatched seeds, generate scenario-based expansions
            scenario = _scenario_expand(seed)
            if scenario:
                lateral.extend(scenario)

    # Collaborative profile keywords
    collaborative = []
    for tag in (identity_tags or []):
        for profile_key, keywords in COLLABORATIVE_PROFILES.items():
            if any(t in tag for t in profile_key.split()):
                collaborative.extend(random.sample(keywords, min(len(keywords), 3)))

    # Deduplicate each list
    precise = list(dict.fromkeys(precise))
    lateral = list(dict.fromkeys(lateral))
    serendipity = list(dict.fromkeys(serendipity))
    collaborative = list(dict.fromkeys(collaborative))

    return {
        "precise": precise,
        "lateral": lateral,
        "serendipity": serendipity,
        "collaborative": collaborative,
    }


def _scenario_expand(seed: str) -> list[str]:
    """Generate scenario-based expansions for unmatched seeds.
    
    Idea: think about WHEN/WHERE/WHY someone encounters this topic,
    then expand to related scenarios.
    """
    # Common scenario patterns
    if any(kw in seed for kw in ["学习", "教程", "入门"]):
        return [f"{seed} 避坑", f"{seed} 实战项目"]
    if any(kw in seed for kw in ["工具", "软件", "app"]):
        return [f"{seed} 替代品", f"{seed} workflow"]
    if any(kw in seed for kw in ["论文", "paper", "研究"]):
        return [f"{seed} 解读", f"{seed} 代码复现"]
    return []


def get_all_expanded_keywords(profile_data: dict) -> list[str]:
    """Get all expanded keywords for query builder.
    
    Called by query_builder to inject cognitive expansions into searches.
    """
    explicit = list(profile_data.get("explicit_interests", {}).keys())
    behavioral = list(profile_data.get("behavioral_interests", {}).keys())[:10]

    seeds = explicit + behavioral

    # Identity tags from user context (matched via bilibili favorites + user profile)
    identity_tags = ["AI研究生", "USTC学生", "技术宅", "内容消费者",
                     "影迷", "足球迷", "视频创作者", "公开课学习者"]

    expanded = expand_keywords(seeds, identity_tags, max_per_seed=6)

    # Merge all types with shuffle
    all_kw = []
    all_kw.extend(expanded["precise"])
    all_kw.extend(expanded["lateral"])
    all_kw.extend(expanded["serendipity"])
    all_kw.extend(expanded["collaborative"])

    random.shuffle(all_kw)
    return list(dict.fromkeys(all_kw))  # Dedup preserving order
