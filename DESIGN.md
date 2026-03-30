# OmniFeed — 跨平台个性化内容聚合器

> 让 AI Agent 成为你的个人信息策展人。

## 核心理念

每个人每天被淹没在十几个 App 的信息流里。Twitter 上有 AI 前沿、小红书上有本地美食、B站有技术教程、微博有热点、V2EX 有技术讨论、GitHub 有新项目……

OmniFeed 做的事情很简单：**一个 Agent，理解你是谁，去所有平台替你看，把值得看的内容挑出来，放在一个页面上。**

不是简单的 RSS 聚合。是基于你的身份、记忆、兴趣、当前状态的**主动信息策展**。

## 技术架构

```
                    ┌─────────────────┐
                    │   User Profile  │
                    │  Memory / Chat  │
                    │   Interests     │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Intent Engine  │  ← 理解用户需要什么
                    │  (LLM-powered)  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐
        │  Channel   │ │  Channel   │ │  Channel   │  ← 平台适配器
        │  Twitter   │ │    XHS     │ │  Bilibili  │  ...
        └─────┬─────┘ └─────┬─────┘ └─────┬─────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼────────┐
                    │    Processor    │  ← 去重 / 摘要 / 分类 / 聚合
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │     Ranker      │  ← 个性化排序 + 多样化混排
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │    Renderer     │  ← HTML / JSON / 晨报
                    └─────────────────┘
```

## 核心模块详解

### 1. Intent Engine（意图引擎）

这是 OmniFeed 区别于普通 RSS 聚合器的核心。

**输入**：
- `profile.yaml` — 用户显式定义的身份、兴趣
- Agent 记忆文件 — MEMORY.md、daily notes
- 聊天历史（如果 Agent 集成）
- 当前时间/地点/上下文

**输出**：每个 channel 的**检索计划**（query plan）

```yaml
# Intent Engine 生成的检索计划示例
queries:
  - channel: twitter
    keywords: ["RLVR", "inference scaling", "LLM safety"]
    accounts: ["@kaboroevsky", "@AndrewYNg"]  # 关注的人
    reason: "用户研究方向是 AI，最近在看 RLVR 相关论文"
    
  - channel: xhs
    keywords: ["合肥高新区 美食", "中科大 日常"]
    reason: "用户在 USTC 高新校区，关注本地生活"
    
  - channel: github
    keywords: ["LLM agent", "reasoning"]
    reason: "用户是 AI 方向研究生，关注开源项目"
    
  - channel: bilibili
    keywords: ["大模型 教程", "论文精读"]
    reason: "研究生阶段，需要学习资料"
```

**两种运行模式**：
- **LLM 模式**（Agent 集成）：用 LLM 从记忆/历史推理出检索意图
- **规则模式**（Standalone）：纯配置文件驱动，`profile.yaml` 里写关键词

### 2. Channel Adapters（平台适配器）

统一接口，每个平台一个 adapter：

```python
class BaseChannel:
    """所有平台适配器的基类"""
    
    name: str               # "twitter", "xhs", "bilibili"...
    requires_auth: bool     # 是否需要认证
    rate_limit: float       # 请求间隔（秒）
    
    async def search(self, query: str, limit: int = 20) -> list[FeedItem]:
        """搜索内容"""
        
    async def trending(self, limit: int = 20) -> list[FeedItem]:
        """热门/趋势"""
        
    async def user_feed(self, user_id: str, limit: int = 20) -> list[FeedItem]:
        """指定用户的动态"""
        
    async def health_check(self) -> ChannelStatus:
        """检查通道是否可用"""
```

**统一输出格式**：

```python
@dataclass
class FeedItem:
    id: str                    # 全局唯一: "{platform}:{native_id}"
    platform: str              # "twitter" | "xhs" | "bilibili" | ...
    title: str
    content: str               # 正文摘要（截断到 500 字）
    author: str
    author_url: str
    cover: str                 # 封面图 URL
    url: str                   # 原文链接
    timestamp: int             # Unix ms
    engagement: Engagement     # likes, comments, shares, views
    media_type: str            # "text" | "image" | "video"
    tags: list[str]            # 原始标签/话题
    language: str              # "zh" | "en"
    raw: dict                  # 原始数据（debug 用）
    
    # 后处理填充
    category: str = ""         # 🔬科研 | 🍜美食 | 📢资讯 | ...
    summary: str = ""          # AI 生成的一句话摘要
    relevance: float = 0.0     # 与用户兴趣的相关度 0-1
    cluster_id: str = ""       # 话题聚合 ID
    recommend_reason: str = "" # "因为你关注 AI Safety"
```

**平台支持矩阵**：

| 平台 | 认证 | 搜索 | 热门 | 用户动态 | 优先级 |
|------|------|------|------|----------|--------|
| 微博 | 无需 | ✅ | ✅ | ✅ | P0 |
| V2EX | 无需 | ❌ | ✅ | ❌ | P0 |
| GitHub | gh CLI | ✅ | ✅ | ❌ | P0 |
| Reddit | 无需 | ✅ | ✅ | ❌ | P0 |
| RSS | 无需 | N/A | N/A | ✅ | P0 |
| 小红书 | Cookie | ✅ | ❌ | ✅ | P1 |
| Twitter | bird/Cookie | ✅ | ✅ | ✅ | P1 |
| Bilibili | 可选 | ✅ | ✅ | ❌ | P1 |
| 微信公众号 | Camoufox | ✅ | ❌ | ❌ | P2 |
| 雪球 | 无需 | ✅ | ✅ | ❌ | P2 |
| 抖音 | 无需 | ❌ | ❌ | link解析 | P2 |
| 小宇宙 | Groq | ❌ | ❌ | link转录 | P2 |

### 3. Processor（内容处理器）

抓取完成后的处理 pipeline：

#### 3a. 去重引擎
- **URL 去重**：同一链接在多平台被分享
- **内容去重**：标题/正文相似度 > 阈值（简单用 Jaccard + 关键词重叠，不依赖 embedding）
- **话题聚合**：把讨论同一事件的内容归为一组

```python
# 话题聚合示例输出
clusters = {
    "cluster_iclr2026": {
        "topic": "ICLR 2026 OpenReview 事件",
        "items": [
            FeedItem(platform="twitter", title="..."),
            FeedItem(platform="xhs", title="ICLR 2026 事件的一些感慨"),
            FeedItem(platform="v2ex", title="..."),
        ],
        "platforms": ["twitter", "xhs", "v2ex"],
        "total_engagement": 12345,
    }
}
```

#### 3b. 智能分类
- **规则层**（快速，无需 LLM）：关键词匹配分类
  ```python
  CATEGORY_RULES = {
      "🔬 科研": ["论文", "paper", "NeurIPS", "ICLR", "arxiv", "模型", "训练"],
      "🍜 美食": ["美食", "探店", "奶茶", "火锅", "餐厅"],
      "📢 资讯": ["通知", "公告", "招聘", "讲座"],
      "💻 技术": ["GitHub", "开源", "教程", "代码"],
      "🎮 趣味": ["哈哈", "搞笑", "太离谱"],
  }
  ```
- **LLM 层**（可选，更准确）：batch 分类 + 一句话摘要

#### 3c. AI 摘要
- 对较长内容（> 200 字）生成一句话摘要
- Batch 处理：一次 LLM 调用处理 10-20 条
- 标注推荐理由：`"因为你关注 LLM Reasoning"`

### 4. Ranker（排序引擎）

多信号融合的个性化排序：

```python
def score(item: FeedItem, profile: UserProfile) -> float:
    """计算内容与用户的匹配分数"""
    
    # 1. 兴趣相关度 (0-1)
    relevance = keyword_overlap(item.tags + item.title_tokens, profile.interests)
    
    # 2. 新鲜度 (0-1)，指数衰减
    freshness = exp(-age_hours / 48)
    
    # 3. 参与度信号 (0-1)，对数归一化
    engagement = log1p(item.likes + item.comments * 3) / max_engagement
    
    # 4. 平台多样性惩罚（同平台连续出现扣分）
    diversity_penalty = ...
    
    # 5. 已读/不感兴趣惩罚
    seen_penalty = ...
    
    return (
        0.35 * relevance +
        0.25 * freshness +
        0.20 * engagement +
        0.10 * diversity_penalty +
        0.10 * category_diversity
    )
```

**混排策略**（保证多样性）：
- 不能连续 3 条来自同一平台
- 不能连续 3 条属于同一分类
- 话题聚合的多条内容折叠为一组，展开时按平台排
- Top 3 位置保证来自 3 个不同平台

### 5. Renderer（渲染器）

三种输出模式：

#### 5a. HTML 发现页
- 瀑布流卡片布局
- 平台 icon + 颜色标识
- 封面图 lazy load
- 分类/平台筛选器
- "不感兴趣" 按钮 → localStorage
- 话题聚合折叠展开
- PWA manifest（可加到手机桌面）
- 暗色/亮色主题

#### 5b. 晨报（Daily Digest）
```markdown
☀️ OmniFeed 日报 — 2026/03/28 (周六)

## 🔬 科研动态
1. **[Twitter] @karpathy: 新的 reasoning scaling 实验结果** (2.3k ❤️)
   > 在 GSM8K 上用 RL 训练 7B 模型超过了 70B 的 SFT baseline
   📎 https://twitter.com/...

2. **[话题聚合] ICLR 2026 事件后续** (跨 3 个平台, 共 15k 互动)
   > 官方确认回退到 rebuttal 前，社区讨论持续
   📕 小红书 · 🐦 Twitter · 💬 V2EX

## 🏫 校园
3. **[小红书] 腾讯 AI 百校行今天下午 C101** (12 ❤️)
   > 下午 2-5 点，手把手教部署 AI 小龙虾，带电脑
   📍 高新校区图书教育中心

## 🍜 发现
4. **[小红书] 合肥高新天街新开的烤肉店** (989 ❤️)
   > 离科大骑车 10 分钟，人均 80
...

---
📊 今日检索: 7 个平台 · 234 条原始内容 · 精选 15 条
```

#### 5c. JSON API
```json
{
  "generated_at": "2026-03-28T08:00:00+08:00",
  "profile": "...",
  "stats": { "platforms": 7, "raw_items": 234, "final_items": 15 },
  "items": [ ... ],
  "clusters": [ ... ]
}
```

## 配置文件

```yaml
# ~/.omnifeed/config.yaml

# 用户画像
profile:
  name: "Your Name"
  location: "Your City"
  identity: "AI researcher / student / developer"
  
  # 兴趣标签（权重 1-5）
  interests:
    - topic: "LLM Reasoning"
      weight: 5
    - topic: "AI Safety"
      weight: 4
    - topic: "推荐系统"
      weight: 3
    - topic: "合肥美食"
      weight: 3
    - topic: "开源项目"
      weight: 2
      
  # 关注的人/账号
  follows:
    - platform: xhs
      user_id: "5905662a50c4b44cd4968643"
      name: "科大小青椒"
    - platform: twitter
      username: "karpathy"
    - platform: github
      username: "openai"
      
  # RSS 订阅
  feeds:
    - url: "https://arxiv.org/rss/cs.AI"
      name: "arXiv CS.AI"
    - url: "https://sspai.com/feed"
      name: "少数派"

# 平台配置
channels:
  weibo:
    enabled: true
    # 零配置
  v2ex:
    enabled: true
    nodes: ["python", "ai", "jobs"]
  github:
    enabled: true
    # 使用 gh CLI 认证
  reddit:
    enabled: true
    subreddits: ["MachineLearning", "LocalLLaMA"]
  xhs:
    enabled: true
    # Cookie 在 secrets/ 目录
  twitter:
    enabled: false  # 需要 bird 工具
  bilibili:
    enabled: false  # 需要 yt-dlp

# 输出配置
output:
  html: true
  daily_digest: true
  json: true
  deploy:
    github_pages:
      repo: "username/omnifeed"
      branch: "gh-pages"

# AI 增强（可选）
ai:
  enabled: true
  model: "anthropic/claude-sonnet-4-20250514"  # 或任何 LLM
  features:
    - summarize      # 一句话摘要
    - categorize     # 智能分类
    - recommend_reason  # 推荐理由
  batch_size: 20    # 一次处理条数
  
# 调度
schedule:
  fetch_interval: "4h"     # 每 4 小时抓取
  digest_time: "08:00"     # 晨报时间
  timezone: "Asia/Shanghai"
```

## CLI 设计

```bash
# 安装
pip install omnifeed

# 初始化配置
omnifeed init                    # 交互式创建 config.yaml

# 健康检查
omnifeed doctor                  # 检查各平台可用性

# 抓取
omnifeed fetch                   # 全平台抓取
omnifeed fetch --channel xhs     # 只抓小红书
omnifeed fetch --dry-run         # 只看检索计划

# 构建输出
omnifeed build                   # 生成 HTML + JSON
omnifeed build --digest          # 生成晨报

# 本地预览
omnifeed serve                   # localhost:8080 预览

# 部署
omnifeed deploy                  # 推 GitHub Pages

# 一键全流程
omnifeed run                     # fetch + build + deploy
```

## OpenClaw Skill 集成

作为 OpenClaw skill 使用时，Agent 可以：
1. 从 `USER.md` / `MEMORY.md` 自动生成检索意图
2. 用 LLM 做内容摘要和分类
3. 定时推送晨报到聊天
4. 用户说"帮我看看今天有什么新鲜事"触发即时抓取

## 开发计划

### Phase 1: 核心框架 + P0 平台（今天）
- [ ] 项目骨架：pyproject.toml, CLI, config
- [ ] FeedItem 数据模型
- [ ] BaseChannel + 5 个零配置 channel（微博、V2EX、GitHub、Reddit、RSS）
- [ ] 基础 Ranker（keyword 匹配 + 新鲜度 + 多样性）
- [ ] HTML 渲染器（卡片布局模板）
- [ ] `omnifeed fetch` + `omnifeed build` 可用

### Phase 2: 个性化 + P1 平台
- [ ] 小红书 channel（复用 mcporter）
- [ ] Twitter channel（复用 bird）
- [ ] Bilibili channel（复用 yt-dlp）
- [ ] Intent Engine 规则模式
- [ ] 去重引擎
- [ ] 智能分类（规则层）

### Phase 3: AI 增强
- [ ] LLM 摘要 + 分类
- [ ] 推荐理由生成
- [ ] 话题聚合
- [ ] 晨报生成
- [ ] OpenClaw skill 集成

### Phase 4: 体验打磨
- [ ] PWA 支持
- [ ] 亮/暗色主题
- [ ] "不感兴趣" 反馈
- [ ] 浏览历史追踪
- [ ] 部署自动化

## 命名

**OmniFeed** — Omni（全渠道）+ Feed（信息流）

替代候选：CrossFeed, FeedPulse, InfoBrew, CurateAI
